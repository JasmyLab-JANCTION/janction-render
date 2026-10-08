"""JANCTION Render for Cinema 4D: export the document (FBX or USD) and render it with Cycles on JANCTION GPUs.

Cinema 4D's renderers cannot run on the farm, so this Script Manager script exports the active
document to a file Blender can import, sends it with the bitmap textures it finds, and opens
the result (sheet.png or output.mp4).

Install: Script > Script Manager > File > Import Script (this file). Put jr_submit.py (from the
folder above) next to it, or anywhere on Python's path (for example the C4D python library
folder: C4D Preferences > Open Preferences Folder > python3xx > libs).

Python 3 (Cinema 4D R23 and newer). Nothing else to install.
"""
import os
import sys
import tempfile
import time

try:
    import c4d
    from c4d import gui
except ImportError:  # outside Cinema 4D (tests, syntax checks)
    c4d = None
    gui = None

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
for _folder in (_HERE, os.path.dirname(_HERE)):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)
try:
    import jr_submit as jr
except ImportError:  # reported by main() with a dialog instead of a console traceback
    jr = None

TITLE = "JANCTION Render"
FBX_EXPORTER = 1026370
USD_EXPORTER = 1055179
LIGHTING = ("studio", "sunset", "overcast", "night", "scene lights only")

# dialog ids
ID_FORMAT = 1001
ID_START = 1002
ID_END = 1003
ID_LIGHTING = 1004
ID_WIDTH = 1005
ID_HEIGHT = 1006
ID_SAMPLES = 1007
ID_PREVIEW = 1010
ID_FINAL = 1011
ID_TURNTABLE = 1012
ID_CANCEL = 1013
ID_CLOSE = 1014
ID_STATUS = 1020
CHILD_FBX = 0
CHILD_USD = 1


# ---------------------------------------------------------------- scene queries

def doc_info(doc):
    fps = int(doc.GetFps()) or 30
    start = doc.GetMinTime().GetFrame(fps)
    end = doc.GetMaxTime().GetFrame(fps)
    current = doc.GetTime().GetFrame(fps)
    rd = doc.GetActiveRenderData()
    try:
        width, height = int(rd[c4d.RDATA_XRES]), int(rd[c4d.RDATA_YRES])
    except Exception:  # noqa: BLE001
        width, height = 1920, 1080
    return {"fps": max(1, min(120, fps)), "start": start, "end": max(start, end), "current": current,
            "width": width, "height": height}


def usd_available():
    try:
        return c4d.plugins.FindPlugin(USD_EXPORTER, c4d.PLUGINTYPE_SCENESAVER) is not None
    except Exception:  # noqa: BLE001
        return False


def _walk_shaders(shader, out):
    while shader is not None:
        try:
            if shader.GetType() == c4d.Xbitmap:
                name = shader[c4d.BITMAPSHADER_FILENAME]
                if name:
                    out.append(str(name))
        except Exception:  # noqa: BLE001
            pass
        _walk_shaders(shader.GetDown(), out)
        shader = shader.GetNext()


def _resolve_texture(doc_path, name):
    if os.path.isabs(name) and os.path.isfile(name):
        return os.path.abspath(name)
    try:
        found = c4d.GenerateTexturePath(doc_path, name, "")
        if found and os.path.isfile(found):
            return os.path.abspath(found)
    except Exception:  # noqa: BLE001
        pass
    for folder in (doc_path, os.path.join(doc_path, "tex")):
        candidate = os.path.join(folder, name)
        if folder and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def collect_textures(doc):
    """Bitmap shaders of all materials (color, bump, normal, ... channels and nested shaders).
    Returns ([(asset_name, absolute_path)], notes). Node materials are not inspected."""
    doc_path = doc.GetDocumentPath() or ""
    raw = []
    for mat in doc.GetMaterials():
        try:
            _walk_shaders(mat.GetFirstShader(), raw)
        except Exception:  # noqa: BLE001
            continue
    out = []
    notes = []
    seen = {}
    for name in raw:
        if jr.is_sequence_path(name):
            notes.append("sequence / UDIM textures are not sent (%s)" % name)
            continue
        full = _resolve_texture(doc_path, name)
        if full is None:
            notes.append("texture not found on disk (%s)" % name)
            continue
        asset = jr.safe_asset_name(full)
        if not asset:
            notes.append("file type not accepted by the service (%s)" % os.path.basename(full))
            continue
        if asset in seen:
            if seen[asset].lower() != full.lower():
                notes.append("two textures share the name %s; only %s is sent" % (asset, seen[asset]))
            continue
        seen[asset] = full
        if asset != os.path.basename(full):
            notes.append("%s is sent as %s (only letters, digits, . _ - are accepted)" % (os.path.basename(full), asset))
        out.append((asset, full))
    return out, notes


