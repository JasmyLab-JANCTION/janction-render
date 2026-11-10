// Tests of the terminal subcommands against a tiny local fake of the API (no network, no real keys or jobs).
// HOME / USERPROFILE point at a temporary folder, so the real ~/.janction-render.json is never read or written.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFile } = require("node:child_process");

const BIN = path.join(__dirname, "..", "bin", "janction-render.js");
const PKG = require("../package.json");
const PNG = Buffer.from("89504e470d0a1a0a0000000d49484452", "hex");
const FAKE_KEY = `jr_${"a1b2c3d4".repeat(4)}`;
const OPERATOR_KEY = `jr_${"0f".repeat(16)}`;

// ---------------------------------------------------------------------------------------------------- the fake API

function fakeServer() {
  const state = { calls: [], jobs: {}, uploads: {}, nextJob: 1, keysCreated: 0 };
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const body = Buffer.concat(chunks);
      const url = new URL(req.url, "http://x");
      const call = { method: req.method, path: url.pathname, query: url.search, headers: req.headers, body };
      try { call.json = JSON.parse(body.toString("utf8")); } catch (e) { /* not JSON */ }
      state.calls.push(call);
      const send = (status, obj, headers = {}) => {
        res.writeHead(status, { "Content-Type": "application/json", ...headers });
        res.end(obj === undefined ? "" : JSON.stringify(obj));
      };
      const base = `http://127.0.0.1:${server.address().port}`;
      const authed = () => {
        const k = req.headers["x-api-key"];
        if (k === "jr_revoked") { send(401, { error: "unauthorized", detail: "invalid API key" }); return false; }
        if (!k) { send(401, { error: "unauthorized", detail: "missing X-API-Key" }); return false; }
        return true;
      };
      const newJob = (extra) => {
        const id = `j_${state.nextJob++}`;
        const job = { job_id: id, status: "queued", kind: extra.kind, polls: 0, request: extra,
          estimate: { seconds: 6, human: "about 6 seconds" },
          progress: { frames_done: 0, frames_total: 1, chunks_total: 1, queue_ahead: 0 } };
        state.jobs[id] = job;
        return job;
      };
      const view = (job) => {
        const out = { job_id: job.job_id, status: job.status, kind: job.kind, progress: job.progress,
          estimate: job.estimate, gpu_seconds: 4.2, device: "Fake GPU", expires_at: 1, warnings: [] };
        out.artifacts = job.status === "done" ? [
          { name: "frame_0001.png", size: PNG.length, url: `https://render.example/v1/jobs/${job.job_id}/artifacts/frame_0001.png`,
            view_url: `https://render.example/v/${job.job_id}/frame_0001.png?sig=1` },
          ...(job.kind === "final" ? [{ name: "output.mp4", size: 5, url: `/v1/jobs/${job.job_id}/artifacts/output.mp4`,
            view_url: `https://render.example/v/${job.job_id}/output.mp4?sig=1` }] : []),
        ] : [];
        return out;
      };

      const p = url.pathname;
      if (req.method === "POST" && p === "/v1/keys") {
        state.keysCreated += 1;
        return send(200, { api_key: FAKE_KEY, prefix: FAKE_KEY.slice(0, 10), first_render: { cli: "uvx janction-render try" } });
      }
      if (!authed()) return undefined;
      if (req.method === "GET" && p === "/v1/files/lookup") return send(404, { error: "not_found", detail: "" });
      if (req.method === "POST" && p === "/v1/files") {
        const text = body.toString("latin1");
        const name = (text.match(/filename="([^"]+)"/) || [])[1];
        return send(200, { scene_id: "s_file", name, assets: [] });
      }
      if (req.method === "POST" && /^\/v1\/files\/[^/]+\/assets$/.test(p)) {
        const names = [...body.toString("latin1").matchAll(/name="files"; filename="([^"]+)"/g)].map((m) => m[1]);
        return send(200, { scene_id: p.split("/")[3], assets: names.map((n) => ({ name: n, size: 1 })) });
      }
      if (req.method === "POST" && p === "/v1/files/url") {
        if (String(call.json.url).includes("payme")) return send(200, { scene_id: "s_pay" });
        if (String(call.json.url).includes("quota")) return send(200, { scene_id: "s_quota" });
        return send(200, { scene_id: "s_url" });
      }
      if (req.method === "POST" && p === "/v1/uploads") {
        const id = `u${Object.keys(state.uploads).length + 1}`;
        state.uploads[id] = { length: Number(req.headers["upload-length"]), got: [], meta: req.headers["upload-metadata"] };
        return send(201, { part_bytes: 512 * 1024 }, { Location: `/v1/uploads/${id}` });
      }
      if (req.method === "PATCH" && p.startsWith("/v1/uploads/")) {
        const u = state.uploads[p.split("/")[3]];
        const have = u.got.reduce((n, b) => n + b.length, 0);
        if (Number(req.headers["upload-offset"]) !== have) return send(409, { error: "conflict" }, { "Upload-Offset": String(have) });
        u.got.push(body);
        const now = have + body.length;
        if (now < u.length) { res.writeHead(204, { "Upload-Offset": String(now) }); return res.end(); }
        return send(200, { scene_id: "s_big", scene: { scene_id: "s_big", name: "big.glb", assets: [] } });
      }
      if (req.method === "POST" && p === "/v1/jobs") {
        const b = call.json;
        if (b.scene_id === "s_pay") {
          return send(402, { error: "payment_required", detail: "not enough credit for this render", needed_yen: 120,
            balance_yen: 0, topup_yen: 500, checkout_url: "https://checkout.example/pay/1", tell_user: "needs a top-up" });
        }
        if (b.scene_id === "s_quota") {
          return send(429, { error: "quota_exceeded", detail: "daily free time used", scope: "key", gpu_seconds_used_today: 120,
            gpu_seconds_per_day: 120, resets_at: 99 });
        }
        return send(200, view(newJob(b)));
      }
      let m = p.match(/^\/v1\/jobs\/([^/]+)$/);
      if (req.method === "GET" && m) {
        const job = state.jobs[m[1]];
        if (!job) return send(404, { error: "not_found", detail: "no such job" });
        job.polls += 1;
        if (job.polls >= 2) {
          job.status = "done";
          job.progress = { ...job.progress, frames_done: job.progress.frames_total };
        }
        return send(200, view(job));
      }
      m = p.match(/^\/v1\/jobs\/([^/]+)\/artifacts\/([^/]+)$/);
      if (req.method === "GET" && m) {
        res.writeHead(200, { "Content-Type": "application/octet-stream" });
        return res.end(m[2].endsWith(".png") ? PNG : Buffer.from("mp4!!"));
      }
      send(404, { error: "not_found", detail: `${req.method} ${p}` });
      return undefined;
    });
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => {
    state.url = `http://127.0.0.1:${server.address().port}`;
    resolve({ server, state });
  }));
}

