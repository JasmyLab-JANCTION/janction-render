/*
 * janction-render (npm): terminal subcommands. Render with only Node (>= 18) and npx, no Python or uv.
 *
 *   npx -y janction-render key                       create a free key and save it (prints only the prefix)
 *   npx -y janction-render try                       render the sample scene and print the image link
 *   npx -y janction-render preview <scene>           a fast preview of a .blend, a bpy script or a 3D file (path or https link)
 *   npx -y janction-render final <scene> --frames 1-24 [--preset product|turntable|animation] [--max-yen N]
 *   npx -y janction-render status <job_id>
 *   npx -y janction-render download <job_id> [--out dir]
 *
 * The HTTP flow is the one of the Python client (janction_render/client.py and cli.py): the same endpoints, the X-API-Key
 * header, the same key file (~/.janction-render.json, a JSON object keyed by server URL) so the Python CLI and this one share
 * one key. This file never replaces or removes an entry of that file; it only adds one when the server has none.
 * No runtime dependencies: global fetch, FormData and Blob.
 */
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const PKG = require("../package.json");

const DEFAULT_SERVER = "https://render.janction.jp";
const LOCAL_SERVER = "http://127.0.0.1:8340";
const SAMPLE_SCENE = `${DEFAULT_SERVER}/samples/cube_scene.py`;
const SCENE_SUFFIXES = [".blend", ".py", ".fbx", ".glb", ".gltf", ".obj", ".stl", ".ply", ".usd", ".usda", ".usdc", ".usdz", ".abc"];
const PRESETS = ["product", "turntable", "animation"];
const ONLY_CHOICES = ["all", "mp4", "frames", "sheet", "output", "video", "blend"];
const FINAL_TOOL_DEFAULTS = { width: 1920, height: 1080, samples: 128, output: "auto" };
const EDGE_UPLOAD_MB = 100;                  // Cloudflare in front of render.janction.jp passes 100 MB per request
const RESUMABLE_ABOVE = 64 * 1024 * 1024;    // larger scenes go in parts (POST /v1/uploads, tus 1.0)
const ASSET_LINK_MAX_BYTES = 128 * 1024 * 1024;
const PART_SECONDS = 60;
const PART_MIN = 1024 * 1024;
const DOWNLOAD_TRIES = 3;
const FRAME_NAME_RE = /^(part-\d+_)?frame_/;
const KEY_FILE_LABEL = "~/.janction-render.json";
const CMD = "npx -y janction-render";

const SUBCOMMANDS = ["key", "try", "preview", "final", "status", "download"];
const GLOBAL_OPTS = { server: "string", key: "string", json: "bool", help: "bool" };

// ---------------------------------------------------------------------------------------------------- errors

class ClientError extends Error {
  constructor(status, error, detail, extra) {
    super(detail ? `${error}: ${detail}` : error);
    this.status = status;
    this.error = error;
    this.detail = detail || "";
    this.extra = extra || {};
  }

  /** The same fields as ClientError.payment() of the Python client (402: checkout link and amounts). */
  payment() {
    if (this.status !== 402) return null;
    const x = this.extra;
    const out = { payment_required: true, detail: this.detail, code: "INSUFFICIENT_CREDIT", retryable: false,
      recommended_action: "TOP_UP" };
    for (const k of ["needed_yen", "balance_yen", "topup_yen", "checkout_url", "session_id", "yen_per_gpu_second", "how"]) {
      out[k] = x[k] === undefined ? null : x[k];
    }
    for (const k of ["tell_user", "this_job_yen", "renders_per_topup"]) if (x[k] != null) out[k] = x[k];
    for (const k of ["welcome", "first_topup_bonus", "card_offer", "topup_options", "topup_credit_yen", "resume"]) if (x[k]) out[k] = x[k];
    if (x.accepts) out.x402 = { x402Version: x.x402Version, accepts: x.accepts, how: x.how_x402 };
    return out;
  }

  /** code / retryable / recommended_action like ClientError.agent_fields() of the Python client. */
  agentFields() {
    const x = this.extra;
    const out = {};
    for (const k of ["code", "retryable", "recommended_action", "possible_fix", "retry_after_s", "resets_at_iso"]) {
      if (x[k] != null) out[k] = x[k];
    }
    if (!("code" in out)) {
      if (this.error === "network_blocked") {
        Object.assign(out, { code: "NETWORK_BLOCKED", retryable: false, recommended_action: "SWITCH_ROUTE", possible_fix: x.hint });
      } else if (this.error === "server_unreachable" || this.status >= 500) {
        Object.assign(out, { code: this.error === "server_unreachable" ? "WORKERS_UNAVAILABLE" : "INTERNAL_ERROR",
          retryable: true, recommended_action: "WAIT_AND_RETRY" });
      } else {
        Object.assign(out, { code: String(this.error || "error").toUpperCase().replace(/[^A-Z0-9_]/g, "_").slice(0, 40),
          retryable: this.status === 429, recommended_action: "READ_DETAIL" });
      }
    }
    return out;
  }
}

class UsageError extends Error {}

function unreachable(server, url, err) {
  let target = server;
  try { const u = new URL(url); target = `${u.protocol}//${u.host}`; } catch (e) { /* keep server */ }
  const why = (err && err.cause && (err.cause.code || err.cause.message)) || (err && (err.name || err.message)) || "error";
  let hint;
  if (server === LOCAL_SERVER) {
    hint = "JANCTION_RENDER_SERVER points at a local dev server that is not running. Unset it (or set "
      + "JANCTION_RENDER_SERVER=https://render.janction.jp) to use the public service";
  } else if (server === DEFAULT_SERVER) {
    hint = "could not reach the public service; check your network and the status page https://render.janction.jp/status. "
      + "Node's fetch does not use HTTPS_PROXY by itself; behind a proxy, set NODE_USE_ENV_PROXY=1 (Node 24+)";
  } else {
    hint = "check the URL and your network; the service status is at https://render.janction.jp/status";
  }
  return new ClientError(0, "server_unreachable", `could not reach ${target} (${why}). ${hint}`,
    { server, url, retryable: true, hint });
}

function networkBlocked(url) {
  let host = "render.janction.jp";
  try { host = new URL(url).hostname; } catch (e) { /* keep */ }
  const hint = `The request did not leave this environment: its network proxy refused ${host} (a sandbox allowlist, not an `
    + "outage of the render service), so retrying will not help. Allow the host in the environment's network settings, or use "
    + `the remote MCP server ${DEFAULT_SERVER}/mcp from the AI app instead. Steps: ${DEFAULT_SERVER}/claude-code-blender#cloud-sessions`;
  return new ClientError(0, "network_blocked", `could not reach ${host}: ${hint}`, { url, retryable: false, hint });
}

// ---------------------------------------------------------------------------------------------------- helpers

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const say = (msg) => process.stderr.write(`${msg}\n`);
const j = (obj) => JSON.stringify(obj, null, 2);
const prefixOf = (key) => String(key || "").slice(0, 10);   // the server's prefix: jr_ and 7 characters
const mib = (n) => (n / 1048576).toFixed(1);

function keyFile() {
  return path.join(os.homedir(), ".janction-render.json");
}

function resumeFile() {
  return path.join(os.homedir(), ".janction-render-uploads.json");
}

