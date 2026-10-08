"""JANCTION Render for Maya: export the scene (USD or FBX) and render it with Cycles on JANCTION GPUs.

Maya's own renderers cannot run on the farm, so this tool exports the scene to a file Blender can
import, sends it with the textures it finds, and opens the result (sheet.png or output.mp4).

Install: put this file and jr_submit.py (from the folder above) into Maya's scripts folder
(Documents/maya/scripts or Documents/maya/<version>/scripts), then run in the Script Editor
(Python tab) or from a shelf button:

    import janction_render_maya; janction_render_maya.show()

Python 3 (Maya 2022 and newer). Nothing else to install.
"""
import os
import re
import sys
import tempfile
import time

try:
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.utils as mutils
except ImportError:  # outside Maya (tests, syntax checks)
    cmds = None
    mel = None
    mutils = None

_HERE = os.path.dirname(os.path.abspath(__file__))
for _folder in (_HERE, os.path.dirname(_HERE)):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)
import jr_submit as jr  # noqa: E402

WINDOW = "janctionRenderWindow"
TITLE = "JANCTION Render"
FORMAT_USD = "USD (.usda, mayaUsdPlugin)"
FORMAT_FBX = "FBX (fbxmaya)"
LIGHTING = ("studio", "sunset", "overcast", "night", "scene lights only")
_FPS = {"game": 15, "film": 24, "pal": 25, "ntsc": 30, "show": 48, "palf": 50, "ntscf": 60}

_ui = {}  # widget names
_runner = None  # the BackgroundRender of the job in flight


# ---------------------------------------------------------------- scene queries

def scene_fps():
    """Maya's time unit as frames per second (1..120)."""
    unit = cmds.currentUnit(query=True, time=True) or "film"
    if unit in _FPS:
        return _FPS[unit]
    m = re.match(r"([\d.]+)fps", unit)
    if m:
        return max(1, min(120, int(round(float(m.group(1))))))
    return 24


def frame_range():
    start = int(round(cmds.playbackOptions(query=True, minTime=True)))
    end = int(round(cmds.playbackOptions(query=True, maxTime=True)))
    return start, max(start, end)


def render_size():
    try:
        return int(cmds.getAttr("defaultResolution.width")), int(cmds.getAttr("defaultResolution.height"))
    except Exception:  # noqa: BLE001
        return 1920, 1080


def collect_textures():
    """Textures from `file` nodes: [(asset_name, absolute_path)], plus notes about what was skipped.
    The asset name is the file's basename (characters the service rejects become '_')."""
    out = []
    notes = []
    seen = {}
    root = ""
    try:
        root = cmds.workspace(query=True, rootDirectory=True) or ""
    except Exception:  # noqa: BLE001
        pass
    for node in cmds.ls(type="file") or []:
        try:
            raw = cmds.getAttr(node + ".fileTextureName") or ""
        except Exception:  # noqa: BLE001
            continue
        if not raw.strip():
            continue
        if jr.is_sequence_path(raw):
            notes.append("%s: UDIM / sequence textures are not sent (%s)" % (node, raw))
            continue
        candidates = [raw] if os.path.isabs(raw) else [os.path.join(root, raw), os.path.join(root, "sourceimages", raw), raw]
        full = None
        for c in candidates:
            if os.path.isfile(c):
                full = os.path.abspath(c)
                break
        if full is None:
            notes.append("%s: texture not found on disk (%s)" % (node, raw))
            continue
        name = jr.safe_asset_name(full)
        if not name:
            notes.append("%s: file type not accepted by the service (%s)" % (node, os.path.basename(full)))
            continue
        if name in seen:
            if seen[name].lower() != full.lower():
                notes.append("two textures share the name %s; only %s is sent" % (name, seen[name]))
            continue
        seen[name] = full
        if name != os.path.basename(full):
            notes.append("%s is sent as %s (only letters, digits, . _ - are accepted)" % (os.path.basename(full), name))
        out.append((name, full))
    return out, notes


