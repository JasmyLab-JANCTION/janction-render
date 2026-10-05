# JANCTION Render

[![JasmyLab-JANCTION/janction-render MCP server](https://glama.ai/mcp/servers/JasmyLab-JANCTION/janction-render/badges/score.svg)](https://glama.ai/mcp/servers/JasmyLab-JANCTION/janction-render)

JANCTION Render is a cloud GPU render farm for Blender that AI agents call as an MCP server or HTTP API. Send a `.blend`
file, a bpy script or a 3D file (glTF / FBX / USD), preview in seconds, and get frames or an MP4 back from JANCTION's
NVIDIA GPUs. No local Blender or GPU is needed. Free beta, operated by JasmyLab Inc. Works from **Claude, ChatGPT,
Claude Code, Codex, Cursor or any MCP client**: an MCP server (remote and stdio), an HTTP API and a CLI.

An execution layer for agent-authored scenes and existing `.blend` files: edit in your agent or local Blender,
then send the scene to cloud GPUs for rendering.

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
- `scene_info` reads the scene without rendering (cameras, frame range, missing files).
- `render_preview` returns 1-4 low-cost frames tiled in one image within seconds, so the agent can look, fix, and repeat.
- `render_estimate` says how long a render will take ("about 3 minutes") and whether it fits today's free quota.
- `render_final` renders the frames on GPUs and joins them into an MP4; `render_status` reports the remaining time.
- Free beta: no charges. Each key gets 10 GPU-minutes per day; a final render is up to 240 frames at 1080p.
  Paid plans (per GPU second, prepaid credit) will be announced on the service page before they start.
- Inputs and results are deleted 24 hours after last use and are never used for training. A render you choose to
  share (`render_share`) gets a public page (`/r/<id>`, OGP for X and Discord) that stays until you unshare it.

## Status

Free beta. Service page: `https://render.janction.jp` (`/v1/health`, `/llms.txt`, `/faq`). Blender 5.0, Cycles on GPU
(`blender="5.2"` selects Blender 5.2 when the worker has it; `render_info` lists what is available).
Guides: [render farm for agents](https://render.janction.jp/blender-render-farm) · [without a GPU](https://render.janction.jp/render-blender-without-gpu) ·
[Claude](https://render.janction.jp/claude-blender) · [ChatGPT](https://render.janction.jp/chatgpt-blender) · [Claude Code](https://render.janction.jp/claude-code-blender) ·
[Codex](https://render.janction.jp/codex-blender) · [bpy scripts](https://render.janction.jp/bpy-script-cloud-gpu) · [API](https://render.janction.jp/blender-render-api) ·
[comparison](https://render.janction.jp/blender-render-farm-api-comparison) · [Blender add-on](https://render.janction.jp/blender-addon) ·
[Maya / Houdini / Cinema 4D](https://render.janction.jp/maya-houdini-cinema4d) · 日本語は `/ja/`

## Connect (remote MCP, nothing to install)

MCP server URL: **`https://render.janction.jp/mcp`** (Streamable HTTP). Auth is OAuth 2.1 with dynamic client
registration: pressing "Connect" opens a page that creates a free API key (or takes one you already have). A raw API key
also works as `Authorization: Bearer jr_...`.

| client | how |
|---|---|
| Claude.ai (web, desktop, mobile) | Settings → Connectors → Add custom connector → paste the URL → Connect |
| ChatGPT | Settings → Connectors → Advanced → Developer mode → Create → paste the URL (OAuth) |
| Claude Code | `claude mcp add --transport http janction-render https://render.janction.jp/mcp`, then `/mcp` to authenticate |
| Codex | `codex mcp add janction-render --url https://render.janction.jp/mcp` |
| Gemini CLI / Antigravity CLI | `gemini extensions install https://github.com/JasmyLab-JANCTION/janction-render` (this repository carries `gemini-extension.json`) |
| Grok (grok.com) | Connectors → New Connector → Custom → paste the URL |
| Perplexity (Pro / Max / Enterprise), Le Chat (workspace admin) | Add a custom remote MCP connector with the URL |
| Cursor, Windsurf, Cline, Goose, other MCP clients | Streamable HTTP at the URL above (OAuth, or a Bearer API key header). Installer notes: [llms-install.md](llms-install.md) |

Remote tools take `scene_script` (bpy code as text), `scene_url` (an https link to a `.blend`, `.py` or a 3D file) or
`scene_id`, plus `asset_urls` for textures or glTF `.bin` files; results come back as an inline image plus download links
that need no key and work for about 24 hours (`render_download(only="mp4")` for just the video).

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
| `scene_info(scene_script | scene_url | scene_path | scene_id, assets?)` | cameras, frame range, fps, resolution, objects, lights, missing files. No render. |
| `render_preview(..., frames="1-24", environment?, blender?)` | up to 4 frames (720p budget) tiled with frame labels; returns the image inline |
| `render_estimate(scene_id, frame_start, frame_end, width, height, samples)` | GPU seconds, queue wait, "about N minutes", fits today's free quota? No GPU time used |
| `render_final(scene_id, frame_start, frame_end, width, height, samples, fps, output, environment?, blender?, engine?, transparent?, notify_url?)` | frames (png / exr) or video (mp4 / webm / prores / gif / webp); `transparent=True` keeps an alpha background (png / exr / webm / gif / webp); `notify_url` gets one JSON POST when the job finishes; returns job_id + estimate |
| `render_status(job_id)` | progress and ETA (`eta.human`); `render_download(job_id, only="mp4" / "frames" / "all")` files or links; `render_cancel(job_id)` |
| `billing()` | free-beta quota (used today, daily limit, reset time); later balance and top-up link |
| `render_share(job_id, title?, note?, include_script?, listed?)` | a public page `/r/<id>` with the image or video, the conditions and (optionally) the script; survives the 24-hour expiry until `render_unshare`; with `listed=True` it appears in `/gallery` after a review |
| `asset_search(query, kind)` | CC0 models / textures / HDRIs on Poly Haven by words; results carry `polyhaven:<id>` and the entry file |
| `render_info()` | workers online or gated (GPU lent to another workload), queue, expected wait, supported inputs, environment presets, Blender versions |

Options on `render_preview` / `render_final`: `environment` (`studio`, `sunset`, `overcast`, `night`, `compare` on previews; `environment_strength`,
`environment_visible=False` for a flat grey backdrop with HDRI lighting), `orbit` / `orbit_frames` / `orbit_elevation` (turntable),
`blender` (`"5.2"`), and `assets` (stdio: local files
sent with the scene, found in the script through `os.environ["JR_ASSETS_DIR"]`; a `.blend`'s external files are collected
automatically with `pip install janction-render[blend]`) or `asset_urls` (remote).

CLI: `janction-render inspect|preview|render|status|download|share|unshare|cancel|jobs|balance|topup|info`.

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

The service sets the engine (Cycles by default; `engine="eevee"` for cheaper animations: about half the per-frame cost after ~7 s of shader compilation per job), resolution, samples and denoising; your script sets the scene, camera and frame range. In Blender 5.0 materials always use nodes: set the Principled BSDF Base Color, not `diffuse_color`.
Scripts run in an isolated container with no network. See `samples/cube_scene.py`.

## HTTP API

```
POST /v1/keys                                   -> {api_key}         (header X-API-Key afterwards)
POST /v1/files  multipart "file" (.blend|.py|.glb|.fbx|.usd|.obj|...)   -> {scene_id}
POST /v1/files/{id}/assets  multipart "files"   textures, glTF .bin ...   GET /v1/files/lookup?sha256=  reuse an upload
POST /v1/estimate {kind, frames|frame_start/frame_end, width, height, samples, scene_id?} -> seconds, wall_seconds, human, quota
POST /v1/jobs   {scene_id, kind: info|preview|final, frames|frame_start/frame_end, width, height, samples, camera, fps, output (png|exr|mp4|webm|prores|gif|webp), transparent, notify_url (https), engine (cycles|eevee),
                 environment, environment_strength, environment_visible, blender, orbit, orbit_frames, orbit_elevation}
GET  /v1/jobs/{id}      status, progress, eta, artifacts[], cost, warnings, info    DELETE /v1/jobs/{id}  cancel
GET  /v1/jobs/{id}/artifacts/{name}             PNG / MP4
POST /v1/jobs/{id}/share {title?, note?, include_script?, listed?} -> {share_id, url}   DELETE /v1/jobs/{id}/share   GET /v1/shares
GET  /r/{share_id}  public page (no key)   GET /gallery
GET  /v1/assets/search?q=&kind=models|textures|hdris   CC0 assets (Poly Haven) -> spec polyhaven:<id>
POST /v1/files/{id}/assets/urls {urls: ["https://...", "polyhaven:<id>"]}   fetch assets server-side
POST /mcp                                       remote MCP (Streamable HTTP; Bearer api key or OAuth)
GET  /.well-known/oauth-protected-resource/mcp  OAuth discovery
POST /v1/billing/checkout {amount_yen} -> {checkout_url}   POST /v1/billing/sync   GET /v1/ledger   GET /v1/me
GET  /llms.txt  /llms-full.txt  /ja/llms.txt  /faq  /terms  /privacy  /legal  /security  /support
```

During the free beta a `429 quota_exceeded` response carries `resets_at`; a `400 beta_limit` means the job is too big
(split it). Once paid plans start, a `402 payment_required` response carries `checkout_url`.

## Blender add-on and DCC tools (for people, not agents)

- **Blender extension** (`addons/blender/`, Blender 4.2+): a JANCTION Render panel under Properties → Render with Preview,
  Estimate and Final. A copy of the open file and the textures it references with relative paths are uploaded; results land
  next to the .blend. Install from the extension repository `https://render.janction.jp/extensions/index.json`
  (Preferences → Get Extensions → Repositories → + → Add Remote Repository), or install the zip from
  `https://render.janction.jp/extensions/janction_render-0.1.0.zip` (`python scripts/build_blender_addon.py` builds it
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

## License

MIT (see LICENSE) for the package, the MCP servers, the CLI and the DCC tools. The Blender extension under
`addons/blender/` is GPL-3.0-or-later, as Blender requires for add-ons. Operated by JasmyLab Inc.