/** The key file as an object. {ok:false} when it exists but is not a JSON object: then nothing is ever written to it. */
function readKeyFile() {
  let text;
  try {
    text = fs.readFileSync(keyFile(), "utf8");
  } catch (e) {
    if (e.code === "ENOENT") return { ok: true, data: {}, exists: false };
    return { ok: false, why: e.message };
  }
  try {
    const data = JSON.parse(text);
    if (data && typeof data === "object" && !Array.isArray(data)) return { ok: true, data, exists: true };
  } catch (e) { /* fall through */ }
  return { ok: false, why: "it is not a JSON object" };
}

function writeKeyFile(data) {
  // write next to it and rename, so a crash never leaves half a file (the file may hold other keys)
  const file = keyFile();
  const tmp = `${file}.${process.pid}.${crypto.randomBytes(4).toString("hex")}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 1), { encoding: "utf8", mode: 0o600 });
  try {
    fs.renameSync(tmp, file);
  } catch (e) {
    try { fs.rmSync(tmp, { force: true }); } catch (e2) { /* ignore */ }
    throw e;
  }
  try { fs.chmodSync(file, 0o600); } catch (e) { /* not on every file system */ }
}

function readResume() {
  try {
    const d = JSON.parse(fs.readFileSync(resumeFile(), "utf8"));
    return d && typeof d === "object" && !Array.isArray(d) ? d : {};
  } catch (e) {
    return {};
  }
}

function setResume(ident, url) {
  const d = readResume();
  if (url) d[ident] = url; else delete d[ident];
  try { fs.writeFileSync(resumeFile(), JSON.stringify(d), "utf8"); } catch (e) { /* only a convenience */ }
}

function sha256File(p) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash("sha256");
    fs.createReadStream(p).on("data", (d) => h.update(d)).on("end", () => resolve(h.digest("hex"))).on("error", reject);
  });
}

function isLink(s) {
  return /^https?:\/\//i.test(String(s || "").trim());
}

/** GitHub / Hugging Face file pages to the raw file; null unless https, short and a scene extension (links.scene_link). */
function sceneLink(url) {
  let u = String(url || "").trim();
  let m = u.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/(?:blob|raw)\/(.+)$/);
  if (m) u = `https://raw.githubusercontent.com/${m[1]}/${m[2]}/${m[3]}`;
  m = u.match(/^https:\/\/huggingface\.co\/(.+?)\/blob\/(.+)$/);
  if (m) u = `https://huggingface.co/${m[1]}/resolve/${m[2]}`;
  if (!u.toLowerCase().startsWith("https://") || u.length > 1000 || /[\r\n\t <>"'`]/.test(u)) return null;
  let p;
  try { p = new URL(u).pathname.toLowerCase(); } catch (e) { return null; }
  return SCENE_SUFFIXES.some((ext) => p.endsWith(ext)) ? u : null;
}

/** '1,8,16,24' as is, '1-24' four evenly spaced frames, '12' one frame, '' the default (client.parse_frames). */
function parseFrames(spec, dflt = 1, count = 4) {
  const s = String(spec || "").trim();
  let vals;
  if (!s) return [Number(dflt)];
  if (s.includes(",")) {
    vals = s.split(",").filter((x) => x.trim()).map((x) => toInt(x, "--frames"));
  } else if (s.includes("-")) {
    const [a, b] = s.split("-", 2).map((x) => toInt(x, "--frames"));
    if (b < a) throw new UsageError("frames: end must be >= start");
    const n = Math.min(count, b - a + 1);
    vals = n > 1 ? Array.from({ length: n }, (_, i) => a + Math.round((i * (b - a)) / (n - 1))) : [a];
  } else {
    vals = [toInt(s, "--frames")];
  }
  const out = [];
  for (const v of vals) {
    if (v < 0) throw new UsageError("frames must be >= 0");
    if (!out.includes(v)) out.push(v);
  }
  return out;
}

function frameRange(spec) {
  const s = String(spec || "").trim();
  const m = s.match(/^(\d+)(?:-(\d+))?$/);
  if (!m) throw new UsageError("--frames must look like 1-240 or 12");
  const a = Number(m[1]);
  const b = m[2] === undefined ? a : Number(m[2]);
  if (b < a) throw new UsageError("--frames: end must be >= start");
  return [a, b];
}

function toInt(v, name) {
  const s = String(v).trim();
  if (!/^-?\d+$/.test(s)) throw new UsageError(`${name} must be a whole number, got ${JSON.stringify(v)}`);
  return Number(s);
}

function size(v) {
  const m = String(v || "").toLowerCase().match(/^(\d+)x(\d+)$/);
  if (!m) throw new UsageError("--size must look like 1920x1080");
  return [Number(m[1]), Number(m[2])];
}

function selectArtifacts(artifacts, only) {
  const o = String(only || "all").trim().toLowerCase();
  if (o === "" || o === "all") return artifacts.slice();
  if (o === "mp4" || o === "video") {
    const videos = artifacts.filter((a) => /\.(mp4|webm|mov)$/.test(a.name));
    const whole = videos.filter((a) => ["output.mp4", "output.webm", "output.mov"].includes(a.name));
    return whole.length ? whole : videos;
  }
  if (o === "frames") return artifacts.filter((a) => FRAME_NAME_RE.test(a.name));
  if (o === "sheet") return artifacts.filter((a) => a.name === "sheet.png");
  if (o === "blend") return artifacts.filter((a) => a.name === "scene.blend");
  if (o === "output") {
    const picked = artifacts.filter((a) => ["output.mp4", "output.webm", "output.mov", "sheet.png", "scene.blend"].includes(a.name));
    return picked.length ? picked : artifacts.filter((a) => FRAME_NAME_RE.test(a.name)).slice(0, 1);
  }
  throw new UsageError(`--only must be one of: ${ONLY_CHOICES.join(", ")}`);
}

/** An artifact name as a file name in the output folder; refuses anything that would leave it. */
function safeName(name) {
  const n = String(name || "");
  if (!n || n.includes("/") || n.includes("\\") || n === "." || n === ".." || n.includes("\0") || /^[A-Za-z]:/.test(n)) {
    throw new ClientError(0, "bad_artifact_name", `the server sent an artifact name that is not a plain file name: ${JSON.stringify(n)}`);
  }
  return n;
}

// ---- external files next to a glTF / OBJ (client.companion_refs) -------------------------------------------------

function refProblem(ref) {
  let s = String(ref || "").trim();
  if (!s || s.slice(0, 5).toLowerCase() === "data:") return null;
  for (let i = 0; i < 4; i += 1) {
    let d;
    try { d = decodeURIComponent(s); } catch (e) { d = s; }
    if (d === s) break;
    s = d;
  }
  if (/[\x00-\x1f\x7f]/.test(s)) return "control characters in a file path";
  s = s.replace(/\\/g, "/");
  if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(s)) return "URLs and drive letters are not accepted; refer to files by a relative name";
  if (s.startsWith("/")) return "absolute paths are not accepted; refer to files by a relative name";
  if (s.split("/").includes("..")) return "paths may not go above the scene's folder (..)";
  return null;
}

function companionKind(name) {
  return { ".gltf": "gltf", ".obj": "obj", ".mtl": "mtl", ".usda": "usda" }[path.extname(name).toLowerCase()] || "";
}

function rawRefs(kind, text) {
  const out = [];
  if (kind === "gltf") {
    let doc;
    try { doc = JSON.parse(text); } catch (e) { return out; }
    const walk = (o) => {
      if (Array.isArray(o)) o.forEach(walk);
      else if (o && typeof o === "object") {
        for (const [k, v] of Object.entries(o)) {
          if (k === "uri" && typeof v === "string") out.push(v); else walk(v);
        }
      }
    };
    walk(doc);
  } else if (kind === "obj") {
    for (const line of text.split(/\r?\n/)) {
      const parts = line.trim().split(/\s+/);
      if (parts.length >= 2 && parts[0].toLowerCase() === "mtllib") out.push(...parts.slice(1));
    }
  } else if (kind === "mtl") {
    const maps = ["map_kd", "map_ks", "map_ka", "map_ns", "map_d", "map_bump", "bump", "disp", "decal", "norm", "map_ke", "refl"];
    for (const line of text.split(/\r?\n/)) {
      const parts = line.trim().split(/\s+/);
      if (parts.length >= 2 && maps.includes(parts[0].toLowerCase())) out.push(parts[parts.length - 1]);
    }
  }
  return out;
}

function companionRefs(kind, text) {
  const out = [];
  if (!["gltf", "obj", "mtl"].includes(kind)) return out;
  for (let ref of rawRefs(kind, text)) {
    ref = String(ref || "").trim().replace(/\\/g, "/");
    if (!ref || ref.slice(0, 5).toLowerCase() === "data:" || refProblem(ref)) continue;
    if (!out.includes(ref)) out.push(ref);
  }
  return out;
}

function fitPart(part, moved, seconds, cut = false) {
  if (moved <= 0 || !(cut || seconds > 90)) return part;
  const step = 256 * 1024;
  const fit = Math.floor((moved / Math.max(seconds, 0.001)) * PART_SECONDS / step) * step;
  return Math.max(PART_MIN, Math.min(part, fit));
}

// ---------------------------------------------------------------------------------------------------- client

class Client {
  constructor({ server, key } = {}) {
    this.server = String(server || process.env.JANCTION_RENDER_SERVER || DEFAULT_SERVER).trim().replace(/\/+$/, "");
    const envKey = String(process.env.JANCTION_RENDER_API_KEY || "").trim();
    this._key = String(key || "").trim() || envKey || null;
    this.keySource = key ? "--key" : (envKey ? "JANCTION_RENDER_API_KEY" : null);
    const name = String(process.env.JANCTION_RENDER_CLIENT || "").trim() || "cli/npm";
    this.clientHeader = `${name} ${PKG.version}`;
    this.pollMs = Math.max(10, Number(process.env.JANCTION_RENDER_POLL_MS) || 2000);
    try {
      const u = new URL(this.server);
      if (u.protocol !== "https:" && u.protocol !== "http:") throw new Error("scheme");
    } catch (e) {
      throw new UsageError(`the server must be an http(s) URL, got ${JSON.stringify(this.server)}`);
    }
  }

  // ---- HTTP -------------------------------------------------------------

  async fetch(method, url, { headers = {}, body, timeoutMs = 30000, idle = false } = {}) {
    const ctl = new AbortController();
    let timer = setTimeout(() => ctl.abort(), timeoutMs);
    const res = await fetch(url, { method, body, signal: ctl.signal, redirect: "follow",
      headers: { "X-Client": this.clientHeader, ...headers } })
      .catch((err) => { clearTimeout(timer); throw unreachable(this.server, url, err); });
    if (idle) {
      // a download keeps going as long as bytes arrive: the timer restarts on each chunk (resetIdle)
      res.resetIdle = () => { clearTimeout(timer); timer = setTimeout(() => ctl.abort(), timeoutMs); };
      res.done = () => clearTimeout(timer);
    } else {
      clearTimeout(timer);
    }
    return res;
  }

  static async raise(res) {
    if (res.status < 400) return;
    if (res.status === 403 && res.headers.get("x-deny-reason") === "host_not_allowed") throw networkBlocked(res.url);
    const text = await res.text().catch(() => "");
    let body;
    try { body = JSON.parse(text); } catch (e) { body = undefined; }
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      throw new ClientError(res.status, `http_${res.status}`, text.slice(0, 300));
    }
    let detail = body.detail === undefined || body.detail === null ? "" : body.detail;
    if (typeof detail !== "string") detail = JSON.stringify(detail);
    throw new ClientError(res.status, String(body.error === undefined ? res.status : body.error), detail, body);
  }

  static async json(res) {
    await Client.raise(res);
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch (e) {
      throw new ClientError(res.status, "bad_response", `the server did not answer with JSON: ${text.slice(0, 200)}`);
    }
  }

  // ---- the key ----------------------------------------------------------

  /** The key in use: --key, JANCTION_RENDER_API_KEY, the saved one for this server, or a new free key that gets saved. */
  async key({ create = true } = {}) {
    if (this._key) return this._key;
    const file = readKeyFile();
    if (!file.ok) {
      throw new ClientError(0, "key_file_unreadable",
        `${KEY_FILE_LABEL} exists but could not be read (${file.why}); it was left as it is. Fix the file, or pass a key with `
        + "JANCTION_RENDER_API_KEY", { retryable: false, recommended_action: "FIX_KEY_FILE" });
    }
    const saved = file.data[this.server];
    if (typeof saved === "string" && saved.trim()) {
      this._key = saved.trim();
      this.keySource = "saved";
      return this._key;
    }
    if (!create) return null;
    const res = await this.fetch("POST", `${this.server}/v1/keys`, { timeoutMs: 15000,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label: this.clientHeader, source: "npm" }) });
    const out = await Client.json(res);
    const fresh = String(out.api_key || "");
    if (!fresh) throw new ClientError(res.status, "bad_response", "POST /v1/keys returned no api_key");
    // read again just before writing: never replace an entry that appeared meanwhile (another process saved one)
    const again = readKeyFile();
    if (!again.ok) {
      this._key = fresh;
      this.keySource = "created";
      this.created = { prefix: out.prefix || prefixOf(fresh), saved: false };
      say(`janction-render: created key ${this.created.prefix} for this run, but ${KEY_FILE_LABEL} could not be read `
        + `(${again.why}), so it was not saved`);
      return fresh;
    }
    const raced = again.data[this.server];
    if (typeof raced === "string" && raced.trim()) {
      this._key = raced.trim();
      this.keySource = "saved";
      return this._key;
    }
    let savedOk = true;
    try {
      writeKeyFile({ ...again.data, [this.server]: fresh });
    } catch (e) {
      savedOk = false;
      say(`janction-render: could not save the new key in ${KEY_FILE_LABEL} (${e.message}); this run uses it, the next run `
        + "creates another one");
    }
    this._key = fresh;
    this.keySource = "created";
    this.created = { prefix: out.prefix || prefixOf(fresh), saved: savedOk };
    if (savedOk) {
      say(`janction-render: created a free key ${this.created.prefix} and saved it in ${KEY_FILE_LABEL} (no sign-up)`);
    }
    if (out.first_render) say(`janction-render: nothing has rendered yet. To check rendering works: ${CMD} try`);
    return fresh;
  }

  async headers(extra = {}) {
    return { "X-API-Key": await this.key(), ...extra };
  }

  async req(method, p, { json, timeoutMs = 30000 } = {}) {
    const headers = await this.headers(json === undefined ? {} : { "Content-Type": "application/json" });
    const res = await this.fetch(method, `${this.server}${p}`,
      { headers, timeoutMs, body: json === undefined ? undefined : JSON.stringify(json) });
    // A 401 is reported, not repaired: the Python client forgets the saved key and makes a new one, but this CLI never
    // removes an entry from the key file (it may be someone's paid key).
    return Client.json(res);
  }

  me() { return this.req("GET", "/v1/me"); }

  job(id) { return this.req("GET", `/v1/jobs/${encodeURIComponent(id)}`); }

  submit(sceneId, params) {
    const body = { scene_id: sceneId };
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) body[k] = v;
    return this.req("POST", "/v1/jobs", { json: body });
  }

  uploadUrl(url) {
    if (!String(url || "").trim().toLowerCase().startsWith("https://")) throw new UsageError("scene_url must be an https URL");
    return this.req("POST", "/v1/files/url", { json: { url: String(url).trim() }, timeoutMs: 120000 });
  }

  async lookup(digest) {
    const res = await this.fetch("GET", `${this.server}/v1/files/lookup?sha256=${digest}`, { headers: await this.headers() });
    if (res.status === 404) return null;
    return Client.json(res);
  }

  uploadCapBytes() {
    const raw = String(process.env.JANCTION_RENDER_MAX_UPLOAD_MB || "").trim();
    if (raw && /^\d+$/.test(raw)) return Number(raw) * 1024 * 1024;
    return this.server === DEFAULT_SERVER ? EDGE_UPLOAD_MB * 1024 * 1024 : 0;
  }

  tooLarge(what, n, cap, field) {
    return new ClientError(413, "too_large",
      `${what} is ${Math.round(n / 1048576)} MB; one upload to ${this.server} is limited to ${Math.floor(cap / 1048576)} MB. `
      + `Put the file on a public https link that downloads it and pass the link as ${field}, or make it smaller`,
      { code: "INVALID_INPUT", retryable: false, recommended_action: "FIX_INPUT" });
  }

  async fileBlob(p) {
    // fs.openAsBlob (Node 19.8+) streams from disk; Node 18 reads the file (single requests are at most 64 MiB on the public server)
    if (typeof fs.openAsBlob === "function") return fs.openAsBlob(p);
    return new Blob([fs.readFileSync(p)]);
  }

  /** Send a scene like Client.upload of the Python client: reuse by sha256, parts above 64 MiB, files next to glTF / OBJ. */
  async upload(file, progress = () => {}) {
    const p = path.resolve(file);
    let st;
    try { st = fs.statSync(p); } catch (e) { st = null; }
    if (!st || !st.isFile()) throw new ClientError(0, "file_not_found", `${file} is not a file`);
    if (!SCENE_SUFFIXES.includes(path.extname(p).toLowerCase())) {
      throw new UsageError(`scene must be a .blend file, a Blender Python script (.py), or a 3D file (${SCENE_SUFFIXES.slice(2).join(", ")})`);
    }
    const digest = await sha256File(p);
    let out = null;
    let reused = false;
    let method = "single_request";
    try {
      out = await this.lookup(digest);
      reused = out !== null;
    } catch (e) {
      if (!(e instanceof ClientError)) throw e;
      out = null;
    }
    if (out === null) {
      const cap = this.uploadCapBytes();
      if (cap && st.size > Math.min(cap, RESUMABLE_ABOVE)) {
        method = "resumable_parts";
        const done = await this.uploadResumable(p, digest, { progress });
        if (done === null) throw this.tooLarge(`the scene file ${path.basename(p)}`, st.size, cap, "a link (https URL) instead of the file");
        out = done.scene || done;
      } else {
        progress(0, st.size);
        const form = new FormData();
        form.append("file", await this.fileBlob(p), path.basename(p));
        const res = await this.fetch("POST", `${this.server}/v1/files`, { headers: await this.headers(), body: form,
          timeoutMs: 1800000 });
        out = await Client.json(res);
        progress(st.size, st.size);
      }
    } else {
      method = "reused_existing";
    }
    const items = [];
    const missing = [];
    const kind = companionKind(p);
    if (path.extname(p).toLowerCase() === ".blend") {
      out.asset_note = "textures next to the .blend were not looked for by the npm CLI: pack them into the .blend (File > "
        + "External Data > Pack Resources) and save, or send it with the Python CLI (uvx janction-render preview <file>)";
    } else if (kind === "gltf" || kind === "obj") {
      const base = path.dirname(p);
      const queue = companionRefs(kind, fs.readFileSync(p, "utf8"));
      const seen = new Set();
      while (queue.length) {
        const rel = queue.shift();
        if (seen.has(rel)) continue;
        seen.add(rel);
        const fp = path.join(base, rel);
        if (!fs.existsSync(fp) || !fs.statSync(fp).isFile()) { missing.push(rel); continue; }
        items.push([rel, fp]);
        if (companionKind(rel) === "mtl") {
          const folder = path.posix.dirname(rel);
          for (const sub of companionRefs("mtl", fs.readFileSync(fp, "utf8"))) {
            queue.push(folder === "." || folder === "" ? sub : `${folder}/${sub}`);
          }
        }
      }
    }
    const already = new Map((out.assets || []).map((a) => [a.name, a]));
    const todo = [];
    for (const [name, fp] of items) {
      const a = already.get(name);
      let same = false;
      if (a) same = a.sha256 ? a.sha256 === await sha256File(fp) : Number(a.size == null ? -1 : a.size) === fs.statSync(fp).size;
      if (!same) todo.push([name, fp]);
    }
    if (todo.length) out = await this.uploadAssets(out.scene_id, todo);
    out.missing_assets = missing;
    out.original_name = path.basename(p);
    out.stored_name = out.name || path.basename(p);
    out.upload_bytes = st.size;
    out.upload_method = method;
    out.reused_existing = reused;
    return out;
  }

  async uploadAssets(sceneId, items) {
    const cap = this.uploadCapBytes();
    if (!cap) return this.postAssets(sceneId, items);
    const room = cap - 1024 * 1024;
    let out = {};
    const rest = [];
    for (const [name, fp] of items) {
      if (fs.statSync(fp).size > Math.min(room, RESUMABLE_ABOVE)) {
        const done = await this.uploadResumable(fp, "", { sceneId, asset: name.replace(/\\/g, "/") });
        if (done !== null) { out = done.scene || out; continue; }
      }
      rest.push([name, fp]);
    }
    if (!rest.length) return out;
    const batches = [[]];
    let used = 0;
    for (const [name, fp] of rest) {
      const n = fs.statSync(fp).size;
      if (n > room) {
        if (n > ASSET_LINK_MAX_BYTES) {
          throw new ClientError(413, "too_large", `asset ${name} is ${Math.round(n / 1048576)} MB; an asset can be at most `
            + `${ASSET_LINK_MAX_BYTES / 1048576} MB. Make it smaller (lower texture resolution, or compress it)`,
          { code: "INVALID_INPUT", retryable: false, recommended_action: "FIX_INPUT" });
        }
        throw this.tooLarge(`asset ${name}`, n, cap, "asset_urls");
      }
      if (batches[batches.length - 1].length && used + n > room) { batches.push([]); used = 0; }
      batches[batches.length - 1].push([name, fp]);
      used += n;
    }
    for (const b of batches) out = await this.postAssets(sceneId, b);
    return out;
  }

  async postAssets(sceneId, items) {
    const form = new FormData();
    for (const [name, fp] of items) form.append("files", await this.fileBlob(fp), name);
    const res = await this.fetch("POST", `${this.server}/v1/files/${encodeURIComponent(sceneId)}/assets`,
      { headers: await this.headers(), body: form, timeoutMs: 1800000 });
    return Client.json(res);
  }

  /** tus 1.0 in parts (POST /v1/uploads, then PATCH), resumable across runs via ~/.janction-render-uploads.json. null when the
   * server has no such route. */
  async uploadResumable(p, digest, { progress = () => {}, sceneId = "", asset = "" } = {}) {
    const total = fs.statSync(p).size;
    digest = digest || await sha256File(p);
    const hdr = await this.headers();
    const ident = `${this.server}|${digest}|${total}` + (asset ? `|${sceneId}|${asset}` : "");
    const tus = { "Tus-Resumable": "1.0.0" };
    const b64 = (s) => Buffer.from(s, "utf8").toString("base64");
    let url = readResume()[ident] || null;
    let off = 0;
    if (url) {
      try {
        const h = await this.fetch("HEAD", url, { headers: { ...hdr, ...tus } });
        if (h.status === 200 && Number(h.headers.get("Upload-Length") || -1) === total) off = Number(h.headers.get("Upload-Offset") || 0);
        else url = null;
      } catch (e) {
        url = null;
      }
    }
    let part = 0;
    if (!url) {
      let meta = `filename ${b64(path.basename(p))},sha256 ${b64(digest)}`;
      if (asset) meta += `,scene_id ${b64(sceneId)},asset ${b64(asset)}`;
      const r = await this.fetch("POST", `${this.server}/v1/uploads`, { timeoutMs: 60000,
        headers: { ...hdr, ...tus, "Upload-Length": String(total), "Upload-Metadata": meta } });
      if (r.status === 404 || r.status === 405) return null;
      const created = await Client.json(r);
      url = `${this.server}${r.headers.get("Location")}`;
      part = Number(created.part_bytes) || 0;
      setResume(ident, url);
    }
    part = part || 32 * 1024 * 1024;
    let tries = 0;
    progress(off, total);
    const fd = fs.openSync(p, "r");
    try {
      for (;;) {
        const n = Math.max(0, Math.min(part, total - off));
        const data = Buffer.alloc(n);
        if (n) fs.readSync(fd, data, 0, n, off);
        const sum = `sha256 ${crypto.createHash("sha256").update(data).digest("base64")}`;
        const sentFrom = off;
        const t0 = Date.now();
        let r = null;
        try {
          r = await this.fetch("PATCH", url, { timeoutMs: 600000, body: data, headers: { ...hdr, ...tus,
            "Upload-Offset": String(off), "Content-Type": "application/offset+octet-stream", "Upload-Checksum": sum } });
        } catch (e) {
          if (!(e instanceof ClientError)) throw e;
          r = null;   // cut or unreachable: ask for the offset again below
        }
        if (r && r.status === 200) {
          setResume(ident, null);
          progress(total, total);
          return Client.json(r);
        }
        if (r && r.status === 204) {
          off = Number(r.headers.get("Upload-Offset") || off);
          tries = 0;
          part = fitPart(part, off - sentFrom, (Date.now() - t0) / 1000);
          progress(off, total);
          continue;
        }
        if (r && r.status === 409 && r.headers.get("Upload-Offset") !== null) {
          off = Number(r.headers.get("Upload-Offset"));
          continue;
        }
        if (r && r.status === 460) r = null;   // the part arrived damaged: send it again (counts as a try)
        if (r && ((r.status < 500 && ![408, 409, 429].includes(r.status)) || r.status === 507)) {
          if (r.status === 404) setResume(ident, null);
          await Client.raise(r);
        }
        tries += 1;
        if (tries > 8) {
          throw new ClientError(0, "upload_interrupted", `the upload of ${path.basename(p)} kept failing at ${off} of ${total} bytes; `
            + "run the same command again to continue from there", { retryable: true, offset: off });
        }
        await sleep(Math.min(30, 2 ** tries) * 1000);
        try {
          const h = await this.fetch("HEAD", url, { headers: { ...hdr, ...tus } });
          if (h.status === 200) {
            off = Number(h.headers.get("Upload-Offset") || off);
            if (off > sentFrom) {
              tries = 0;
              part = fitPart(part, off - sentFrom, (Date.now() - t0) / 1000, true);
              progress(off, total);
            }
          } else if (h.status === 404) {
            setResume(ident, null);
            await Client.raise(h);
          }
        } catch (e) {
          if (!(e instanceof ClientError) || e.status) throw e;
        }
      }
    } finally {
      fs.closeSync(fd);
    }
  }

  /** Poll until done / failed / canceled, or until the timeout (then the current state). */
  async wait(id, timeoutS, onProgress = () => {}) {
    const deadline = Date.now() + timeoutS * 1000;
    let last = null;
    for (;;) {
      const job = await this.job(id);
      const k = `${job.status}|${(job.progress || {}).frames_done}`;
      if (k !== last) { onProgress(job); last = k; }
      if (["done", "failed", "canceled"].includes(job.status) || Date.now() > deadline) return job;
      await sleep(this.pollMs);
    }
  }

  /** Download the artifacts of a job into outDir under their own names; resumes a cut file with Range. */
  async download(id, outDir, only) {
    const job = await this.job(id);
    fs.mkdirSync(outDir, { recursive: true });
    const wanted = selectArtifacts(job.artifacts || [], only);
    const paths = [];
    let lastSay = Date.now();
    for (let i = 0; i < wanted.length; i += 1) {
      const a = wanted[i];
      const dest = path.join(outDir, safeName(a.name));
      if (a.size != null && fs.existsSync(dest) && fs.statSync(dest).size === Number(a.size)) {
        paths.push(dest);
        continue;
      }
      if (wanted.length > 1 && Date.now() - lastSay > 10000) {
        lastSay = Date.now();
        say(`  downloading ${i + 1}/${wanted.length} files`);
      }
      // the server builds URLs on its public address; keep the path and use the server this CLI talks to
      let url = a.url;
      try {
        const u = new URL(a.url);
        if (u.pathname.startsWith("/v1/")) url = `${this.server}${u.pathname}${u.search}`;
      } catch (e) {
        url = `${this.server}${String(a.url || "").startsWith("/") ? "" : "/"}${a.url}`;
      }
      await this.downloadFile(url, dest);
      paths.push(dest);
    }
    return { job, paths };
  }

  async downloadFile(url, dest) {
    const part = `${dest}.part`;
    for (let attempt = 0; ; attempt += 1) {
      const have = fs.existsSync(part) ? fs.statSync(part).size : 0;
      const headers = await this.headers(have ? { Range: `bytes=${have}-` } : {});
      try {
        const res = await this.fetch("GET", url, { headers, timeoutMs: 600000, idle: true });
        if (res.status === 416) { res.done(); break; }
        if (res.status === 429 && attempt < DOWNLOAD_TRIES + 2) {
          res.done();
          const after = Math.min(60, Number(res.headers.get("Retry-After")) || 5);
          say(`  the server asked to slow down; waiting ${after}s`);
          await sleep(after * 1000);
          continue;
        }
        if (res.status >= 400) { res.done(); await Client.raise(res); }
        const fd = fs.openSync(part, res.status === 206 ? "a" : "w");
        try {
          if (res.body) {
            for await (const chunk of res.body) {
              fs.writeSync(fd, chunk);
              res.resetIdle();
            }
          }
        } finally {
          fs.closeSync(fd);
          res.done();
        }
        break;
      } catch (e) {
        // a cut connection or a stalled body (fetch errors carry no syscall; disk errors do and are not retried)
        const network = e instanceof ClientError ? e.status === 0 : !e.syscall;
        if (!network) throw e;
        if (attempt >= DOWNLOAD_TRIES - 1) throw e instanceof ClientError ? e : unreachable(this.server, url, e);
        await sleep(2000 * (attempt + 1));
      }
    }
    if (fs.existsSync(part)) fs.renameSync(part, dest);
  }
}

