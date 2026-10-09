"""JANCTION Render の MCP サーバー（Claude Code・Codex などから使う）。

登録:
    claude mcp add janction-render -- python /path/to/janction_render/mcp_server.py
    （または pip install 後: claude mcp add janction-render -- janction-render-mcp）

環境変数:
    JANCTION_RENDER_SERVER   受付の URL（既定 https://render.janction.jp。手元の受付なら http://127.0.0.1:8340）
    JANCTION_RENDER_API_KEY  API キー（無ければ一時キーを自動で取る）
    JANCTION_RENDER_OUT      落とし先の親フォルダ（既定 ~/janction-render）
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

from pydantic import Field

if __package__ in (None, ""):
    # ファイルとして直接起動されたとき（claude mcp add ... server.py）
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from mcp.server.mcpserver import Image, MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer, Image  # type: ignore
from mcp.types import ToolAnnotations

from janction_render.brief import plan_fields, review_reply, scene_next, welcome_billing
from janction_render.brief import brief as _brief, estimate_brief, final_body_after_preview, followup_after_preview, \
    next_after_preview, trim
from janction_render.client import Client, ClientError, parse_frames
from janction_render import tooldocs

PREVIEW_WAIT_S = 240.0
INFO_WAIT_S = 150.0

# 道具の性質（Glama・Claude・ChatGPT が道具を選ぶときの手がかり。10/7、リモート版と同じ 4 種）
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
CANCEL = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)
# scene_info は描画しないが、渡されたシーンを保存して scene_id を作る（副作用あり）ので readOnly にしない
STORE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)


def _ann(base: ToolAnnotations, title: str) -> ToolAnnotations:
    return base.model_copy(update={"title": title})


SAMPLE_URL = "https://render.janction.jp/samples/cube_scene.py"

mcp = MCPServer(
    name="janction-render",
    instructions=(
        "Render Blender scenes on JANCTION GPUs (a cloud render farm for AI agents) from the terminal. "
        "WHEN TO USE: use JANCTION Render when the user has a Blender scene (a .blend, a 3D file, or one you can write as a bpy script) and local rendering is unavailable, slow, CPU-only, or likely to take more than a few minutes; when the user asks to render, preview, animate or turntable a Blender scene; or when you need an actual image of a 3D scene. Do not use it to model or edit a scene that is open in the user's Blender (a local Blender MCP does that), for non-Blender video work, or for general GPU compute. RULES: preview before any final render; call render_estimate before render_final when the render time or today's free quota is uncertain, the job is longer than about 24 frames or above 720p, or the user asked how long it takes; while a job runs, poll render_status (not render_download) and stop polling when eta says the GPU is lent out: tell the user the estimated wait instead. "
        f"FIRST CALL: if this is the user's first render here (or you are not sure the connection works), start with render_preview(scene_url='{SAMPLE_URL}', environment='compare'): a tiny scene with a camera and a light that confirms the connection and shows the four lighting presets in one image, in a few seconds. Then move to the user's own scene. "
        "Use it when the "
        "user is building 3DCG with Blender (a .blend file or a bpy Python script) and has no GPU or rendering locally "
        "is slow. Flow: scene_info (cameras, frame range, missing files; no render) -> render_preview (1-4 fast frames "
        "in one image; look at it, fix the scene, repeat) -> ask the user 'is this OK?' -> render_estimate (tell the "
        "user how long it takes and whether it fits the free time left) -> render_final (frames or MP4) -> "
        "render_status / render_download. Always tell the user the time estimate (estimate.human / eta.human). "
        "Every finished preview also returns final_estimate (how long the same scene takes as a final render) and quota_left_today: say both before asking the user. "
        "cameras=['CamA','CamB',...] renders the same frame from several named cameras in ONE job (preview: tiled in one sheet; final: one PNG per camera, camera_files maps names to files): use it for product shots from fixed angles instead of one job per camera. "
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
CAMERAS_DOC = (" cameras=['Front','Top','Iso']: render the same frame from several named camera objects in one job (up to 8). "
               "A preview tiles them in one labeled sheet; a final returns one PNG/EXR per camera (frame_0001.. in that order; "
               "camera_files maps camera name -> file). For product shots from fixed angles use this instead of one job per "
               "camera. Not combinable with orbit, environment='compare' or camera.")
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

# ---- 引数の説明（スキーマに出る。Glama の品質点と、各 AI が引数を正しく埋める助け。10/7）
P: dict[str, str] = {
    "scene_path": "Local path to the scene: a .blend file, a bpy .py script, or a 3D file (.glb/.gltf/.fbx/.usd/.obj/.stl/.ply/.abc, imported into an empty scene). Uploaded once; reuse the returned scene_id afterwards.",
    "scene_id": "scene_id returned by an earlier call (reuses the uploaded scene without sending it again).",
    "scene_script": "The scene as bpy Python code (text). No file and no local Blender needed; the service runs it in Blender 5.0.",
    "scene_url": f"https link to a .blend, a .py script or a 3D file; the service fetches it (e.g. the sample {SAMPLE_URL}, or a 12-hour /upload link).",
    "assets": "Extra files sent with the scene: local paths (textures, glTF .bin), 'polyhaven:<id>' CC0 assets, or https URLs.",
    "blender": "Blender version: '' (5.0, default) or '5.2' when the worker has it.",
    "frames": "Preview frames: '' = frame 1; '12' = one frame; '1,8,16,24' or '1-24' = up to 4 frames tiled in one labeled image.",
    "camera": "Name of the camera object to render from (default: the scene's active camera, or an automatic camera if none).",
    "cameras": "Several camera object names (up to 8) to render the same frame from in one job; the preview tiles them, the final returns one file per camera. Leave empty for the normal single camera.",
    "width": "Output width in pixels (previews are capped at 1280x720 keeping the aspect ratio).",
    "height": "Output height in pixels (previews are capped at 1280x720 keeping the aspect ratio).",
    "samples": "Cycles samples per pixel (preview: up to 32, default 16; final: default 128).",
    "out_dir": "Local folder to save the files in (default ~/janction-render/<job_id>).",
    "environment": "Lighting preset: '' (scene's own world), 'studio', 'sunset', 'overcast', 'night', or 'compare' (preview only: all four in one 2x2 image).",
    "environment_review": "Light for the review: 'studio' (default; the same neutral light every time), 'sunset', 'overcast', 'night', or '' for the scene's own lights.",
    "environment_strength": "Multiplier for the HDRI preset's brightness (default 1.0).",
    "environment_visible": "False hides the HDRI from the camera (flat grey backdrop, lighting only).",
    "orbit": "True: turntable; an orbit camera circles the scene once (the scene's own camera is not used).",
    "orbit_frames": "Number of frames for one full turn (default 24).",
    "orbit_elevation": "Orbit camera elevation in degrees (default 18).",
    "orbit_target": "Object name or 'x,y,z' to centre the orbit on (default: the scene's main objects).",
    "orbit_distance": "Multiplier for the orbit camera distance (default 1.0).",
    "engine": "'' or 'cycles' (path tracing, default) | 'eevee' (real-time rasterizer; cheaper on long animations).",
    "transparent": "True renders on a transparent background (alpha); png/exr/webm/gif/webp keep it.",
    "frame_start": "First frame to render (inclusive).",
    "frame_end": "Last frame to render (inclusive); equal to frame_start for a single image. With orbit=True and no frame_end, one full turn is rendered.",
    "fps": "Frames per second of the video output (default 24).",
    "output": "'auto' (mp4 for a range, png for one frame) | 'png' | 'exr' | 'mp4' | 'webm' | 'prores' | 'gif' | 'webp'.",
    "notify_url": "Optional https URL that receives one JSON POST when the final render finishes.",
    "kind": "'final' (frame_start..frame_end at width x height, samples) or 'preview' (frames like '1-24').",
    "job_id": "The job_id returned by render_preview or render_final (looks like j_…).",
    "wait_seconds": "Wait up to this many seconds for the job to finish before downloading (0 = do not wait).",
    "only": "'all' (every frame plus output.mp4 / sheet.png) | 'mp4' | 'frames' | 'sheet' | 'output' (the MP4 or the sheet only).",
    "query": "Words to search Poly Haven for (name, tags, category), e.g. 'wooden chair' or 'forest hdri'.",
    "kind_assets": "'models' (default) | 'textures' | 'hdris'.",
    "title": "Title shown on the public share page (optional).",
    "note": "A sentence shown under the image on the share page (optional).",
    "include_script": "True also publishes the bpy script on the share page.",
    "listed": "True asks for the page to appear in the public gallery after the operator reviews it.",
    "prompt": "What the user asked you, in their words (shown as 'what the user asked the agent').",
    "topup_yen": "0 = just report the quota / balance; > 0 (minimum 500) = create a Stripe checkout link for that amount in yen.",
}


def D(name: str, default: Any) -> Any:
    """既定値つきの引数の説明（pydantic の Field）。"""
    return Field(default=default, description=P[name])


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
    """1 日の無料枠の上限に当たった（429 quota_exceeded、無料ベータのモード）ときの返事。"""
    if exc.status != 429 or exc.error != "quota_exceeded":
        return None
    x = exc.extra
    sug = x.get("suggested")
    return {"quota_exceeded": True, "detail": exc.detail, "scope": x.get("scope"),
            "gpu_seconds_used_today": x.get("gpu_seconds_used_today"), "gpu_seconds_per_day": x.get("gpu_seconds_per_day"),
            "resets_at": x.get("resets_at_iso") or x.get("resets_at"),
            # 残りに何コマ入るか（受付 10/8 から。古い受付なら無い）
            **{k: x[k] for k in ("gpu_seconds_left_today", "seconds_per_frame_estimate", "fits_frames", "suggested") if k in x},
            "next": ((f"tell the user today's free GPU time is used up and when it resets; frames {sug['frame_start']}-"
                      f"{sug['frame_end']} still fit today with the same settings (render those now and the rest after the reset)")
                     if isinstance(sug, dict) else
                     "tell the user today's free GPU time is used up and when it resets; a smaller job (fewer frames, "
                     "lower resolution or samples) may still fit")}


def _payment_block(exc: ClientError) -> Optional[dict[str, Any]]:
    """残高不足（402）なら、決済ページのリンクと次の手順を返す。"""
    p = exc.payment()
    if p is None:
        return None
    p["next"] = ("tell the user the job goes past the free GPU time left and what the top-up costs; show checkout_url "
                 "and ask them to pay in a browser (Stripe; the rest stays as credit); after they paid, call billing() to "
                 "confirm the balance, then submit the same job again (or render a smaller job that fits the free time)")
    return p


_LAST_UPLOAD: dict[str, Any] = {}


def _is_remote_asset(a: str) -> bool:
    s = str(a).strip().lower()
    return s.startswith("polyhaven:") or s.startswith("https://")


def _resolve_scene(c: Client, scene_path: str, scene_id: str, scene_script: str = "",
                   assets: Optional[list[str]] = None, scene_url: str = "") -> str:
    """手元のファイルは upload、https のシーンは受付に取らせ、polyhaven:<id> と https の素材も受付に取らせる。"""
    remote = [str(a) for a in (assets or []) if _is_remote_asset(a)]
    local = [a for a in (assets or []) if not _is_remote_asset(a)]
    sid = _resolve_scene_local(c, scene_path, scene_id, scene_script, local or None, scene_url=scene_url)
    if remote:
        up = c.fetch_asset_urls(sid, remote)
        got = list(_LAST_UPLOAD.get("assets") or [])
        _LAST_UPLOAD["assets"] = got + [x for x in (up.get("added") or []) if x not in got]
        if up.get("polyhaven"):
            _LAST_UPLOAD["polyhaven"] = up["polyhaven"]
    return sid


def _resolve_scene_local(c: Client, scene_path: str, scene_id: str, scene_script: str = "",
                         assets: Optional[list[str]] = None, scene_url: str = "") -> str:
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
    if scene_url.strip():
        up = c.upload_url(scene_url.strip())
        _log(f"fetched {scene_url.strip()} -> {up.get('scene_id')}")
        if assets:
            up2 = c.upload_assets(up["scene_id"], [(Path(a).name, a) for a in assets])
            _LAST_UPLOAD.update({"assets": [x["name"] for x in up2.get("assets") or []]})
        return up["scene_id"]
    if not scene_path:
        raise ValueError("pass scene_path (a .blend, a bpy .py script, or a 3D file such as .glb/.fbx/.usd), "
                         "scene_script (bpy code as text), scene_url (an https link), or scene_id from a previous call")
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


def _preview_followup(c: Client, j: dict[str, Any]) -> dict[str, Any]:
    """試し描きの後に「仕上げならどれくらい・今日の枠の残り」を足す（10/7）。失敗しても試し描きの返事は返す。"""
    body = final_body_after_preview(j)
    if not body:
        return {}
    try:
        est = c.estimate(body.pop("scene_id"), **body)
    except Exception as exc:  # noqa: BLE001
        _log(f"follow-up estimate skipped: {exc}")
        return {}
    return followup_after_preview(est, {**body, "scene_id": j.get("scene_id")})


@mcp.tool(annotations=_ann(STORE, "Read scene info"))
def scene_info(scene_path: Annotated[str, D("scene_path", "")] = "",
               scene_id: Annotated[str, D("scene_id", "")] = "",
               scene_script: Annotated[str, D("scene_script", "")] = "",
               scene_url: Annotated[str, D("scene_url", "")] = "",
               assets: Annotated[Optional[list[str]], D("assets", None)] = None,
               blender: Annotated[str, D("blender", "")] = "") -> str:
    """Read a Blender scene WITHOUT rendering: cameras (and which is active), frame range and fps,
    resolution, engine, objects by type, lights, materials, whether it is animated, and any linked
    files that are missing (textures etc. that would render pink). Takes a few seconds, no GPU.

    Give the scene as scene_path (a .blend, a bpy .py script, or a 3D file: .glb/.gltf/.fbx/.usd/.obj/.stl/.ply/.abc,
    imported into an empty scene), scene_script (bpy Python code as text, no file needed), scene_url (https link), or
    scene_id from a previous call. assets: local files to send with the scene (textures, glTF .bin). Call this first for
    a .blend you did not write yourself, or after writing a bpy script to check what it produced. Use the camera names
    and frame range in render_preview / render_final (cameras=[...] takes several of them). Returns scene_id to reuse.
    """
    c = _client()
    try:
        sid = _resolve_scene(c, scene_path, scene_id, scene_script, assets, scene_url=scene_url)
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
    info.update(scene_next(info))          # 次の一手: シーンの縦横比に合わせた試し描き（10/9）
    return _j(_attach_upload_notes(info))


RENDER_PREVIEW_DESCRIPTION = (
    """Render a fast, cheap preview of a Blender scene on a JANCTION GPU and show the image. Choose it over a local
    render when the machine has no NVIDIA GPU, the job is an animation, or you only have a bpy script and no Blender; a
    local Blender MCP is the right tool to edit a scene that is open in the user's Blender, and a single still on a
    machine with its own GPU usually renders faster locally. Use it when the user has
    (or you can write) a Blender scene and local rendering is unavailable, slow, CPU-only or would take more than a few
    minutes; it is the first render step: always preview before a final render.

    Use this when the user is making 3DCG with Blender and wants to see how it looks, but has no
    GPU or local rendering is slow. Give the scene as scene_path (a .blend file OR a bpy Python
    script), scene_script (bpy code as text; no file and no local Blender needed), scene_url (an https link,
    e.g. the sample cube_scene.py for a first connection check), or scene_id from a previous call. frames: '' = frame 1;
    '12' = one frame; '1,8,16,24' or '1-24' = up to 4 frames tiled in ONE image (2x2, each tile
    labeled with its frame number) so you can judge camera motion and animation. Same GPU cost as
    one 720p frame. Quality is deliberately low (up to 1280x720, few samples, denoised).
    Look at the returned image, fix the scene, preview again; when it looks right, ask the user and
    call render_final. Returns scene_id (reuse it without re-uploading), job_id, saved PNG paths,
    Blender warnings (e.g. missing textures), GPU seconds, the expiry time (24h after last use), final_estimate
    (how long the same scene takes as a 1080p final) and quota_left_today: tell the user both before asking.
    """ + ENV_DOC + ORBIT_DOC + CAMERAS_DOC + TRANSPARENT_DOC
)


@mcp.tool(annotations=_ann(READ, "Search CC0 assets"))
def asset_search(query: Annotated[str, Field(description=P["query"])],
                 kind: Annotated[str, D("kind_assets", "models")] = "models") -> str:
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


@mcp.tool(annotations=_ann(WRITE, "Render preview"), structured_output=False, meta=_ui_meta(), description=RENDER_PREVIEW_DESCRIPTION)
def render_preview(
    scene_path: Annotated[str, D("scene_path", "")] = "",
    scene_id: Annotated[str, D("scene_id", "")] = "",
    scene_script: Annotated[str, D("scene_script", "")] = "",
    scene_url: Annotated[str, D("scene_url", "")] = "",
    frames: Annotated[str, D("frames", "")] = "",
    camera: Annotated[str, D("camera", "")] = "",
    cameras: Annotated[Optional[list[str]], D("cameras", None)] = None,
    width: Annotated[int, D("width", 1280)] = 1280,
    height: Annotated[int, D("height", 720)] = 720,
    samples: Annotated[int, D("samples", 16)] = 16,
    out_dir: Annotated[str, D("out_dir", "")] = "",
    environment: Annotated[str, D("environment", "")] = "",
    environment_strength: Annotated[float, D("environment_strength", 1.0)] = 1.0,
    environment_visible: Annotated[bool, D("environment_visible", True)] = True,
    blender: Annotated[str, D("blender", "")] = "",
    assets: Annotated[Optional[list[str]], D("assets", None)] = None,
    orbit: Annotated[bool, D("orbit", False)] = False,
    orbit_frames: Annotated[int, D("orbit_frames", 24)] = 24,
    orbit_elevation: Annotated[float, D("orbit_elevation", 18.0)] = 18.0,
    orbit_target: Annotated[str, D("orbit_target", "")] = "",
    orbit_distance: Annotated[float, D("orbit_distance", 1.0)] = 1.0,
    engine: Annotated[str, D("engine", "")] = "",
    transparent: Annotated[bool, D("transparent", False)] = False,
) -> list[Any]:
    """Render a fast, cheap preview of a Blender scene on a JANCTION GPU and show the image. (full description on the tool)."""
    c = _client()
    try:
        frame_list = parse_frames(frames) if (frames or not orbit) else None
        sid = _resolve_scene(c, scene_path, scene_id, scene_script, assets, scene_url=scene_url)
        j = c.submit(sid, kind="preview", frames=frame_list, camera=camera or None,
                     cameras=(list(cameras) if cameras else None),
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
    fu = _preview_followup(c, j)
    brief.update(fu)
    brief["next"] = next_after_preview(fu, "edit it and call render_preview again", "ask the user before calling render_final",
                                       critic=j.get("critic"))
    _attach_upload_notes(brief)
    result: list[Any] = [_j(brief)]
    if show is not None:
        result.append(Image(data=show.read_bytes(), format="png"))
    return result


@mcp.tool(annotations=_ann(WRITE, "Review a 3D model or scene"), structured_output=False, meta=_ui_meta(),
          description=tooldocs.review_description("stdio"))
def render_review(
    scene_path: Annotated[str, D("scene_path", "")] = "",
    scene_id: Annotated[str, D("scene_id", "")] = "",
    scene_script: Annotated[str, D("scene_script", "")] = "",
    scene_url: Annotated[str, D("scene_url", "")] = "",
    assets: Annotated[Optional[list[str]], D("assets", None)] = None,
    environment: Annotated[str, D("environment_review", "studio")] = "studio",
    orbit_elevation: Annotated[float, D("orbit_elevation", 18.0)] = 18.0,
    orbit_target: Annotated[str, D("orbit_target", "")] = "",
    orbit_distance: Annotated[float, D("orbit_distance", 1.0)] = 1.0,
    blender: Annotated[str, D("blender", "")] = "",
    out_dir: Annotated[str, D("out_dir", "")] = "",
) -> list[Any]:
    """Check a 3D model or a generated Blender scene from 4 sides: pass / warning / fail. (full description on the tool)."""
    c = _client()
    try:
        sid = _resolve_scene(c, scene_path, scene_id, scene_script, assets, scene_url=scene_url)
        j = c.submit(sid, kind="preview", review=True, orbit=True, orbit_elevation=orbit_elevation,
                     orbit_target=orbit_target or None, orbit_distance=orbit_distance,
                     environment=environment or "", blender=blender or None)
        _log(f"review job {j['job_id']} submitted")
        j = _wait_unless_gated(c, j, PREVIEW_WAIT_S)
    except ClientError as exc:
        block = _payment_block(exc) or _quota_block(exc)
        return [_j(block if block else {"ok": False, "error": str(exc)})]
    except (ValueError, FileNotFoundError) as exc:
        return [_j({"ok": False, "error": str(exc)})]
    if j["status"] != "done":
        b = _brief(j)
        b["hint"] = ((_gated_hint(j, "render_status(job_id)") or "still running: call render_status(job_id) and then render_download")
                     if j["status"] in ("queued", "running") else "fix the scene and try again")
        return [_j(b)]
    out = Path(out_dir) if out_dir else _out_root() / j["job_id"]
    paths = c.download(j["job_id"], out)
    show = next((p for p in paths if p.name == "sheet.png"), None) or next((p for p in paths if p.suffix == ".png"), None)
    reply = review_reply(j, _preview_followup(c, j))
    reply["files"] = [str(p) for p in paths]
    _attach_upload_notes(reply)
    result: list[Any] = [_j(reply)]
    if show is not None:
        result.append(Image(data=show.read_bytes(), format="png"))
    return result


@mcp.tool(annotations=_ann(READ, "Estimate render time"))
def render_estimate(scene_id: Annotated[str, D("scene_id", "")] = "",
                    kind: Annotated[str, D("kind", "final")] = "final",
                    frame_start: Annotated[int, D("frame_start", 1)] = 1,
                    frame_end: Annotated[int, D("frame_end", 1)] = 1,
                    frames: Annotated[str, D("frames", "")] = "",
                    width: Annotated[int, D("width", 1920)] = 1920,
                    height: Annotated[int, D("height", 1080)] = 1080,
                    samples: Annotated[int, D("samples", 128)] = 128,
                    cameras: Annotated[Optional[list[str]], D("cameras", None)] = None) -> str:
    """Estimate how long a render will take BEFORE starting it (no GPU time used): GPU seconds, queue wait,
    wall-clock time as a human-readable string ('about 3 minutes'), and whether it fits the free time left and
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
        if cameras:
            params["cameras"] = list(cameras)
            if kind != "preview":
                params.pop("frame_end", None)
        est = c.estimate(scene_id or None, **params)
    except (ClientError, ValueError) as exc:
        return _j({"ok": False, "error": str(exc)})
    out = estimate_brief(est) or {}
    out["kind"] = kind
    q = est.get("quota") or {}
    cost = est.get("cost") or {}
    if q and q.get("fits_size") is False:
        out["next"] = f"too big for one job (max {q.get('max_frames_per_job')} frames and 1920x1080 per job); split it"
    elif q and not q.get("fits_today", True) and q.get("mode") == "free_allowance":
        # 有料モード（10/8〜）: 無料枠を超えた分は残高から。額と残高を言ってから
        out["next"] = (f"this goes past the free GPU time left: about {cost.get('estimated_yen')} JPY would be charged from "
                       f"credit (balance {cost.get('balance_yen')} JPY). Tell the user the time and the price and ask before "
                       "render_final; a smaller job (fewer frames, lower resolution or samples) may stay free")
    elif q and not q.get("fits_today", True):
        out["next"] = ("this does not fit today's remaining free GPU time; propose fewer frames, lower resolution or "
                       "samples, or wait until resets_at")
    else:
        out["next"] = "tell the user the estimate and ask before calling render_final"
    return _j(out)


