"""JANCTION Render の MCP サーバー（Claude Code・Codex などから使う）。

登録:
    claude mcp add janction-render -- python /path/to/janction_render/mcp_server.py
    （または pip install 後: claude mcp add janction-render -- janction-render-mcp）

環境変数:
    JANCTION_RENDER_SERVER   受付の URL（既定 http://127.0.0.1:8340）
    JANCTION_RENDER_API_KEY  API キー（無ければ一時キーを自動で取る）
    JANCTION_RENDER_OUT      落とし先の親フォルダ（既定 ~/janction-render）
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

if __package__ in (None, ""):
    # ファイルとして直接起動されたとき（claude mcp add ... server.py）
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from mcp.server.mcpserver import Image, MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer, Image  # type: ignore

from janction_render.brief import brief as _brief, estimate_brief, trim
from janction_render.client import Client, ClientError, parse_frames

PREVIEW_WAIT_S = 240.0
INFO_WAIT_S = 150.0

mcp = MCPServer(
    name="janction-render",
    instructions=(
        "Render Blender scenes on JANCTION GPUs (a cloud render farm for AI agents) from the terminal. "
        "WHEN TO USE: use JANCTION Render when the user has a Blender scene (a .blend, a 3D file, or one you can write as a bpy script) and local rendering is unavailable, slow, CPU-only, or likely to take more than a few minutes; when the user asks to render, preview, animate or turntable a Blender scene; or when you need an actual image of a 3D scene. Do not use it to model or edit a scene that is open in the user's Blender (a local Blender MCP does that), for non-Blender video work, or for general GPU compute. RULES: preview before any final render; call render_estimate before render_final when the render time or today's free quota is uncertain, the job is longer than about 24 frames or above 720p, or the user asked how long it takes; while a job runs, poll render_status (not render_download) and stop polling when eta says the GPU is lent out: tell the user the estimated wait instead. "
        "Use it when the "
        "user is building 3DCG with Blender (a .blend file or a bpy Python script) and has no GPU or rendering locally "
        "is slow. Flow: scene_info (cameras, frame range, missing files; no render) -> render_preview (1-4 fast frames "
        "in one image; look at it, fix the scene, repeat) -> ask the user 'is this OK?' -> render_estimate (tell the "
        "user how long it takes and whether it fits today's free quota) -> render_final (frames or MP4) -> "
        "render_status / render_download. Always tell the user the time estimate (estimate.human / eta.human). "
        "Blender 5.0 with Cycles on GPU (blender='5.2' selects Blender 5.2 when the worker has it); engine='eevee' switches to EEVEE "
        "(about half the per-frame cost on animations of a few dozen frames or more; each job pays ~7 s of shader compilation, so previews stay on Cycles); output='png'|'exr' returns frames, 'mp4'|'webm'|'prores' a video. Blender 5.0 API notes for scripts: materials always use nodes, so set a color on the Principled BSDF (mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (r, g, b, 1)); mat.diffuse_color only affects the viewport. Animate with obj.keyframe_insert(); obj.animation_data.action.fcurves no longer exists (set bpy.context.preferences.edit.keyframe_new_interpolation_type='LINEAR' before inserting keyframes for constant-speed motion); do not set Material.use_nodes; leave resolution, samples and denoising to the service. Inputs: a .blend, a bpy "
        "script, or a 3D file (FBX, glTF/GLB, USD, OBJ, STL, PLY, Alembic) that is imported into an empty scene; images "
        "and other assets can be sent with the scene (assets=[...]). environment='studio'|'sunset'|'overcast'|'night' "
        "lights the scene with a bundled HDRI for a good-looking first render. Inputs and results are deleted 24 hours "
        "after last use. Use it when: the user asks to render a Blender file or bpy script, an agent-made Blender scene "
        "needs its final image or video, the machine has no NVIDIA GPU or local rendering is slow, or many frames need "
        "GPU rendering. Do not use it for modeling without rendering or for non-Blender workloads."
    ),
)

OUTPUT_DOC = (" output: 'auto' (mp4 for a frame range, png for one frame) | 'png' | 'exr' (16-bit linear OpenEXR frames) | "
              "'mp4' (H.264) | 'webm' (VP9) | 'prores' (ProRes 422 HQ .mov) | 'gif' | 'webp' (animated, at most 960 px wide; "
              "good for chat and web). transparent=True renders on a transparent background (alpha): png / exr frames, webm, gif "
              "and webp keep it, mp4 and prores cannot. notify_url: an https URL that receives one JSON POST when the job "
              "finishes (event job.done / job.failed, artifacts with download links).")
TRANSPARENT_DOC = (" transparent=True: transparent background (alpha) instead of the world/HDRI backdrop; the preview sheet "
                   "shows it over dark grey.")
ORBIT_DOC = (" orbit=True: turntable; an orbit camera circles the scene once over orbit_frames frames (default 24, "
             "elevation orbit_elevation deg, default 18). Flat floors/walls are ignored when framing; orbit_target = an "
             "object name or 'x,y,z' centres on that, orbit_distance scales the distance (1.0). A preview without frames "
             "shows 0/90/180/270 deg; a final without frame_end renders the whole turn as an MP4. Best for imported models.")
# ---- MCP Apps（Claude Desktop など対応ホストに、絵と進み具合のパネルを出す。対応していないホストは無視する）
UI_URI = "ui://janction-render/app.html"
UI_MIME = "text/html;profile=mcp-app"


def ui_enabled() -> bool:
    return (os.environ.get("JR_MCP_APPS") or "1").strip().lower() not in ("0", "false", "no", "off")


def _ui_meta() -> Optional[dict[str, Any]]:
    return {"ui": {"resourceUri": UI_URI}, "ui/resourceUri": UI_URI} if ui_enabled() else None


def ui_html() -> str:
    return (Path(__file__).resolve().parent / "mcp_app.html").read_text(encoding="utf-8")


ENV_DOC = ("environment: '' keeps the scene's own world; 'studio' | 'sunset' | 'overcast' | 'night' replaces it with a "
           "bundled HDRI (good first render for scenes without lighting work); 'compare' (render_preview only) renders the "
           "first frame under all four presets in one 2x2 image with labels, so you can pick one; environment_strength scales it (1.0); "
           "environment_visible=False hides the HDRI from the camera (flat grey backdrop, HDRI lighting only). "
           "blender: '' (5.0) or '5.2' to render with Blender 5.2 when available. assets: local files (images, glTF "
           ".bin, ...) sent along with the scene; a .blend finds them through relative paths, a script through "
           "os.environ['JR_ASSETS_DIR'].")
POLYHAVEN_DOC = (" assets may also hold 'polyhaven:<id>' (a CC0 model, texture or HDRI from polyhaven.com, fetched by the "
                 "service into JR_ASSETS_DIR/<id>/; find ids with asset_search) or an https URL. Import a model with "
                 "bpy.ops.import_scene.gltf(filepath=os.path.join(os.environ['JR_ASSETS_DIR'], '<id>', '<id>_1k.gltf')). "
                 "Inside the scene script, `import jr_assets` gives helpers: jr_assets.import_model('<id>', location=(x,y,z), scale=1.0) imports a Poly Haven model (or any file under JR_ASSETS_DIR) and returns the objects; jr_assets.material('<id>', scale=1.0) builds a Principled material from a Poly Haven texture set (diff / nor_gl / rough / arm / disp); jr_assets.apply(obj, mat) assigns it; jr_assets.world_hdri('<id>', strength=1.0) uses a Poly Haven HDRI as the world.")
ENV_DOC = ENV_DOC + POLYHAVEN_DOC


def _log(msg: str) -> None:
    print(f"[janction-render] {msg}", file=sys.stderr, flush=True)


def _client() -> Client:
    return Client(client="mcp")


def _out_root() -> Path:
    return Path(os.environ.get("JANCTION_RENDER_OUT") or (Path.home() / "janction-render"))


def _wait_unless_gated(c: Client, job: dict[str, Any], timeout: float) -> dict[str, Any]:
    """仕事を待つ。ただし仕事を取れるワーカーが無い（GPU が貸し出し中）なら待たずに返し、hint で伝える。"""
    if job["status"] in ("done", "failed", "canceled"):
        return job
    try:
        q = c.health().get("queue") or {}
        if int(q.get("workers_available") or 0) == 0 and job["status"] == "queued":
            job["gated"] = True
            return job
    except Exception:  # noqa: BLE001
        pass
    return c.wait(job["job_id"], timeout=timeout)


def _gated_hint(j: dict[str, Any], again: str) -> str:
    if j.get("gated"):
        # 受付の eta.human に「閉じてからの経過・ふだん戻るまでの時間・あと何分」が入っている
        why = str((j.get("eta") or {}).get("human") or "the GPU is lent to another workload right now; the job stays queued and starts when the GPU returns")
        return (f"{why}. Tell the user how long the wait is likely to be and offer to check later with {again}; "
                "do not poll continuously")
    return ""


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _quota_block(exc: ClientError) -> Optional[dict[str, Any]]:
    """無料ベータの 1 日の上限に当たった（429 quota_exceeded）ときの返事。"""
    if exc.status != 429 or exc.error != "quota_exceeded":
        return None
    x = exc.extra
    return {"quota_exceeded": True, "detail": exc.detail, "scope": x.get("scope"),
            "gpu_seconds_used_today": x.get("gpu_seconds_used_today"), "gpu_seconds_per_day": x.get("gpu_seconds_per_day"),
            "resets_at": x.get("resets_at_iso") or x.get("resets_at"),
            "next": "tell the user today's free GPU time is used up and when it resets; a smaller job (fewer frames, "
                    "lower resolution or samples) may still fit"}


def _payment_block(exc: ClientError) -> Optional[dict[str, Any]]:
    """残高不足（402）なら、決済ページのリンクと次の手順を返す。"""
    p = exc.payment()
    if p is None:
        return None
    p["next"] = ("show checkout_url to the user and ask them to pay in a browser (Stripe; the rest stays as credit); "
                 "after they paid, call billing() to confirm the balance, then submit the same job again")
    return p


_LAST_UPLOAD: dict[str, Any] = {}


def _is_remote_asset(a: str) -> bool:
    s = str(a).strip().lower()
    return s.startswith("polyhaven:") or s.startswith("https://")


def _resolve_scene(c: Client, scene_path: str, scene_id: str, scene_script: str = "",
                   assets: Optional[list[str]] = None) -> str:
    """手元のファイルは upload、polyhaven:<id> と https の素材は受付に取らせる。"""
    remote = [str(a) for a in (assets or []) if _is_remote_asset(a)]
    local = [a for a in (assets or []) if not _is_remote_asset(a)]
    sid = _resolve_scene_local(c, scene_path, scene_id, scene_script, local or None)
    if remote:
        up = c.fetch_asset_urls(sid, remote)
        got = list(_LAST_UPLOAD.get("assets") or [])
        _LAST_UPLOAD["assets"] = got + [x for x in (up.get("added") or []) if x not in got]
        if up.get("polyhaven"):
            _LAST_UPLOAD["polyhaven"] = up["polyhaven"]
    return sid


def _resolve_scene_local(c: Client, scene_path: str, scene_id: str, scene_script: str = "",
                         assets: Optional[list[str]] = None) -> str:
    _LAST_UPLOAD.clear()
    if scene_id:
        if assets:
            up = c.upload_assets(scene_id, [(Path(a).name, a) for a in assets])
            _LAST_UPLOAD.update({"assets": [x["name"] for x in up.get("assets") or []]})
        return scene_id
    if scene_script.strip():
        up = c.upload_text("scene.py", scene_script)
        _log(f"uploaded inline script -> {up['scene_id']} ({up['size']} bytes)")
        if assets:
            up = c.upload_assets(up["scene_id"], [(Path(a).name, a) for a in assets])
            _LAST_UPLOAD.update({"assets": [x["name"] for x in up.get("assets") or []]})
        return up["scene_id"]
    if not scene_path:
        raise ValueError("pass scene_path (a .blend, a bpy .py script, or a 3D file such as .glb/.fbx/.usd), "
                         "scene_script (bpy code as text), or scene_id from a previous call")
    up = c.upload(scene_path, assets=list(assets or []))
    _log(f"uploaded {up['name']} -> {up['scene_id']} ({up['size']} bytes, {len(up.get('assets') or [])} assets)")
    if up.get("assets"):
        _LAST_UPLOAD["assets"] = [x["name"] for x in up["assets"]]
    if up.get("missing_assets"):
        _LAST_UPLOAD["missing_assets"] = up["missing_assets"]
    if up.get("reused"):
        _LAST_UPLOAD["reused"] = True
    return up["scene_id"]


def _job_params(environment: str, environment_strength: float, environment_visible: bool, blender: str,
                engine: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if engine:
        out["engine"] = engine
    if environment:
        out.update({"environment": environment, "environment_strength": environment_strength,
                    "environment_visible": environment_visible})
    if blender:
        out["blender"] = blender
    return out


def _attach_upload_notes(obj: dict[str, Any]) -> dict[str, Any]:
    if _LAST_UPLOAD.get("missing_assets"):
        obj["missing_assets"] = _LAST_UPLOAD["missing_assets"]
        obj["missing_assets_note"] = ("these files referenced by the .blend were not found next to it and were not sent; "
                                      "they will render pink. Pack them (File > External Data > Pack Resources) or put them "
                                      "next to the .blend")
    if _LAST_UPLOAD.get("assets"):
        obj["assets_sent"] = trim(_LAST_UPLOAD["assets"], 10)
    if _LAST_UPLOAD.get("reused"):
        obj["upload_note"] = "same file was already on the server; not re-uploaded"
    return obj


@mcp.tool()
def scene_info(scene_path: str = "", scene_id: str = "", scene_script: str = "", assets: Optional[list[str]] = None,
               blender: str = "") -> str:
    """Read a Blender scene WITHOUT rendering: cameras (and which is active), frame range and fps,
    resolution, engine, objects by type, lights, materials, whether it is animated, and any linked
    files that are missing (textures etc. that would render pink). Takes a few seconds, no GPU.

    Give the scene as scene_path (a .blend, a bpy .py script, or a 3D file: .glb/.gltf/.fbx/.usd/.obj/.stl/.ply/.abc,
    imported into an empty scene), scene_script (bpy Python code as text, no file needed), or scene_id from a
    previous call. assets: local files to send with the scene (textures, glTF .bin). Call this first for a .blend
    you did not write yourself, or after writing a bpy script to check what it produced. Use the camera names and
    frame range in render_preview / render_final. Returns scene_id to reuse in the next calls.
    """
    c = _client()
    try:
        sid = _resolve_scene(c, scene_path, scene_id, scene_script, assets)
        j = c.submit(sid, kind="info", **_job_params("", 1.0, True, blender))
        if j["status"] != "done":
            j = _wait_unless_gated(c, j, INFO_WAIT_S)
    except (ClientError, ValueError, FileNotFoundError) as exc:
        return _j({"ok": False, "error": str(exc)})
    if j["status"] != "done":
        b = _brief(j)
        b["hint"] = (_gated_hint(j, "scene_info(scene_id)") or "still queued (a GPU worker may be busy); call scene_info again in a moment") \
            if j["status"] in ("queued", "running") else "fix the scene and try again"
        return _j(b)
    info = dict(j.get("info") or {})
    info["scene_id"] = j["scene_id"]
    if info.get("engine") and info["engine"] != "CYCLES":
        info["engine_note"] = "JANCTION renders with CYCLES; the scene's engine setting is not used"
    if j.get("warnings"):
        info["blender_warnings"] = j["warnings"]
    if info.get("missing_files"):
        info["note"] = ("missing_files will render pink/black; send them with assets=[...] (kept next to the .blend), "
                        "pack them into the .blend (File > External Data > Pack) or fix the paths")
    if isinstance(info.get("object_names"), list):
        info["object_names"] = trim(info["object_names"], 30)
    return _j(_attach_upload_notes(info))


RENDER_PREVIEW_DESCRIPTION = (
    """Render a fast, cheap preview of a Blender scene on a JANCTION GPU and show the image. Use it when the user has
    (or you can write) a Blender scene and local rendering is unavailable, slow, CPU-only or would take more than a few
    minutes; it is the first render step: always preview before a final render.

    Use this when the user is making 3DCG with Blender and wants to see how it looks, but has no
    GPU or local rendering is slow. Give the scene as scene_path (a .blend file OR a bpy Python
    script), scene_script (bpy code as text; no file and no local Blender needed), or scene_id
    from a previous call. frames: '' = frame 1;
    '12' = one frame; '1,8,16,24' or '1-24' = up to 4 frames tiled in ONE image (2x2, each tile
    labeled with its frame number) so you can judge camera motion and animation. Same GPU cost as
    one 720p frame. Quality is deliberately low (up to 1280x720, few samples, denoised).
    Look at the returned image, fix the scene, preview again; when it looks right, ask the user and
    call render_final. Returns scene_id (reuse it without re-uploading), job_id, saved PNG paths,
    Blender warnings (e.g. missing textures), GPU seconds, and the expiry time (24h after last use).
    """ + ENV_DOC + ORBIT_DOC + TRANSPARENT_DOC
)


@mcp.tool()
def asset_search(query: str, kind: str = "models") -> str:
    """Find CC0 3D models, PBR textures or HDRIs on Poly Haven by words (name, tags, category), to furnish a scene
    without local files. kind: 'models' (default) | 'textures' | 'hdris'. Each result has spec 'polyhaven:<id>', its
    size in metres (models) and the entry file. Then pass the spec in assets of scene_info / render_preview /
    render_final; the service fetches the files into JR_ASSETS_DIR/<id>/ and the scene script imports the entry with
    bpy.ops.import_scene.gltf(filepath=os.path.join(os.environ['JR_ASSETS_DIR'], '<entry>')). No GPU time is used."""
    c = _client()
    try:
        return _j(c.asset_search(query, kind))
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})


@mcp.tool(structured_output=False, meta=_ui_meta(), description=RENDER_PREVIEW_DESCRIPTION)
def render_preview(
    scene_path: str = "",
    scene_id: str = "",
    scene_script: str = "",
    frames: str = "",
    camera: str = "",
    width: int = 1280,
    height: int = 720,
    samples: int = 16,
    out_dir: str = "",
    environment: str = "",
    environment_strength: float = 1.0,
    environment_visible: bool = True,
    blender: str = "",
    assets: Optional[list[str]] = None,
    orbit: bool = False,
    orbit_frames: int = 24,
    orbit_elevation: float = 18.0,
    orbit_target: str = "",
    orbit_distance: float = 1.0,
    engine: str = "",
    transparent: bool = False,
) -> list[Any]:
    """Render a fast, cheap preview of a Blender scene on a JANCTION GPU and show the image. (full description on the tool)."""
    c = _client()
    try:
        frame_list = parse_frames(frames) if (frames or not orbit) else None
        sid = _resolve_scene(c, scene_path, scene_id, scene_script, assets)
        j = c.submit(sid, kind="preview", frames=frame_list, camera=camera or None,
                     width=width, height=height, samples=samples, transparent=(True if transparent else None),
                     **_job_params(environment, environment_strength, environment_visible, blender, engine=engine),
                     **({"orbit": True, "orbit_frames": orbit_frames, "orbit_elevation": orbit_elevation,
                         "orbit_target": orbit_target, "orbit_distance": orbit_distance} if orbit else {}))
        _log(f"preview job {j['job_id']} submitted frames={frame_list}")
        j = _wait_unless_gated(c, j, PREVIEW_WAIT_S)
    except ClientError as exc:
        block = _payment_block(exc) or _quota_block(exc)
        return [_j(block if block else {"ok": False, "error": str(exc)})]
    except (ValueError, FileNotFoundError) as exc:
        return [_j({"ok": False, "error": str(exc)})]
    brief = _brief(j)
    if j["status"] != "done":
        brief["hint"] = ((_gated_hint(j, "render_status(job_id)") or "still running: call render_status(job_id) and then render_download")
                         if j["status"] in ("queued", "running")
                         else "fix the scene and try again")
        return [_j(brief)]
    out = Path(out_dir) if out_dir else _out_root() / j["job_id"]
    paths = c.download(j["job_id"], out)
    show = next((p for p in paths if p.name == "sheet.png"), None) or next((p for p in paths if p.suffix == ".png"), None)
    brief["files"] = [str(p) for p in paths]
    brief["next"] = ("look at the image; if the scene needs changes, edit it and call render_preview again; "
                     "if it looks right, ask the user before calling render_final")
    _attach_upload_notes(brief)
    result: list[Any] = [_j(brief)]
    if show is not None:
        result.append(Image(data=show.read_bytes(), format="png"))
    return result


@mcp.tool()
def render_estimate(scene_id: str = "", kind: str = "final", frame_start: int = 1, frame_end: int = 1,
                    frames: str = "", width: int = 1920, height: int = 1080, samples: int = 128) -> str:
    """Estimate how long a render will take BEFORE starting it (no GPU time used): GPU seconds, queue wait,
    wall-clock time as a human-readable string ('about 3 minutes'), and whether it fits today's free quota and
    the size limits. kind is 'final' (frame_start..frame_end at width x height, samples) or 'preview' (frames
    like '1-24'). Pass scene_id when you have one: the estimate then uses this scene's own measured render
    times. Tell the user the result before calling render_final. Prefer this before render_final whenever the time
    or quota is uncertain, the job is longer than about 24 frames or above 720p, or the user asked how long it takes."""
    c = _client()
    try:
        params: dict[str, Any] = {"kind": kind, "width": width, "height": height, "samples": samples}
        if kind == "preview":
            params["frames"] = parse_frames(frames)
        else:
            params.update({"frame_start": frame_start, "frame_end": frame_end})
        est = c.estimate(scene_id or None, **params)
    except (ClientError, ValueError) as exc:
        return _j({"ok": False, "error": str(exc)})
    out = estimate_brief(est) or {}
    out["kind"] = kind
    q = est.get("quota") or {}
    if q and not q.get("fits_today", True):
        out["next"] = ("this does not fit today's remaining free GPU time; propose fewer frames, lower resolution or "
                       "samples, or wait until resets_at")
    elif q and q.get("fits_size") is False:
        out["next"] = f"too big for the free beta (max {q.get('max_frames_per_job')} frames and 1920x1080 per job); split it"
    else:
        out["next"] = "tell the user the estimate and ask before calling render_final"
    return _j(out)


RENDER_FINAL_DESCRIPTION = (
    """Render the final frames (or a video) of a Blender scene on JANCTION GPUs. Use it after a preview the user approved.
    When the render time or today's free quota is uncertain, the job is longer than about 24 frames or above 720p, or the
    user asked how long it takes, call render_estimate first and tell the user.

    Call this after the user approved a preview. Pass scene_id from render_preview (or scene_path /
    scene_script to upload a new .blend / bpy script / 3D file). frame_start..frame_end are inclusive; several frames are
    split across GPUs and joined into output.mp4 (output='mp4', fps), a single frame gives a PNG
    (output='png'; 'auto' picks). Use the same environment / blender as the approved preview. Returns job_id and a
    time estimate right away; the render runs in the background: poll with render_status, then fetch with
    render_download. Inputs and results are deleted 24 hours after last use, so download them.
    """ + ENV_DOC + ORBIT_DOC + OUTPUT_DOC
)


@mcp.tool(meta=_ui_meta(), description=RENDER_FINAL_DESCRIPTION)
def render_final(
    scene_path: str = "",
    scene_id: str = "",
    scene_script: str = "",
    frame_start: int = 1,
    frame_end: int = 1,
    width: int = 1920,
    height: int = 1080,
    samples: int = 128,
    fps: int = 24,
    output: str = "auto",
    camera: str = "",
    environment: str = "",
    environment_strength: float = 1.0,
    environment_visible: bool = True,
    blender: str = "",
    assets: Optional[list[str]] = None,
    orbit: bool = False,
    orbit_frames: int = 24,
    orbit_elevation: float = 18.0,
    orbit_target: str = "",
    orbit_distance: float = 1.0,
    engine: str = "",
    transparent: bool = False,
    notify_url: str = "",
) -> str:
    """Render the final frames (or a video) of a Blender scene on JANCTION GPUs. (full description on the tool)."""
    c = _client()
    try:
        sid = _resolve_scene(c, scene_path, scene_id, scene_script, assets)
        extra: dict[str, Any] = {}
        if orbit:
            extra.update({"orbit": True, "orbit_frames": orbit_frames, "orbit_elevation": orbit_elevation,
                          "orbit_target": orbit_target, "orbit_distance": orbit_distance})
            if frame_end <= frame_start:
                frame_end = None  # type: ignore[assignment]  # 1 周ぶんは受付が決める
        j = c.submit(sid, kind="final", frame_start=frame_start, frame_end=frame_end,
                     width=width, height=height, samples=samples, fps=fps, output=output,
                     camera=camera or None, transparent=(True if transparent else None), notify_url=notify_url or None,
                     **_job_params(environment, environment_strength, environment_visible, blender, engine=engine), **extra)
    except ClientError as exc:
        block = _payment_block(exc) or _quota_block(exc)
        return _j(block if block else {"ok": False, "error": str(exc)})
    except (ValueError, FileNotFoundError) as exc:
        return _j({"ok": False, "error": str(exc)})
    brief = _brief(j)
    est = j.get("estimate") or {}
    brief["next"] = (f"tell the user it will take {est.get('human', 'a few minutes')}; then render_status(job_id) "
                     "until status is done, then render_download(job_id, only='mp4') for the video")
    return _j(_attach_upload_notes(brief))


@mcp.tool(meta=_ui_meta())
def render_status(job_id: str) -> str:
    """Check a JANCTION render job: status (queued/running/done/failed/canceled), frames done,
    how many chunks are queued ahead, the ETA (eta.human = remaining time including queue wait),
    artifacts ready, Blender warnings, and the error plus log tail if it failed. Use render_download
    once status is done."""
    try:
        j = _client().job(job_id)
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})
    b = _brief(j)
    if j["status"] in ("queued", "running"):
        b["next"] = f"tell the user: {((j.get('eta') or {}).get('human') or 'still working')}; check again in a while"
    return _j(b)


@mcp.tool(meta=_ui_meta())
def render_download(job_id: str, out_dir: str = "", wait_seconds: int = 0, only: str = "all") -> str:
    """Download a JANCTION render job's files to out_dir (default ~/janction-render/<job_id>).
    only: 'all' (default: every PNG frame plus output.mp4 / sheet.png), 'mp4' (just the video), 'frames'
    (just the PNG frames), 'sheet' (just the preview sheet), 'output' (the MP4 or the sheet only). Pass only='mp4'
    when the user wants the video: it avoids downloading hundreds of frames. wait_seconds > 0 first waits up to
    that long for the job to finish. Returns the local file paths (long lists are summarised)."""
    c = _client()
    try:
        j = c.wait(job_id, timeout=float(wait_seconds)) if wait_seconds > 0 else c.job(job_id)
        if j["status"] != "done" and not j["artifacts"]:
            b = _brief(j)
            b["hint"] = "nothing to download yet"
            return _j(b)
        out = Path(out_dir) if out_dir else _out_root() / job_id
        paths = c.download(job_id, out, only=only)
    except (ClientError, ValueError) as exc:
        return _j({"ok": False, "error": str(exc)})
    b = _brief(j)
    names = [str(p) for p in paths]
    b["output_file"] = next((n for n in names if n.endswith("output.mp4") or n.endswith("sheet.png")), None)
    b["files"] = trim(names, 6)
    b["folder"] = str(out)
    skipped = len(j["artifacts"]) - len(paths)
    if skipped > 0:
        b["not_downloaded"] = f"{skipped} other files (frames); call again with only='frames' or 'all' if needed"
    if j["status"] != "done":
        b["hint"] = "job is not finished; these are the frames ready so far"
    return _j(b)


@mcp.tool()
def render_cancel(job_id: str) -> str:
    """Cancel a queued or running JANCTION render job. GPU time after the cancel is not used."""
    try:
        return _j(_brief(_client().cancel(job_id)))
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})


@mcp.tool()
def render_share(job_id: str, title: str = "", note: str = "", include_script: bool = False, listed: bool = False,
                 prompt: str = "") -> str:
    """Publish a finished render as a public page the user can send to anyone (X, Discord, a client): the image or
    video, the render conditions, an optional title and note, and the bpy script if include_script=True. The page
    keeps a copy of the result after the job's 24-hour expiry, until render_unshare. listed=True asks for it to appear
    in the public gallery after the operator reviews it. prompt: what the user asked you, in their words (shown on the page as 'what the user asked the
    agent'). Ask the user before sharing; return the url to them."""
    try:
        return _j(_client().share(job_id, title=title, note=note, include_script=include_script, listed=listed, prompt=prompt))
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})


