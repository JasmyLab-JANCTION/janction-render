"""JANCTION Render for Houdini: export /obj to Alembic (or use a USD ROP) and render it with Cycles on JANCTION GPUs.

Karma/Mantra cannot run on the farm, so this shelf tool writes the geometry out as a file Blender
can import, sends it, and opens the result (sheet.png or output.mp4).

Install (shelf tool): right-click a shelf > New Tool > Script tab (Python):

    import sys; sys.path.append(r"C:/path/to/integrations/houdini")
    import janction_render_houdini; janction_render_houdini.main()

Keep jr_submit.py in the folder above this file (integrations/) or next to it.
Python 3 (Houdini 18.5 and newer). Nothing else to install.
"""
import os
import sys
import tempfile
import time

try:
    import hou
except ImportError:  # outside Houdini (tests, syntax checks)
    hou = None

_HERE = os.path.dirname(os.path.abspath(__file__))
for _folder in (_HERE, os.path.dirname(_HERE)):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)
import jr_submit as jr  # noqa: E402

TITLE = "JANCTION Render"
ROP_NAME = "janction_render_abc"
LIGHTING = ("studio", "sunset", "overcast", "night", "")
SOURCE_ALEMBIC = "Export /obj to Alembic (geometry and cameras; no lights or materials)"
SOURCE_USD_ROP = "Render an existing USD ROP and send its output file"
SOURCE_FILE = "Pick a 3D file on disk (.usd .abc .fbx .obj .glb ...)"

_state = {"runner": None, "callback": None, "last_text": ""}


# ---------------------------------------------------------------- scene queries

def usd_rops():
    """USD ROP nodes in /out and /stage (type 'usd' in ROP networks, 'usd_rop' in LOP networks)."""
    found = []
    for root in ("/out", "/stage"):
        node = hou.node(root)
        if node is None:
            continue
        for child in node.allSubChildren():
            try:
                if child.type().name() in ("usd", "usd_rop"):
                    found.append(child)
            except Exception:  # noqa: BLE001
                continue
    return found


def frame_range():
    start, end = hou.playbar.playbackRange()
    start, end = int(round(start)), int(round(end))
    return start, max(start, end)


def render_size():
    """Resolution of the first camera in /obj, else 1920x1080."""
    obj = hou.node("/obj")
    if obj is not None:
        for child in obj.children():
            try:
                if child.type().name() == "cam":
                    w, h = child.parmTuple("res").eval()
                    return int(w), int(h)
            except Exception:  # noqa: BLE001
                continue
    return 1920, 1080


# ---------------------------------------------------------------- export

def _set_parm(node, name, value):
    parm = node.parm(name)
    if parm is None:
        return
    try:
        parm.deleteAllKeyframes()
    except Exception:  # noqa: BLE001
        pass
    try:
        parm.set(value)
    except Exception:  # noqa: BLE001 - a menu without that entry: keep the default
        pass


def export_alembic(path, start, end):
    """Create or reuse /out/janction_render_abc (type alembic), export /obj over start..end."""
    out = hou.node("/out")
    if out is None:
        raise RuntimeError("no /out network in this scene")
    rop = out.node(ROP_NAME)
    if rop is not None and rop.type().name() != "alembic":
        raise RuntimeError("/out/%s exists but is not an Alembic ROP; rename it" % ROP_NAME)
    if rop is None:
        rop = out.createNode("alembic", ROP_NAME)
        try:
            rop.moveToGoodPosition()
        except Exception:  # noqa: BLE001
            pass
    _set_parm(rop, "trange", 1 if end > start else 0)
    _set_parm(rop, "f1", start)
    _set_parm(rop, "f2", end)
    _set_parm(rop, "f3", 1)
    _set_parm(rop, "filename", path.replace("\\", "/"))
    _set_parm(rop, "root", "/obj")
    _set_parm(rop, "objects", "*")
    _set_parm(rop, "collapse", 1)
    _set_parm(rop, "build_from_path", 0)
    _set_parm(rop, "format", "ogawa")
    rop.render(frame_range=(start, end, 1), verbose=False)
    if not os.path.isfile(path):
        raise RuntimeError("the Alembic ROP produced no file at %s" % path)
    return rop