RENDER_FINAL_DESCRIPTION = (
    """Render the final frames (or a video) of a Blender scene on JANCTION GPUs. Use it after a preview the user approved.
    Choose it over a local render for animations, machines without an NVIDIA GPU, and bpy scripts with no Blender
    installed; a single still on a machine with its own GPU usually renders faster locally, and editing a scene open in
    the user's Blender belongs to a local Blender MCP.
    When the render time or the free time left is uncertain, the job is longer than about 24 frames or above 720p, or the
    user asked how long it takes, call render_estimate first and tell the user.

    Call this after the user approved a preview. Pass scene_id from render_preview (or scene_path /
    scene_script / scene_url to upload a new .blend / bpy script / 3D file). frame_start..frame_end are inclusive; several frames are
    split across GPUs and joined into output.mp4 (output='mp4', fps), a single frame gives a PNG
    (output='png'; 'auto' picks). Use the same environment / blender as the approved preview. Returns job_id and a
    time estimate right away; the render runs in the background: poll with render_status, then fetch with
    render_download. Inputs and results are deleted 24 hours after last use, so download them.
    """ + ENV_DOC + ORBIT_DOC + CAMERAS_DOC + OUTPUT_DOC
)


@mcp.tool(annotations=_ann(WRITE, "Render final frames or video"), meta=_ui_meta(), description=RENDER_FINAL_DESCRIPTION)
def render_final(
    scene_path: Annotated[str, D("scene_path", "")] = "",
    scene_id: Annotated[str, D("scene_id", "")] = "",
    scene_script: Annotated[str, D("scene_script", "")] = "",
    scene_url: Annotated[str, D("scene_url", "")] = "",
    frame_start: Annotated[int, D("frame_start", 1)] = 1,
    frame_end: Annotated[int, D("frame_end", 1)] = 1,
    width: Annotated[int, D("width", 1920)] = 1920,
    height: Annotated[int, D("height", 1080)] = 1080,
    samples: Annotated[int, D("samples", 128)] = 128,
    fps: Annotated[int, D("fps", 24)] = 24,
    output: Annotated[str, D("output", "auto")] = "auto",
    camera: Annotated[str, D("camera", "")] = "",
    cameras: Annotated[Optional[list[str]], D("cameras", None)] = None,
    environment: Annotated[str, D("environment", "")] = "",
    environment_strength: Annotated[float, D("environment_strength", 1.0)] = 1.0,
    environment_visible: Annotated[bool, D("environment_visible", True)] = True,
    blender: Annotated[str, D("blender", "")] = "",
    assets: Annotated[Optional[list[str]], D("assets", None)] = None,
    orbit: Annotated[bool, D("orbit", False)] = False,
    orbit_frames: Annotated[int, D("orbit_frames", 24)] = 24,
    orbit_elevation: Annotated[float, D("orbit_elevation", 18.0)] = 18.0,
    orbit_target: Annotated[str, D("orbit_target", "")] = "",
    orbit_distance: Annotated[float, D("orbit_distance", 1.0)] = 1.0,
    engine: Annotated[str, D("engine", "")] = "",
    transparent: Annotated[bool, D("transparent", False)] = False,
    notify_url: Annotated[str, D("notify_url", "")] = "",
) -> str:
    """Render the final frames (or a video) of a Blender scene on JANCTION GPUs. (full description on the tool)."""
    c = _client()
    try:
        sid = _resolve_scene(c, scene_path, scene_id, scene_script, assets, scene_url=scene_url)
        extra: dict[str, Any] = {}
        if orbit:
            extra.update({"orbit": True, "orbit_frames": orbit_frames, "orbit_elevation": orbit_elevation,
                          "orbit_target": orbit_target, "orbit_distance": orbit_distance})
            if frame_end <= frame_start:
                frame_end = None  # type: ignore[assignment]  # 1 周ぶんは受付が決める
        if cameras:
            extra["cameras"] = list(cameras)
            frame_end = None  # type: ignore[assignment]  # カメラごとに 1 枚（frame_start のコマ）
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
    if cameras:
        brief["next"] = (f"tell the user it will take {est.get('human', 'a few minutes')}; then render_status(job_id) "
                         "until status is done, then render_download(job_id, only='frames'); camera_files says which PNG is which camera")
    else:
        brief["next"] = (f"tell the user it will take {est.get('human', 'a few minutes')}; then render_status(job_id) "
                         "until status is done, then render_download(job_id, only='mp4') for the video")
    return _j(_attach_upload_notes(brief))