@mcp.tool()
def render_unshare(job_id: str) -> str:
    """Remove the public share page of a job (the copy of the result is deleted)."""
    try:
        return _j(_client().unshare(job_id))
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})


@mcp.tool()
def billing(topup_yen: int = 0) -> str:
    """Check the account's quota or credit. During the free beta it returns today's GPU-time usage,
    the daily quota and when it resets (no charges). Once paid plans start: with topup_yen = 0 it
    confirms any payment the user just made and returns the balance (yen), the price per GPU second
    and free previews left; with topup_yen > 0 (minimum 500) it returns a Stripe checkout URL to show
    to the user. Renders are charged by GPU seconds and only for frames that actually rendered."""
    c = _client()
    try:
        if topup_yen > 0:
            co = c.checkout(topup_yen)
            return _j({"checkout_url": co["checkout_url"], "amount_yen": co["amount_yen"],
                       "next": "the user pays at checkout_url in a browser; then call billing() to confirm"})
        me = c.me()
        synced: dict[str, Any] = {}
        if me["billing"]["enabled"]:
            synced = c.billing_sync()
            me = c.me()
        if me.get("quota"):
            q = me["quota"]
            return _j({"mode": "free_beta", "note": "no charges during the free beta; daily GPU-time quota per key",
                       "gpu_seconds_used_today": q["gpu_seconds_used_today"], "gpu_seconds_per_day": q["gpu_seconds_per_day"],
                       "resets_at": q["resets_at"], "max_frames_per_job": q["max_frames_per_job"],
                       "max_pixels": q["max_pixels"]})
        return _j({"balance_yen": me["balance_yen"], "free_previews_left": me["free_previews_left"],
                   "yen_per_gpu_second": me["billing"]["yen_per_gpu_second"],
                   "min_topup_yen": me["billing"]["min_topup_yen"], "billing_enabled": me["billing"]["enabled"],
                   "just_credited": synced.get("credited", []),
                   "pending_checkout_url": me["billing"]["pending_checkout_url"],
                   "charged_yen_total": me["charged_yen_total"]})
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})


