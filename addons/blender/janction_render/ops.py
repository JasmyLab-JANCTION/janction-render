"""Operators: preview, estimate, final render, cancel, open results, refresh quota.

A render runs in a background thread (``Runner``): save a copy of the file on
the main thread, then upload, submit, poll every 2 seconds and download without
blocking Blender. A ``bpy.app.timers`` tick on the main thread redraws the
panel and loads the finished preview into an Image Editor.

11/9（0.1.11）: 始めた仕事は jobs_store に残し、Blender を閉じても次の起動で続きを追う。アドオンを外しても受付の仕事は
止めない（前は DELETE を送っていた）。投入は Idempotency-Key つき。終わったら Blender の中で知らせる。
"""
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import bpy

from . import assets as assets_mod
from . import state
from .client import Client, JRError
from .jobs_store import Store
from .prefs import get_prefs, make_client

# 1 回の指示の上限（受付が 240 コマずつに分けて 1 本の動画にする）と、先払いのクレジットでの画素の上限。無料の分の 1080p は
# 受付が鍵ごとに判定して断る（10/14: ここで 240 コマ・1080p に黙って切り詰めていて、有料の 4K と長いアニメが出せなかった）
MAX_FRAMES_PER_INSTRUCTION = 3000
MAX_PIXELS = 3840 * 2160
FREE_MAX_FRAMES = MAX_FRAMES_PER_INSTRUCTION      # 互換（古い名前）
FREE_MAX_PIXELS = 1920 * 1080
PREVIEW_SAMPLES_MAX = 32
# 仕上げはシーンのサンプル数のまま送る（11/9。前は 128 に黙って切り詰めていて、512 のシーンが 128 で描かれていた）。
# 上限は受付の FINAL_SAMPLES_MAX（4096）。高くつく分は受付の見積もりと 402・max_yen が止める
FINAL_SAMPLES_MAX = 4096
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


def payment_text(extra: dict) -> str:
    """The panel line for a 402: the render goes past the free GPU time and needs prepaid credit."""
    need = extra.get("needed_yen")
    topup = extra.get("topup_yen")
    if need:
        return f"Past the free GPU time: needs {need} JPY of credit (top up from {topup or need} JPY)"
    return "Past the free GPU time: top up credit to render this"


def fit_pixels(width: int, height: int, max_pixels: int = MAX_PIXELS) -> tuple[int, int]:
    """Shrink (keeping the aspect) until width*height fits the pixel cap (4K; 1080p on free time is checked by the service)."""
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


# A final over 240 frames is rendered in parts; its frames come back as part-01_frame_0001.png, part-02_frame_0241.png ...
# (2026-10-14: only frame_* was picked, so such a render ended with "produced no frames"). They are saved without the
# part prefix, so the folder holds one frame_0001 ... frame_0400 sequence.
FRAME_RE = re.compile(r"^(?:part-\d+_)?frame_\d+")
PART_PREFIX_RE = re.compile(r"^part-\d+_")
DOWNLOAD_TRIES = 4


# ---- bpy helpers ------------------------------------------------------------

def _results_dir(fallback: Path, prefs: Any = None) -> Path:
    """成果物を置くフォルダ。設定の Download folder（11/9、// は .blend からの相対）、無ければ .blend の隣の janction_render。"""
    custom = str(getattr(prefs, "download_dir", "") or "").strip() if prefs is not None else ""
    if custom:
        return Path(bpy.path.abspath(custom))
    if bpy.data.filepath:
        return Path(bpy.data.filepath).parent / RESULTS_FOLDER
    return fallback


def _save_copy(tmp_dir: Path, remaps: Any = ()) -> Path:
    """Write a copy of the open file to tmp_dir. Relative paths are kept as written
    (relative_remap=False) so textures sent as assets resolve on the server.
    11/9: remaps（詰め替えのフォルダへの道）は写しを保存する間だけ書き換え、保存の直後に開いているファイルの道を元に戻す。"""
    name = (Path(bpy.data.filepath).stem if bpy.data.filepath else "untitled") + ".blend"
    dest = tmp_dir / name
    done = assets_mod.apply_remaps(remaps)
    try:
        result = bpy.ops.wm.save_as_mainfile(filepath=str(dest), copy=True, relative_remap=False, compress=True)
    finally:
        assets_mod.restore_remaps(done)
    if 'FINISHED' not in result or not dest.is_file():
        raise JRError("save_failed", "could not save a copy of the file")
    return dest


