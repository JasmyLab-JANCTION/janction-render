"""Operators: preview, estimate, final render, cancel, open results, refresh quota.

A render runs in a background thread (``Runner``): save a copy of the file on
the main thread, then upload, submit, poll every 2 seconds and download without
blocking Blender. A ``bpy.app.timers`` tick on the main thread redraws the
panel and loads the finished preview into an Image Editor.
"""
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

import bpy

from . import assets as assets_mod
from . import state
from .client import Client, JRError
from .prefs import get_prefs, make_client

FREE_MAX_FRAMES = 240
FREE_MAX_PIXELS = 1920 * 1080
PREVIEW_SAMPLES_MAX = 32
FINAL_SAMPLES_MAX = 128
POLL_SECONDS = 2.0
TICK_SECONDS = 1.0
RESULTS_FOLDER = "janction_render"

_runner: Optional["Runner"] = None


# ---- pure helpers (no bpy) ---------------------------------------------------

def preview_frames(start: int, end: int, current: int, count: int = 4) -> list[int]:
    """Up to ``count`` frames spread over start..end; the current frame when the range is one frame."""
    if end <= start:
        return [int(current)]
    n = min(count, end - start + 1)
    out: list[int] = []
    for i in range(n):
        f = start + round(i * (end - start) / (n - 1))
        if f not in out:
            out.append(int(f))
    return out


