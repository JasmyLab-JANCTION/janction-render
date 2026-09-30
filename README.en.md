# JANCTION Render

[![JasmyLab-JANCTION/janction-render MCP server](https://glama.ai/mcp/servers/JasmyLab-JANCTION/janction-render/badges/score.svg)](https://glama.ai/mcp/servers/JasmyLab-JANCTION/janction-render)

A cloud GPU render farm for Blender, built for AI agents. Render Blender scenes on JANCTION GPUs from **Claude, ChatGPT,
Claude Code, Codex, Cursor or any MCP client**: an MCP server (remote and stdio) plus a CLI. Use it to render Blender
without a GPU, or when rendering locally is slow.

- Input: a `.blend` file, or a **bpy Python script that builds the scene** (no local Blender needed).
- `scene_info` reads the scene without rendering (cameras, frame range, missing files).
- `render_preview` returns 1-4 low-cost frames tiled in one image within seconds, so the agent can look, fix, and repeat.
- `render_estimate` says how long a render will take ("about 3 minutes") and whether it fits today's free quota.
- `render_final` renders the frames on GPUs and joins them into an MP4; `render_status` reports the remaining time.
- Free beta: no charges. Each key gets 10 GPU-minutes per day; a final render is up to 240 frames at 1080p.
  Paid plans (per GPU second, prepaid credit) will be announced on the service page before they start.
- Inputs and results are deleted 24 hours after last use and are never used for training.

## Status

Free beta. Service page: `https://render.janction.jp` (`/v1/health`, `/llms.txt`). Blender 5.0, Cycles on GPU.

## Connect (remote MCP, nothing to install)

MCP server URL: **`https://render.janction.jp/mcp`** (Streamable HTTP). Auth is OAuth 2.1 with dynamic client
registration: pressing "Connect" opens a page that creates a free API key (or takes one you already have). A raw API key
also works as `Authorization: Bearer jr_...`.

| client | how |
|---|---|
| Claude.ai (web, desktop, mobile) | Settings → Connectors → Add custom connector → paste the URL → Connect |
| ChatGPT | Settings → Connectors → Advanced → Developer mode → Create → paste the URL (OAuth) |
| Claude Code | `claude mcp add --transport http janction-render https://render.janction.jp/mcp`, then `/mcp` to authenticate |
| Cursor, Windsurf, other MCP clients | Streamable HTTP at the URL above (OAuth, or a Bearer API key header) |

Remote tools take `scene_script` (bpy code as text), `scene_url` (an https link to a `.blend` or `.py`) or `scene_id`;
results come back as an inline image plus download links that need no key and work for about 24 hours.

Claude Code plugin (the remote connector plus a skill with the workflow):

```
/plugin marketplace add JasmyLab-JANCTION/janction-render
/plugin install janction-render@janction-render
```

## Install (stdio MCP, sends local files)

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

Then, in Claude Code:

> Build a small street scene in Blender with a camera fly-through and render a preview with janction-render.

## Tools

| tool | what |
|---|---|
| `scene_info(scene_script | scene_url | scene_path | scene_id)` | cameras, frame range, fps, resolution, objects, lights, missing files. No render. |
| `render_preview(..., frames="1-24")` | up to 4 frames (720p budget) tiled with frame labels; returns the image inline |
| `render_estimate(scene_id, frame_start, frame_end, width, height, samples)` | GPU seconds, queue wait, "about N minutes", fits today's free quota? No GPU time used |
| `render_final(scene_id, frame_start, frame_end, width, height, samples, fps, output)` | PNG or MP4; returns job_id + estimate |
| `render_status(job_id)` | progress and ETA (`eta.human`); `render_download(job_id)` files or links; `render_cancel(job_id)` |
| `billing()` | free-beta quota (used today, daily limit, reset time); later balance and top-up link |
| `render_info()` | workers online, queue and expected wait |

CLI: `janction-render inspect|preview|render|status|download|cancel|jobs|balance|topup|info`.

## Writing a scene script

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

The service sets engine (Cycles), resolution, samples and denoising; your script sets the scene, camera and frame range.
Scripts run in an isolated container with no network. See `samples/cube_scene.py`.

## HTTP API

```
POST /v1/keys                                   -> {api_key}         (header X-API-Key afterwards)
POST /v1/files  multipart "file" (.blend|.py)   -> {scene_id}
POST /v1/estimate {kind, frames|frame_start/frame_end, width, height, samples, scene_id?} -> seconds, wall_seconds, human, quota
POST /v1/jobs   {scene_id, kind: info|preview|final, frames|frame_start/frame_end, width, height, samples, camera, fps, output}
GET  /v1/jobs/{id}      status, progress, eta, artifacts[], cost, warnings, info    DELETE /v1/jobs/{id}  cancel
GET  /v1/jobs/{id}/artifacts/{name}             PNG / MP4
POST /mcp                                       remote MCP (Streamable HTTP; Bearer api key or OAuth)
GET  /.well-known/oauth-protected-resource/mcp  OAuth discovery
POST /v1/billing/checkout {amount_yen} -> {checkout_url}   POST /v1/billing/sync   GET /v1/ledger   GET /v1/me
GET  /llms.txt  /terms  /privacy  /legal  /security
```

During the free beta a `429 quota_exceeded` response carries `resets_at`; a `400 beta_limit` means the job is too big
(split it). Once paid plans start, a `402 payment_required` response carries `checkout_url`.

## Self-hosting

The server (FastAPI + SQLite, with the remote MCP endpoint) and the worker (Blender in disposable Docker containers,
`--network none --cap-drop ALL`) live in the internal repository and are not part of this package yet. This repository
holds the client side: stdio MCP server, CLI, HTTP client, samples and the Claude Code plugin.

## MCP registry

This server is listed in the official MCP registry as `io.github.JasmyLab-JANCTION/janction-render` (remote: `https://render.janction.jp/mcp`).

mcp-name: io.github.JasmyLab-JANCTION/janction-render

## License

MIT (see LICENSE). Operated by JasmyLab Inc.