def _write_library_map(tmp_dir: Path, doc: Optional[dict[str, Any]]) -> Optional[Path]:
    """jr_libraries.json を写しの隣に書く（付け替えが無ければ書かない）。送り終えたら Runner._cleanup が消す。"""
    if not doc:
        return None
    import json

    dest = tmp_dir / assets_mod.libplan.MAP_NAME
    dest.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True), encoding="utf-8")
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
        # A file saved by this Blender must not be opened by an older one on the worker: 5.3 for Blender 5.3+,
        # 5.2 for 5.1 and 5.2, else 5.0 (0.1.13).
        running = tuple(getattr(getattr(bpy, "app", None), "version", (5, 0, 0)))[:2]
        if running >= (5, 3):
            return "5.3"
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


# ---- 受付が開けている旗つきの引数を、Blender の設定から拾う（11/13） -----------------------------------------
# ボタンは増やさない。旗が全部 OFF の受付（optional_arguments が無い）には、今までと 1 字も同じ本文を送る。

SPLIT_MIN_PIXELS = 3840 * 2160      # これより大きい 1 枚の静止画は、分けて描く（待ちが短い。GPU の時間はほぼ同じ）


def _has_file_output(scene) -> bool:
    for attr in ("compositing_node_group", "node_tree"):       # 5.0 以降は compositing_node_group
        tree = getattr(scene, attr, None)
        for node in (getattr(tree, "nodes", None) or []):
            if getattr(node, "bl_idname", "") == "CompositorNodeOutputFile" and not getattr(node, "mute", False):
                return True
    return False


def border_region(scene, width: int, height: int) -> Optional[list[int]]:
    """描く範囲の枠（Render Region）をピクセルの [x0, y0, x1, y1]（左上が原点）に。枠が無い・全体なら None。"""
    r = scene.render
    if not getattr(r, "use_border", False):
        return None
    x0, x1 = float(r.border_min_x), float(r.border_max_x)
    y0, y1 = float(r.border_min_y), float(r.border_max_y)   # Blender は下が 0
    box = [int(round(x0 * width)), int(round((1.0 - y1) * height)), int(round(x1 * width)), int(round((1.0 - y0) * height))]
    if box[2] - box[0] < 8 or box[3] - box[1] < 8 or box == [0, 0, width, height]:
        return None
    return box


def ocio_assets() -> tuple[str, list[tuple[str, str]]]:
    """Blender を OCIO=... で起動していれば、その色管理の設定と LUT を ocio/ の下に送る。(config の名前, 送る物)。"""
    path = os.environ.get("OCIO") or ""
    cfg = Path(path) if path else None
    if cfg is None or cfg.suffix.lower() != ".ocio" or not cfg.is_file():
        return "", []
    root = cfg.parent
    out: list[tuple[str, str]] = []
    total = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in OCIO_EXTENSIONS:
            continue
        rel = p.relative_to(root).as_posix()
        if len(rel.split("/")) > 4 or not assets_mod.NAME_RE.match(f"ocio/{rel}"):
            continue
        total += p.stat().st_size
        if total > OCIO_MAX_BYTES or len(out) >= 30:
            return "", []                     # 大きすぎる色管理は送らない（今までどおり受付の既定で描く）
        out.append((f"ocio/{rel}", str(p)))
    return f"ocio/{cfg.name}", out


OCIO_EXTENSIONS = {".ocio", ".cube", ".spi1d", ".spi3d", ".spimtx", ".csp", ".clf", ".ctf", ".3dl", ".cc", ".ccc", ".cdl", ".icc"}
OCIO_MAX_BYTES = 200 * 1024 * 1024