// ---------------------------------------------------------------------------------------------------- helpers

function tempHome() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "jr-npm-test-"));
}

function run(args, { home, server, env = {}, cwd } = {}) {
  const e = { ...process.env, HOME: home, USERPROFILE: home, JANCTION_RENDER_POLL_MS: "20", ...env };
  delete e.JANCTION_RENDER_API_KEY;
  delete e.JANCTION_RENDER_CLIENT;
  delete e.JANCTION_RENDER_MAX_UPLOAD_MB;
  if (server) e.JANCTION_RENDER_SERVER = server;
  Object.assign(e, env);
  return new Promise((resolve) => {
    execFile(process.execPath, [BIN, ...args], { env: e, cwd: cwd || home, timeout: 30000 }, (err, stdout, stderr) => {
      resolve({ code: err ? (typeof err.code === "number" ? err.code : 1) : 0, stdout, stderr });
    });
  });
}

const keyFileOf = (home) => path.join(home, ".janction-render.json");
const readKeys = (home) => JSON.parse(fs.readFileSync(keyFileOf(home), "utf8"));

let fake;
test.before(async () => { fake = await fakeServer(); });
test.after(() => new Promise((r) => fake.server.close(r)));
test.beforeEach(() => { fake.state.calls.length = 0; });

// ---------------------------------------------------------------------------------------------------- tests