@mcp.tool(annotations=_ann(READ, "Render status and ETA"), meta=_ui_meta())
def render_status(job_id: Annotated[str, Field(description=P["job_id"])]) -> str:
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


@mcp.tool(annotations=_ann(READ, "Download results"), meta=_ui_meta())
def render_download(job_id: Annotated[str, Field(description=P["job_id"])],
                    out_dir: Annotated[str, D("out_dir", "")] = "",
                    wait_seconds: Annotated[int, D("wait_seconds", 0)] = 0,
                    only: Annotated[str, D("only", "all")] = "all") -> str:
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


@mcp.tool(annotations=_ann(CANCEL, "Cancel render"))
def render_cancel(job_id: Annotated[str, Field(description=P["job_id"])]) -> str:
    """Cancel a queued or running JANCTION render job. GPU time after the cancel is not used. Frames already rendered
    stay downloadable; the job cannot be resumed (submit it again if needed)."""
    try:
        return _j(_brief(_client().cancel(job_id)))
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})


@mcp.tool(annotations=_ann(WRITE, "Share a render"))
def render_share(job_id: Annotated[str, Field(description=P["job_id"])],
                 title: Annotated[str, D("title", "")] = "",
                 note: Annotated[str, D("note", "")] = "",
                 include_script: Annotated[bool, D("include_script", False)] = False,
                 listed: Annotated[bool, D("listed", False)] = False,
                 prompt: Annotated[str, D("prompt", "")] = "") -> str:
    """Publish a finished render as a public page the user can send to anyone (X, Discord, a client): the image or
    video, the render conditions, an optional title and note, and the bpy script if include_script=True. The page
    keeps a copy of the result after the job's 24-hour expiry, until render_unshare. listed=True asks for it to appear
    in the public gallery after the operator reviews it. prompt: what the user asked you, in their words (shown on the page as 'what the user asked the
    agent'). Ask the user before sharing; return the url to them."""
    try:
        return _j(_client().share(job_id, title=title, note=note, include_script=include_script, listed=listed, prompt=prompt))
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})


