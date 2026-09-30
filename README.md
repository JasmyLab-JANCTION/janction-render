# JANCTION Render

Render Blender scenes on JANCTION GPUs straight from a terminal AI agent (Claude Code, Codex, or any MCP client).
Use it when you are building 3DCG with Blender and have no GPU, or rendering locally is slow.

- Input: a `.blend` file, or a **bpy Python script that builds the scene** (no local Blender needed).
- `scene_info` reads the scene without rendering (cameras, frame range, missing files).
- `render_preview` returns 1-4 low-cost frames tiled in one image within seconds, so the agent can look, fix, and repeat.
- `render_final` renders the frames on GPUs and joins them into an MP4.
- Free beta: no charges. Each key gets 10 GPU-minutes per day; a final render is up to 240 frames at 1080p.
  Paid plans (per GPU second, prepaid credit) will be announced on the service page before they start.
- Inputs and results are deleted 24 hours after last use and are never used for training.

## Status

Free beta. The public endpoint is `https://render.janction.jp` (`/v1/health`, `/llms.txt`). Quotas and limits are on the
service page; paid plans will be announced there before they start.

## Install

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
`JANCTION_RENDER_API_KEY` to pin one (quota and, later, credit belong to the key).

Then, in Claude Code:

> Build a small street scene in Blender with a camera fly-through and render a preview with janction-render.

## Tools

| tool | what |
|---|---|
| `scene_info(scene_path | scene_script | scene_id)` | cameras, frame range, fps, resolution, objects, lights, missing files. No render. |
| `render_preview(..., frames="1-24")` | up to 4 frames (720p budget) tiled with frame labels; returns the image inline |
| `render_final(scene_id, frame_start, frame_end, width, height, samples, fps, output)` | PNG or MP4; returns job_id + estimate |
| `render_status(job_id)` / `render_download(job_id)` / `render_cancel(job_id)` | progress, files, cancel |
| `billing(topup_yen=0)` | free-beta quota (used today, daily limit, reset time); later balance and top-up link |
| `render_info()` | server, workers online, queue |

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
POST /v1/jobs   {scene_id, kind: info|preview|final, frames|frame_start/frame_end, width, height, samples, camera, fps, output}
GET  /v1/jobs/{id}      status, progress, artifacts[], cost, warnings, info      DELETE /v1/jobs/{id}  cancel
GET  /v1/jobs/{id}/artifacts/{name}             PNG / MP4
POST /v1/billing/checkout {amount_yen} -> {checkout_url}   POST /v1/billing/sync   GET /v1/ledger   GET /v1/me
GET  /llms.txt  /terms  /privacy  /tokushoho
```

During the free beta a `429 quota_exceeded` response carries `resets_at`; a `400 beta_limit` means the job is too big
(split it). Once paid plans start, a `402 payment_required` response carries `checkout_url`.

## Self-hosting

The server (FastAPI + SQLite) and the worker (Blender in disposable Docker containers, `--network none --cap-drop ALL`)
live in the internal repository and are not part of this package yet. This repository holds the client side: MCP server, CLI,
HTTP client and samples.

## License

MIT (see LICENSE). Operated by JasmyLab Inc.