def export_usd_rop(rop, start, end):
    """Render the given USD ROP for start..end and return its output file."""
    rop.render(frame_range=(start, end, 1), verbose=False)
    path = None
    for name in ("lopoutput", "sopoutput", "usdfile"):
        parm = rop.parm(name)
        if parm is not None:
            path = hou.expandString(parm.eval())
            break
    if not path or not os.path.isfile(path):
        raise RuntimeError("the USD ROP %s produced no file (%s)" % (rop.path(), path))
    if os.path.splitext(path)[1].lower() not in jr.SCENE_SUFFIXES:
        raise RuntimeError("%s is not a file type the service accepts" % path)
    return path


def usd_assets(path):
    """Textures referenced by an ASCII USD file, renamed to basenames inside the file. (binary USD: none)"""
    found = jr.scan_usda_asset_paths(path)
    if not found:
        return [], []
    names = dict((os.path.basename(full).lower(), name) for name, full, _ref in found)
    jr.rewrite_usda_asset_paths(path, names)
    return [(name, full) for name, full, _ref in found], \
        ["%d texture path(s) rewritten to relative names" % len(found)]


# ---------------------------------------------------------------- UI

def _message(text, error=False):
    sev = hou.severityType.Error if error else hou.severityType.Message
    hou.ui.displayMessage(text, title=TITLE, severity=sev)


def _status(text, error=False):
    try:
        sev = hou.severityType.Error if error else hou.severityType.Message
        hou.ui.setStatusMessage("%s: %s" % (TITLE, text), severity=sev)
    except Exception:  # noqa: BLE001
        print("[%s] %s" % (TITLE, text))


def _poll():
    """Event-loop callback (main thread): mirror the worker's text, finish when it is done."""
    runner = _state["runner"]
    if runner is None:
        _stop_polling()
        return
    if runner.text != _state["last_text"]:
        _state["last_text"] = runner.text
        _status(runner.text)
    if not runner.done:
        return
    _stop_polling()
    _state["runner"] = None
    if runner.error is not None:
        text = runner.text
        if isinstance(runner.error, jr.JRError) and runner.error.extra.get("job_id"):
            text += "\n(job %s)" % runner.error.extra["job_id"]
        _status("failed", error=True)
        _message("Render failed.\n\n" + text, error=True)
        return
    result = runner.result or {}
    files = result.get("files") or []
    folder = os.path.dirname(files[0]) if files else ""
    lines = ["Done in %s GPU seconds." % result.get("gpu_seconds")]
    lines += ["Note: %s" % w for w in result.get("warnings") or []]
    lines.append("Saved to %s" % (folder or "(nothing downloaded)"))
    _status("done, %s GPU seconds" % result.get("gpu_seconds"))
    main = jr.main_artifact(result.get("job") or {})
    target = next((f for f in files if os.path.basename(f) == main), None)
    if target:
        jr.open_path(target)
    elif folder:
        jr.open_path(folder)
    _message("\n".join(lines))


def _stop_polling():
    cb = _state.get("callback")
    if cb is not None:
        try:
            hou.ui.removeEventLoopCallback(cb)
        except Exception:  # noqa: BLE001
            pass
        _state["callback"] = None


def _ask_settings(start, end, width, height):
    """One dialog for the numbers plus the mode buttons. Returns (mode, values) or (None, None)."""
    labels = ("Start frame", "End frame", "Lighting (studio / sunset / overcast / night / empty = scene lights)",
              "Final width", "Final height", "Samples (final)")
    initial = (str(start), str(end), "studio", str(width), str(height), "64")
    choice, values = hou.ui.readMultiInput(
        "Export the scene and render it with Cycles on JANCTION GPUs (free beta).\n"
        "Preview: 4 frames across the range in one image. Final: MP4 (or PNG for one frame).\n"
        "Turntable: the current frame from 0/90/180/270 degrees.",
        input_labels=labels, initial_contents=initial, buttons=("Preview", "Final", "Turntable", "Cancel"),
        default_choice=0, close_choice=3, title=TITLE)
    if choice == 3:
        return None, None
    return ("preview", "final", "turntable")[choice], values


def main():
    """Entry point for the shelf tool."""
    if hou is None:
        raise RuntimeError("janction_render_houdini.main() must run inside Houdini")
    runner = _state["runner"]
    if runner is not None and not runner.done:
        pick = hou.ui.displayMessage("A JANCTION Render job is still running.\n\n%s" % runner.text,
                                     buttons=("Keep waiting", "Cancel the job"), title=TITLE)
        if pick == 1:
            runner.cancel()
        return
    try:
        _run()
    except Exception as exc:  # noqa: BLE001 - never let a tool error reach Houdini's console only
        _status("failed", error=True)
        _message("%s: %s" % (type(exc).__name__, exc), error=True)