test("--help lists the subcommands and --version prints the package version", async () => {
  const home = tempHome();
  const h = await run(["--help"], { home });
  assert.equal(h.code, 0);
  for (const cmd of ["key", "try", "preview <scene>", "final <scene>", "status <job_id>", "download <job_id>", "--json"]) {
    assert.ok(h.stdout.includes(cmd), `help mentions ${cmd}`);
  }
  assert.ok(h.stdout.includes("--local"), "the launcher options are still there");
  const v = await run(["--version"], { home });
  assert.equal(v.stdout.trim(), PKG.version);
});

test("no subcommand stays the MCP launcher (the CLI module does not claim it)", () => {
  const { findCommand } = require("../lib/cli");
  assert.equal(findCommand([]), null);
  assert.equal(findCommand(["--key", "jr_x"]), null);
  assert.equal(findCommand(["--local"]), null);
  assert.equal(findCommand(["--url", "https://x/mcp", "--", "--transport", "sse-only"]), null);
  assert.deepEqual(findCommand(["--json", "status", "j_1"]), { name: "status", index: 1 });
  assert.deepEqual(findCommand(["--server", "http://h", "try"]), { name: "try", index: 2 });
});

test("key creates a free key, saves it keyed by server and prints only the prefix", async () => {
  const home = tempHome();
  const r = await run(["key", "--json"], { home, server: fake.state.url });
  assert.equal(r.code, 0, r.stderr);
  const out = JSON.parse(r.stdout);
  assert.equal(out.prefix, FAKE_KEY.slice(0, 10));
  assert.equal(out.created, true);
  assert.ok(!r.stdout.includes(FAKE_KEY) && !r.stderr.includes(FAKE_KEY), "the whole key is never printed");
  assert.deepEqual(readKeys(home), { [fake.state.url]: FAKE_KEY });
  const call = fake.state.calls.find((c) => c.path === "/v1/keys");
  assert.match(call.headers["x-client"], /^cli\/npm \d/);
  assert.equal(call.json.source, "npm");
  // the second run reuses it and creates nothing
  const before = fake.state.keysCreated;
  const again = await run(["key"], { home, server: fake.state.url });
  assert.equal(again.code, 0);
  assert.equal(fake.state.keysCreated, before);
  assert.match(again.stdout, /already saved/);
});

test("key keeps every existing entry: other servers and an existing key for this server are never replaced", async () => {
  const home = tempHome();
  fs.writeFileSync(keyFileOf(home), JSON.stringify({ "https://render.janction.jp": OPERATOR_KEY }, null, 1));
  const r = await run(["key"], { home, server: fake.state.url });
  assert.equal(r.code, 0, r.stderr);
  assert.deepEqual(readKeys(home), { "https://render.janction.jp": OPERATOR_KEY, [fake.state.url]: FAKE_KEY });

  const home2 = tempHome();
  fs.writeFileSync(keyFileOf(home2), JSON.stringify({ [fake.state.url]: OPERATOR_KEY }));
  const before = fake.state.keysCreated;
  const r2 = await run(["key", "--json"], { home: home2, server: fake.state.url });
  assert.equal(r2.code, 0);
  assert.equal(JSON.parse(r2.stdout).prefix, OPERATOR_KEY.slice(0, 10));
  assert.equal(fake.state.keysCreated, before, "no new key when one is saved");
  assert.deepEqual(readKeys(home2), { [fake.state.url]: OPERATOR_KEY });
});

test("an unreadable key file is left untouched and no key is created", async () => {
  const home = tempHome();
  fs.writeFileSync(keyFileOf(home), "{ not json");
  const before = fake.state.keysCreated;
  const r = await run(["key", "--json"], { home, server: fake.state.url });
  assert.equal(r.code, 2);
  assert.equal(JSON.parse(r.stdout).error, "key_file_unreadable");
  assert.equal(fs.readFileSync(keyFileOf(home), "utf8"), "{ not json");
  assert.equal(fake.state.keysCreated, before);
});