// ---------------------------------------------------------------------------------------------------- output

function progressLine(job) {
  const p = job.progress || {};
  say(`  ${job.status}: ${p.frames_done == null ? "?" : p.frames_done}/${p.frames_total == null ? "?" : p.frames_total} frames`
    + (p.queue_ahead ? `, ${p.queue_ahead} chunks ahead` : ""));
}

function uploadProgress(done, total) {
  const pct = !total ? 100 : Math.min(100, Math.floor((done * 100) / total));
  say(`  upload: ${String(pct).padStart(3)}% (${mib(done)}/${mib(total)} MiB)`
    + (done === 0 && total > 100 * 1024 * 1024 ? "; safe to rerun the same command if interrupted" : ""));
}

function links(job) {
  return (job.artifacts || []).map((a) => ({ name: a.name, view_url: a.view_url || null, size: a.size == null ? null : a.size }));
}

function failed(job) {
  const out = {};
  for (const k of ["job_id", "status", "error", "log_tail", "warnings"]) out[k] = job[k] === undefined ? null : job[k];
  return out;
}

function emit(opts, obj, lines) {
  if (opts.json) process.stdout.write(`${j(obj)}\n`);
  else process.stdout.write(`${(Array.isArray(lines) ? lines : [lines]).filter((x) => x !== null && x !== undefined).join("\n")}\n`);
}