def _run():
    start, end = frame_range()
    width, height = render_size()
    rops = usd_rops()
    sources = [SOURCE_ALEMBIC] + ([SOURCE_USD_ROP] if rops else []) + [SOURCE_FILE]
    picked = hou.ui.selectFromList(sources, default_choices=(0,), exclusive=True, message="What should be sent?",
                                   title=TITLE, column_header="Source", clear_on_cancel=True)
    if not picked:
        return
    source = sources[picked[0]]
    rop = None
    if source == SOURCE_USD_ROP:
        names = [n.path() for n in rops]
        chosen = hou.ui.selectFromList(names, default_choices=(0,), exclusive=True, message="Which USD ROP?",
                                       title=TITLE, column_header="ROP", clear_on_cancel=True)
        if not chosen:
            return
        rop = rops[chosen[0]]
    mode, values = _ask_settings(start, end, width, height)
    if mode is None:
        return
    try:
        start, end = int(float(values[0])), int(float(values[1]))
        env = values[2].strip().lower()
        width, height = int(float(values[3])), int(float(values[4]))
        samples = int(float(values[5]))
    except ValueError as exc:
        raise RuntimeError("please enter whole numbers: %s" % exc)
    if end < start:
        start, end = end, start
    if env not in LIGHTING:
        raise RuntimeError("lighting must be one of studio, sunset, overcast, night, or empty")
    if mode == "turntable":
        start = end = int(round(hou.frame()))
    if mode == "final" and end - start + 1 > jr.FREE_MAX_FRAMES:
        raise RuntimeError("the free beta renders at most %d frames per job; narrow the range" % jr.FREE_MAX_FRAMES)

    tmp = None
    assets = []
    notes = []
    _status("exporting...")
    if source == SOURCE_ALEMBIC:
        tmp = tempfile.mkdtemp(prefix="janction_render_houdini_")
        path = os.path.join(tmp, "houdini_scene.abc")
        export_alembic(path, start, end)
        notes.append("Alembic carries geometry and cameras only: lights and materials are not exported, "
                     "so the %s preset lights the render" % (env or "studio"))
        if not env:
            env = "studio"
    elif source == SOURCE_USD_ROP:
        path = export_usd_rop(rop, start, end)
        assets, notes = usd_assets(path)
    else:
        pattern = " ".join("*" + s for s in jr.SCENE_SUFFIXES if s not in (".blend", ".py"))
        path = hou.ui.selectFile(title="Pick a 3D file to render", pattern=pattern, chooser_mode=hou.fileChooserMode.Read)
        path = hou.expandString(path or "")
        if not path:
            return
        if not os.path.isfile(path):
            raise RuntimeError("not a file: %s" % path)
        if path.lower().endswith(".usda"):
            assets, notes = usd_assets(path)
    for n in notes:
        print("[%s] %s" % (TITLE, n))

    params = {"environment": env}
    if mode == "preview":
        kind = "preview"
        params["frames"] = jr.preview_frames(start, end, 4)
        timeout_s = 900
    elif mode == "turntable":
        kind = "preview"
        params["orbit"] = True
        timeout_s = 900
    else:
        kind = "final"
        width, height = jr.fit_free_size(width, height)
        params.update({"frame_start": start, "frame_end": end, "width": width, "height": height,
                       "samples": samples, "fps": max(1, min(120, int(round(hou.fps())))),
                       "output": "mp4" if end > start else "png"})
        timeout_s = 3600
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(os.path.expanduser("~"), "janction_render", "houdini", "%s_%s" % (stamp, mode))
    runner = jr.BackgroundRender(path, kind, assets, out_dir, timeout_s=timeout_s, cleanup=[tmp] if tmp else [],
                                 client="jr-houdini", **params)
    _state["runner"] = runner
    _state["last_text"] = ""
    _status("uploading %s..." % os.path.basename(path))
    runner.start()
    _state["callback"] = _poll
    hou.ui.addEventLoopCallback(_poll)


if __name__ == "__main__" and hou is not None:
    main()
