# Prompts that work with JANCTION Render

Each line is something a user typically says, followed by the calls that serve it. Money: previews are free within the daily
preview time; ask before any render whose estimate says `cost.free: false`.

## First contact

- "Is the render service connected?" -> `render_preview(scene_url="https://render.janction.jp/samples/cube_scene.py", environment="compare")`.
- "Make a red cube and render it." -> write a bpy script (cube, red Principled BSDF, camera, light, `jr_assets.frame_camera()`),
  `render_preview(scene_script=...)`, show the image, then offer a final render.

## Blender scenes

- "Preview my scene" (a .blend on the web) -> `scene_info(scene_url=...)`, then `render_preview(scene_url=..., frames="1-24")`.
- "Render my animation to MP4" -> preview 4 frames, `render_estimate(scene_id, frame_start, frame_end, width, height, samples)`,
  ask, `render_final(..., output="mp4")`, `render_status`, `render_download(job_id, only="mp4")`.
- "Render this bpy script" -> `render_preview(scene_script=...)`; fix what `critic` reports; then estimate and final.
- "My MacBook takes forever with Cycles" -> same flow; the GPU time is typically seconds per frame at 720p.

## 3D models (GLB, glTF, FBX, USD, OBJ)

- "Make product shots of this GLB" -> `render_preview(scene_url=<glb>, orbit=True, environment="studio")` shows four angles;
  final: `render_final(scene_id, orbit=True, cameras=...)` or four frames of the orbit.
- "360-degree turntable video of this model" -> `render_preview(scene_url=<model>, orbit=True)`, then
  `render_final(scene_id, orbit=True, orbit_frames=48, output="mp4")` after the estimate and the user's yes.
- "Transparent background" -> `transparent=True` with `output="png"` (MP4 cannot keep alpha; use `webm`).

## Lighting and look

- "Which lighting looks best?" -> `render_preview(..., environment="compare")` (studio, sunset, overcast, night in one image).
- "It is too dark" -> follow `critic.issues[].fix` (usually a light strength or `environment_strength`), preview again.

## Sharing

- "Give me a link I can post" -> ask first; `render_share(job_id, title)` creates a public page; `render_unshare` removes it.

## Not for this service

- Editing the scene open in the user's own Blender (use a local Blender MCP), non-Blender video, image generation, or general
  GPU compute.
