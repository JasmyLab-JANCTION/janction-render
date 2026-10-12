#!/usr/bin/env node
/*
 * janction-render (npm): connect an MCP client to JANCTION Render with one command.
 *
 *   npx -y janction-render                 OAuth: the first call opens a consent page that creates a free key
 *   npx -y janction-render --key jr_...    a key you already have (or JANCTION_RENDER_API_KEY in the environment)
 *   npx -y janction-render --local         the Python stdio server through uv (sends local files; needs uv)
 *
 * The remote bridge is mcp-remote (stdio <-> Streamable HTTP with OAuth). This launcher only fixes the URL,
 * tags the key with its source, keeps the key out of the process list and passes the rest of the arguments through.
 */
"use strict";

const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const PKG = require("../package.json");
const SITE = "https://render.janction.jp";
const DEFAULT_URL = `${SITE}/mcp?src=npm`;

function usage() {
  return [
    `janction-render ${PKG.version} (npm launcher for the JANCTION Render MCP server)`,
    "",
    "Usage: janction-render [--key jr_...] [--url https://render.janction.jp/mcp] [--local] [-- <mcp-remote args>]",
    "",
    "  (no options)      bridge stdio to the remote MCP server with OAuth; the first call opens a consent page",
    "                    that creates a free key (100 JPY of GPU time with no card, 400 JPY more after saving a card)",
    "  --key jr_...      use an API key instead of OAuth (also: JANCTION_RENDER_API_KEY in the environment)",
    "  --url <url>       another MCP endpoint (default: " + DEFAULT_URL + ")",
    "  --local           run the Python stdio server through uv (uvx janction-render); sends local .blend / 3D files",
    "  --help, --version",
    "",
    "Claude Desktop / Cursor / Windsurf (mcpServers): { \"janction-render\": { \"command\": \"npx\", \"args\": [\"-y\", \"janction-render\"] } }",
    "Claude Code: claude mcp add janction-render -- npx -y janction-render",
    "",
    `Docs: ${SITE}/llms.txt   Pricing: ${SITE}/pricing`,
  ].join("\n");
}

function parse(argv) {
  const out = { url: DEFAULT_URL, key: process.env.JANCTION_RENDER_API_KEY || "", local: false, rest: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--") {
      out.rest = argv.slice(i + 1);
      break;
    }
    if (a === "--help" || a === "-h") {
      out.help = true;
    } else if (a === "--version" || a === "-v") {
      out.version = true;
    } else if (a === "--local") {
      out.local = true;
    } else if (a === "--key") {
      out.key = argv[i + 1] || "";
      i += 1;
    } else if (a.startsWith("--key=")) {
      out.key = a.slice("--key=".length);
    } else if (a === "--url") {
      out.url = argv[i + 1] || "";
      i += 1;
    } else if (a.startsWith("--url=")) {
      out.url = a.slice("--url=".length);
    } else {
      out.rest.push(a);
    }
  }
  return out;
}

function fail(msg, code = 2) {
  process.stderr.write(`janction-render: ${msg}\n`);
  process.exit(code);
}

function runLocal(opts) {
  // The Python stdio server: local files, results saved under ~/janction-render/<job_id>. Needs uv (https://docs.astral.sh/uv/).
  const which = spawnSync(process.platform === "win32" ? "where" : "which", ["uvx"], { stdio: "ignore" });
  if (which.status !== 0) {
    fail("--local needs uv (uvx). Install it from https://docs.astral.sh/uv/ or run without --local to use the remote server.", 3);
  }
  const env = { ...process.env, JANCTION_RENDER_SERVER: process.env.JANCTION_RENDER_SERVER || SITE };
  if (opts.key) env.JANCTION_RENDER_API_KEY = opts.key;
  const child = spawn("uvx", ["--from", "janction-render", "janction-render-mcp", ...opts.rest],
    { stdio: "inherit", env, shell: process.platform === "win32" });
  forward(child);
}

function mcpRemoteBin() {
  const pkgPath = require.resolve("mcp-remote/package.json");
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
  const bin = typeof pkg.bin === "string" ? pkg.bin : (pkg.bin && pkg.bin["mcp-remote"]);
  if (!bin) fail("mcp-remote is installed but has no mcp-remote bin entry", 4);
  return path.join(path.dirname(pkgPath), bin);
}

function runRemote(opts) {
  let url;
  try {
    url = new URL(opts.url);
  } catch (e) {
    fail(`--url is not a URL: ${opts.url}`);
  }
  if (url.protocol !== "https:" && !opts.rest.includes("--allow-http")) {
    fail("--url must be https (pass --allow-http after -- for a trusted private network)");
  }
  const args = [url.toString()];
  const cleanup = [];
  if (opts.key) {
    if (!/^jr_[0-9a-f]{32}$/.test(opts.key)) fail("the key should look like jr_ followed by 32 hex characters");
    // mcp-remote reads headers from a file, so the key never appears in the process list
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "janction-render-"));
    const file = path.join(dir, "headers.txt");
    fs.writeFileSync(file, `Authorization: Bearer ${opts.key}\n`, { mode: 0o600 });
    cleanup.push(() => { try { fs.rmSync(dir, { recursive: true, force: true }); } catch (e) { /* ignore */ } });
    args.push("--header-file", file);
  }
  if (!opts.rest.includes("--transport")) args.push("--transport", "http-first");
  args.push(...opts.rest);
  const child = spawn(process.execPath, [mcpRemoteBin(), ...args], { stdio: "inherit", env: process.env });
  forward(child, cleanup);
}

function forward(child, cleanup = []) {
  const done = (code, signal) => {
    cleanup.forEach((f) => f());
    if (signal) process.kill(process.pid, signal);
    process.exit(code == null ? 1 : code);
  };
  child.on("exit", done);
  child.on("error", (err) => {
    cleanup.forEach((f) => f());
    fail(`could not start: ${err.message}`, 4);
  });
  for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
    process.on(sig, () => { try { child.kill(sig); } catch (e) { /* ignore */ } });
  }
}

function main() {
  const opts = parse(process.argv.slice(2));
  if (opts.help) {
    process.stdout.write(usage() + "\n");
    return;
  }
  if (opts.version) {
    process.stdout.write(`${PKG.version}\n`);
    return;
  }
  if (opts.local) return runLocal(opts);
  return runRemote(opts);
}

main();