// ---------------------------------------------------------------------------------------------------- scene argument

async function sceneOf(c, opts, label = "scene") {
  if (opts.sceneId) return { scene_id: opts.sceneId };
  const scene = opts._[0];
  if (!scene) throw new UsageError(`give a ${label}: a local file (.blend, .py, .glb ...) or an https link, or --scene-id`);
  if (isLink(scene)) {
    const url = sceneLink(scene);
    if (!url) throw new UsageError(`the link must be https and end in ${SCENE_SUFFIXES.join(" / ")}`);
    const up = await c.uploadUrl(url);
    say(`fetched ${url} -> scene_id ${up.scene_id}`);
    return up;
  }
  const up = await c.upload(scene, uploadProgress);
  if (up.reused_existing) {
    say(`same file already uploaded; reused scene_id ${up.scene_id} (no bytes sent)`);
  } else {
    const renamed = up.stored_name && up.stored_name !== up.original_name ? ` (stored as ${up.stored_name})` : "";
    say(`upload complete: ${up.original_name}${renamed} -> scene_id ${up.scene_id}`);
  }
  if (up.missing_assets && up.missing_assets.length) say(`note: not found next to the file, not sent: ${up.missing_assets.join(", ")}`);
  if (up.asset_note) say(`note: ${up.asset_note}`);
  return up;
}

