#!/usr/bin/env python3
"""JANCTION Render from the DeepSeek API: the remote MCP tools as DeepSeek function calls (2026-10-19, DS-003 / DS-004).

DeepSeek's chat API is OpenAI-compatible (https://api.deepseek.com, model deepseek-flash). It has no MCP client of its own,
so this script is the bridge: it asks the JANCTION Render MCP server for its tools (tools/list), hands them to DeepSeek as
`tools=[{"type": "function", ...}]`, and runs the tool loop (tools/call for every function the model picks). Nothing here is
specific to DeepSeek beyond the base URL and the model name; any OpenAI-compatible endpoint works the same way.

    pip install requests
    export DEEPSEEK_API_KEY=sk-...                 # https://platform.deepseek.com
    export JANCTION_RENDER_API_KEY=jr_...          # POST https://render.janction.jp/v1/keys (created for you if missing)
    python examples/deepseek_tool_calling.py --dry-run                       # the tools as DeepSeek will see them, no DeepSeek call
    python examples/deepseek_tool_calling.py "Preview https://render.janction.jp/samples/cube_scene.py and tell me what the critic said"
    python examples/deepseek_tool_calling.py --yes "Render a 24-frame turntable of ... as an MP4"   # skip the terminal confirmation

Money: render_final spends GPU time. The model is told to call render_estimate first and to show the price; this script also
stops before every render_final and asks on the terminal unless --yes is given. Unattended runs can pass --no-final to hide the
tool entirely. Keys never leave the two services; the script prints neither of them.

Env: DEEPSEEK_BASE_URL (default https://api.deepseek.com), DEEPSEEK_MODEL (default deepseek-flash),
JANCTION_RENDER_SERVER (default https://render.janction.jp), JANCTION_RENDER_SRC (ledger tag on the MCP URL, default deepseek-api).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("pip install requests")

MCP_PROTOCOL = "2025-06-18"
FUNCTION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")     # OpenAI-style function names; DeepSeek accepts the same form
PAID_TOOLS = ("render_final",)
SYSTEM = (
    "You can render Blender scenes on JANCTION Render's cloud GPUs through the tools. Order: scene_info or render_preview first "
    "(previews are free within the daily limit), look at the critic verdict and fix the scene, call render_estimate before any "
    "render_final, tell the user the price and the time estimate, and call render_final only after the user agreed. After "
    "render_final, poll with render_status / render_download until the links come back. Give the user every https link you get."
)


# ------------------------------------------------------------------ MCP (Streamable HTTP, stateless server)

class Mcp:
    def __init__(self, server: str, key: str, src: str = "") -> None:
        self.url = server.rstrip("/") + "/mcp" + (f"?src={src}" if src else "")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {key}", "Accept": "application/json, text/event-stream",
                               "Content-Type": "application/json", "MCP-Protocol-Version": MCP_PROTOCOL,
                               "User-Agent": "janction-render-deepseek-bridge/1.0"})
        self._id = 0

    def rpc(self, method: str, params: Optional[dict[str, Any]] = None, timeout: int = 120) -> dict[str, Any]:
        self._id += 1
        r = self.s.post(self.url, json={"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}, timeout=timeout)
        if r.status_code == 401:
            raise SystemExit("JANCTION Render replied 401: the key is missing, revoked or mistyped (JANCTION_RENDER_API_KEY).")
        r.raise_for_status()
        body = _decode(r)
        if "error" in body:
            raise RuntimeError(f"{method}: {body['error']}")
        return body["result"]

    def initialize(self) -> dict[str, Any]:
        return self.rpc("initialize", {"protocolVersion": MCP_PROTOCOL, "capabilities": {},
                                       "clientInfo": {"name": "deepseek-api-bridge", "version": "1.0"}})

    def tools(self) -> list[dict[str, Any]]:
        return list(self.rpc("tools/list").get("tools") or [])

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.rpc("tools/call", {"name": name, "arguments": arguments}, timeout=180)


def _decode(r: requests.Response) -> dict[str, Any]:
    """JSON, or the last JSON-RPC message of an SSE body (the server may answer either way)."""
    if "text/event-stream" not in (r.headers.get("content-type") or ""):
        return r.json()
    last: dict[str, Any] = {}
    for line in r.text.splitlines():
        if line.startswith("data:"):
            try:
                last = json.loads(line[5:].strip())
            except ValueError:
                continue
    return last


# ------------------------------------------------------------------ MCP tools -> DeepSeek / OpenAI functions

def to_functions(tools: list[dict[str, Any]], include_paid: bool = True) -> list[dict[str, Any]]:
    """MCP tool definitions as `tools` for chat/completions. The input schema is passed through unchanged (it is JSON Schema already);
    only the envelope differs. Tools whose names cannot be function names are skipped with a note on stderr."""
    out: list[dict[str, Any]] = []
    for t in tools:
        name = str(t.get("name") or "")
        if not FUNCTION_NAME_RE.match(name):
            print(f"skipping tool {name!r}: not a valid function name", file=sys.stderr)
            continue
        if not include_paid and name in PAID_TOOLS:
            continue
        schema = t.get("inputSchema") or {"type": "object", "properties": {}}
        if schema.get("type") != "object":
            schema = {"type": "object", "properties": {}, **{k: v for k, v in schema.items() if k != "type"}}
        out.append({"type": "function", "function": {"name": name, "description": str(t.get("description") or "")[:4096],
                                                     "parameters": schema}})
    return out


def result_text(result: dict[str, Any]) -> str:
    """What the model gets back: the text parts joined; images become a one-line note (the preview result also carries its https link)."""
    parts: list[str] = []
    for c in result.get("content") or []:
        if c.get("type") == "text":
            parts.append(c.get("text") or "")
        elif c.get("type") == "image":
            parts.append(f"[image {c.get('mimeType', 'image/png')} returned; see the https link in the text]")
        elif c.get("type") == "resource_link":
            parts.append(f"[link] {c.get('uri')}")
    if result.get("isError"):
        parts.insert(0, "[tool error]")
    return "\n".join(parts) or json.dumps(result)[:4000]


# ------------------------------------------------------------------ DeepSeek chat loop

def chat(base: str, key: str, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    r = requests.post(f"{base.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"model": model, "messages": messages, "tools": tools, "tool_choice": "auto"}, timeout=180)
    if r.status_code >= 400:
        raise SystemExit(f"DeepSeek {r.status_code}: {r.text[:400]}")
    return r.json()


def run(prompt: str, mcp: Mcp, ds_base: str, ds_key: str, model: str, yes: bool, no_final: bool, max_turns: int = 12) -> int:
    mcp.initialize()
    tools = to_functions(mcp.tools(), include_paid=not no_final)
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    usage_in = usage_out = 0
    for _ in range(max_turns):
        d = chat(ds_base, ds_key, model, messages, tools)
        u = d.get("usage") or {}
        usage_in += int(u.get("prompt_tokens") or 0)
        usage_out += int(u.get("completion_tokens") or 0)
        msg = (d.get("choices") or [{}])[0].get("message") or {}
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if msg.get("content"):
            print(msg["content"])
        if not calls:
            break
        for call in calls:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            print(f"-> {name}({json.dumps(args, ensure_ascii=False)[:300]})")
            if name in PAID_TOOLS and not yes:
                ans = input("render_final spends GPU time (see the estimate above). Proceed? [y/N] ").strip().lower()
                if ans not in ("y", "yes"):
                    messages.append({"role": "tool", "tool_call_id": call.get("id"),
                                     "content": "The user declined the paid render. Do not call render_final again unless asked."})
                    continue
            try:
                text = result_text(mcp.call(name, args))
            except Exception as exc:  # noqa: BLE001 — the model gets the error and can recover or explain
                text = f"[tool error] {exc}"
            print(text[:1200] + ("…" if len(text) > 1200 else ""))
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": text[:16000]})
    print(f"\n(DeepSeek tokens: {usage_in} in, {usage_out} out, model {model})")
    return 0


def ensure_key(server: str) -> str:
    key = os.environ.get("JANCTION_RENDER_API_KEY") or ""
    if key:
        return key
    r = requests.post(f"{server.rstrip('/')}/v1/keys", json={"label": "deepseek-api-bridge", "found_via": "deepseek"}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"could not create a JANCTION Render key ({r.status_code}): {r.text[:300]}")
    key = r.json()["api_key"]
    print("created a JANCTION Render key; export it so the next run reuses it:", file=sys.stderr)
    print(f"  export JANCTION_RENDER_API_KEY={key}", file=sys.stderr)
    return key


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("prompt", nargs="?", default="")
    ap.add_argument("--dry-run", action="store_true", help="list the tools as DeepSeek functions and exit (no DeepSeek call)")
    ap.add_argument("--yes", action="store_true", help="do not ask on the terminal before render_final")
    ap.add_argument("--no-final", action="store_true", help="hide render_final from the model (unattended, free-only runs)")
    ap.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL") or "deepseek-flash")
    a = ap.parse_args(argv)
    server = os.environ.get("JANCTION_RENDER_SERVER") or "https://render.janction.jp"
    mcp = Mcp(server, ensure_key(server), os.environ.get("JANCTION_RENDER_SRC", "deepseek-api"))
    if a.dry_run:
        mcp.initialize()
        fns = to_functions(mcp.tools(), include_paid=not a.no_final)
        for f in fns:
            p = f["function"]["parameters"]
            req = ", ".join(p.get("required") or [])
            print(f"{f['function']['name']:18} required: {req or '-'}  ({len(p.get('properties') or {})} params)")
        print(f"{len(fns)} tools -> tools=[...] for {a.model}; add DEEPSEEK_API_KEY and a prompt to run the loop")
        return 0
    if not a.prompt:
        ap.error("a prompt is required (or --dry-run)")
    ds_key = os.environ.get("DEEPSEEK_API_KEY") or ""
    if not ds_key:
        ap.error("DEEPSEEK_API_KEY is not set")
    return run(a.prompt, mcp, os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com", ds_key, a.model, a.yes, a.no_final)


if __name__ == "__main__":
    sys.exit(main())