@mcp.tool()
def render_info() -> str:
    """Show the JANCTION Render connection: server URL, whether GPU workers are online, queue
    length, and this key's usage. Call this if renders seem stuck or before the first render. Use it to decide
    whether to route a render here: workers_available > 0 means a preview comes back in seconds; gated means the
    GPU is lent out and 'gate' says how long the wait usually is."""
    c = _client()
    try:
        health = c.health()
        me = c.me()
    except (ClientError, Exception) as exc:  # noqa: BLE001
        return _j({"ok": False, "server": c.server, "error": str(exc)})
    return _j({"ok": True, "server": c.server, "workers": health["workers"], "queue": health["queue"],
               "features": health.get("features"),
               "key": me, "downloads_go_to": str(_out_root()),
               "remote_mcp": f"{c.server}/mcp (Streamable HTTP; for Claude.ai, ChatGPT, Cursor: add this URL as a connector)"})


if ui_enabled():
    @mcp.resource(UI_URI, name="JANCTION Render app", title="JANCTION Render", mime_type=UI_MIME,
                  description="Interactive view for JANCTION Render results: preview image, progress, ETA, links, preset picker.",
                  meta={"ui": {"csp": {"resourceDomains": ["https://unpkg.com", "https://render.janction.jp"], "connectDomains": []},
                               "prefersBorder": True}})
    def janction_render_app() -> str:
        return ui_html()


def main() -> None:
    _log(f"stdio, server={Client().server}")
    mcp.run()


if __name__ == "__main__":
    main()
