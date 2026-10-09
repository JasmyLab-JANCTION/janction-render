# JANCTION Render

[![JasmyLab-JANCTION/janction-render MCP server](https://glama.ai/mcp/servers/JasmyLab-JANCTION/janction-render/badges/score.svg)](https://glama.ai/mcp/servers/JasmyLab-JANCTION/janction-render)

## What is JANCTION Render?

JANCTION Render is a cloud GPU render farm for Blender that AI agents call as an MCP server or HTTP API. Send a `.blend`
file, a bpy script or a 3D file (glTF / FBX / USD), preview in seconds, and get frames or an MP4 back from JANCTION's
NVIDIA GPUs. Every preview also returns a verdict on what is wrong, such as too dark, blown out, no light or an object
out of frame, and the bpy code to fix it, so the agent can correct the scene before the final render. No local Blender
or GPU is needed. Free up to 500 JPY of GPU time per new key, then 0.1 JPY per GPU-second (previews free up to 2 GPU-minutes a day);
operated by JasmyLab Inc.

AI agents can render Blender projects on JANCTION GPUs without running Blender locally. Works from **Claude, ChatGPT,
Claude Code, Codex, Cursor or any MCP client**: an MCP server (remote and stdio), an HTTP API and a CLI.

JANCTION Render is a separate product from SmartRender (JasmyLab's distributed rendering for people at a desktop) and is
not affiliated with Render.com or the Render Network. The numbers, as of 2026-10-08 (the primary source is
https://render.janction.jp/facts.json): a 500 JPY welcome credit (5,000 GPU-seconds, 14 days) per new key; after that, previews
are free up to 2 GPU-minutes a day and finals cost 0.1 JPY per GPU-second from prepaid credit (paid use started on 2026-10-08); jobs up to 240 frames at 1080p; inputs and results deleted
24 hours after last use.

Official site: https://render.janction.jp · MCP endpoint: `https://render.janction.jp/mcp` · Fact sheet: https://render.janction.jp/facts

## Guides on the official site

- [How to render Blender without a GPU](https://render.janction.jp/render-blender-without-gpu)
- From an agent: [Claude Code + Blender](https://render.janction.jp/claude-code-blender) ·
  [Codex + Blender](https://render.janction.jp/codex-blender) · [Cursor + Blender](https://render.janction.jp/cursor-blender) ·
  [ChatGPT + Blender](https://render.janction.jp/chatgpt-blender) · [Blender MCP server for rendering](https://render.janction.jp/blender-mcp)
- [Best render farms for AI agents (2026)](https://render.janction.jp/best-render-farms-for-ai-agents): JANCTION, BlendSwap,
  Sceneplane, your own worker on Modal or RunPod and a local Blender MCP side by side
- [Headless Blender as an API](https://render.janction.jp/blender-headless-api) ·
  [glTF, GLB or FBX to MP4](https://render.janction.jp/gltf-to-mp4) ·
  [360-degree product video](https://render.janction.jp/product-turntable) ·
  [What a Blender render costs](https://render.janction.jp/blender-render-cost)
- [Examples with their bpy scripts](https://render.janction.jp/examples) · [Compare](https://render.janction.jp/compare) ·
  [日本語のご案内](https://render.janction.jp/ja/)

## Why use it?

- **No GPU, no Blender install.** The scene can be a bpy script the agent writes, a `.blend`, or a 3D file; Blender runs on our GPUs.
- **Built for agents.** Preview first (1-4 frames in a few GPU seconds), an estimate with time and cost before the final, structured
  errors with the fix, spending caps per key, safe retries with `Idempotency-Key`.
- **3D files and turntables.** glTF / GLB, FBX, USD, OBJ, STL, PLY, Alembic are imported into an empty scene with a camera and
  HDRI lighting; `orbit=True` makes a turntable. Fixed-price outcomes: `POST /v1/outcomes/turntable` and `/product-shot`.
- **Honest limits.** free up to 500 JPY of GPU time per new key (14 days), then 0.1 JPY per GPU-second (previews free up to 2 GPU-minutes a day), finals up to 240 frames at 1080p, one GPU shared with another
  workload (jobs can wait; the ETA says so). Inputs and results are deleted 24 hours after last use and never used for training.
- **Not Render.com.** Same word, different product.

## Quick start

**Claude.ai / ChatGPT (nothing to install).** Settings → Connectors → add `https://render.janction.jp/mcp` → Connect (a free key
is created on the consent page). Then paste:

> Render a preview of https://render.janction.jp/samples/cube_scene.py

A 4-frame preview comes back in a few seconds. A file on your computer: drop it at https://render.janction.jp/upload to get a
12-hour link, then "Render this file: <link>".

**Claude Code.**

```
claude mcp add --transport http janction-render https://render.janction.jp/mcp
```

Then `/mcp` to authenticate and ask: "Build a small street scene in Blender with a camera fly-through and render a preview with janction-render."

**HTTP (any language).**

```
curl -s -X POST https://render.janction.jp/v1/keys                                   # -> {"api_key": "jr_..."}  no sign-up
curl -s -X POST https://render.janction.jp/v1/files -H "X-API-Key: $KEY" -F "file=@scene.blend"   # -> {"scene_id": "f_..."}
curl -s -X POST https://render.janction.jp/v1/jobs -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"scene_id":"f_...","kind":"preview","frames":[1]}'                             # -> job_id; then GET /v1/jobs/{job_id}
```

## From your own agent or app

**Python** (`pip install janction-render`; the first call creates a free key and keeps it in `~/.janction-render.json`):

```python
from janction_render.client import Client

c = Client()                                   # or Client(api_key="jr_...")
scene = c.upload("scene.py")                   # a bpy script, a .blend, or a .glb / .fbx / .usd / .obj file
job = c.submit(scene["scene_id"], kind="final", frame_start=1, frame_end=48, output="mp4")
job = c.wait(job["job_id"], timeout=1800)
print(job["status"], c.download(job["job_id"], "out", only="mp4"))
```

Pay per use with prepaid credit; no subscription is needed (prices: https://render.janction.jp/pricing).
Instead of polling, pass `notify_url` (https) to `POST /v1/jobs` and get one JSON POST when the job finishes (`job.done` /
`job.failed`, with download links); an `Idempotency-Key` header makes retries safe. OpenAPI: https://render.janction.jp/openapi.json

**Agent frameworks** connect to the remote MCP server at `https://render.janction.jp/mcp` with the key as a bearer token
(`curl -s -X POST https://render.janction.jp/v1/keys` gives one, no sign-up).

OpenAI Agents SDK (keep the longer timeout: `render_preview` waits for the image, longer than the 5-second default):

```python
import asyncio
from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp

async def main():
    async with MCPServerStreamableHttp(name="janction-render", client_session_timeout_seconds=120,
                                       params={"url": "https://render.janction.jp/mcp",
                                               "headers": {"Authorization": "Bearer jr_..."}}) as render:
        agent = Agent(name="3D artist", instructions="Render Blender scenes with janction-render.", mcp_servers=[render])
        result = await Runner.run(agent, "Render a preview of https://render.janction.jp/samples/cube_scene.py")
        print(result.final_output)

asyncio.run(main())
```

LangChain (`pip install langchain-mcp-adapters`):

```python
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

async def main():
    client = MultiServerMCPClient({"janction-render": {"url": "https://render.janction.jp/mcp", "transport": "streamable_http",
                                                       "headers": {"Authorization": "Bearer jr_..."}}})
    tools = await client.get_tools()           # render_preview, render_final, render_status, render_download, ...
    print([t.name for t in tools])

asyncio.run(main())
```

## MCP

### Remote (Streamable HTTP, OAuth 2.1 with dynamic client registration; a raw key also works as `Authorization: Bearer jr_...`)

| client | how |
|---|---|
| Claude.ai (web, desktop, mobile) | Settings → Connectors → Add custom connector → paste the URL → Connect |
| ChatGPT | Settings → Connectors → Advanced → Developer mode → Create → paste the URL (OAuth) |
| Claude Code | `claude mcp add --transport http janction-render https://render.janction.jp/mcp`, then `/mcp` to authenticate |
| Codex | `codex mcp add janction-render --url https://render.janction.jp/mcp` |
| Gemini CLI / Antigravity CLI | `gemini extensions install https://github.com/JasmyLab-JANCTION/janction-render` (this repository carries `gemini-extension.json`) |
| Grok (grok.com) | Connectors → New Connector → Custom → paste the URL |
| Perplexity (Pro / Max / Enterprise), Le Chat (workspace admin) | Add a custom remote MCP connector with the URL |
| Cursor | `.cursor/mcp.json` (project) or `~/.cursor/mcp.json`: `{"mcpServers": {"janction-render": {"url": "https://render.janction.jp/mcp"}}}`, then sign in when Cursor asks (OAuth). One click: [install in Cursor](cursor://anysphere.cursor-deeplink/mcp/install?name=janction-render&config=eyJ1cmwiOiJodHRwczovL3JlbmRlci5qYW5jdGlvbi5qcC9tY3AifQ==) |
| VS Code (Copilot agent mode) | `.vscode/mcp.json`: `{"servers": {"janction-render": {"type": "http", "url": "https://render.janction.jp/mcp"}}}` or `code --add-mcp '{"name":"janction-render","type":"http","url":"https://render.janction.jp/mcp"}'`, then Start the server and sign in (OAuth) |
| Windsurf, Cline, Goose, other MCP clients | Streamable HTTP at the URL above (OAuth, or a Bearer API key header). Installer notes: [llms-install.md](https://github.com/JasmyLab-JANCTION/janction-render/blob/main/llms-install.md). Cursor project rule (when to use it, preview-first flow): [integrations/cursor](https://github.com/JasmyLab-JANCTION/janction-render/tree/main/integrations/cursor) |

Remote tools take `scene_script` (bpy code as text), `scene_url` (an https link to a `.blend`, `.py` or a 3D file, or a link
from https://render.janction.jp/upload) or `scene_id`, plus `asset_urls` for textures or glTF `.bin` files. Results come back as
an inline image plus download links that need no key and work for about 24 hours (`render_download(only="mp4")` for just the video).

Claude Code plugin (the remote connector plus a skill with the workflow):

```
/plugin marketplace add JasmyLab-JANCTION/janction-render
/plugin install janction-render@janction-render
```

### Stdio (sends local files)

The package is on PyPI as `janction-render`.

```
# Claude Code (uvx runs it without a global install)
claude mcp add janction-render -e JANCTION_RENDER_SERVER=https://render.janction.jp -- uvx --from janction-render janction-render-mcp

# or with pip / pipx
pip install janction-render
claude mcp add janction-render -e JANCTION_RENDER_SERVER=https://render.janction.jp -- janction-render-mcp
```

Codex: add to `~/.codex/config.toml`

```toml
[mcp_servers.janction-render]
command = "uvx"
args = ["--from", "janction-render", "janction-render-mcp"]
env = { JANCTION_RENDER_SERVER = "https://render.janction.jp" }
```

A temporary API key is issued automatically on first use and cached in `~/.janction-render.json`; set
`JANCTION_RENDER_API_KEY` to pin one (quota and, later, credit belong to the key). The same key can be used from the
remote connector: paste it on the connect page.

### Tools

| tool | what |
|---|---|
| `scene_info(scene_script | scene_url | scene_path | scene_id, assets?)` | cameras, frame range, fps, resolution, objects, lights, missing files. No render. |
| `render_preview(..., frames="1-24", environment?, blender?)` | up to 4 frames (720p budget) tiled with frame labels; returns the image inline |
| `render_review(scene_path / scene_script / scene_url / scene_id, environment="studio")` | checks a 3D model or a generated scene from 4 sides (0/90/180/270 degrees) under studio light: pass / warning / fail, a score, the checks it ran (files, visibility, framing, exposure, lighting) with fix code, and the 4 views in one image. Stdio server; same GPU time as one preview |
| `render_estimate(scene_id, frame_start, frame_end, width, height, samples)` | GPU seconds, queue wait, "about N minutes", fits the free GPU time left? No GPU time used |
| `render_final(scene_id, frame_start, frame_end, width, height, samples, fps, output, environment?, blender?, engine?, transparent?, notify_url?)` | frames (png / exr) or video (mp4 / webm / prores / gif / webp); `transparent=True` keeps an alpha background (png / exr / webm / gif / webp); `notify_url` gets one JSON POST when the job finishes; returns job_id + estimate |
| `render_status(job_id)` | progress and ETA (`eta.human`); `render_download(job_id, only="mp4" / "frames" / "all")` files or links; `render_cancel(job_id)` |
| `billing()` | the free GPU time left (the welcome credit, then the free preview minutes today), the credit, a top-up link, and the auto top-up and monthly plan status |
| `render_share(job_id, title?, note?, include_script?, listed?)` | a public page `/r/<id>` with the image or video, the conditions and (optionally) the script; survives the 24-hour expiry until `render_unshare`; with `listed=True` it appears in `/gallery` after a review |
| `asset_search(query, kind)` | CC0 models / textures / HDRIs on Poly Haven by words; results carry `polyhaven:<id>` and the entry file |
| `render_info()` | workers online or gated (GPU lent to another workload), queue, expected wait, supported inputs, environment presets, Blender versions |

Options on `render_preview` / `render_final`: `environment` (`studio`, `sunset`, `overcast`, `night`, `compare` on previews; `environment_strength`,
`environment_visible=False` for a flat grey backdrop with HDRI lighting), `orbit` / `orbit_frames` / `orbit_elevation` (turntable),
`blender` (`"5.2"`), and `assets` (stdio: local files sent with the scene, found in the script through `os.environ["JR_ASSETS_DIR"]`;
a `.blend`'s external files are collected automatically with `pip install janction-render[blend]`) or `asset_urls` (remote).

CLI: `janction-render inspect|preview|render|status|download|share|unshare|cancel|jobs|balance|topup|limits|outcomes|info`.

## API

```
POST /v1/keys                                   -> {api_key}         (header X-API-Key afterwards)
POST /v1/files  multipart "file" (.blend|.py|.glb|.fbx|.usd|.obj|...)   -> {scene_id}
POST /v1/files/{id}/assets  multipart "files"   textures, glTF .bin ...   GET /v1/files/lookup?sha256=  reuse an upload
POST /v1/estimate {kind, frames|frame_start/frame_end, width, height, samples, scene_id?} -> seconds, wall_seconds, human, quota, currency, expires_at
POST /v1/jobs   {scene_id, kind: info|preview|final, frames|frame_start/frame_end, width, height, samples, camera, fps, output (png|exr|mp4|webm|prores|gif|webp), transparent, notify_url (https), engine (cycles|eevee),
                 environment, environment_strength, environment_visible, blender, orbit, orbit_frames, orbit_elevation}   header Idempotency-Key makes retries safe
GET  /v1/jobs/{id}      status, progress, eta, artifacts[], cost, warnings, info, failure (code + fix)    DELETE /v1/jobs/{id}  cancel
GET  /v1/jobs/{id}/artifacts/{name}             PNG / MP4
GET  /v1/outcomes       fixed-price outcomes;  POST /v1/outcomes/turntable {scene_id, size, frames}   POST /v1/outcomes/product-shot {scene_id, size, transparent?}
POST /v1/try    JSON {scene_script | scene_url, frames?, width?, height?, environment?} (no key) -> first 720p preview + an API key to continue, in one response (1 per network per 24h)
POST /v1/drops  multipart "file" (no key)       -> a 12-hour https link to pass as scene_url (the /upload page uses this)
POST /v1/jobs/{id}/share {title?, note?, include_script?, listed?} -> {share_id, url}   DELETE /v1/jobs/{id}/share   GET /v1/shares
GET  /r/{share_id}  public page (no key)   GET /gallery
GET  /v1/assets/search?q=&kind=models|textures|hdris   CC0 assets (Poly Haven) -> spec polyhaven:<id>
POST /v1/files/{id}/assets/urls {urls: ["https://...", "polyhaven:<id>"]}   fetch assets server-side
GET  /v1/me  (quota, balance, limits)   POST /v1/me/limits {job_yen?, day_yen?}   spending caps per key
POST /mcp                                       remote MCP (Streamable HTTP; Bearer api key or OAuth)
GET  /.well-known/oauth-protected-resource/mcp  OAuth discovery
POST /v1/billing/checkout {amount_yen} -> {checkout_url}   POST /v1/billing/sync   GET /v1/ledger
GET  /openapi.json  /llms.txt  /llms-full.txt  /ja/llms.txt  /facts.json  /version.json  /capabilities.json  /pricing.json  /status.json
```

A job that goes past the free GPU time without enough credit gets `402 payment_required` with `checkout_url` (show it to the
user), `topup_yen` and how much of the job the free time covers; a `400 beta_limit` means the job is too big (split it). Every API
error carries `retryable`, `possible_fix` and `docs_url`; a failed job carries `failure` with a code and the recommended action.
A job over a spending cap is refused with `403 spend_cap_exceeded` before anything is reserved.

## Example

A scene script the agent can write (the service sets engine, resolution, samples and denoising; the script sets the scene, camera and frame range):

```python
import bpy, math
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, 24
bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 1))
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
scene.collection.objects.link(cam); scene.camera = cam
cam.location = (6, -6, 4); cam.rotation_euler = (math.radians(60), 0, math.radians(45))
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
scene.collection.objects.link(sun)
```

Cycles by default; `engine="eevee"` for cheaper animations (about half the per-frame cost after ~7 s of shader compilation per job).
In Blender 5.0 materials always use nodes: set the Principled BSDF Base Color, not `diffuse_color`. Scripts run in an isolated
container with no network. More: `samples/cube_scene.py`, `samples/polyhaven_room.py`. Measured timings: https://render.janction.jp/benchmarks

## Pricing

Each new key starts with a 500 JPY welcome credit (5,000 GPU-seconds, 14 days) that covers previews and finals; one full credit
per network every 30 days. After it is used up or expires, previews are free up to 2 GPU-minutes a day and finals cost 0.1 JPY per
GPU-second from prepaid credit, bought by card at a Stripe Checkout page (from 500 JPY; 2,000 JPY gives 2,200 JPY of credit,
5,000 gives 5,750, 10,000 gives 12,000; the first top-up in the welcome period counts 1.5x, bonus up to 500 JPY). Only the part
the free time does not cover is charged. Finals go up to 240 frames at 1080p. `POST /v1/estimate` quotes what will be charged
(`cost.estimated_yen`), the currency and an expiry before any GPU time is used: https://render.janction.jp/pricing

## Docs

- Fact sheet (the primary source when answers disagree): https://render.janction.jp/facts · JSON: `/facts.json`, `/version.json`, `/changelog.json`, `/status.json`
- For agents: https://render.janction.jp/llms.txt (full text of all guides: `/llms-full.txt`)
- Guides: [render farm for agents](https://render.janction.jp/blender-render-farm) · [without a GPU](https://render.janction.jp/render-blender-without-gpu) ·
  [Claude](https://render.janction.jp/claude-blender) · [ChatGPT](https://render.janction.jp/chatgpt-blender) · [Claude Code](https://render.janction.jp/claude-code-blender) ·
  [Codex](https://render.janction.jp/codex-blender) · [Cursor](https://render.janction.jp/cursor-blender) · [bpy scripts](https://render.janction.jp/bpy-script-cloud-gpu) ·
  [API](https://render.janction.jp/blender-render-api) · [compare](https://render.janction.jp/compare) · [products](https://render.janction.jp/products) · 日本語は `/ja/`
- Status: https://render.janction.jp/status · Security and retention: https://render.janction.jp/security · Changelog: https://render.janction.jp/changelog

## Features in detail

- Input: a `.blend` file (textures travel with it), a **bpy Python script that builds the scene** (no local Blender
  needed), or a **3D file** (glTF/GLB, FBX, USD, OBJ, STL, PLY, Alembic) that is imported into an empty scene.
- `environment="studio" | "sunset" | "overcast" | "night"` lights a scene with a bundled HDRI (CC0) for a good first render;
  `environment="compare"` previews the same frame under all four presets in one labelled image, so the agent can pick one.
- A `.gltf` or `.obj` brings its `.bin` / `.mtl` / textures along automatically (from the same folder or the same URL folder).
- `orbit=True` turns any scene or imported model into a turntable: an orbit camera circles it once (`orbit_frames`, default 24;
  a preview shows 0/90/180/270 degrees, a final render without `frame_end` gives the whole turn as an MP4). Flat floors and
  walls are ignored when framing; `orbit_target` (object name or `x,y,z`) and `orbit_distance` (multiplier) adjust the shot.
- While the GPU is lent to another workload, tools answer right away with the queued job and a wait estimate (how long it
  has been out, how long it usually stays out, how much longer to expect; `eta.gate`) instead of waiting.
- While a job renders, `render_status` counts finished frames inside the running chunk, so the ETA updates every few seconds.
- In hosts that support MCP Apps (Claude web and desktop, among others), previews, progress and download links also appear
  as an interactive panel in the chat: the image, a progress bar, "Open MP4", and preset buttons after an `environment="compare"` preview.
  Both the remote connector and the stdio package ship the panel (`janction_render/mcp_app.html`); set `JR_MCP_APPS=0` to turn it off.
- CC0 assets by name: `asset_search("wooden table")` finds Poly Haven models, textures and HDRIs; pass `polyhaven:<id>` in
  `asset_urls` (remote) or `assets` (stdio) and the files land in `JR_ASSETS_DIR/<id>/` on the GPU, ready to import
  (`bpy.ops.import_scene.gltf(filepath=os.path.join(os.environ['JR_ASSETS_DIR'], 'wooden_table_02', 'wooden_table_02_1k.gltf'))`).
  Scene scripts can `import jr_assets` for one-liners: `jr_assets.import_model('wooden_table_02')`,
  `jr_assets.apply(floor, jr_assets.material('wood_floor_deck', scale=2))` (diff / normal / roughness / metal wired into a
  Principled BSDF), `jr_assets.world_hdri('studio_small_09')`. See `samples/polyhaven_room.py`.
- A render you choose to share (`render_share`) gets a public page (`/r/<id>`, OGP for X and Discord) that stays until you unshare it.
- Blender 5.0, Cycles on GPU (`blender="5.2"` selects Blender 5.2 when the worker has it; `render_info` lists what is available).

## Blender add-on and DCC tools (for people, not agents)

- **Blender extension** (`addons/blender/`, Blender 4.2+): a JANCTION Render panel under Properties → Render with Preview,
  Estimate and Final. A copy of the open file and the textures it references with relative paths are uploaded; results land
  next to the .blend. Install from the extension repository `https://render.janction.jp/extensions/index.json`
  (Preferences → Get Extensions → Repositories → + → Add Remote Repository), or install the zip from
  `https://render.janction.jp/extensions/janction_render-0.1.2.zip` (`python scripts/build_blender_addon.py` builds it
  from this repository). Guide: https://render.janction.jp/blender-addon
- **Maya, Houdini, Cinema 4D** (`integrations/`): export to USD / FBX / Alembic, upload with textures, render with Cycles,
  open the result; Preview, Final (MP4) and Turntable. Standard-library Python only; `jr_submit.py` is the shared client.
  Guide: https://render.janction.jp/maya-houdini-cinema4d

## Self-hosting

The server (FastAPI + SQLite, with the remote MCP endpoint) and the worker (Blender in disposable Docker containers,
`--network none --cap-drop ALL`) live in the internal repository and are not part of this package yet. This repository
holds the client side: stdio MCP server, CLI, HTTP client, samples, the Claude Code plugin, the Blender add-on and the
DCC tools.

## MCP registry

This server is listed in the official MCP registry as `io.github.JasmyLab-JANCTION/janction-render` (remote: `https://render.janction.jp/mcp`).

mcp-name: io.github.JasmyLab-JANCTION/janction-render

## Security

Vulnerability reports: see [SECURITY.md](https://github.com/JasmyLab-JANCTION/janction-render/blob/main/SECURITY.md). Retention, isolation and the external tests are summarised on the [security page](https://render.janction.jp/security).

## License

MIT (see LICENSE) for the package, the MCP servers, the CLI and the DCC tools. The Blender extension under
`addons/blender/` is GPL-3.0-or-later, as Blender requires for add-ons. Operated by JasmyLab Inc.