def fit_pixels(width: int, height: int, max_pixels: int = FREE_MAX_PIXELS) -> tuple[int, int]:
    """Shrink (keeping the aspect) until width*height fits the per-job pixel cap (1080p)."""
    if width * height <= max_pixels:
        return width, height
    scale = (max_pixels / float(width * height)) ** 0.5
    return max(16, int(width * scale) // 2 * 2), max(16, int(height * scale) // 2 * 2)


def progress_text(job: dict[str, Any]) -> str:
    status = str(job.get("status") or "")
    prog = job.get("progress") or {}
    eta = job.get("eta") or {}
    human = str(eta.get("human") or "") if isinstance(eta, dict) else ""
    if status == "queued":
        ahead = int(prog.get("queue_ahead") or 0)
        text = "Queued" + (f", {ahead} ahead" if ahead else "")
    elif status == "running":
        text = f"Rendering {int(prog.get('frames_done') or 0)}/{int(prog.get('frames_total') or 0)} frames"
    else:
        text = status.capitalize()
    if human and status in ("queued", "running"):
        text += f" ({human})"
    return text


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


# ---- bpy helpers ------------------------------------------------------------

def _results_dir(fallback: Path) -> Path:
    if bpy.data.filepath:
        return Path(bpy.data.filepath).parent / RESULTS_FOLDER
    return fallback


def _save_copy(tmp_dir: Path) -> Path:
    """Write a copy of the open file to tmp_dir. Relative paths are kept as written
    (relative_remap=False) so textures sent as assets resolve on the server."""
    name = (Path(bpy.data.filepath).stem if bpy.data.filepath else "untitled") + ".blend"
    dest = tmp_dir / name
    result = bpy.ops.wm.save_as_mainfile(filepath=str(dest), copy=True, relative_remap=False, compress=True)
    if 'FINISHED' not in result or not dest.is_file():
        raise JRError("save_failed", "could not save a copy of the file")
    return dest


def _resolution(scene) -> tuple[int, int]:
    r = scene.render
    pct = max(1, int(r.resolution_percentage)) / 100.0
    return max(16, int(r.resolution_x * pct)), max(16, int(r.resolution_y * pct))


def _samples(scene, settings, cap: int) -> int:
    if not settings.use_scene_samples:
        return int(settings.samples)
    cycles = getattr(scene, "cycles", None)
    scene_samples = int(getattr(cycles, "samples", 0) or 0) or 64
    return max(1, min(scene_samples, cap))


def _fps(scene) -> int:
    r = scene.render
    base = float(getattr(r, "fps_base", 1.0) or 1.0)
    return max(1, min(120, int(round(r.fps / base))))


def _environment(prefs, settings) -> str:
    value = settings.environment if settings.environment != 'DEFAULT' else (prefs.environment if prefs else 'SCENE')
    return "" if value == 'SCENE' else str(value)


def _blender_version(prefs, settings) -> str:
    value = settings.blender_version if settings.blender_version != 'DEFAULT' else (prefs.blender_version if prefs else 'AUTO')
    if value == 'AUTO':
        # A file saved by this Blender must not be opened by an older one on the worker: 5.2 for Blender 5.1+, else 5.0.
        running = tuple(getattr(getattr(bpy, "app", None), "version", (5, 0, 0)))[:2]
        return "5.2" if running >= (5, 1) else "5.0"
    return str(value)


def _common_body(context, prefs, settings) -> dict[str, Any]:
    scene = context.scene
    width, height = _resolution(scene)
    return {
        "camera": "",
        "environment": _environment(prefs, settings),
        "blender": _blender_version(prefs, settings),
        "width": width,
        "height": height,
        "fps": _fps(scene),
    }


def preview_body(context, prefs, settings) -> dict[str, Any]:
    scene = context.scene
    body = _common_body(context, prefs, settings)
    body.update({
        "kind": "preview",
        "frames": preview_frames(scene.frame_start, scene.frame_end, scene.frame_current),
        "samples": _samples(scene, settings, PREVIEW_SAMPLES_MAX),
    })
    return body


def final_body(context, prefs, settings) -> tuple[dict[str, Any], list[str]]:
    """The /v1/jobs body for a final render plus the adjustments made for the per-job limits."""
    scene = context.scene
    notes: list[str] = []
    body = _common_body(context, prefs, settings)
    fs, fe = int(scene.frame_start), int(scene.frame_end)
    if fe < fs:
        fe = fs
    if fe - fs + 1 > FREE_MAX_FRAMES:
        fe = fs + FREE_MAX_FRAMES - 1
        notes.append(f"A job renders at most {FREE_MAX_FRAMES} frames; rendering {fs}-{fe}")
    w, h = fit_pixels(body["width"], body["height"])
    if (w, h) != (body["width"], body["height"]):
        notes.append(f"Resolution reduced to {w}x{h} (1080p cap per job)")
        body["width"], body["height"] = w, h
    output = str(settings.output)
    if fe == fs and output == "mp4":
        output = "png"
    body.update({
        "kind": "final",
        "frame_start": fs,
        "frame_end": fe,
        "samples": _samples(scene, settings, FINAL_SAMPLES_MAX),
        "output": output,
    })
    return body, notes


# ---- background runner --------------------------------------------------------

class Runner(threading.Thread):
    """Upload, submit, poll and download for one job. Never touches bpy."""

    def __init__(self, client: Client, kind: str, scene_path: Path, scene_assets: list[tuple[str, str]],
                 body: dict[str, Any], out_dir: Path, tmp_dir: Path, open_when_done: bool = False) -> None:
        super().__init__(name="janction-render", daemon=True)
        self.client = client
        self.kind = kind
        self.scene_path = scene_path
        self.scene_assets = scene_assets
        self.body = body
        self.out_dir = out_dir
        self.tmp_dir = tmp_dir
        self.open_when_done = open_when_done
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            self._run()
        except JRError as exc:
            text = f"{exc}"
            if exc.code == "quota_exceeded" and exc.resets_at_iso:
                text = f"Daily free quota used up; resets at {exc.resets_at_iso.replace('T', ' ').rstrip('Z')} UTC"
            state.fail(text)
        except Exception as exc:  # noqa: BLE001 - never let a thread die silently
            state.fail(f"{type(exc).__name__}: {exc}")
        finally:
            self._cleanup()
            self._refresh_quota()

    def _cleanup(self) -> None:
        try:
            if self.scene_path.parent == self.tmp_dir and self.scene_path.is_file():
                self.scene_path.unlink()
            if self.tmp_dir.is_dir() and not any(self.tmp_dir.iterdir()):
                self.tmp_dir.rmdir()
        except OSError:
            pass

    def _refresh_quota(self) -> None:
        try:
            state.set_quota(self.client.me())
        except JRError:
            pass

    def _canceled(self) -> bool:
        return self.cancel_event.is_set()

    def _run(self) -> None:
        state.update(phase="uploading", message="Uploading...")
        scene = self.client.upload_scene(self.scene_path, self.scene_assets,
                                         on_progress=lambda msg: state.update(message=msg))
        if self._canceled():
            state.update(phase="canceled", message="Canceled")
            return
        state.update(phase="submitting", message="Submitting...")
        body = dict(self.body)
        body["scene_id"] = scene["scene_id"]
        job = self.client.submit(body)
        job_id = str(job["job_id"])
        state.update(job_id=job_id, phase=str(job.get("status") or "queued"), message=progress_text(job))
        warnings = list(state.get("warnings") or [])
        while True:
            if self.cancel_event.wait(POLL_SECONDS):
                try:
                    self.client.cancel(job_id)
                except JRError:
                    pass
                state.update(phase="canceled", message="Canceled")
                return
            job = self.client.job(job_id)
            status = str(job.get("status") or "")
            for w in job.get("warnings") or []:
                if str(w) not in warnings:
                    warnings.append(str(w))
            if status in ("done", "failed", "canceled"):
                break
            state.update(phase=status if status in ("queued", "running") else "running",
                         message=progress_text(job), warnings=list(warnings))
        state.update(warnings=list(warnings))
        if status == "failed":
            state.fail(f"Render failed: {job.get('error') or 'unknown error'}")
            return
        if status == "canceled":
            state.update(phase="canceled", message="Canceled")
            return
        self._download(job)

    def _download(self, job: dict[str, Any]) -> None:
        job_id = str(job["job_id"])
        names = [str(a.get("name") or "") for a in (job.get("artifacts") or [])]
        gpu = job.get("gpu_seconds")
        took = f" ({gpu:.0f} GPU s)" if isinstance(gpu, (int, float)) else ""
        state.update(phase="downloading", message="Downloading...")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if self.kind == "preview":
            name = "sheet.png" if "sheet.png" in names else next((n for n in names if n.startswith("frame_")), "")
            if not name:
                state.fail("The render finished but produced no image")
                return
            dest = self.client.artifact(job_id, name, self.out_dir / f"preview_{stamp()}.png")
            state.update(phase="done", result=str(dest), pending_image=str(dest), message=f"Preview ready{took}")
            return
        if "output.mp4" in names:
            dest = self.client.artifact(job_id, "output.mp4", self.out_dir / f"final_{stamp()}.mp4")
            result: Path = dest
        else:
            frames = [n for n in names if n.startswith("frame_")]
            if not frames:
                state.fail("The render finished but produced no frames")
                return
            folder = self.out_dir / f"final_{stamp()}"
            for i, n in enumerate(frames, 1):
                if self._canceled():
                    state.update(phase="canceled", message="Canceled while downloading")
                    return
                state.update(message=f"Downloading {i}/{len(frames)}")
                self.client.artifact(job_id, n, folder / n)
            result = folder
        state.update(phase="done", result=str(result), message=f"Final render ready{took}",
                     pending_open=str(result) if self.open_when_done else "")


# ---- main-thread timer ----------------------------------------------------------

def _redraw() -> None:
    for wm in bpy.data.window_managers:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type in ('PROPERTIES', 'IMAGE_EDITOR', 'PREFERENCES'):
                    area.tag_redraw()


def _show_image(path: str) -> None:
    try:
        img = bpy.data.images.load(path, check_existing=True)
        img.reload()
    except Exception as exc:  # noqa: BLE001
        state.update(message=f"Saved {path} (could not load it: {exc})")
        return
    for wm in bpy.data.window_managers:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'IMAGE_EDITOR':
                    area.spaces.active.image = img
                    area.tag_redraw()
                    return
    state.update(message=f"Preview saved: {path} (open an Image Editor to see it here)")


def _tick() -> Optional[float]:
    image = state.pop("pending_image")
    if image:
        _show_image(image)
    to_open = state.pop("pending_open")
    if to_open:
        try:
            bpy.ops.wm.path_open(filepath=to_open)
        except Exception:  # noqa: BLE001
            pass
    _redraw()
    alive = _runner is not None and _runner.is_alive()
    if not alive and state.get("phase") in state.TERMINAL:
        return None
    return TICK_SECONDS


def _ensure_timer() -> None:
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=TICK_SECONDS, persistent=True)