test("a refused saved key (401) is reported and the key file is not changed", async () => {
  const home = tempHome();
  const saved = { [fake.state.url]: "jr_revoked", "https://render.janction.jp": OPERATOR_KEY };
  fs.writeFileSync(keyFileOf(home), JSON.stringify(saved));
  const r = await run(["status", "j_1", "--json"], { home, server: fake.state.url });
  assert.equal(r.code, 2);
  assert.equal(JSON.parse(r.stdout).http_status, 401);
  assert.match(r.stderr, /was not changed/);
  assert.deepEqual(readKeys(home), saved);
  assert.equal(fake.state.calls.filter((c) => c.path === "/v1/keys").length, 0);
});

test("try renders the sample preview and prints the image link", async () => {
  const home = tempHome();
  const r = await run(["try", "--json"], { home, server: fake.state.url });
  assert.equal(r.code, 0, r.stderr);
  const out = JSON.parse(r.stdout);
  assert.equal(out.images[0].view_url, `https://render.example/v/${out.job_id}/frame_0001.png?sig=1`);
  assert.equal(fs.readFileSync(path.join(home, out.files[0])).length, PNG.length);
  const fetched = fake.state.calls.find((c) => c.path === "/v1/files/url");
  assert.equal(fetched.json.url, "https://render.janction.jp/samples/cube_scene.py");
  const job = fake.state.calls.find((c) => c.path === "/v1/jobs");
  assert.deepEqual(job.json, { scene_id: "s_url", kind: "preview", frames: [1], environment: "compare" });
  assert.equal(job.headers["x-api-key"], FAKE_KEY);
  // the text output carries the link too
  const t = await run(["try"], { home, server: fake.state.url });
  assert.match(t.stdout, /image: https:\/\/render\.example\/v\//);
});

test("preview uploads a local file, waits, and downloads the frames under their names", async () => {
  const home = tempHome();
  const scene = path.join(home, "scene.py");
  fs.writeFileSync(scene, "import bpy\n");
  const outDir = path.join(home, "out");
  const r = await run(["preview", scene, "--frames", "1-24", "--out", outDir, "--max-yen", "5", "--json"],
    { home, server: fake.state.url });
  assert.equal(r.code, 0, r.stderr);
  const out = JSON.parse(r.stdout);
  assert.deepEqual(out.frames, [1, 9, 16, 24]);
  assert.deepEqual(fs.readFileSync(path.join(outDir, "frame_0001.png")), PNG);
  const up = fake.state.calls.find((c) => c.path === "/v1/files");
  assert.match(up.body.toString("latin1"), /name="file"; filename="scene.py"/);
  assert.ok(fake.state.calls.some((c) => c.path === "/v1/files/lookup" && c.query.startsWith("?sha256=")));
  const job = fake.state.calls.find((c) => c.path === "/v1/jobs").json;
  assert.equal(job.kind, "preview");
  assert.equal(job.width, 1280);
  assert.equal(job.samples, 16);
  assert.equal(job.max_yen, 5);
  // the artifact URL on the public host was rewritten onto the server in use, with the key
  const dl = fake.state.calls.find((c) => c.path.endsWith("/artifacts/frame_0001.png"));
  assert.equal(dl.headers["x-api-key"], FAKE_KEY);
});

test("final with a link, --frames, --preset and --max-yen sends the preset body with an idempotency key", async () => {
  const home = tempHome();
  const r = await run(["final", "https://github.com/acme/models/blob/main/chair.glb", "--frames", "1-24", "--preset", "turntable",
    "--max-yen", "50", "--json"], { home, server: fake.state.url });
  assert.equal(r.code, 0, r.stderr);
  const out = JSON.parse(r.stdout);
  assert.match(out.job_id, /^j_/);
  assert.match(out.idempotency_key, /^auto:\d+:[0-9a-f]{32}$/);
  const fetched = fake.state.calls.find((c) => c.path === "/v1/files/url");
  assert.equal(fetched.json.url, "https://raw.githubusercontent.com/acme/models/main/chair.glb");
  const job = fake.state.calls.find((c) => c.path === "/v1/jobs").json;
  assert.equal(job.preset, "turntable");
  assert.equal(job.frame_start, 1);
  assert.equal(job.frame_end, 24);
  assert.equal(job.max_yen, 50);
  assert.equal(job.idempotency_key, out.idempotency_key);
  assert.ok(!("width" in job) && !("samples" in job) && !("output" in job), "tool defaults give way to the preset");
  // the same command again gives the same idempotency key (the server returns the first job)
  const r2 = await run(["final", "https://github.com/acme/models/blob/main/chair.glb", "--frames", "1-24", "--preset", "turntable",
    "--max-yen", "50", "--json"], { home, server: fake.state.url });
  if (JSON.parse(r2.stdout).idempotency_key.split(":")[1] === out.idempotency_key.split(":")[1]) {
    assert.equal(JSON.parse(r2.stdout).idempotency_key, out.idempotency_key);
  }
});

test("final needs --frames unless a preset is given", async () => {
  const home = tempHome();
  const r = await run(["final", "https://example.com/a.blend", "--json"], { home, server: fake.state.url });
  assert.equal(r.code, 2);
  assert.equal(JSON.parse(r.stdout).error, "usage");
  assert.equal(fake.state.calls.length, 0, "nothing was sent");
  const p = await run(["final", "https://example.com/a.glb", "--preset", "product", "--json"], { home, server: fake.state.url });
  assert.equal(p.code, 0, p.stderr);
  const job = fake.state.calls.find((c) => c.path === "/v1/jobs").json;
  assert.equal(job.preset, "product");
  assert.ok(!("frame_end" in job));
});

test("final --wait downloads the video and frames; status and download work on the job id", async () => {
  const home = tempHome();
  const r = await run(["final", "https://example.com/a.blend", "--frames", "1-2", "--wait", "--out", "o", "--json"],
    { home, server: fake.state.url });
  assert.equal(r.code, 0, r.stderr);
  const out = JSON.parse(r.stdout);
  assert.equal(out.files.length, 2);
  assert.equal(fs.readFileSync(path.join(home, "o", "output.mp4"), "utf8"), "mp4!!");

  const s = await run(["status", out.job_id, "--json"], { home, server: fake.state.url });
  assert.equal(s.code, 0);
  assert.equal(JSON.parse(s.stdout).status, "done");
  const st = await run(["status", out.job_id], { home, server: fake.state.url });
  assert.match(st.stdout, /: done/);
  assert.match(st.stdout, /output\.mp4: https:\/\/render\.example/);

  const d = await run(["download", out.job_id, "--out", "dl", "--only", "mp4", "--json"], { home, server: fake.state.url });
  assert.equal(d.code, 0, d.stderr);
  const got = JSON.parse(d.stdout);
  assert.equal(got.files.length, 1);
  assert.equal(path.basename(got.files[0]), "output.mp4");
});

test("402 prints the checkout link and exits 3; 429 quota exits 4", async () => {
  const home = tempHome();
  const r = await run(["final", "https://example.com/payme.blend", "--frames", "1-10", "--json"], { home, server: fake.state.url });
  assert.equal(r.code, 3);
  const pay = JSON.parse(r.stdout);
  assert.equal(pay.payment_required, true);
  assert.equal(pay.checkout_url, "https://checkout.example/pay/1");
  assert.match(r.stderr, /checkout\.example\/pay\/1/);
  const q = await run(["preview", "https://example.com/quota.blend", "--json"], { home, server: fake.state.url });
  assert.equal(q.code, 4);
  assert.equal(JSON.parse(q.stdout).error, "quota_exceeded");
});

test("a large local scene goes in parts (tus) and a glTF sends the files it refers to", async () => {
  const home = tempHome();
  const big = path.join(home, "big.glb");
  fs.writeFileSync(big, Buffer.alloc(1536 * 1024, 7));
  const r = await run(["preview", big, "--json"], { home, server: fake.state.url, env: { JANCTION_RENDER_MAX_UPLOAD_MB: "1" } });
  assert.equal(r.code, 0, r.stderr);
  const patches = fake.state.calls.filter((c) => c.method === "PATCH");
  assert.equal(patches.length, 3, "1.5 MiB in parts of 512 KiB");
  assert.match(patches[0].headers["upload-checksum"], /^sha256 /);
  assert.equal(fake.state.calls.find((c) => c.path === "/v1/jobs").json.scene_id, "s_big");

  const gltf = path.join(home, "model.gltf");
  fs.writeFileSync(gltf, JSON.stringify({ buffers: [{ uri: "model.bin" }], images: [{ uri: "tex/a.png" }, { uri: "../escape.png" }] }));
  fs.writeFileSync(path.join(home, "model.bin"), "bin");
  fs.mkdirSync(path.join(home, "tex"));
  fs.writeFileSync(path.join(home, "tex", "a.png"), PNG);
  const g = await run(["preview", gltf, "--json"], { home, server: fake.state.url });
  assert.equal(g.code, 0, g.stderr);
  const assets = fake.state.calls.find((c) => /\/assets$/.test(c.path)).body.toString("latin1");
  assert.match(assets, /filename="model.bin"/);
  assert.match(assets, /filename="tex\/a.png"/);
  assert.ok(!assets.includes("escape.png"), "references outside the folder are not sent");
});

test("--key and JANCTION_RENDER_API_KEY are used for the run and never saved", async () => {
  const home = tempHome();
  await run(["status", "j_1", "--key", OPERATOR_KEY, "--json"], { home, server: fake.state.url });
  assert.equal(fake.state.calls[0].headers["x-api-key"], OPERATOR_KEY);
  assert.ok(!fs.existsSync(keyFileOf(home)));
  const k = await run(["key", "--json"], { home, server: fake.state.url, env: { JANCTION_RENDER_API_KEY: OPERATOR_KEY } });
  assert.equal(JSON.parse(k.stdout).source, "JANCTION_RENDER_API_KEY");
  assert.ok(!fs.existsSync(keyFileOf(home)));
});

test("unknown options are refused before any request", async () => {
  const home = tempHome();
  const r = await run(["preview", "x.blend", "--bogus", "1"], { home, server: fake.state.url });
  assert.equal(r.code, 2);
  assert.match(r.stderr, /unknown option --bogus/);
  assert.equal(fake.state.calls.length, 0);
});

// 11/10 audit: the key goes only to the server this CLI talks to, also across redirects and for artifact links elsewhere

function keyEcho() {
  const seen = [];
  const server = http.createServer((req, res) => {
    seen.push({ path: req.url, key: req.headers["x-api-key"] || null });
    const to = req.url.startsWith("/go-away") ? req.headers["x-target"] : null;
    if (req.url.startsWith("/hop-home")) { res.writeHead(302, { Location: "/v1/landed" }); return res.end(); }
    if (req.url.startsWith("/to-file")) { res.writeHead(302, { Location: "file:///etc/passwd" }); return res.end(); }
    if (to) { res.writeHead(302, { Location: to }); return res.end(); }
    res.writeHead(200, { "Content-Type": "application/octet-stream" });
    return res.end("ok");
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ server, seen, url: `http://127.0.0.1:${server.address().port}` })));
}

