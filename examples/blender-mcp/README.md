# Build in Blender with an MCP server, render on a cloud GPU with JANCTION Render

Two MCP servers in one chat:

- a **Blender MCP server** drives the Blender on your machine: [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender)
  (`uvx mcp-for-blender`, Blender 3.0 or newer) or Blender's own [Lab MCP server](https://www.blender.org/lab/mcp-server/) (Blender 5.1 or newer);
- **JANCTION Render** renders the result on a datacenter GPU (NVIDIA RTX PRO 6000, Blender 5.0 or 5.2, Cycles or EEVEE):
  a preview the agent can look at in a few seconds, then frames or an MP4.

Neither project needs a change. The hand-off is a file on your disk.

## Set up

Claude Code:

```
claude mcp add blender uvx mcp-for-blender
claude mcp add janction-render -- uvx --from "janction-render[blend]" janction-render-mcp
```

Claude Desktop, Cursor and other clients (`mcpServers` in their JSON settings):

```json
{
  "mcpServers": {
    "blender": { "command": "uvx", "args": ["mcp-for-blender"] },
    "janction-render": { "command": "uvx", "args": ["--from", "janction-render[blend]", "janction-render-mcp"] }
  }
}
```

The `[blend]` extra adds blender-asset-tracer, so a .blend is sent together with the textures it points to.
JANCTION Render needs no sign-up: the first call creates a key. Each key gets 10 GPU-minutes free per day;
past that, 0.1 JPY per GPU-second from prepaid credit. A 720p preview usually takes 2 to 10 GPU-seconds.

## Two hand-offs

### 1. The scene as you see it: your camera, lights and materials

The agent saves a copy of the open file through the Blender MCP server (`execute_blender_code` in mcp-for-blender;
the Lab server also runs Python in Blender):

```python
import bpy, os, tempfile
path = os.path.join(tempfile.gettempdir(), "for_janction.blend")
bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)   # the open file stays as it is
print(path)
```

then calls JANCTION Render with that path:

```
render_preview(scene_path="<that path>")                 # one frame back in seconds, with a short verdict
render_final(scene_path="<that path>", frame_start=1, frame_end=48, output="mp4")
```

A file saved by Blender 5.1 or newer needs `blender="5.2"` on both calls; older files open in the default 5.0.

### 2. Objects only, for a product shot or a turntable

The agent exports a GLB through the same Python tool:

```python
import bpy, os, tempfile
path = os.path.join(tempfile.gettempdir(), "for_janction.glb")
bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True, export_animations=True)
print(path)
```

```
render_preview(scene_path="<that path>", environment="studio", environment_visible=false)
render_final(scene_path="<that path>", orbit=true, orbit_frames=48, environment="studio", output="mp4")
```

JANCTION Render adds the camera and the lighting.

## A prompt that uses both

> In Blender, model a ceramic mug on a wooden table and frame it with the scene camera. When it looks right,
> save a copy and render a preview on JANCTION Render. If the preview is fine, render frames 1-48 at
> 1280x720 as an MP4 and give me the link.

## Check the hand-off without opening Blender's window

The Blender MCP servers need Blender's UI running, so `verify_handoff.py` runs the same bpy calls in a headless
Blender (build a small scene, save a copy, export a GLB), then starts the janction-render MCP server over stdio,
as your MCP client would, and renders both files:

```
pip install janction-render mcp
python examples/blender-mcp/verify_handoff.py --blender /path/to/blender
```

Run on 2026-10-08 with Blender 5.2.0 and janction-render 0.4.22: the .blend preview (with `blender="5.2"`) took
2.5 GPU-seconds and the GLB preview (studio lighting) 3.4 GPU-seconds; both came back as images.

## Notes

- mcp-for-blender's safe mode (`BLENDER_MCP_SAFE_MODE=1`) still allows saving and exporting, so both hand-offs work with it on.
- Inputs and results are deleted 24 hours after last use. Previews are 720p by default; the final render goes up to
  1920x1080 and 240 frames per job.
- More: https://render.janction.jp/llms.txt and https://render.janction.jp/blender-mcp