// ---------------------------------------------------------------------------------------------------- commands

async function cmdKey(c, opts) {
  if (c.keySource === "--key" || c.keySource === "JANCTION_RENDER_API_KEY") {
    const prefix = prefixOf(c._key);
    emit(opts, { server: c.server, prefix, source: c.keySource, created: false, saved: false },
      `using the key from ${c.keySource} (${prefix}) for ${c.server}; nothing was saved`);
    return 0;
  }
  const existing = await c.key({ create: false });
  if (existing) {
    const prefix = prefixOf(existing);
    emit(opts, { server: c.server, prefix, source: "saved", created: false, saved: true, key_file: keyFile() },
      `a key is already saved for ${c.server}: ${prefix} (in ${KEY_FILE_LABEL}, left unchanged)`);
    return 0;
  }
  await c.key();
  const info = c.created || { prefix: prefixOf(c._key), saved: true };
  emit(opts, { server: c.server, prefix: info.prefix, source: c.created ? "created" : "saved", created: Boolean(c.created),
    saved: info.saved, key_file: keyFile(), next: `${CMD} try` },
  [info.saved ? `saved key ${info.prefix} for ${c.server} in ${KEY_FILE_LABEL}` : `created key ${info.prefix} (not saved)`,
    `next: ${CMD} try`]);
  return 0;
}