test("the key is sent only to the server's own origin, also after a redirect", async () => {
  const { Client, ClientError } = require("../lib/cli");
  const home = await keyEcho();
  const away = await keyEcho();
  try {
    const c = new Client({ server: home.url, key: FAKE_KEY });
    const h = await c.headers();
    await c.fetch("GET", `${away.url}/v1/jobs/j_1/artifacts/a.png`, { headers: h });
    assert.equal(away.seen[0].key, null);
    await c.fetch("GET", `${home.url}/go-away`, { headers: { ...h, "x-target": `${away.url}/stolen` } });
    assert.equal(home.seen[0].key, FAKE_KEY);
    assert.deepEqual(away.seen[1], { path: "/stolen", key: null });
    const r = await c.fetch("GET", `${home.url}/hop-home`, { headers: h });
    assert.equal(r.status, 200);
    assert.deepEqual(home.seen.slice(-1)[0], { path: "/v1/landed", key: FAKE_KEY });
    await assert.rejects(c.fetch("GET", `${home.url}/to-file`, { headers: h }), (e) => e instanceof ClientError && e.error === "bad_redirect");
    // an artifact link on another host is downloaded without the key
    const dir = tempHome();
    await c.downloadFile(`${away.url}/dl/x.png`, path.join(dir, "x.png"));
    assert.equal(fs.readFileSync(path.join(dir, "x.png"), "utf8"), "ok");
    assert.deepEqual(away.seen.slice(-1)[0], { path: "/dl/x.png", key: null });
  } finally {
    await new Promise((r) => home.server.close(r));
    await new Promise((r) => away.server.close(r));
  }
});
