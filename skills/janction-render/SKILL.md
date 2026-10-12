---
name: janction-render
description: Render Blender scenes, bpy scripts, 3D files (GLB, glTF, FBX, USD, OBJ) and animations on remote NVIDIA GPUs through the JANCTION Render MCP server, with no local Blender or GPU. Use when the user wants a rendered image or video of 3D content - preview a Blender scene, render a bpy script, turn a GLB/FBX/USD model into product shots or a 360-degree turntable MP4, render a Blender animation to MP4, or render on a machine without an NVIDIA GPU or where Cycles is slow. Flow - preview, fix, estimate the cost, ask, render, download.
---

# JANCTION Render

The `janction-render` MCP server (`https://render.janction.jp/mcp`) renders Blender 5.0 scenes with Cycles on JANCTION's
NVIDIA GPUs. A new key gets 100 JPY of free GPU time (14 days; one per network every 30 days, further keys on the same
network share what is left), and 400 JPY more, once per card, when the user saves a card on a Stripe page that charges
nothing (the service offers it as `card_offer` once the 100 JPY is used up; tell the user it costs nothing). When a reply
carries `autocharge_offer` (the credit is about to run out), ask the user once whether to turn on auto top-up and share its
link only if they say yes; after that, previews are free up to 2 GPU-minutes a day and other renders cost 0.1 JPY per
GPU-second from prepaid credit. Up to 1,000 frames per instruction (the service runs them as parts of 240 under one job id): 1920x1080 on free time, up to
3840x2160 on prepaid credit. Inputs and results
are deleted 24 hours after last use.

Do not use it to edit a scene open in the user's own Blender (a local Blender MCP does that), for one still image on a machine
with its own NVIDIA GPU, or for non-Blender video or general GPU compute.

## Is it connected?

Look for the tools `render_preview`, `render_estimate`, `render_final`. If they are missing, the server is not
authenticated yet. Say so plainly and give the step for the user's app; never say a render ran when no tool was called.

- Claude Code: run `/mcp`, choose janction-render, press Authenticate, then Connect in the browser (creates a free key).
- Codex: `codex mcp login janction-render`. Gemini CLI: `/mcp auth janction-render`.
- No MCP at all: `uvx janction-render try` renders a sample from the terminal (same service, free).

The first call `render_preview(scene_url="https://render.janction.jp/samples/cube_scene.py", environment="compare")` checks the
connection in a few seconds.

## Standard flow

1. Find the scene: a bpy script you write (pass `scene_script`), a `.blend` or 3D file on the web (`scene_url`, https), or a
   local file (`scene_path`, stdio server only). Reuse the returned `scene_id` instead of sending the scene again.
2. `scene_info` when you did not write the scene: cameras, frame range, objects, lights, missing files. No render.
3. `render_preview` - up to 4 frames tiled in one image, seconds, free within the daily preview time. Look at the image.
   Every preview returns `critic` (`ok` / `check` / `fix`) with fix code; on `fix`, apply it and preview again.
4. Show the preview and confirm frames, resolution and samples with the user.
5. `render_estimate` - GPU seconds, wall time (`human`), queue wait, and `cost` (`free`, `estimated_yen`, `reserved_yen`,
   `balance_yen`, `within_caps`). Tell the user the time and the price in yen.
6. Ask before every final, even a free one: say the time and the price (0 yen when `cost.free` is true) and wait for a yes.
   Skip the question only when the user already said "render the final" in this conversation. If they set a budget, keep
   the job inside it (`reserved_yen` from `render_estimate`); on the terminal server or the HTTP API, also pass it as
   `max_yen`.
7. `render_final` - returns `job_id`. Tell the user how long it will take.
8. `render_status(job_id)` - report `eta.human`. If it says the GPU is lent out, tell the user the wait and stop polling.
9. `render_download(job_id)` - links that need no key and work for about 24 hours.
10. Show the image inline, give the MP4 link, or save it locally when the user wants a file.