# ---------------------------------------------------------------- export

def usd_available():
    try:
        if cmds.pluginInfo("mayaUsdPlugin", query=True, loaded=True):
            return True
        cmds.loadPlugin("mayaUsdPlugin", quiet=True)
        return bool(cmds.pluginInfo("mayaUsdPlugin", query=True, loaded=True))
    except Exception:  # noqa: BLE001
        return False


def export_usd(path, start, end):
    """mayaUSDExport with materials (UsdPreviewSurface) over start..end. Written as ASCII (.usda)
    so texture paths can be rewritten to the names that are uploaded."""
    if not usd_available():
        raise RuntimeError("mayaUsdPlugin could not be loaded; choose FBX instead")
    file_arg = path.replace("\\", "/")
    full = dict(file=file_arg, exportMaterials=True, shadingMode="useRegistry",
                convertMaterialsTo=["UsdPreviewSurface"], exportUVs=True, exportDisplayColor=True,
                exportVisibility=True, mergeTransformAndShape=True, frameRange=(start, end))
    try:
        cmds.mayaUSDExport(**full)
    except TypeError:
        # an older plugin without some of these flags: the minimal call
        cmds.mayaUSDExport(file=file_arg, exportMaterials=True, frameRange=(start, end))
    if not os.path.isfile(path):
        raise RuntimeError("mayaUSDExport produced no file at %s" % path)


def export_fbx(path, start, end):
    """FBX export of everything, animation baked over start..end, textures referenced (not embedded)."""
    try:
        if not cmds.pluginInfo("fbxmaya", query=True, loaded=True):
            cmds.loadPlugin("fbxmaya", quiet=True)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("fbxmaya plugin could not be loaded: %s" % exc)
    settings = (
        "FBXResetExport",
        "FBXExportCameras -v true",
        "FBXExportLights -v true",
        "FBXExportSmoothingGroups -v true",
        "FBXExportEmbeddedTextures -v false",
        "FBXExportInAscii -v false",
        "FBXExportInputConnections -v false",
        "FBXExportBakeComplexAnimation -v true",
        "FBXExportBakeComplexStart -v %d" % start,
        "FBXExportBakeComplexEnd -v %d" % end,
    )
    for command in settings:
        try:
            mel.eval(command)
        except Exception:  # noqa: BLE001 - a missing setting only changes a default
            pass
    cmds.file(path.replace("\\", "/"), force=True, options="v=0;", type="FBX export", exportAll=True)
    if not os.path.isfile(path):
        raise RuntimeError("FBX export produced no file at %s" % path)


def export_scene(fmt, start, end):
    """Export to a temp folder. Returns (file_path, assets, notes, temp_dir)."""
    tmp = tempfile.mkdtemp(prefix="janction_render_maya_")
    textures, notes = collect_textures()
    if fmt == FORMAT_USD:
        path = os.path.join(tmp, "maya_scene.usda")
        export_usd(path, start, end)
        names = dict((os.path.basename(full).lower(), name) for name, full in textures)
        rewritten = jr.rewrite_usda_asset_paths(path, names)
        # textures the exporter wrote that the file nodes did not list (rare); send them too
        for name, full, _ref in jr.scan_usda_asset_paths(path):
            if name not in names.values():
                textures.append((name, full))
                names[os.path.basename(full).lower()] = name
        if textures and not rewritten:
            notes.append("no texture path in the USD could be rewritten; textures may be missing on the farm")
        elif rewritten:
            notes.append("%d texture path%s rewritten to relative names" % (rewritten, "" if rewritten == 1 else "s"))
    else:
        path = os.path.join(tmp, "maya_scene.fbx")
        export_fbx(path, start, end)
        if textures:
            notes.append("the FBX references textures by their original paths; Blender finds them next to the "
                         "file by basename, so renamed textures (see above) will be missing")
    return path, textures, notes, tmp