async function finishPreview(c, opts, job, sceneId, extra = {}) {
  if (job.status !== "done") {
    emit(opts, failed(job), [`job ${job.job_id} ${job.status}${job.error ? `: ${job.error}` : ""}`,
      job.status === "failed" ? null : `follow it with: ${CMD} status ${job.job_id}`]);
    return 1;
  }
  const out = opts.out || path.join("render_out", job.job_id);
  const { paths } = await c.download(job.job_id, out);
  const images = links(job);
  emit(opts, { job_id: job.job_id, scene_id: sceneId, ...extra, images, files: paths, warnings: job.warnings || [],
    gpu_seconds: job.gpu_seconds, device: job.device, expires_at: job.expires_at },
  [`done: ${job.gpu_seconds} GPU seconds on ${job.device || "GPU"}`,
    ...images.filter((a) => a.view_url).map((a) => `image: ${a.view_url}`),
    ...paths.map((p) => `saved: ${p}`),
    ...(job.warnings || []).map((w) => `warning: ${typeof w === "string" ? w : JSON.stringify(w)}`)]);
  return 0;
}

async function cmdTry(c, opts) {
  say("rendering a sample scene on a cloud GPU (four lighting presets in one image)...");
  // the sample of the server in use when it is https (the Python CLI uses <server>/samples/...), else the public one
  const sample = c.server.startsWith("https://") ? `${c.server}/samples/cube_scene.py` : SAMPLE_SCENE;
  const up = await c.uploadUrl(sample);
  let job = await c.submit(up.scene_id, { kind: "preview", frames: [1], environment: "compare" });
  job = await c.wait(job.job_id, opts.timeout == null ? 180 : opts.timeout, progressLine);
  const code = await finishPreview(c, opts, job, up.scene_id);
  if (code === 0 && !opts.json) {
    say(`next:\n  ${CMD} preview my_scene.blend          (a .blend, a bpy script, or a .glb / .fbx / .usd / .obj file)\n`
      + `  ${CMD} final my_scene.blend --frames 1-48\n  ${CMD} final model.glb --preset turntable`);
  }
  return code;
}

async function cmdPreview(c, opts) {
  const up = await sceneOf(c, opts);
  const [w, h] = opts.size ? size(opts.size) : [1280, 720];
  const frames = parseFrames(opts.frames, opts.frame == null ? 1 : opts.frame);
  if (opts.engine && !["cycles", "eevee"].includes(opts.engine)) throw new UsageError("--engine must be cycles or eevee");
  let job = await c.submit(up.scene_id, { kind: "preview", frames, camera: opts.camera, width: w, height: h,
    samples: opts.samples == null ? 16 : opts.samples, engine: opts.engine, max_yen: opts.maxYen });
  say(`job ${job.job_id} queued: frames ${JSON.stringify(frames)} (estimate ~${(job.estimate || {}).seconds == null ? "?" : job.estimate.seconds}s)`);
  job = await c.wait(job.job_id, opts.timeout == null ? 300 : opts.timeout, progressLine);
  return finishPreview(c, opts, job, up.scene_id, { frames });
}