def scene_extras(context, tool: str, body: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """旗つきの引数のうち、受付が全員に開けている物だけを Blender の設定から足す。(足す物, 一言)。"""
    scene = context.scene
    add: dict[str, Any] = {}
    notes: list[str] = []
    if state.open_arg(tool, "scene_name") and len(getattr(bpy.data, "scenes", []) or []) > 1:
        add["scene_name"] = str(scene.name)
    if state.open_arg(tool, "ocio_config"):
        name, _files = ocio_assets()
        if name:
            add["ocio_config"] = name
    if state.open_feature("project_tag"):
        # 11/13 v2 REN-05（受付の旗 JR_PROJECT_TAG）: .blend が持つ案件の番号（無ければ作ってシーンに残す。保存すれば次も同じ）
        pid = project_id(scene)
        if pid:
            add["project"] = pid
            add["project_name"] = project_name(scene)
    if tool != "render_final":
        return add, notes
    single = int(body.get("frame_start", 0)) == int(body.get("frame_end", -1))
    w, h = int(body.get("width") or 0), int(body.get("height") or 0)
    if state.open_arg(tool, "file_outputs") and _has_file_output(scene):
        add["file_outputs"] = True
    last = state.get("last_still") or {}
    box = border_region(scene, w, h) if single else None
    if (box and state.open_arg(tool, "region") and body.get("output") == "png" and not add.get("file_outputs")
            and last.get("job_id") and (last.get("width"), last.get("height")) == (w, h)):
        add["region"] = box
        add["region_of"] = str(last["job_id"])
        notes.append(f"Rendering only the region {box[2] - box[0]}x{box[3] - box[1]} into {last['job_id']}")
    elif (single and body.get("output") == "png" and w * h > SPLIT_MIN_PIXELS and state.open_arg(tool, "split")
          and not add.get("file_outputs")):
        add["split"] = 9 if w * h > 2 * SPLIT_MIN_PIXELS else 4
    return add, notes


PROJECT_PROP = "janction_project_id"


def project_id(scene, create: bool = True) -> str:
    """シーンのカスタムプロパティに残した案件の番号。無ければ作る（create）。読めない・書けないシーンは ""。"""
    try:
        pid = scene.get(PROJECT_PROP)
    except Exception:  # noqa: BLE001 — カスタムプロパティを持たないもの
        return ""
    if isinstance(pid, str) and pid.startswith("prj_"):
        return pid
    if not create:
        return ""
    pid = "prj_" + uuid.uuid4().hex[:24]
    try:
        scene[PROJECT_PROP] = pid
    except Exception:  # noqa: BLE001
        return ""
    return pid


def project_name(scene) -> str:
    path = str(getattr(bpy.data, "filepath", "") or "")
    base = os.path.splitext(os.path.basename(path))[0] if path else ""
    return (base or str(getattr(scene, "name", "") or ""))[:80]


def draft_body(context, prefs, settings) -> dict[str, Any]:
    """アニメ全体の下描き動画（受付の旗 JR_DRAFT_VIDEO）: コマは受付が選ぶので frames を送らない。"""
    body = preview_body(context, prefs, settings)
    body.pop("frames", None)
    body.update({"draft_video": True, "frame_start": int(context.scene.frame_start), "frame_end": int(context.scene.frame_end)})
    return body


def preview_body(context, prefs, settings) -> dict[str, Any]:
    scene = context.scene
    body = _common_body(context, prefs, settings)
    body.update({
        "kind": "preview",
        "frames": preview_frames(scene.frame_start, scene.frame_end, scene.frame_current),
        "samples": _samples(scene, settings, PREVIEW_SAMPLES_MAX),
    })
    body.update(scene_extras(context, "render_preview", body)[0])
    return body


def final_body(context, prefs, settings) -> tuple[dict[str, Any], list[str]]:
    """The /v1/jobs body for a final render plus the adjustments made for the per-job limits."""
    scene = context.scene
    notes: list[str] = []
    body = _common_body(context, prefs, settings)
    fs, fe = int(scene.frame_start), int(scene.frame_end)
    if fe < fs:
        fe = fs
    if fe - fs + 1 > MAX_FRAMES_PER_INSTRUCTION:
        fe = fs + MAX_FRAMES_PER_INSTRUCTION - 1
        notes.append(f"One render takes at most {MAX_FRAMES_PER_INSTRUCTION} frames; rendering {fs}-{fe}")
    output = str(settings.output)
    # 11/13: 受付が印刷向けの大きな静止画（8K まで）を全員に開けていれば、1 枚の PNG・EXR はその上限まで
    stills_cap = int(state.get("stills_max_pixels") or 0)
    cap = stills_cap if (fe == fs and output in ("png", "exr", "mp4") and stills_cap > MAX_PIXELS) else MAX_PIXELS
    w, h = fit_pixels(body["width"], body["height"], cap)
    if (w, h) != (body["width"], body["height"]):
        notes.append(f"Resolution reduced to {w}x{h} ({'8K' if cap > MAX_PIXELS else '4K'} cap per render)")
    elif w * h > FREE_MAX_PIXELS:
        notes.append("Above 1920x1080 needs prepaid credit (free time renders up to 1080p)")
        body["width"], body["height"] = w, h
    if fe == fs and output == "mp4":
        output = "png"
    body.update({
        "kind": "final",
        "frame_start": fs,
        "frame_end": fe,
        "samples": _samples(scene, settings, FINAL_SAMPLES_MAX),
        "output": output,                  # mp4 / png / exr（11/9、1 層の OpenEXR。受付は前から受ける）
    })
    extra, extra_notes = scene_extras(context, "render_final", body)
    body.update(extra)
    notes.extend(extra_notes)
    hook = str(getattr(prefs, "chat_webhook", "") or "").strip() if prefs is not None else ""
    if hook.startswith("https://") and state.open_feature("notify_chat"):
        body["notify_url"] = hook               # 11/13 Discord・Slack の Webhook に、終わったら結果が届く
    # 支出の上限（円）は、料金を出す設定（既定 OFF、文面は本人の承認待ち）を入れた人だけが送る
    if prefs is not None and getattr(prefs, "show_costs", False):
        cap = int(getattr(settings, "max_yen", 0) or 0)
        if cap > 0:
            body["max_yen"] = cap
    return body, notes


# ---- background runner --------------------------------------------------------

class Runner(threading.Thread):
    """Upload, submit, poll and download for one job. Never touches bpy.

    11/9: store（jobs_store.Store）があれば、投入の前に Idempotency-Key と scene_id を、投入の後に job_id を残し、
    受け取り終えたら消す。resume に残した行を渡すと、送る・投入を飛ばして（job_id が無ければ同じ鍵で投入し直して）続きを追う。
    detach_event はアドオンを外したとき: 受付の仕事は止めずに追うのだけをやめる（行は残す）。"""

    def __init__(self, client: Client, kind: str, scene_path: Optional[Path], scene_assets: list[tuple[str, str]],
                 body: dict[str, Any], out_dir: Path, tmp_dir: Optional[Path], open_when_done: bool = False,
                 store: Optional[Store] = None, idem: str = "", resume: Optional[dict[str, Any]] = None) -> None:
        super().__init__(name="janction-render", daemon=True)
        self.client = client
        self.kind = kind
        self.scene_path = scene_path
        self.scene_assets = scene_assets
        self.body = body
        self.out_dir = out_dir
        self.tmp_dir = tmp_dir
        self.open_when_done = open_when_done
        self.store = store
        self.idem = idem or str((resume or {}).get("idem") or "") or uuid.uuid4().hex
        self.resume = resume
        self.cancel_event = threading.Event()
        self.detach_event = threading.Event()

    def run(self) -> None:
        try:
            self._run()
        except JRError as exc:
            text = f"{exc}"
            if exc.code == "quota_exceeded" and exc.resets_at_iso:
                text = f"Daily free quota used up; resets at {exc.resets_at_iso.replace('T', ' ').rstrip('Z')} UTC"
            if exc.code == "payment_required":
                state.need_payment(payment_text(exc.extra), str(exc.extra.get("checkout_url") or ""))
            else:
                state.fail(text)
            row = self.store.get(self.idem) if self.store is not None else None
            transient = exc.code in ("network", "timeout") or exc.status >= 500
            if exc.status != 404 and ((row and row.get("job_id")) or (transient and self._row_has_scene())):
                # 追っている途中・投入の返事が届かなかった: 行は残す（次の起動・Resume で、同じ Idempotency-Key で続きを追う）
                state.update(message=text + " (the job is kept; press Resume to follow it again)")
            else:
                self._forget()
            state.update(pending_notice=("failed", text))
        except Exception as exc:  # noqa: BLE001 - never let a thread die silently
            state.fail(f"{type(exc).__name__}: {exc}")
            if not self._row_has_scene():
                self._forget()
        finally:
            self._cleanup()
            self._refresh_quota()

    # ---- 残す行 ----------------------------------------------------------------

    def _remember(self, **fields: Any) -> None:
        if self.store is None:
            return
        if self.store.get(self.idem) is None:
            self.store.put({"idem": self.idem, "kind": self.kind, "server": self.client.server, "scene_id": "",
                            "job_id": "", "body": {k: v for k, v in self.body.items() if k != "scene_id"},
                            "out_dir": str(self.out_dir), "open_when_done": self.open_when_done,
                            "blend": self.scene_path.name if self.scene_path else ""})
        self.store.update(self.idem, **fields)

    def _row_has_scene(self) -> bool:
        row = self.store.get(self.idem) if self.store is not None else None
        return bool(row and (row.get("scene_id") or row.get("job_id")))

    def _forget(self) -> None:
        if self.store is not None:
            self.store.remove(self.idem)

    def _cleanup(self) -> None:
        if self.tmp_dir is None or self.scene_path is None:
            return
        try:
            if self.scene_path.parent == self.tmp_dir and self.scene_path.is_file():
                self.scene_path.unlink()
            for name, path in self.scene_assets:
                # 11/9 夜（0.1.12）: 写しの隣に書いた jr_libraries.json
                if Path(path).parent == self.tmp_dir and Path(path).is_file():
                    Path(path).unlink()
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

    def _submit(self, body: dict[str, Any]) -> str:
        job = self.client.submit(body, idempotency_key=self.idem)
        job_id = str(job["job_id"])
        self._remember(job_id=job_id)
        state.update(job_id=job_id, phase=str(job.get("status") or "queued"), message=progress_text(job))
        return job_id

    def _run(self) -> None:
        if self.resume is not None:
            job_id = str(self.resume.get("job_id") or "")
            scene_id = str(self.resume.get("scene_id") or "")
            if not job_id:
                if not scene_id:
                    self._forget()
                    state.fail("The upload did not finish before Blender closed; press Render again")
                    return
                state.update(phase="submitting", message="Submitting again (same request, not a second job)...")
                job_id = self._submit({**(self.resume.get("body") or {}), "scene_id": scene_id})
            else:
                state.update(job_id=job_id, phase="queued", message=f"Following {job_id} again...")
            self._poll(job_id)
            return
        state.update(phase="uploading", message="Uploading...")
        scene = self.client.upload_scene(self.scene_path, self.scene_assets,
                                         on_progress=lambda msg: state.update(message=msg))
        dropped = [str(d) for d in scene.get("assets_dropped") or []]
        if dropped:
            # 受付が受けない型・数の上限で外した物（11/9）。理由ごと警告に出す
            state.update(warnings=list(state.get("warnings") or []) + dropped)
        if self._canceled():
            state.update(phase="canceled", message="Canceled")
            return
        if self.detach_event.is_set():
            return
        state.update(phase="submitting", message="Submitting...")
        body = dict(self.body)
        body["scene_id"] = scene["scene_id"]
        self._remember(scene_id=str(scene["scene_id"]))
        job_id = self._submit(body)
        self._poll(job_id)

    def _poll(self, job_id: str) -> None:
        warnings = list(state.get("warnings") or [])
        while True:
            if self.cancel_event.wait(POLL_SECONDS):
                try:
                    self.client.cancel(job_id)
                except JRError:
                    pass
                self._forget()
                state.update(phase="canceled", message="Canceled")
                return
            if self.detach_event.is_set():
                return                                   # 受付の仕事はそのまま（行も残す）
            try:
                job = self.client.job(job_id)
            except JRError as exc:
                if exc.status == 404 and self.resume is not None:
                    self._forget()
                    state.fail(f"{job_id} is no longer on the server (results are kept 24 hours, 7 days with credit)")
                    return
                raise
            status = str(job.get("status") or "")
            for w in job.get("warnings") or []:
                if str(w) not in warnings:
                    warnings.append(str(w))
            if status in ("done", "failed", "canceled", "verification_failed"):
                break
            state.update(phase=status if status in ("queued", "running") else "running",
                         message=progress_text(job), warnings=list(warnings))
        state.update(warnings=list(warnings))
        if status in ("failed", "verification_failed"):
            self._forget()
            text = f"Render failed: {job.get('error') or status}"
            state.fail(text)
            state.update(pending_notice=("failed", text))
            return
        if status == "canceled":
            self._forget()
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
                self._forget()
                state.fail("The render finished but produced no image")
                return
            tag = stamp()
            dest = self.client.artifact(job_id, name, self.out_dir / f"preview_{tag}.png")
            result = dest
            if "draft.mp4" in names:      # 下描き動画（11/13）: 一覧の絵は Blender で開き、動画はフォルダから
                result = self.client.artifact(job_id, "draft.mp4", self.out_dir / f"draft_{tag}.mp4")
            self._forget()
            word = "Draft" if result is not dest else "Preview"
            state.update(phase="done", result=str(result), pending_image=str(dest), message=f"{word} ready{took}",
                         pending_notice=("done", f"{word} ready{took}"))
            return
        if "output.mp4" in names:
            dest = self.client.artifact(job_id, "output.mp4", self.out_dir / f"final_{stamp()}.mp4")
            result: Path = dest
        else:
            frames = [n for n in names if FRAME_RE.match(n)]
            if not frames:
                self._forget()
                state.fail("The render finished but produced no frames")
                return
            folder = self.out_dir / f"final_{stamp()}"
            for i, n in enumerate(frames, 1):
                if self._canceled():
                    state.update(phase="canceled", message="Canceled while downloading")
                    return
                if self.detach_event.is_set():
                    return
                state.update(message=f"Downloading {i}/{len(frames)}")
                self._fetch(job_id, n, folder / PART_PREFIX_RE.sub("", n))
            result = folder
        self._forget()
        frames_done = [n for n in names if FRAME_RE.match(n)]
        if self.body.get("output") == "png" and len(frames_done) == 1 and "output.mp4" not in names:
            # 次に描く範囲の枠だけ描き直すときの元（11/13、受付の旗 JR_REGION_RENDER）
            state.update(last_still={"job_id": job_id, "width": int(self.body.get("width") or 0),
                                     "height": int(self.body.get("height") or 0)})
        state.update(phase="done", result=str(result), message=f"Final render ready{took}",
                     pending_open=str(result) if self.open_when_done else "",
                     pending_notice=("done", f"Final render ready{took}: {result}"))

    def _fetch(self, job_id: str, name: str, dest: Path) -> None:
        """One file, fetched again when the connection drops in the middle (a 5 GB render is hundreds of files)."""
        for attempt in range(DOWNLOAD_TRIES):
            try:
                self.client.artifact(job_id, name, dest)
                return
            except JRError as exc:
                if exc.code not in ("network", "timeout") or attempt == DOWNLOAD_TRIES - 1:
                    raise
                time.sleep(min(10.0, 2.0 ** attempt))


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


def _notify(kind: str, text: str) -> None:
    """終わった・失敗したを Blender の中で小さな窓で知らせる（11/9。設定 Notify when done、既定 ON）。"""
    prefs = get_prefs()
    if prefs is not None and not getattr(prefs, "notify_when_done", True):
        return
    try:
        wm = bpy.context.window_manager
        windows = list(wm.windows) if wm is not None else []
        if not windows:
            return

        def draw(menu, _context):
            menu.layout.label(text=text)

        with bpy.context.temp_override(window=windows[0]):
            wm.popup_menu(draw, title="JANCTION Render", icon='CHECKMARK' if kind == "done" else 'ERROR')
    except Exception:  # noqa: BLE001 - 知らせられなくてもパネルには出ている
        pass


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
    notice = state.pop("pending_notice", None)
    if notice:
        _notify(*notice)
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
    if bpy.app.timers.is_registered(_resume_on_start):
        bpy.app.timers.unregister(_resume_on_start)


# ---- 残した仕事（11/9） ------------------------------------------------------------

_STORE: Optional[Store] = None


def _store_path() -> Path:
    """拡張機能の利用者のフォルダ（Blender 4.2+ の extension_path_user）。古い入れ方なら設定のフォルダ。"""
    try:
        return Path(bpy.utils.extension_path_user(__package__, path="", create=True)) / "jobs.json"
    except Exception:  # noqa: BLE001
        pass
    try:
        return Path(bpy.utils.user_resource('CONFIG', path="janction_render", create=True)) / "jobs.json"
    except Exception:  # noqa: BLE001
        return Path(tempfile.gettempdir()) / "janction_render_jobs.json"


def job_store() -> Store:
    global _STORE
    if _STORE is None:
        _STORE = Store(_store_path())
    return _STORE


def pending_jobs(prefs: Any) -> list[dict[str, Any]]:
    """この設定の受付に残っている仕事（いま追っている仕事は除く）。"""
    if prefs is None:
        return []
    server = make_client(prefs).server
    current = _runner.idem if _runner is not None and _runner.is_alive() else ""
    return [r for r in job_store().all() if r.get("server") == server and r.get("idem") != current]


def resume_job(prefs: Any, row: dict[str, Any]) -> bool:
    """残した行の続きを追う。True なら追い始めた。"""
    global _runner
    if prefs is None or not prefs.api_key or state.busy():
        return False
    state.start_job(str(row.get("kind") or "final"), [])
    state.update(job_id=str(row.get("job_id") or ""), message="Resuming...")
    out_dir = Path(str(row.get("out_dir") or "")) if row.get("out_dir") else _results_dir(Path(tempfile.gettempdir()), prefs)
    _runner = Runner(make_client(prefs), str(row.get("kind") or "final"), None, [], dict(row.get("body") or {}), out_dir,
                     None, open_when_done=bool(row.get("open_when_done")), store=job_store(), resume=row)
    _runner.start()
    _ensure_timer()
    return True


def _resume_on_start() -> Optional[float]:
    """起動の少し後に 1 回: 前の Blender で終わらなかった仕事があれば、いちばん新しいものの続きを追う。"""
    try:
        if getattr(bpy.app, "background", False):
            return None
        prefs = get_prefs()
        rows = pending_jobs(prefs)
        if rows:
            resume_job(prefs, rows[-1])
    except Exception:  # noqa: BLE001 - 起動を止めない
        pass
    return None


# ---- starting a job (main thread) -----------------------------------------------

def _roots(prefs: Any) -> list[str]:
    return assets_mod.parse_roots(str(getattr(prefs, "asset_roots", "") or "")) if prefs is not None else []


def local_checks(context) -> list:
    """11/13 v2 QAD-01: ネットを使わない手元の点検（checks.py）。結果は state.checks（Files の上に出す）。"""
    from . import checks
    try:
        found = checks.run(context.scene, tuple(getattr(getattr(bpy, "app", None), "version", (5, 0, 0))))
    except Exception as exc:  # noqa: BLE001 — 点検が落ちても送る・描くは止めない
        found = [("info", "check_failed", f"Local checks could not run: {exc}")]
    state.update(checks=found, checks_summary=checks.summary(found))
    return found


def scan_files(context, prefs: Any) -> "assets_mod.Collected":
    """依存を集めて、Files の一覧（state.deps）を新しくする。手元の点検（local_checks）も一緒に。"""
    collected = assets_mod.collect_from_bpy(scene=getattr(context, "scene", None), roots=_roots(prefs))
    state.update(deps=list(collected.deps), deps_summary=collected.summary())
    local_checks(context)
    return collected


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
    # 11/13 v2 QAD-01: 送る前に手元で分かる止まる理由（新しすぎる版・使えない描画方式）なら、何も送らずに止める
    blocking = [c for c in local_checks(context) if c[0] == "block"]
    if blocking:
        msg = blocking[0][2]
        state.fail(msg)
        report({'ERROR'}, msg)
        return False
    tmp_dir = Path(tempfile.mkdtemp(prefix="janction_render_"))
    try:
        state.start_job(kind, notes)
        # 11/9: 先に集める（詰め替えの道 remaps を写しの保存に使う。開いているファイルの道は保存の直後に戻す）
        collected = scan_files(context, prefs)
        scene_path = _save_copy(tmp_dir, collected.remaps)
        # 11/9 夜（0.1.12）: リンクした .blend の入れ子・外のフォルダの付け替えの組（受付の旗 JR_LINKED_BLEND の受付が読む）
        if body.get("ocio_config"):
            collected.assets.extend(ocio_assets()[1])
        map_file = _write_library_map(tmp_dir, collected.library_map)
        if map_file is not None:
            collected.assets.append((assets_mod.libplan.MAP_NAME, str(map_file)))
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
    for w in collected.warnings[:10]:
        report({'WARNING'}, w)
    if len(collected.warnings) > 10:
        report({'WARNING'}, f"{len(collected.warnings) - 10} more: see Render Properties > JANCTION Render > Files")
    _runner = Runner(make_client(prefs), kind, scene_path, collected.assets, body, _results_dir(tmp_dir, prefs), tmp_dir,
                     open_when_done=bool(prefs.open_results) and kind == "final", store=job_store())
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


class JR_OT_draft(bpy.types.Operator):
    """Preview the whole animation as a quick, small draft video"""
    bl_idname = "jr.draft"
    bl_label = "Draft video"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        return (not state.busy() and state.open_arg("render_preview", "draft_video")
                and scene is not None and scene.frame_end > scene.frame_start)

    def execute(self, context):
        body = draft_body(context, get_prefs(context), context.scene.jr_settings)
        return {'FINISHED'} if start_job(context, "preview", body, [], self.report) else {'CANCELLED'}


class JR_OT_final(bpy.types.Operator):
    """Render up to 3,000 frames; the service splits parts and enforces the key's resolution entitlement."""
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


def estimate_text(body: dict[str, Any], est: dict[str, Any], show_costs: bool = False) -> str:
    """見積もりの 1 行。円の額は料金を出す設定（既定 OFF）のときだけ足す（文面は本人の承認待ち、11/9）。"""
    frames = body["frame_end"] - body["frame_start"] + 1
    text = f"{frames} frames at {body['width']}x{body['height']}, {body['samples']} samples: {est.get('human') or 'unknown'}"
    quota = est.get("quota") or {}
    if isinstance(quota, dict) and quota:
        left = float(quota.get("gpu_seconds_left_today") or 0) / 60.0
        fits = quota.get("fits_today")
        text += f"; {left:.1f} free min left" + ("" if fits is None else (", fits" if fits else ", does not fit"))
    cost = est.get("cost") if isinstance(est.get("cost"), dict) else {}
    if show_costs and cost.get("estimated_yen") is not None:
        text += f"; about {cost['estimated_yen']} JPY"
        if cost.get("max_charge_yen") is not None:
            text += f" (at most {cost['max_charge_yen']} JPY)"
    return text


class JR_OT_estimate(bpy.types.Operator):
    """Ask the server how long the final render would take and whether it fits the free GPU time left"""
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
        text = estimate_text(body, est, bool(getattr(prefs, "show_costs", False)))
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
            folder = _results_dir(Path(tempfile.gettempdir()), get_prefs(context))
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


class JR_OT_project_history(bpy.types.Operator):
    """Show the renders of this .blend's project (also from other sessions and computers)"""
    bl_idname = "jr.project_history"
    bl_label = "Project history"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        return state.open_feature("project_tag") and scene is not None and bool(project_id(scene, create=False))

    def execute(self, context):
        prefs = get_prefs(context)
        if prefs is None or not prefs.api_key:
            self.report({'ERROR'}, "No API key yet")
            return {'CANCELLED'}
        try:
            got = make_client(prefs).project_history(project_id(context.scene, create=False))
        except JRError as exc:
            self.report({'ERROR'}, f"Could not read the project history: {exc}")
            return {'CANCELLED'}
        rows = got.get("jobs") or []
        state.update(project_history=rows[:10])
        self.report({'INFO'}, f"{len(rows)} render(s) in this project")
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
            client = make_client(prefs)
            state.set_quota(client.me())
        except JRError as exc:
            self.report({'ERROR'}, f"Could not read the quota: {exc}")
            return {'CANCELLED'}
        try:
            state.set_capabilities(client.capabilities())
        except JRError:
            pass
        self.report({'INFO'}, state.quota_text() or "Quota unknown")
        return {'FINISHED'}


class JR_OT_scan_files(bpy.types.Operator):
    """List every file this scene needs and whether it will be sent"""
    bl_idname = "jr.scan_files"
    bl_label = "Check files"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            collected = scan_files(context, get_prefs(context))
        except Exception as exc:  # noqa: BLE001
            self.report({'ERROR'}, f"Could not list the files: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, collected.summary())
        return {'FINISHED'}


def file_list_text(deps: list[dict[str, Any]]) -> str:
    """Files の一覧を貼り付けられる文に（1 行 1 つ）。"""
    lines = []
    for d in deps:
        files = f" ({d['files']} files, {d['bytes'] / 1048576.0:.1f} MB)" if d.get("files") else ""
        moved = " [path rewritten in the uploaded copy]" if d.get("remapped") else ""
        note = f": {d['note']}" if d.get("note") else ""
        lines.append(f"[{d['status']}] {d['kind']} {d['label']} {d['path']}{files}{moved}{note}".rstrip())
    return "\n".join(lines)


class JR_OT_copy_file_list(bpy.types.Operator):
    """Copy the file list to the clipboard"""
    bl_idname = "jr.copy_file_list"
    bl_label = "Copy list"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        deps = state.get("deps") or []
        if not deps:
            self.report({'WARNING'}, "Press Check files first")
            return {'CANCELLED'}
        context.window_manager.clipboard = file_list_text(deps)
        self.report({'INFO'}, f"Copied {len(deps)} lines")
        return {'FINISHED'}


class JR_OT_resume_job(bpy.types.Operator):
    """Follow a render started earlier (before Blender was closed) and download its result"""
    bl_idname = "jr.resume_job"
    bl_label = "Resume"
    bl_options = {'REGISTER', 'INTERNAL'}

    idem: bpy.props.StringProperty(options={'HIDDEN'})

    def execute(self, context):
        row = job_store().get(self.idem)
        if row is None:
            self.report({'WARNING'}, "That render is no longer listed")
            return {'CANCELLED'}
        if not resume_job(get_prefs(context), row):
            self.report({'WARNING'}, "A render is already running, or there is no API key")
            return {'CANCELLED'}
        return {'FINISHED'}


class JR_OT_forget_job(bpy.types.Operator):
    """Stop listing this render here (the render itself is not canceled)"""
    bl_idname = "jr.forget_job"
    bl_label = "Forget"
    bl_options = {'REGISTER', 'INTERNAL'}

    idem: bpy.props.StringProperty(options={'HIDDEN'})

    def execute(self, context):
        job_store().remove(self.idem)
        return {'FINISHED'}


CLASSES = (JR_OT_preview, JR_OT_draft, JR_OT_final, JR_OT_estimate, JR_OT_cancel, JR_OT_open_results, JR_OT_refresh_quota,
           JR_OT_scan_files, JR_OT_copy_file_list, JR_OT_resume_job, JR_OT_forget_job, JR_OT_project_history)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    # 前の Blender で終わらなかった仕事の続き（起動の少し後に 1 回。ファイルを開いても消えないよう persistent）
    if not bpy.app.timers.is_registered(_resume_on_start):
        bpy.app.timers.register(_resume_on_start, first_interval=3.0, persistent=True)


def unregister() -> None:
    global _runner
    if _runner is not None and _runner.is_alive():
        # 11/9: 受付の仕事は止めない（前は DELETE を送っていた）。追うのをやめるだけで、行は残して次に続きを追う
        _runner.detach_event.set()
    _runner = None
    _stop_timer()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