# ---------------------------------------------------------------- UI

def _set_status(text):
    if _ui.get("status") and cmds.text(_ui["status"], exists=True):
        cmds.text(_ui["status"], edit=True, label=text)


def _enable(running):
    for key in ("preview", "final", "turntable"):
        if _ui.get(key) and cmds.button(_ui[key], exists=True):
            cmds.button(_ui[key], edit=True, enable=not running)
    if _ui.get("cancel") and cmds.button(_ui["cancel"], exists=True):
        cmds.button(_ui["cancel"], edit=True, enable=running)


def _dialog(message):
    try:
        cmds.confirmDialog(title=TITLE, message=message, button=["OK"])
    except Exception:  # noqa: BLE001
        print("[%s] %s" % (TITLE, message))


def _on_update(runner):
    """Called from the worker thread: hand the refresh to Maya's main thread."""
    mutils.executeDeferred(_refresh, runner)


def _refresh(runner):
    global _runner
    if runner is not _runner:
        return
    _set_status(runner.text)
    if not runner.done:
        return
    _enable(False)
    _runner = None
    if runner.error is not None:
        message = runner.text
        if isinstance(runner.error, jr.JRError) and runner.error.extra.get("job_id"):
            message += "\n(job %s)" % runner.error.extra["job_id"]
        _dialog("Render failed.\n\n" + message)
        return
    result = runner.result or {}
    files = result.get("files") or []
    lines = ["Done in %s GPU seconds." % result.get("gpu_seconds")]
    for w in result.get("warnings") or []:
        lines.append("Note: %s" % w)
    folder = os.path.dirname(files[0]) if files else ""
    lines.append("Saved to %s" % (folder or "(nothing downloaded)"))
    _set_status("\n".join(lines))
    main = jr.main_artifact(result.get("job") or {})
    target = next((f for f in files if os.path.basename(f) == main), None)
    if target:
        jr.open_path(target)
    elif folder:
        jr.open_path(folder)


def _values():
    fmt = cmds.optionMenuGrp(_ui["format"], query=True, value=True)
    start = int(cmds.intFieldGrp(_ui["range"], query=True, value1=True))
    end = int(cmds.intFieldGrp(_ui["range"], query=True, value2=True))
    env = cmds.optionMenuGrp(_ui["lighting"], query=True, value=True)
    width = int(cmds.intFieldGrp(_ui["size"], query=True, value1=True))
    height = int(cmds.intFieldGrp(_ui["size"], query=True, value2=True))
    samples = int(cmds.intFieldGrp(_ui["samples"], query=True, value1=True))
    if end < start:
        start, end = end, start
    environment = "" if env == "scene lights only" else env
    return fmt, start, end, environment, width, height, samples


def _start(mode):
    """Button handler: export on the main thread, then upload/render in a background thread."""
    global _runner
    if _runner is not None and not _runner.done:
        _dialog("A job is already running. Cancel it or wait for it to finish.")
        return
    try:
        fmt, start, end, environment, width, height, samples = _values()
    except Exception as exc:  # noqa: BLE001
        _dialog("Please check the fields: %s" % exc)
        return
    if mode == "turntable":
        current = int(round(cmds.currentTime(query=True)))
        start = end = current
    _set_status("Exporting %s..." % ("USD" if fmt == FORMAT_USD else "FBX"))
    cmds.refresh(force=True)
    try:
        path, assets, notes, tmp = export_scene(fmt, start, end)
    except Exception as exc:  # noqa: BLE001
        _set_status("Export failed: %s" % exc)
        _dialog("Export failed:\n%s" % exc)
        return
    params = {"environment": environment}
    if mode == "preview":
        kind = "preview"
        params["frames"] = jr.preview_frames(start, end, 4)
        timeout_s = 900
    elif mode == "turntable":
        kind = "preview"
        params["orbit"] = True  # the service picks 0/90/180/270 degrees around the model
        timeout_s = 900
    else:
        kind = "final"
        width, height = jr.fit_free_size(width, height)
        params.update({"frame_start": start, "frame_end": end, "width": width, "height": height,
                       "samples": samples, "fps": scene_fps(), "output": "mp4" if end > start else "png"})
        timeout_s = 3600
        if end - start + 1 > jr.FREE_MAX_FRAMES:
            _set_status("A job renders at most %d frames." % jr.FREE_MAX_FRAMES)
            _dialog("A job renders at most %d frames; narrow the frame range." % jr.FREE_MAX_FRAMES)
            return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(os.path.expanduser("~"), "janction_render", "maya", "%s_%s" % (stamp, mode))
    for n in notes:
        print("[%s] %s" % (TITLE, n))
    _runner = jr.BackgroundRender(path, kind, assets, out_dir, on_update=_on_update, timeout_s=timeout_s,
                                  cleanup=[tmp], client="jr-maya", **params)
    _enable(True)
    _set_status("Uploading %s (%d texture%s)..." % (os.path.basename(path), len(assets), "" if len(assets) == 1 else "s"))
    _runner.start()