function withPreset(body, preset) {
  // client side of mcp_common.with_preset: settings left at the tool defaults give way to the preset's own defaults
  if (!preset) return body;
  const out = { ...body, preset };
  for (const [k, d] of Object.entries(FINAL_TOOL_DEFAULTS)) if (out[k] === d) out[k] = null;
  if ((out.frame_end || 0) <= (out.frame_start || 0)) {
    out.frame_end = null;
    if (preset === "animation") out.frame_start = null;
  }
  return out;
}

function autoIdempotencyKey(body) {
  // like mcp_common.auto_idempotency_key: the same request within the same 2 minutes gets the same key (no second job)
  const sorted = (v) => (Array.isArray(v) ? v.map(sorted) : v && typeof v === "object"
    ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])])) : v);
  const blob = JSON.stringify({ tool: "npm_final", body: sorted(body) });
  return `auto:${Math.floor(Date.now() / 1000 / 120)}:${crypto.createHash("sha256").update(blob).digest("hex").slice(0, 32)}`;
}

async function cmdFinal(c, opts) {
  const preset = String(opts.preset || "").trim().toLowerCase();
  if (preset && !PRESETS.includes(preset)) throw new UsageError("--preset must be product, turntable or animation");
  if (opts.engine && !["cycles", "eevee"].includes(opts.engine)) throw new UsageError("--engine must be cycles or eevee");
  const output = opts.output || "auto";
  let range = opts.frames ? frameRange(opts.frames) : null;
  if (!range && !preset && output !== "blend") {
    throw new UsageError("--frames is required (e.g. 1-240 or 12) unless --preset is given (or --output blend)");
  }
  range = range || [1, 1];
  const [w, h] = opts.size ? size(opts.size) : [1920, 1080];
  const up = await sceneOf(c, opts);
  if (preset === "animation" && range[1] <= range[0]) {
    // the preset takes the scene's own frame range: read the scene first (no render, like the MCP server)
    say("reading the scene's frame range first (no render)...");
    let info = await c.submit(up.scene_id, { kind: "info" });
    if (info.status !== "done") info = await c.wait(info.job_id, 180, () => {});
    if (info.status !== "done") {
      throw new UsageError(`--preset animation needs the scene's frame range, but reading the scene did not finish (${info.error || info.status}); pass --frames instead`);
    }
  }
  let params = { kind: "final", frame_start: range[0], frame_end: range[1], width: w, height: h,
    samples: opts.samples == null ? 128 : opts.samples, fps: opts.fps == null ? 24 : opts.fps, output, camera: opts.camera,
    engine: opts.engine, transparent: opts.transparent ? true : null, max_yen: opts.maxYen, notify_url: opts.notifyUrl };
  params = withPreset(params, preset);
  const idem = opts.idempotencyKey || autoIdempotencyKey({ scene_id: up.scene_id, ...params });
  params.idempotency_key = idem;
  let job = await c.submit(up.scene_id, params);
  if (job.idempotent_replayed) say(`job ${job.job_id} was already submitted with this idempotency key (nothing new queued or charged)`);
  const est = job.estimate || {};
  const p = job.progress || {};
  say(`job ${job.job_id} queued` + (p.frames_total ? `: ${p.frames_total} frames` : "")
    + (p.chunks_total ? ` in ${p.chunks_total} chunks` : "") + `, estimate ${est.human || `~${est.seconds == null ? "?" : est.seconds}s`}`);
  if (job.tell_user) say(String(job.tell_user));
  if (!opts.wait) {
    emit(opts, { job_id: job.job_id, scene_id: up.scene_id, status: job.status, estimate: job.estimate || null,
      idempotency_key: idem, split: job.split || undefined,
      next: `${CMD} status ${job.job_id}; when done: ${CMD} download ${job.job_id}` },
    [`job ${job.job_id} ${job.status || "queued"}`, `follow it: ${CMD} status ${job.job_id}`,
      `when done: ${CMD} download ${job.job_id} --out render_out/${job.job_id}`]);
    return 0;
  }
  job = await c.wait(job.job_id, opts.timeout == null ? 7200 : opts.timeout, progressLine);
  if (job.status !== "done") {
    emit(opts, failed(job), [`job ${job.job_id} ${job.status}${job.error ? `: ${job.error}` : ""}`]);
    return 1;
  }
  const out = opts.out || path.join("render_out", job.job_id);
  const { paths } = await c.download(job.job_id, out);
  emit(opts, { job_id: job.job_id, scene_id: up.scene_id, files: paths, links: links(job), warnings: job.warnings || [],
    gpu_seconds: job.gpu_seconds, device: job.device, expires_at: job.expires_at },
  [`done: ${job.gpu_seconds} GPU seconds on ${job.device || "GPU"}`, ...paths.map((x) => `saved: ${x}`)]);
  return 0;
}

async function cmdStatus(c, opts) {
  const id = opts._[0];
  if (!id) throw new UsageError("give a job id: status <job_id>");
  const job = await c.job(id);
  const p = job.progress || {};
  const eta = (job.eta && (job.eta.human || job.eta.en)) || null;
  const lines = [`${job.job_id}: ${job.status}` + (p.frames_total ? `, ${p.frames_done || 0}/${p.frames_total} frames` : "")
    + (p.queue_ahead ? `, ${p.queue_ahead} chunks ahead` : "") + (eta ? `, ${typeof eta === "string" ? eta : JSON.stringify(eta)}` : "")];
  if (job.error) lines.push(`error: ${job.error}`);
  if (job.status === "done") {
    for (const a of links(job).slice(0, 12)) lines.push(`${a.name}: ${a.view_url || "(download it)"}`);
    lines.push(`download: ${CMD} download ${job.job_id} --out render_out/${job.job_id}`);
  }
  if (opts.json) process.stdout.write(`${j(job)}\n`); else process.stdout.write(`${lines.join("\n")}\n`);
  return ["failed", "canceled"].includes(job.status) ? 1 : 0;
}

async function cmdDownload(c, opts) {
  const id = opts._[0];
  if (!id) throw new UsageError("give a job id: download <job_id> [--out dir]");
  if (opts.only) selectArtifacts([], opts.only);   // check the choice before any request
  let job = opts.wait ? await c.wait(id, opts.wait, progressLine) : null;
  const out = opts.out || path.join("render_out", id);
  const got = await c.download(id, out, opts.only);
  job = got.job;
  emit(opts, { job_id: id, status: job.status, files: got.paths },
    [...got.paths.map((x) => `saved: ${x}`), got.paths.length ? null : "no files yet", job.status === "done" ? null
      : `the job is ${job.status}; ${CMD} status ${id}`]);
  return job.status === "done" ? 0 : 1;
}

// ---------------------------------------------------------------------------------------------------- help / parsing