def _stop_timer() -> None:
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)


# ---- starting a job (main thread) -----------------------------------------------

def start_job(context, kind: str, body: dict[str, Any], notes: list[str], report) -> bool:
    """Save a copy, collect assets and hand everything to a Runner. Reports problems; True when started."""
    global _runner
    prefs = get_prefs(context)
    if prefs is None or not prefs.api_key:
        report({'ERROR'}, "No API key: open the add-on preferences and press 'Get a free key'")
        return False
    if state.busy():
        report({'WARNING'}, "A render is already running")
        return False
    tmp_dir = Path(tempfile.mkdtemp(prefix="janction_render_"))
    try:
        state.start_job(kind, notes)
        scene_path = _save_copy(tmp_dir)
        collected = assets_mod.collect_from_bpy()
    except JRError as exc:
        state.fail(str(exc))
        report({'ERROR'}, str(exc))
        return False
    except Exception as exc:  # noqa: BLE001
        state.fail(f"{type(exc).__name__}: {exc}")
        report({'ERROR'}, f"Could not prepare the file: {exc}")
        return False
    warnings = notes + collected.warnings
    state.update(warnings=warnings)
    for w in collected.warnings:
        report({'WARNING'}, w)
    _runner = Runner(make_client(prefs), kind, scene_path, collected.assets, body, _results_dir(tmp_dir), tmp_dir,
                     open_when_done=bool(prefs.open_results) and kind == "final")
    _runner.start()
    _ensure_timer()
    report({'INFO'}, f"{kind.capitalize()} started: uploading {scene_path.name}"
                     + (f" and {len(collected.assets)} files" if collected.assets else ""))
    return True