# ---------------------------------------------------------------- export

def _exporter_settings(plugin_id, values):
    """Set options on an exporter's container (values: {c4d attribute name: value}); missing ones are skipped."""
    plug = c4d.plugins.FindPlugin(plugin_id, c4d.PLUGINTYPE_SCENESAVER)
    if plug is None:
        raise RuntimeError("exporter %d is not installed" % plugin_id)
    data = {}
    if not plug.Message(c4d.MSG_RETRIEVEPRIVATEDATA, data):
        return
    container = data.get("imexporter")
    if container is None:
        return
    for attr, value in values.items():
        key = getattr(c4d, attr, None)
        if key is not None:
            try:
                container[key] = value
            except Exception:  # noqa: BLE001
                pass


def export_fbx(doc, path, animation=True):
    _exporter_settings(FBX_EXPORTER, {
        "FBXEXPORT_CAMERAS": True, "FBXEXPORT_LIGHTS": True, "FBXEXPORT_TRACKS": animation,
        "FBXEXPORT_BAKE_ALL_FRAMES": animation, "FBXEXPORT_EMBED_TEXTURES": False, "FBXEXPORT_ASCII": False,
        "FBXEXPORT_SELECTION_ONLY": False, "FBXEXPORT_SAVE_NORMALS": True, "FBXEXPORT_TRIANGULATE": False,
        "FBXEXPORT_MATERIALS": True, "FBXEXPORT_TEXTURES": True,
    })
    ok = c4d.documents.SaveDocument(doc, path, c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST, FBX_EXPORTER)
    if not ok or not os.path.isfile(path):
        raise RuntimeError("FBX export failed (%s)" % path)


def export_usd(doc, path):
    if not usd_available():
        raise RuntimeError("the USD exporter (id %d) is not installed; choose FBX" % USD_EXPORTER)
    ok = c4d.documents.SaveDocument(doc, path, c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST, USD_EXPORTER)
    if not ok or not os.path.isfile(path):
        raise RuntimeError("USD export failed (%s)" % path)


def export_scene(doc, use_usd, animation=True):
    """Export to a temp folder. Returns (file_path, assets, notes, temp_dir)."""
    tmp = tempfile.mkdtemp(prefix="janction_render_c4d_")
    textures, notes = collect_textures(doc)
    if use_usd:
        path = os.path.join(tmp, "c4d_scene.usda")
        export_usd(doc, path)
        names = dict((os.path.basename(full).lower(), name) for name, full in textures)
        for name, full, _ref in jr.scan_usda_asset_paths(path):
            if name not in names.values():
                textures.append((name, full))
                names[os.path.basename(full).lower()] = name
        rewritten = jr.rewrite_usda_asset_paths(path, names)
        if rewritten:
            notes.append("%d texture path(s) rewritten to relative names" % rewritten)
        elif textures:
            notes.append("no texture path in the USD could be rewritten (binary file?); textures may be missing")
    else:
        path = os.path.join(tmp, "c4d_scene.fbx")
        export_fbx(doc, path, animation)
        if textures:
            notes.append("Blender looks for the FBX's textures next to the file by basename; "
                         "renamed textures (see above) will be missing")
    return path, textures, notes, tmp


# ---------------------------------------------------------------- UI