const COMMANDS = {
  key: { fn: cmdKey, usage: "key", options: {},
    help: "create a free key (no sign-up) and save it in ~/.janction-render.json; prints only its prefix. A key already saved "
      + "for the server is kept as it is." },
  try: { fn: cmdTry, usage: "try [--out dir]", options: { out: "string", timeout: "int" },
    help: "render the sample scene (a few seconds) and print the image link" },
  preview: { fn: cmdPreview, usage: "preview <scene> [--frames 1-24 | --frame 12] [--size 1280x720] [--samples 16] [--engine cycles|eevee] [--camera NAME] [--max-yen N] [--out dir]",
    options: { "scene-id": "string", frame: "int", frames: "string", camera: "string", size: "string", samples: "int",
      engine: "string", out: "string", timeout: "int", "max-yen": "int" },
    help: "a fast preview (up to 4 frames tiled in one image); <scene> is a local .blend / .py / 3D file or an https link" },
  final: { fn: cmdFinal, usage: "final <scene> [--frames 1-24] [--preset product|turntable|animation] [--max-yen N] [--size 1920x1080] [--samples 128] [--fps 24] [--output auto|png|mp4|...] [--transparent] [--wait] [--out dir]",
    options: { "scene-id": "string", frames: "string", preset: "string", size: "string", samples: "int", fps: "int",
      output: "string", camera: "string", engine: "string", transparent: "bool", "notify-url": "string", wait: "bool",
      out: "string", timeout: "int", "max-yen": "int", "idempotency-key": "string" },
    help: "final frames or a video; returns the job id at once (add --wait to wait and download). --frames is needed unless "
      + "--preset is given. The same command run again within 2 minutes returns the same job (no second charge)." },
  status: { fn: cmdStatus, usage: "status <job_id>", options: {}, help: "progress, ETA and, when done, the links" },
  download: { fn: cmdDownload, usage: "download <job_id> [--out dir] [--only all|mp4|frames|sheet|output] [--wait SECONDS]",
    options: { out: "string", only: "string", wait: "int" },
    help: "save the files of a job under their own names (default folder: render_out/<job_id>)" },
};

function cliHelp() {
  const lines = ["Render from a terminal (Node only, no Python):"];
  for (const name of SUBCOMMANDS) lines.push(`  ${CMD} ${COMMANDS[name].usage}`, `      ${COMMANDS[name].help}`);
  lines.push("",
    "  --json            machine-readable output on stdout (progress goes to stderr) for every subcommand",
    "  --server <url>    another server (default: JANCTION_RENDER_SERVER or https://render.janction.jp)",
    "  --key jr_...      use this key for the run (also JANCTION_RENDER_API_KEY); otherwise the key saved in",
    "                    ~/.janction-render.json (shared with the Python CLI), or a new free key saved there",
    "  Exit codes: 0 ok, 1 job failed or not done, 2 error, 3 payment required (checkout link printed), 4 quota");
  return lines.join("\n");
}

function camel(name) {
  return name.replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
}

/** Find the subcommand: the first token that is not a global option (or its value). null when there is none. */
function findCommand(argv) {
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--json" || a === "--help" || a === "-h" || a.startsWith("--key=") || a.startsWith("--server=")) continue;
    if (a === "--key" || a === "--server") { i += 1; continue; }
    return SUBCOMMANDS.includes(a) ? { name: a, index: i } : null;
  }
  return null;
}

function parseArgs(argv, spec) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--") { out._.push(...argv.slice(i + 1)); break; }
    if (a === "-h") { out.help = true; continue; }
    if (a.startsWith("--")) {
      let name = a.slice(2);
      let val;
      const eq = name.indexOf("=");
      if (eq >= 0) { val = name.slice(eq + 1); name = name.slice(0, eq); }
      const type = GLOBAL_OPTS[name] || spec[name];
      if (!type) throw new UsageError(`unknown option --${name}`);
      if (type === "bool") {
        if (val !== undefined) throw new UsageError(`--${name} takes no value`);
        out[camel(name)] = true;
        continue;
      }
      if (val === undefined) {
        val = argv[i + 1];
        i += 1;
        if (val === undefined) throw new UsageError(`--${name} needs a value`);
      }
      out[camel(name)] = type === "int" ? toInt(val, `--${name}`) : val;
      continue;
    }
    out._.push(a);
  }
  return out;
}

function reportError(err, opts, c) {
  if (err instanceof UsageError) {
    if (opts.json) process.stdout.write(`${j({ ok: false, error: "usage", detail: err.message })}\n`);
    say(`janction-render: ${err.message}`);
    return 2;
  }
  if (!(err instanceof ClientError)) {
    if (opts.json) process.stdout.write(`${j({ ok: false, error: "internal", detail: String(err && err.message || err) })}\n`);
    say(`janction-render: ${err && err.stack ? err.stack : err}`);
    return 2;
  }
  if (err.status === 429 && err.error === "quota_exceeded") {
    say(`quota: ${err.detail}`);
    const q = { ok: false, error: err.error, detail: err.detail };
    for (const k of ["scope", "gpu_seconds_used_today", "gpu_seconds_per_day", "resets_at"]) q[k] = err.extra[k] === undefined ? null : err.extra[k];
    process.stdout.write(`${j(q)}\n`);
    return 4;
  }
  const pay = err.payment();
  if (pay) {
    say(`payment required: ${err.detail}`);
    const order = (pay.resume || {}).order_id;
    if (pay.card_offer) {
      const co = pay.card_offer;
      say(`free option: registering a card costs nothing and the card is not charged; it adds ${Number(co.bonus_yen) || 0} JPY of `
        + `free GPU time for ${co.days || 14} days${co.link ? `. Open ${co.link}` : ""}${order ? "; the render then starts by itself" : ""}`);
      say(`or pay ${pay.topup_yen || ""} JPY: ${pay.checkout_url}${order ? "; the render then starts by itself" : ", then run the command again"}`);
    } else if (order) {
      say(`open this page in a browser and pay: ${pay.checkout_url}`);
      say("the render then starts by itself (nothing to run again)");
    } else {
      say(`open this page in a browser and pay, then run the command again: ${pay.checkout_url}`);
    }
    if (order) say(`follow it with: ${CMD} status ${order}`);
    process.stdout.write(`${j(pay)}\n`);
    return 3;
  }
  say(`error: ${err.message}`);
  if (err.status === 401) {
    const src = c && c.keySource === "saved" ? `the key saved in ${KEY_FILE_LABEL} for ${c.server}` : `the key (${c ? c.keySource : "?"})`;
    say(`${src} was refused. The key file was not changed; pass a working key with --key or JANCTION_RENDER_API_KEY`);
  } else if (err.status === 429) {
    const after = err.extra.retry_after_s;
    say(after ? `retry in about ${after}s` : "too many requests; wait a little and retry");
  } else if (err.status === 413 || err.error === "too_large") {
    const base = c ? c.server : DEFAULT_SERVER;
    say(`instead: open ${base}/upload in a browser and drop the file there (it is sent in parts and resumes), then pass the `
      + "link the page shows in place of the file");
  }
  if (opts.json) {
    process.stdout.write(`${j({ ok: false, error: err.error, detail: err.detail, http_status: err.status || null,
      ...err.agentFields() })}\n`);
  }
  return 2;
}

async function main(argv) {
  const found = findCommand(argv);
  const name = found ? found.name : null;
  const spec = name ? COMMANDS[name].options : {};
  let opts = { _: [] };
  let c = null;
  try {
    opts = parseArgs(found ? [...argv.slice(0, found.index), ...argv.slice(found.index + 1)] : argv, spec);
    if (!name || opts.help) {
      process.stdout.write(`${name ? `Usage: ${CMD} ${COMMANDS[name].usage}\n  ${COMMANDS[name].help}\n\n` : ""}${cliHelp()}\n`);
      return 0;
    }
    c = new Client({ server: opts.server, key: opts.key });
    return await COMMANDS[name].fn(c, opts);
  } catch (err) {
    return reportError(err, opts, c);
  }
}

module.exports = { main, findCommand, cliHelp, SUBCOMMANDS, parseFrames, sceneLink, selectArtifacts, withPreset, Client, ClientError };
