---
name: janction-render
description: Render Blender scenes on JANCTION GPUs (a cloud render farm) when the user has no GPU or local rendering is slow. Use for any Blender / bpy / 3DCG task that needs a rendered image or video - preview, look, fix, then final render with a time estimate.
---

# JANCTION Render

The `janction-render` MCP server (remote, `https://render.janction.jp/mcp`) renders Blender scenes on JANCTION GPUs.
Each new key gets 500 JPY of GPU time free (welcome credit, 14 days); after that, previews are free up to 2 GPU-minutes a day and finals cost 0.1 JPY per GPU-second from prepaid credit. Final renders go up to 240 frames at 1080p.
Blender 5.0, Cycles on GPU.
Inputs and results are deleted 24 hours after last use.

If the tools are missing, the connector is not authenticated yet: run `/mcp` and choose janction-render, then press
Connect in the browser page (it creates a free key).

## Workflow

1. **Write the scene as a bpy script** (no local Blender needed). Set the scene, camera and frame range only; the
   service sets the engine, resolution, samples and denoising. Pass it as `scene_script`. A `.blend` or a 3D file
   (glTF/GLB, FBX, USD, OBJ, STL, PLY, Alembic) on the web can be passed as `scene_url` (https); textures or glTF `.bin`
   files go in `asset_urls`. Reuse the returned `scene_id` afterwards instead of re-sending the script.
   If the user has not described lighting, pass `environment="studio"` (or `sunset` / `overcast` / `night`) for HDRI
   lighting; `environment="compare"` on `render_preview` renders the frame under all four presets in one labelled image
   so the user can choose; `environment_visible=False` keeps the lighting but shows a flat grey backdrop. `blender="5.2"`
   selects Blender 5.2 when `render_info` lists it. A `.gltf` / `.obj` URL brings its `.bin` / `.mtl` / textures along.
   For an imported model (or any scene the user wants shown from all sides), pass `orbit=True`: a preview shows four
   angles, and `render_final(orbit=True)` without `frame_end` renders one full turn (24 frames) as an MP4. Floors are
   ignored when framing; `orbit_target` (object name or `x,y,z`) and `orbit_distance` (0.7 = closer) adjust the shot.
2. `scene_info` - read what the script produced: cameras, frame range, objects, lights, missing files. No render.
3. `render_preview(frames="1-24")` - up to 4 frames tiled in one image (720p budget, a few GPU seconds). Look at the
   image. If something is wrong (camera, lighting, missing objects), fix the script and preview again. Every preview
   also returns `critic`: a verdict (`ok` / `check` / `fix`), a score and `issues`, each with fix code (one bpy line or a
   tool argument). When the verdict is `fix`, apply the fixes and preview again before any final render.
4. Ask the user "is this OK?" and confirm frames, resolution and samples.
5. `render_estimate(scene_id, frame_start, frame_end, width, height, samples)` - tell the user the time ("about 3
   minutes") and whether it fits the free GPU time left; if not, say what it would cost (`cost.estimated_yen`) and propose
   fewer frames / lower samples as the free alternative.
6. `render_final(...)` - returns `job_id` and the estimate. Tell the user how long it will take.
7. `render_status(job_id)` until `status` is `done`; report `eta.human` while waiting. Then `render_download(job_id)`
   (default: the MP4 or sheet plus the first frames; `only="frames"` lists every PNG): the links need no key and work for
   about 24 hours. Show the image link inline; give the MP4 link to the user, or fetch it with `curl -o output.mp4 <link>`
   when a local file is wanted.

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

- Always add a camera and set `scene.camera`, and add at least one light; set `frame_start` / `frame_end` for animations; animate with keyframes.
- To fit every object in the frame, end the script with `import jr_assets; jr_assets.frame_camera()` (keeps the camera's direction, moves it back until everything is in view; `margin=1.2` leaves more room).
- If you start from an empty scene (`bpy.ops.wm.read_factory_settings(use_empty=True)`), there is no camera, no light and no world: add all three. Otherwise the service adds an automatic camera (framing all objects) and a sun, and tells you in `warnings`.
- Do not set `mat.use_nodes = True` (always on in Blender 5.x; it only produces a deprecation warning). Build materials through `mat.node_tree`.
- Blender 5.0 animation API: animate with `obj.keyframe_insert("rotation_euler", frame=n)`; do not touch `obj.animation_data.action.fcurves` (removed in 5.0). For linear motion set `bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'` before inserting keyframes.
- Do not call `bpy.ops.render.render` or change render settings; do not read local files or the network (the sandbox has none).
- Textures: procedural (shader nodes) work; external image files must be packed into a .blend.

## When things go wrong

- `payment_required` (402): the job goes past the free GPU time and the credit is short; tell the user the price, show
  `checkout_url`, or make the job smaller so it fits the free time.
- `beta_limit` (400): too many frames or too large a resolution for one job; split the job.
- `workers_gated` in `render_info` / the estimate, or a `hint` saying the GPU is lent out: jobs queue and start when the
  GPU returns. `eta.human` (and `eta.gate`: closed_for_seconds, typical_seconds, long_seconds, expected_remaining_seconds)
  says how long it has been out, how long it usually stays out and how much longer to expect. Tell the user that estimate
  and offer to check later; do not poll in a loop.
- Need furniture, props, materials or an HDRI without files? `asset_search("wooden table")` (Poly Haven, CC0), then pass
  `polyhaven:<id>` in `asset_urls`; in the script `import jr_assets` and use `jr_assets.import_model('<id>')`,
  `jr_assets.apply(obj, jr_assets.material('<texture_id>'))`, `jr_assets.world_hdri('<hdri_id>')`.
- When the user wants to show the result to someone (X, Discord, a client): ask, then `render_share(job_id, title)` and
  give them the url. `render_unshare(job_id)` removes the page.
- A failed job carries `error` and `log_tail` (Blender's log): fix the script and try again.