# ---- operators ----------------------------------------------------------------

class JR_OT_preview(bpy.types.Operator):
    """Render up to 4 frames of this file on JANCTION GPUs as one preview sheet"""
    bl_idname = "jr.preview"
    bl_label = "Preview"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return not state.busy()

    def execute(self, context):
        settings = context.scene.jr_settings
        body = preview_body(context, get_prefs(context), settings)
        return {'FINISHED'} if start_job(context, "preview", body, [], self.report) else {'CANCELLED'}


class JR_OT_final(bpy.types.Operator):
    """Render the scene frame range on JANCTION GPUs (up to 240 frames at 1080p per job)"""
    bl_idname = "jr.final"
    bl_label = "Final render"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return not state.busy()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        settings = context.scene.jr_settings
        body, notes = final_body(context, get_prefs(context), settings)
        for n in notes:
            self.report({'WARNING'}, n)
        return {'FINISHED'} if start_job(context, "final", body, notes, self.report) else {'CANCELLED'}


class JR_OT_estimate(bpy.types.Operator):
    """Ask the server how long the final render would take and whether it fits today's free quota"""
    bl_idname = "jr.estimate"
    bl_label = "Estimate"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = get_prefs(context)
        if prefs is None or not prefs.api_key:
            self.report({'ERROR'}, "No API key: open the add-on preferences and press 'Get a free key'")
            return {'CANCELLED'}
        body, notes = final_body(context, prefs, context.scene.jr_settings)
        try:
            est = make_client(prefs).estimate(body)
        except JRError as exc:
            self.report({'ERROR'}, f"Estimate failed: {exc}")
            return {'CANCELLED'}
        frames = body["frame_end"] - body["frame_start"] + 1
        text = f"{frames} frames at {body['width']}x{body['height']}: {est.get('human') or 'unknown'}"
        quota = est.get("quota") or {}
        if isinstance(quota, dict) and quota:
            left = float(quota.get("gpu_seconds_left_today") or 0) / 60.0
            fits = quota.get("fits_today")
            text += f"; {left:.1f} min left today" + ("" if fits is None else (", fits" if fits else ", does not fit"))
        state.update(message=text)
        self.report({'INFO'}, text)
        return {'FINISHED'}


class JR_OT_cancel(bpy.types.Operator):
    """Cancel the running render"""
    bl_idname = "jr.cancel"
    bl_label = "Cancel"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return state.busy()

    def execute(self, context):
        if _runner is not None and _runner.is_alive():
            _runner.cancel_event.set()
            state.update(message="Canceling...")
            self.report({'INFO'}, "Canceling")
            return {'FINISHED'}
        state.update(phase="canceled", message="Canceled")
        return {'FINISHED'}


class JR_OT_open_results(bpy.types.Operator):
    """Open the last result (or the results folder) with the system viewer"""
    bl_idname = "jr.open_results"
    bl_label = "Open result"
    bl_options = {'REGISTER'}

    def execute(self, context):
        path = state.get("result") or ""
        if not path or not os.path.exists(path):
            folder = _results_dir(Path(tempfile.gettempdir()))
            if not folder.is_dir():
                self.report({'WARNING'}, "No result yet")
                return {'CANCELLED'}
            path = str(folder)
        try:
            bpy.ops.wm.path_open(filepath=path)
        except Exception as exc:  # noqa: BLE001
            self.report({'ERROR'}, f"Could not open {path}: {exc}")
            return {'CANCELLED'}
        return {'FINISHED'}


class JR_OT_refresh_quota(bpy.types.Operator):
    """Fetch today's remaining free GPU minutes for this key"""
    bl_idname = "jr.refresh_quota"
    bl_label = "Refresh quota"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        prefs = get_prefs(context)
        if prefs is None or not prefs.api_key:
            self.report({'ERROR'}, "No API key yet")
            return {'CANCELLED'}
        try:
            state.set_quota(make_client(prefs).me())
        except JRError as exc:
            self.report({'ERROR'}, f"Could not read the quota: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, state.quota_text() or "Quota unknown")
        return {'FINISHED'}


CLASSES = (JR_OT_preview, JR_OT_final, JR_OT_estimate, JR_OT_cancel, JR_OT_open_results, JR_OT_refresh_quota)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    global _runner
    if _runner is not None and _runner.is_alive():
        _runner.cancel_event.set()
    _runner = None
    _stop_timer()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