For a model the user wants seen from all sides, pass `orbit=True`: the preview shows four angles and
`render_final(orbit=True)` renders one full turn (24 frames) as an MP4. "A turntable preview" means
`render_preview(orbit=True)` (one image with four angles), nothing more; the MP4 turn is a final, so it comes after the
question in step 6. Lighting: `environment="studio"` (or `sunset`, `overcast`, `night`); `environment="compare"` on a
preview shows all four in one image.

Purpose presets fill the camera, light, backdrop, frames and output for a purpose; what you pass still wins:
`preset="product"` (4 studio shots at 0/90/180/270 degrees on a plain backdrop; the final gives 4 PNGs at 1440x1440),
`preset="turntable"` (one full turn as a 720p MP4 on a plain backdrop), `preset="animation"` (the scene's own camera,
lights and frame range; the scene is read first when the range is not known). For product shots of something the user
has no model for: `asset_search("<item>")`, then
`render_preview(scene_script='import jr_assets; jr_assets.import_model("<id>")', asset_urls=["polyhaven:<id>"], preset="product")`.

A script that does not run is a failed job, not a result: a script that does not parse is refused at once
(`script_syntax_error` with `line` and `source_line`, no GPU time), and a script that raises fails with
`SCRIPT_ERROR`, the line and `nothing_rendered`. Fix the line and call again; never present an earlier image as that
result.

## Rules

- Do not run `render_final` before a preview of the same scene unless the user explicitly asks to skip it.
- Do not start anything that is not free without an estimate and the user's yes. Never raise spending caps
  (`POST /v1/me/limits`) or buy credit on your own; give the user the `checkout_url` and let them pay.
- Do not call `render_share` (a public page) unless the user asks to publish.
- Retry only errors marked `retryable: true`, at most twice, waiting as told (`retry_after_s`, `Retry-After`). Do not loop.
- Do not resubmit a final job that timed out on your side: check `render_status` or the job list first. On the terminal
  server or the HTTP API, send the same `idempotency_key` so a resubmission returns the first job instead of rendering (or
  charging) twice.

## When something fails

Errors carry `code`, `retryable` and `recommended_action`. Act on the action:

| code | what to do |
|---|---|
| AUTH_REQUIRED | Reconnect: the steps under "Is it connected?". |
| INSUFFICIENT_CREDIT | Tell the user the price; show `checkout_url` (they pay in the browser), or make the job smaller. |
| COST_LIMIT_EXCEEDED | The job is above the spending cap. Ask the user; offer fewer frames, lower resolution or samples. |
| QUOTA_EXCEEDED / RATE_LIMITED | Wait until `resets_at` or `retry_after_s`; say when. |
| JOB_TOO_LARGE | Split the job: at most 240 frames and 1920x1080 per job. |
| INVALID_SCENE / SCRIPT_BLOCKED | Fix the script (see below); do not retry the same input. |
| MISSING_ASSET | Name the missing files; pass them in `asset_urls` or pack them into the .blend. |
| WORKERS_UNAVAILABLE | Tell the user the wait from `eta`; offer to check later. |
| JOB_FAILED | Read `failure` (`code`, `recommended_action`, `fix_by`) and `log_tail`, fix, preview again. |

More cases: [references/troubleshooting.md](references/troubleshooting.md). Prompts that work: [references/examples.md](references/examples.md).

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
import jr_assets; jr_assets.frame_camera()   # fit every object in the frame
```

- Build the scene, camera, lights and frame range only. The service sets the engine, resolution, samples and GPU; do not call
  `bpy.ops.render.render` or change render settings.
- Blender 5.0 API: animate with `obj.keyframe_insert("rotation_euler", frame=n)`; do not touch `action.fcurves` or
  `mat.use_nodes` (both changed in 5.x). Build materials through `mat.node_tree`.
- The sandbox has no network and no local files: pass web files in `asset_urls` (`assets` on the terminal server), or pack
  textures into a .blend.
- Props, materials and HDRIs without files: `asset_search("wooden table")` (Poly Haven, CC0), then `polyhaven:<id>` in
  `asset_urls` and `jr_assets.import_model('<id>')` in the script.