def _cancel(*_args):
    if _runner is not None and not _runner.done:
        _runner.cancel()
        _set_status("Canceling...")


def show():
    """Open (or re-open) the window."""
    if cmds is None:
        raise RuntimeError("janction_render_maya.show() must run inside Maya")
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    start, end = frame_range()
    width, height = render_size()
    win = cmds.window(WINDOW, title=TITLE, widthHeight=(430, 360), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 10))
    cmds.separator(style="none", height=4)
    cmds.text(label="Export the scene and render it with Cycles on JANCTION GPUs (new keys start free).", align="left")
    _ui["format"] = cmds.optionMenuGrp(label="Export as", columnWidth=(1, 90), columnAlign=(1, "left"))
    formats = [FORMAT_USD, FORMAT_FBX] if usd_available() else [FORMAT_FBX]
    for name in formats:
        cmds.menuItem(label=name)
    _ui["range"] = cmds.intFieldGrp(numberOfFields=2, label="Frames", value1=start, value2=end,
                                    columnWidth=(1, 90), columnAlign=(1, "left"))
    _ui["lighting"] = cmds.optionMenuGrp(label="Lighting", columnWidth=(1, 90), columnAlign=(1, "left"))
    for name in LIGHTING:
        cmds.menuItem(label=name)
    _ui["size"] = cmds.intFieldGrp(numberOfFields=2, label="Final size", value1=width, value2=height,
                                   columnWidth=(1, 90), columnAlign=(1, "left"))
    _ui["samples"] = cmds.intFieldGrp(numberOfFields=1, label="Samples", value1=64,
                                      columnWidth=(1, 90), columnAlign=(1, "left"))
    cmds.rowLayout(numberOfColumns=4, columnWidth4=(100, 100, 100, 100), adjustableColumn=4)
    _ui["preview"] = cmds.button(label="Preview", annotation="4 frames across the range, tiled in one image",
                                 command=lambda *_a: _start("preview"))
    _ui["final"] = cmds.button(label="Final (MP4)", annotation="every frame of the range at the final size",
                               command=lambda *_a: _start("final"))
    _ui["turntable"] = cmds.button(label="Turntable", annotation="the current frame from 0/90/180/270 degrees",
                                   command=lambda *_a: _start("turntable"))
    _ui["cancel"] = cmds.button(label="Cancel", enable=False, command=_cancel)
    cmds.setParent("..")
    _ui["status"] = cmds.text(label="Ready. Exports go to a temp folder; results to ~/janction_render/maya.",
                              align="left", wordWrap=True, height=90)
    cmds.text(label="Lighting presets replace the scene lights with a studio HDRI; exported files rarely carry usable lights.",
              align="left", wordWrap=True, font="smallObliqueLabelFont")
    cmds.showWindow(win)
    return win


if __name__ == "__main__" and cmds is not None:
    show()