@mcp.tool(annotations=_ann(CANCEL, "Unshare a render"))
def render_unshare(job_id: Annotated[str, Field(description=P["job_id"])]) -> str:
    """Remove the public share page of a job (the copy of the result is deleted; the page URL stops working)."""
    try:
        return _j(_client().unshare(job_id))
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})


@mcp.tool(annotations=_ann(READ, "Quota and billing"))
def billing(topup_yen: Annotated[int, D("topup_yen", 0)] = 0) -> str:
    """Check the free GPU time left and the credit. With topup_yen = 0 it confirms any payment the user just
    made and returns what this key can still render for free (a new key's welcome credit, or the free daily
    amount) and when it resets or expires, the balance (yen) and the price per GPU second; with topup_yen > 0
    (minimum 500) it returns a Stripe checkout URL to show to the user. Jobs the free time covers cost nothing;
    beyond it only the extra GPU seconds are charged, and only for frames that actually rendered. Also shows auto
    top-up and monthly plan status, with links the user can open to turn them on."""
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
        q = me.get("quota") or {}
        if q and q.get("mode", "free_beta") == "free_beta":
            return _j({"mode": "free_beta", "note": "no charges during the free beta; daily GPU-time quota per key",
                       "gpu_seconds_used_today": q["gpu_seconds_used_today"], "gpu_seconds_per_day": q["gpu_seconds_per_day"],
                       "gpu_seconds_left_today": max(0, q["gpu_seconds_per_day"] - q["gpu_seconds_used_today"]),
                       "resets_at": q["resets_at"], "max_frames_per_job": q["max_frames_per_job"],
                       "max_pixels": q["max_pixels"]})
        if q and q.get("welcome"):
            # ようこそクレジット（10/8 夜 本人の判断、docs/46）: リモートの billing と同じ形
            return _j(welcome_billing(q["welcome"], me, synced))
        if q:
            # 有料（10/8〜）: 毎日の無料枠と、超えた分を払う残高の両方
            yen = me["billing"]["yen_per_gpu_second"]
            return _j({"mode": "free_allowance",
                       "note": (f"the first {q['gpu_seconds_per_day'] // 60} GPU-minutes of each day are free; beyond that "
                                f"{yen} JPY per GPU-second from prepaid credit (only the part over the free time is charged)"),
                       "gpu_seconds_used_today": q["gpu_seconds_used_today"], "gpu_seconds_per_day": q["gpu_seconds_per_day"],
                       "gpu_seconds_left_today": max(0, q["gpu_seconds_per_day"] - q["gpu_seconds_used_today"]),
                       "resets_at": q["resets_at"], "max_frames_per_job": q["max_frames_per_job"],
                       "max_pixels": q["max_pixels"], "balance_yen": me["balance_yen"],
                       "held_yen": me.get("held_yen", 0), "held_jobs": me.get("held_jobs", 0), "yen_per_gpu_second": yen,
                       "min_topup_yen": me["billing"]["min_topup_yen"], "just_credited": synced.get("credited", []),
                       "pending_checkout_url": me["billing"]["pending_checkout_url"],
                       "topup_options": (me["billing"].get("topup_options") or {}).get("options"),
                       "charged_yen_total": me["charged_yen_total"], **plan_fields(me)})
        return _j({"balance_yen": me["balance_yen"], "free_previews_left": me["free_previews_left"],
                   "yen_per_gpu_second": me["billing"]["yen_per_gpu_second"],
                   "min_topup_yen": me["billing"]["min_topup_yen"], "billing_enabled": me["billing"]["enabled"],
                   "just_credited": synced.get("credited", []),
                   "pending_checkout_url": me["billing"]["pending_checkout_url"],
                   "charged_yen_total": me["charged_yen_total"]})
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})


@mcp.tool(annotations=_ann(READ, "Service status"))
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
               "first_call": f"render_preview(scene_url='{SAMPLE_URL}', environment='compare') confirms the connection in a few seconds",
               "remote_mcp": f"{c.server}/mcp (Streamable HTTP; for Claude.ai, ChatGPT, Cursor: add this URL as a connector)"})


if ui_enabled():
    @mcp.resource(UI_URI, name="JANCTION Render app", title="JANCTION Render", mime_type=UI_MIME,
                  description="Interactive view for JANCTION Render results: preview image, progress, ETA, links, preset picker.",
                  meta={"ui": {"csp": {"resourceDomains": ["https://unpkg.com", "https://render.janction.jp"], "connectDomains": []},
                               "prefersBorder": True}})
    def janction_render_app() -> str:
        return ui_html()


# 道具の説明の新版（stdio の既定。JR_TOOLDOCS=old で今の文面に戻る、docs/40）
tooldocs.apply(mcp, "stdio")


def main() -> None:
    _log(f"stdio, server={Client().server}")
    mcp.run()


if __name__ == "__main__":
    main()
