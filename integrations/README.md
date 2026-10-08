# JANCTION Render from Maya, Houdini and Cinema 4D

Thin "submit to JANCTION Render" tools for DCC applications whose own renderers cannot run on
the farm (Arnold, Redshift, Karma, Mantra, Standard/Physical: all behind license walls). Each tool
does one thing: export the scene to a file Blender can import, send it to
[JANCTION Render](https://render.janction.jp), render it with Cycles on datacenter GPUs, and open
the result.

```
Maya / Houdini / Cinema 4D  --export-->  USD / FBX / Alembic  --upload-->  JANCTION Render (Blender + Cycles on GPU)
                                                                                     |
                                                     sheet.png / output.mp4 / frame_0001.png  <--download--+
```

What this is not: a bridge for the native renderer. Materials are converted approximately by
Blender's importers (USD Preview Surface, FBX Phong/PBR, OBJ/MTL); shader networks, render
passes and renderer-specific nodes are not carried over. Lights rarely survive an export, so the
tools light the scene with the `studio` HDRI preset by default.

No sign-up: each new key gets 500 JPY of GPU time free (welcome credit, 14 days); after that, previews are free up to 2 GPU-minutes a day and finals cost 0.1 JPY per GPU-second from prepaid credit. Final renders go up to 240 frames and 1080p.

## Files

| file | what |
|---|---|
| `jr_submit.py` | shared client (standard library only, Python 3.7+): key/config, upload with assets, estimate, submit, wait, download, open, `render()`, `BackgroundRender` thread for UIs |
| `maya/janction_render_maya.py` | Maya window: USD (mayaUsdPlugin) or FBX export, Preview / Final (MP4) / Turntable |
| `houdini/janction_render_houdini.py` | Houdini shelf tool: Alembic ROP of `/obj`, or an existing USD ROP, or a file on disk |
| `cinema4d/janction_render_c4d.py` | Cinema 4D Script Manager script: FBX (or USD when the exporter is installed) |

Every tool runs the upload and the wait in a background thread and keeps its host responsive;
errors become a dialog or a status line, never a traceback inside the application.

## Install

`jr_submit.py` must be importable from the app script: keep it in the folder above the script
(the scripts add both their own folder and its parent to `sys.path`), or copy it next to the script.

### Maya (2022 and newer)

1. Copy `jr_submit.py` and `maya/janction_render_maya.py` into `Documents/maya/scripts`
   (or `Documents/maya/<version>/scripts`).
2. Script Editor, Python tab:

   ```python
   import janction_render_maya; janction_render_maya.show()
   ```

   Select the two lines and drag them onto a shelf to make a button.
3. The window: export format (USD when `mayaUsdPlugin` loads, else FBX), frame range (from the
   timeline), lighting preset, final size (from the render settings, capped to 1080p worth of
   pixels), samples, and three buttons:
   - Preview: 4 frames spread across the range, tiled into one `sheet.png`.
   - Final (MP4): every frame of the range at the final size; one frame gives a PNG.
   - Turntable: the current frame exported alone, rendered from 0/90/180/270 degrees around the model.

   The result opens in the OS viewer and is saved under `~/janction_render/maya/<timestamp>_<mode>/`.

How Maya exports: USD via `cmds.mayaUSDExport(file=..., exportMaterials=True, shadingMode="useRegistry",
convertMaterialsTo=["UsdPreviewSurface"], frameRange=(start, end))`, written as ASCII `.usda`;
FBX via `cmds.file(path, force=True, options="v=0;", type="FBX export", exportAll=True)` after
`FBXExportBakeComplexAnimation` over the range (cameras and lights on, textures referenced, not embedded).

What is sent: the exported file plus the textures of every `file` node (attribute
`fileTextureName`), each under its basename. For USD the absolute texture paths inside the
`.usda` are rewritten to those basenames, so the farm finds them. For FBX, Blender looks the
textures up by basename next to the file, which is where the service puts assets.

### Houdini (18.5 and newer)

1. Right-click a shelf, New Tool, Script tab (Python):

   ```python
   import sys; sys.path.append(r"C:/path/to/integrations/houdini")
   import janction_render_houdini; janction_render_houdini.main()
   ```
2. The tool asks for the source, then the numbers and the mode in one dialog
   (`hou.ui.readMultiInput`), and reports progress in the status bar (`hou.ui.setStatusMessage`).
   Sources:
   - Export `/obj` to Alembic: creates or reuses `/out/janction_render_abc` (type `alembic`,
     `root=/obj`, `objects=*`, `collapse` on, `build_from_path` off, Ogawa) and renders it over the
     frame range into a temp `.abc`. Alembic carries geometry and cameras only: no lights, no
     materials, so the `studio` preset is used (the dialog says so).
   - Render an existing USD ROP (`usd` in `/out`, `usd_rop` in `/stage`) and send its output file.
     If the output is ASCII USD, textures it references on disk are sent and the paths rewritten.
   - Pick a 3D file on disk.
3. Results open in the OS viewer and are saved under `~/janction_render/houdini/`.

### Cinema 4D (R23 and newer)

1. Script > Script Manager > File > Import Script: `cinema4d/janction_render_c4d.py`. Keep
   `jr_submit.py` importable (next to the script, or in the preferences `python3xx/libs` folder).
2. Run the script: a small dialog with the export format, frame range (document min/max), lighting,
   final size (from the active render settings), samples, and the same three buttons. A timer in the
   dialog mirrors the background thread's progress; Cancel job cancels on the service.
3. Export: FBX through `c4d.documents.SaveDocument(doc, path, SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST, 1026370)`
   with cameras, lights, tracks and materials enabled on the exporter's container
   (`MSG_RETRIEVEPRIVATEDATA`); USD through exporter id 1055179 when `c4d.plugins.FindPlugin` finds it
   (written as `.usda` so texture paths can be rewritten).
4. What is sent: the exported file plus the files of all `Xbitmap` shaders found in the materials
   (color, bump, normal, nested layer shaders; node materials are not inspected), each under its
   basename, resolved through `c4d.GenerateTexturePath` and the document's `tex` folder.

## The key and the config file

The first run creates an API key (`POST /v1/keys`) and stores it in
`~/.janction_render.json`:

```json
{"server": "https://render.janction.jp", "api_key": "jr_..."}
```

The free credit and the balance belong to the key. `JANCTION_RENDER_API_KEY` pins a key without
writing it to disk; `JANCTION_RENDER_SERVER` points the tools at another server. If the stored
key is no longer known to the service, the tools create a new one once and retry.

## What is uploaded, and for how long

- The exported file (USD / FBX / Alembic / what you picked) and the textures listed above. Nothing
  else from the scene. Identical bytes are not sent twice (`GET /v1/files/lookup?sha256=`).
- Files render inside a disposable container with no network. Inputs, intermediate data and
  results are deleted 24 hours after last use and are never used for training
  (details: https://render.janction.jp/security).
- Uploads are capped at 1 GB per file and 128 MB per asset; asset names must use letters, digits,
  `.` `_` `-` only, so the tools rename textures with other characters (printed in the app's console).

## Known limitations

- Texture paths: exporters write absolute paths. The tools fix this for ASCII USD by rewriting the
  references to the uploaded basenames, and rely on Blender's basename lookup for FBX. Binary USD
  (`.usdc`), UDIM tiles and image sequences are not handled: those textures will be missing.
  Two textures with the same basename in different folders collide; only the first is sent.
- Lights: Alembic has none; FBX and USD lights rarely map to something useful in Cycles. The
  `studio` preset (a bundled CC0 HDRI) lights the render; `scene lights only` turns it off.
- Materials are approximated by Blender's importers. Renderer-specific shaders (Arnold, Redshift,
  Karma, V-Ray, Octane) are dropped; a diffuse/base color with textures is what usually survives.
- Cameras: USD and Alembic exports carry the cameras; the service renders through the first camera it
  finds (or frames the objects automatically when there is none). Turntable mode ignores the scene
  camera and orbits the model.
- Frame rate comes from the app's setting (Maya time unit, `hou.fps()`, `doc.GetFps()`), rounded
  to a whole number.
- A job renders at most 240 frames and 1080p worth of pixels; the tools scale the
  final size down and refuse longer ranges with a message.

## Manual fallback from any application

Export to USD, FBX, glTF, OBJ, Alembic, STL or PLY from any tool and use the CLI:

```
pip install janction-render
janction-render render model.usd --environment studio --orbit
```

or the Python module in this folder without any UI:

```python
import jr_submit as jr
result = jr.render("model.usd", "preview", assets=[("wood.png", "/textures/wood.png")],
                   out_dir="renders", frames=[1, 8, 16, 24], environment="studio")
jr.open_path(result["files"][0])
```

`render()` uploads (or reuses) the file, submits, waits and downloads; `BackgroundRender` does the
same in a thread for UIs. Errors are `JRError(code, message, status)`; a 402 `payment_required`
carries `extra["checkout_url"]`, the top-up page to show the user.