class RenderDialog(gui.GeDialog if gui is not None else object):
    """Settings, three buttons, a status line. A timer mirrors the background thread's progress."""

    def __init__(self, doc):
        if gui is not None:
            gui.GeDialog.__init__(self)
        self.doc = doc
        self.info = doc_info(doc)
        self.runner = None
        self.has_usd = usd_available()

    def _label(self, text, flags=None):
        self._next_id += 1
        self.AddStaticText(self._next_id, c4d.BFH_LEFT if flags is None else flags, name=text)

    def CreateLayout(self):
        self._next_id = 3000
        self.SetTitle(TITLE)
        self.GroupBegin(2000, c4d.BFH_SCALEFIT, cols=1, rows=0)
        self.GroupBorderSpace(10, 10, 10, 10)
        self._label("Export the document and render it with Cycles on JANCTION GPUs (new keys start free).", c4d.BFH_SCALEFIT)
        self.GroupBegin(2002, c4d.BFH_SCALEFIT, cols=2, rows=0)
        self._label("Export as")
        self.AddComboBox(ID_FORMAT, c4d.BFH_SCALEFIT)
        self.AddChild(ID_FORMAT, CHILD_FBX, "FBX")
        if self.has_usd:
            self.AddChild(ID_FORMAT, CHILD_USD, "USD (.usda)")
        self._label("Frames")
        self.GroupBegin(2003, c4d.BFH_SCALEFIT, cols=3, rows=0)
        self.AddEditNumberArrows(ID_START, c4d.BFH_SCALEFIT)
        self._label("to", c4d.BFH_CENTER)
        self.AddEditNumberArrows(ID_END, c4d.BFH_SCALEFIT)
        self.GroupEnd()
        self._label("Lighting")
        self.AddComboBox(ID_LIGHTING, c4d.BFH_SCALEFIT)
        for i, name in enumerate(LIGHTING):
            self.AddChild(ID_LIGHTING, i, name)
        self._label("Final size")
        self.GroupBegin(2004, c4d.BFH_SCALEFIT, cols=3, rows=0)
        self.AddEditNumberArrows(ID_WIDTH, c4d.BFH_SCALEFIT)
        self._label("x", c4d.BFH_CENTER)
        self.AddEditNumberArrows(ID_HEIGHT, c4d.BFH_SCALEFIT)
        self.GroupEnd()
        self._label("Samples")
        self.AddEditNumberArrows(ID_SAMPLES, c4d.BFH_SCALEFIT)
        self.GroupEnd()
        self.GroupBegin(2005, c4d.BFH_SCALEFIT, cols=4, rows=0)
        self.AddButton(ID_PREVIEW, c4d.BFH_SCALEFIT, name="Preview")
        self.AddButton(ID_FINAL, c4d.BFH_SCALEFIT, name="Final (MP4)")
        self.AddButton(ID_TURNTABLE, c4d.BFH_SCALEFIT, name="Turntable")
        self.AddButton(ID_CANCEL, c4d.BFH_SCALEFIT, name="Cancel job")
        self.GroupEnd()
        self.AddMultiLineEditText(ID_STATUS, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, inith=70,
                                  style=c4d.DR_MULTILINE_READONLY | c4d.DR_MULTILINE_WORDWRAP)
        self._label("Lighting presets replace the scene lights with an HDRI; FBX/USD exports rarely carry usable lights.",
                    c4d.BFH_SCALEFIT)
        self.AddButton(ID_CLOSE, c4d.BFH_RIGHT, name="Close")
        self.GroupEnd()
        return True

    def InitValues(self):
        self.SetInt32(ID_FORMAT, CHILD_FBX)
        self.SetInt32(ID_START, self.info["start"], min=-100000, max=1000000)
        self.SetInt32(ID_END, self.info["end"], min=-100000, max=1000000)
        self.SetInt32(ID_LIGHTING, 0)
        self.SetInt32(ID_WIDTH, self.info["width"], min=16, max=7680)
        self.SetInt32(ID_HEIGHT, self.info["height"], min=16, max=7680)
        self.SetInt32(ID_SAMPLES, 64, min=1, max=4096)
        self.Enable(ID_CANCEL, False)
        self.SetString(ID_STATUS, "Ready. Exports go to a temp folder; results to ~/janction_render/cinema4d.")
        return True

    def _set_status(self, text):
        self.SetString(ID_STATUS, text)

    def _enable(self, running):
        for cid in (ID_PREVIEW, ID_FINAL, ID_TURNTABLE, ID_FORMAT, ID_START, ID_END, ID_LIGHTING,
                    ID_WIDTH, ID_HEIGHT, ID_SAMPLES):
            self.Enable(cid, not running)
        self.Enable(ID_CANCEL, running)

    def Command(self, cid, msg):
        if cid in (ID_PREVIEW, ID_FINAL, ID_TURNTABLE):
            mode = {ID_PREVIEW: "preview", ID_FINAL: "final", ID_TURNTABLE: "turntable"}[cid]
            try:
                self._start(mode)
            except Exception as exc:  # noqa: BLE001 - every failure becomes text, never a crash
                self._set_status("Failed: %s" % exc)
                gui.MessageDialog("%s\n\n%s" % (TITLE, exc))
        elif cid == ID_CANCEL:
            if self.runner is not None and not self.runner.done:
                self.runner.cancel()
                self._set_status("Canceling...")
        elif cid == ID_CLOSE:
            if self.runner is not None and not self.runner.done:
                if not gui.QuestionDialog("A job is still running. Close anyway? (it keeps running on the service; "
                                          "the files are not downloaded)"):
                    return True
                self.SetTimer(0)
            self.Close()
        return True

    def _start(self, mode):
        if self.runner is not None and not self.runner.done:
            raise RuntimeError("a job is already running; cancel it or wait")
        use_usd = self.has_usd and self.GetInt32(ID_FORMAT) == CHILD_USD
        start, end = self.GetInt32(ID_START), self.GetInt32(ID_END)
        if end < start:
            start, end = end, start
        lighting = LIGHTING[self.GetInt32(ID_LIGHTING)]
        env = "" if lighting == "scene lights only" else lighting
        width, height = self.GetInt32(ID_WIDTH), self.GetInt32(ID_HEIGHT)
        samples = self.GetInt32(ID_SAMPLES)
        if mode == "turntable":
            start = end = self.info["current"]
        if mode == "final" and end - start + 1 > jr.FREE_MAX_FRAMES:
            raise RuntimeError("a job renders at most %d frames; narrow the range" % jr.FREE_MAX_FRAMES)
        self._set_status("Exporting %s..." % ("USD" if use_usd else "FBX"))
        c4d.StatusSetText("%s: exporting" % TITLE)
        try:
            path, assets, notes, tmp = export_scene(self.doc, use_usd, animation=(mode != "turntable"))
        finally:
            c4d.StatusClear()
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
                           "samples": samples, "fps": self.info["fps"], "output": "mp4" if end > start else "png"})
            timeout_s = 3600
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_dir = os.path.join(os.path.expanduser("~"), "janction_render", "cinema4d", "%s_%s" % (stamp, mode))
        self.runner = jr.BackgroundRender(path, kind, assets, out_dir, timeout_s=timeout_s, cleanup=[tmp],
                                          client="jr-cinema4d", **params)
        self._enable(True)
        self._set_status("Uploading %s (%d texture%s)..." % (os.path.basename(path), len(assets),
                                                             "" if len(assets) == 1 else "s"))
        self.runner.start()
        self.SetTimer(500)

    def Timer(self, msg):
        runner = self.runner
        if runner is None:
            self.SetTimer(0)
            return
        self._set_status(runner.text)
        if not runner.done:
            return
        self.SetTimer(0)
        self._enable(False)
        self.runner = None
        if runner.error is not None:
            text = runner.text
            if isinstance(runner.error, jr.JRError) and runner.error.extra.get("job_id"):
                text += "\n(job %s)" % runner.error.extra["job_id"]
            self._set_status("Failed: " + text)
            gui.MessageDialog("%s\n\nRender failed.\n%s" % (TITLE, text))
            return
        result = runner.result or {}
        files = result.get("files") or []
        folder = os.path.dirname(files[0]) if files else ""
        lines = ["Done in %s GPU seconds." % result.get("gpu_seconds")]
        lines += ["Note: %s" % w for w in result.get("warnings") or []]
        lines.append("Saved to %s" % (folder or "(nothing downloaded)"))
        self._set_status("\n".join(lines))
        main = jr.main_artifact(result.get("job") or {})
        target = next((f for f in files if os.path.basename(f) == main), None)
        if target:
            jr.open_path(target)
        elif folder:
            jr.open_path(folder)


def main():
    """Script Manager entry point."""
    if c4d is None:
        raise RuntimeError("janction_render_c4d.main() must run inside Cinema 4D")
    if jr is None:
        gui.MessageDialog("%s: jr_submit.py was not found. Put it next to this script or in the "
                          "preferences python libs folder." % TITLE)
        return
    doc = c4d.documents.GetActiveDocument()
    if doc is None:
        gui.MessageDialog("%s: no active document" % TITLE)
        return
    dlg = RenderDialog(doc)
    dlg.Open(c4d.DLG_TYPE_MODAL_RESIZEABLE, defaultw=460, defaulth=0)


if __name__ == "__main__" and c4d is not None:
    main()
