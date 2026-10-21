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

from janction_render.brief import review_reply
from janction_render.brief import brief as _brief, estimate_brief, final_body_after_preview, followup_after_preview, \
    next_after_preview, trim, PRESENT_FIRST, preview_presentation, turntable_estimate
from janction_render.client import Client, ClientError, parse_frames
from janction_render import mcp_common, prompts as _prompts, tooldocs

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

def _server_version_kw() -> dict:
    """握手（initialize）の serverInfo に版を載せる（10/10 の点検で空だった）。mcp 1.x の FastMCP は version を受けない。"""
    import inspect

    from janction_render import __version__
    return {"version": __version__} if "version" in inspect.signature(MCPServer.__init__).parameters else {}


mcp = MCPServer(
    name="janction-render",
    **_server_version_kw(),
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
        "Blender 5.0 or 5.2 with Cycles on GPU (a .blend opens with the version it was saved in; scripts and 3D files use 5.0 unless blender='5.2'; blender='4.5', '4.2' or '3.6' picks an older Blender, and a script that stops on Blender 5 because of an older API is rendered again on 4.5, 4.2 or 3.6 automatically); engine='eevee' switches to EEVEE "
        "(about half the per-frame cost on animations of a few dozen frames or more; each job pays ~7 s of shader compilation, so previews stay on Cycles); output='png'|'exr' returns frames, 'mp4'|'webm'|'prores' a video. Blender 5.0 API notes for scripts: materials always use nodes, so set a color on the Principled BSDF (mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (r, g, b, 1)); mat.diffuse_color only affects the viewport. Animate with obj.keyframe_insert(); obj.animation_data.action.fcurves no longer exists (set bpy.context.preferences.edit.keyframe_new_interpolation_type='LINEAR' before inserting keyframes for constant-speed motion); do not set Material.use_nodes; leave resolution, samples and denoising to the service. Inputs: a .blend, a bpy "
        "script, or a 3D file (FBX, glTF/GLB, USD, OBJ, STL, PLY, Alembic) that is imported into an empty scene; images "
        "and other assets can be sent with the scene (assets=[...]). environment='studio'|'sunset'|'overcast'|'night' "
        "lights the scene with a bundled HDRI for a good-looking first render. Inputs and results are deleted 24 hours "
        "after last use. Use it when: the user asks to render a Blender file or bpy script, an agent-made Blender scene "
        "needs its final image or video, the machine has no NVIDIA GPU or local rendering is slow, or many frames need "
        "GPU rendering. Do not use it for modeling without rendering or for non-Blender workloads."
    ),
)

# 引数の説明はリモートと共通（janction_render/mcp_common.py、10/12）
_D = mcp_common.docs("stdio")
OUTPUT_DOC, TRANSPARENT_DOC, ORBIT_DOC, CAMERAS_DOC = _D["OUTPUT_DOC"], _D["TRANSPARENT_DOC"], _D["ORBIT_DOC"], _D["CAMERAS_DOC"]
# ---- MCP Apps（Claude Desktop など対応ホストに、絵と進み具合のパネルを出す。対応していないホストは無視する）
UI_URI = "ui://janction-render/app.html"
UI_MIME = "text/html;profile=mcp-app"


def ui_enabled() -> bool:
    return (os.environ.get("JR_MCP_APPS") or "1").strip().lower() not in ("0", "false", "no", "off")


def _ui_meta() -> Optional[dict[str, Any]]:
    return {"ui": {"resourceUri": UI_URI}, "ui/resourceUri": UI_URI} if ui_enabled() else None


def ui_html() -> str:
    return (Path(__file__).resolve().parent / "mcp_app.html").read_text(encoding="utf-8")


ENV_DOC, POLYHAVEN_DOC = _D["ENV_DOC"], _D["POLYHAVEN_DOC"]

# ---- 引数の説明（スキーマに出る。Glama の品質点と、各 AI が引数を正しく埋める助け。10/7）
P: dict[str, str] = {
    "scene_path": "Local path to the scene: a .blend file, a bpy .py script, or a 3D file (.glb/.gltf/.fbx/.usd/.obj/.stl/.ply/.abc, imported into an empty scene). Uploaded once; reuse the returned scene_id afterwards.",
    "scene_id": "scene_id returned by an earlier call (reuses the uploaded scene without sending it again).",
    "scene_script": "The scene as bpy Python code (text). No file and no local Blender needed; the service runs it in Blender 5.0 (5.2 with blender='5.2').",
    "scene_url": f"https link to a .blend, a .py script or a 3D file; the service fetches it (e.g. the sample {SAMPLE_URL}, or a 12-hour /upload link).",
    "assets": "Extra files sent with the scene: local paths (textures, glTF .bin), 'polyhaven:<id>' CC0 assets, or https URLs.",
    "blender": "Blender version: '' (default: a .blend opens with the version it was saved in, other scenes with 5.0) or '5.0' / '5.2' (also '4.5', '4.2', '3.6'; a script that stops on Blender 5 because of an older API is rendered again on those automatically) to choose.",
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
    "max_yen": "Budget for this job in JPY (-1 = none). The job is refused before it starts if it could cost more; pass what the user agreed to.",
    "idempotency_key": "Optional key (letters, digits, . _ : -). Resubmitting with the same key returns the first job instead of rendering and charging twice.",
    "kind": "'final' (frame_start..frame_end at width x height, samples) or 'preview' (frames like '1-24').",
    "job_id": "The job_id returned by render_preview or render_final (looks like j_…).",
    "wait_seconds": "Wait up to this many seconds for the job to finish before downloading (0 = do not wait).",
    "only": "'all' (every frame plus output.mp4 / sheet.png) | 'mp4' | 'frames' | 'sheet' | 'blend' (scene.blend) | 'output' (the MP4, the sheet or scene.blend only).",
    "query": "Words to search Poly Haven for (name, tags, category), e.g. 'wooden chair' or 'forest hdri'.",
    "kind_assets": "'models' (default) | 'textures' | 'hdris'.",
    "title": "Title shown on the public share page (optional).",
    "note": "A sentence shown under the image on the share page (optional).",
    "include_script": "True also publishes the bpy script on the share page.",
    "listed": "True asks for the page to appear in the public gallery after the operator reviews it.",
    "prompt": "What the user asked you, in their words (shown as 'what the user asked the agent').",
    "topup_yen": "0 = just report the quota / balance; > 0 (minimum 500) = create a Stripe checkout link for that amount in yen.",
    "preset": "Purpose preset: 'product' (4 studio shots at 0/90/180/270 deg on a plain backdrop; final = 4 PNGs), 'turntable' (360-degree MP4, studio light, plain backdrop), 'animation' (the scene's own camera, lights and frame range), or '' (none). Fills what you do not pass.",
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
    return {"quota_exceeded": True, "detail": exc.detail, "code": "QUOTA_EXCEEDED", "retryable": True,
            "recommended_action": "WAIT_UNTIL_RESET", "scope": x.get("scope"),
            "gpu_seconds_used_today": x.get("gpu_seconds_used_today"), "gpu_seconds_per_day": x.get("gpu_seconds_per_day"),
            "resets_at": x.get("resets_at_iso") or x.get("resets_at"),
            # 残りに何コマ入るか（受付 10/8 から。古い受付なら無い）
            **{k: x[k] for k in ("gpu_seconds_left_today", "seconds_per_frame_estimate", "fits_frames", "suggested") if k in x},
            "next": ((f"tell the user today's free GPU time is used up and when it resets; frames {sug['frame_start']}-"
                      f"{sug['frame_end']} still fit today with the same settings (render those now and the rest after the reset)")
                     if isinstance(sug, dict) else
                     "tell the user today's free GPU time is used up and when it resets; a smaller job (fewer frames, "
                     "lower resolution or samples) may still fit")}


def _fail(exc: Exception) -> dict[str, Any]:
    """道具の失敗（10/11）: 今までの error の 1 文に、受付の REST と同じ code / retryable / recommended_action を足す。
    エージェントは code で分岐し（AUTH_REQUIRED は接続の案内、INSUFFICIENT_CREDIT は決済、…）、同じ入力を繰り返さない。"""
    out: dict[str, Any] = {"ok": False, "error": str(exc)}
    if isinstance(exc, ClientError):
        out.update(exc.agent_fields())
        # 10/14 IF-03: 大きさで断られたら、ブラウザの /upload（分けて送る・途中から再開）を代わりの道として足す
        mcp_common.add_upload_hint(out, _server_url(), exc.error, exc.status)
        mcp_common.add_feasibility(out, exc.error, exc.extra)     # 1 枚が時間の上限を超える（10/20）: 案を渡す
        if exc.status == 404 and exc.error == "not_found":
            # 10/14 IF-05: 覚えていない job_id には一覧の道を
            out.setdefault("next", "render_status() with no job_id lists this key's recent jobs")
    else:   # この PC の上の入力（ファイルが無い・形が違う）
        out.update({"code": "INVALID_INPUT", "retryable": False, "recommended_action": "FIX_INPUT"})
    return out


def _server_url() -> str:
    try:
        return _client().server
    except Exception:  # noqa: BLE001
        return ""


def _payment_block(exc: ClientError) -> Optional[dict[str, Any]]:
    """残高不足（402）なら、決済ページのリンクと次の手順を返す。"""
    p = exc.payment()
    if p is None:
        return None
    # 払ったあとは預かり（resume.order_id）から自動で始まる受付（0.4.98〜）なら、送り直させない（10/14）
    after = ("after they paid (or registered the card) the render starts by itself: tell them so and follow it with "
             "render_status(job_id=resume.order_id); do not upload or submit it again (a resend returns the same job)"
             if p.get("resume") else "after they paid, call billing() to confirm the balance, then submit the same job again")
    if p.get("card_offer"):
        # 0 円のカード登録で無料の GPU 時間が足される鍵には、その道を先に（docs/62 P0-1）。チャージは代わりの道
        p["next"] = ("first tell the user card_offer.tell_user in their own language (registering a card costs nothing and adds free "
                     "GPU time; they open card_offer.link in a browser), and offer the top-up at checkout_url as the other way; " + after)
        return p
    p["next"] = (("relay tell_user to the user in their own language (what this render costs and what the top-up buys) "
                  "with checkout_url " if p.get("tell_user") else
                  "tell the user the job goes past the free GPU time left and what the top-up costs; show checkout_url ")
                 + "and ask them to pay in a browser (Stripe; the rest stays as credit); " + after
                 + " (or render a smaller job that fits the free time)")
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


# プリセットの規則と仕事の設定の組み立てはリモートと共通（mcp_common、10/12）
_job_params = mcp_common.job_params
PURPOSE_PRESETS = mcp_common.PURPOSE_PRESETS
FINAL_TOOL_DEFAULTS = mcp_common.FINAL_TOOL_DEFAULTS
_preset_of = mcp_common.preset_of
_with_preset = mcp_common.with_preset


def _ensure_scene_info(c: Client, sid: str) -> None:
    """preset='animation' のコマ範囲のために、シーンを一度読んでおく（描かない・GPU なし）。受付が直前の info の結果を使う。"""
    j = c.submit(sid, kind="info")
    if j["status"] != "done":
        j = _wait_unless_gated(c, j, INFO_WAIT_S)
    if j["status"] != "done":
        raise ValueError("preset='animation' needs the scene's frame range, but reading the scene did not finish ("
                         + str((j.get("failure") or {}).get("reason") or j.get("error") or j["status"])
                         + "); pass frames (preview) or frame_start / frame_end (final) instead")


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


def _turntable_followup(c: Client, j: dict[str, Any]) -> dict[str, Any]:
    """試し描きの次の一手「360 度の回転動画」の時間と値段（10/12）。回転・複数カメラの試し描きには出さない。"""
    p = j.get("params") or {}
    if p.get("orbit") or p.get("cameras") or not j.get("scene_id"):
        return {}
    try:
        return turntable_estimate(c.estimate(j["scene_id"], kind="final", preset="turntable"))
    except Exception as exc:  # noqa: BLE001
        _log(f"turntable estimate skipped: {exc}")
        return {}


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
        return _j(_fail(exc))
    if j["status"] != "done":
        b = _brief(j)
        b["hint"] = (_gated_hint(j, "scene_info(scene_id)") or "still queued (a GPU worker may be busy); call scene_info again in a moment") \
            if j["status"] in ("queued", "running") else "fix the scene and try again"
        return _j(b)
    info = mcp_common.scene_info_reply(j, "assets=[...]")
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
        return _j(_fail(exc))


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
    preset: Annotated[str, D("preset", "")] = "",
) -> list[Any]:
    """Render a fast, cheap preview of a Blender scene on a JANCTION GPU and show the image. (full description on the tool)."""
    c = _client()
    try:
        preset = _preset_of(preset)
        frame_list = parse_frames(frames) if (frames or not (orbit or preset)) else None
        sid = _resolve_scene(c, scene_path, scene_id, scene_script, assets, scene_url=scene_url)
        if preset == "animation" and frame_list is None:
            _ensure_scene_info(c, sid)
        params = dict(frames=frame_list, camera=camera or None, cameras=(list(cameras) if cameras else None),
                      width=width, height=height, samples=samples, transparent=(True if transparent else None),
                      **_job_params(environment, environment_strength, environment_visible, blender, engine=engine),
                      **({"orbit": True, "orbit_frames": orbit_frames, "orbit_elevation": orbit_elevation,
                          "orbit_target": orbit_target, "orbit_distance": orbit_distance} if orbit else {}))
        j = c.submit(sid, kind="preview", **_with_preset(params, preset, "preview"))
        _log(f"preview job {j['job_id']} submitted frames={frame_list}")
        j = _wait_unless_gated(c, j, PREVIEW_WAIT_S)
    except ClientError as exc:
        block = _payment_block(exc) or _quota_block(exc)
        return [_j(block if block else _fail(exc))]
    except (ValueError, FileNotFoundError) as exc:
        return [_j(_fail(exc))]
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
    brief.update(preview_presentation(j, fu, saved_to=str(show or out), turntable=_turntable_followup(c, j)))
    brief["next"] = PRESENT_FIRST + next_after_preview(fu, "edit it and call render_preview again",
                                                       "ask the user before calling render_final", critic=j.get("critic"))
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
        return [_j(block if block else _fail(exc))]
    except (ValueError, FileNotFoundError) as exc:
        return [_j(_fail(exc))]
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
                    cameras: Annotated[Optional[list[str]], D("cameras", None)] = None,
                    preset: Annotated[str, D("preset", "")] = "") -> str:
    """Estimate how long a render will take BEFORE starting it (no GPU time used): GPU seconds, queue wait,
    wall-clock time as a human-readable string ('about 3 minutes'), and whether it fits the free time left and
    the size limits. kind is 'final' (frame_start..frame_end at width x height, samples) or 'preview' (frames
    like '1-24'). Pass scene_id when you have one: the estimate then uses this scene's own measured render
    times. Tell the user the result before calling render_final. Prefer this before render_final whenever the time
    or quota is uncertain, the job is longer than about 24 frames or above 720p, or the user asked how long it takes."""
    c = _client()
    try:
        preset = _preset_of(preset)
        params, needs_info = mcp_common.estimate_body(kind, scene_id, frames, frame_start, frame_end, width, height, samples, cameras, preset)
        params.pop("scene_id", None)
        if needs_info:
            _ensure_scene_info(c, scene_id)
        est = c.estimate(scene_id or None, **params)
    except (ClientError, ValueError) as exc:
        return _j(_fail(exc))
    out = estimate_brief(est) or {}
    out["kind"] = kind
    out["next"] = mcp_common.estimate_next(est)
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
    max_yen: Annotated[int, D("max_yen", -1)] = -1,
    idempotency_key: Annotated[str, D("idempotency_key", "")] = "",
    preset: Annotated[str, D("preset", "")] = "",
) -> str:
    """Render the final frames (or a video) of a Blender scene on JANCTION GPUs. (full description on the tool)."""
    c = _client()
    try:
        preset = _preset_of(preset)
        sid = _resolve_scene(c, scene_path, scene_id, scene_script, assets, scene_url=scene_url)
        if preset == "animation" and frame_end <= frame_start:
            _ensure_scene_info(c, sid)
        extra: dict[str, Any] = {}
        if orbit:
            extra.update({"orbit": True, "orbit_frames": orbit_frames, "orbit_elevation": orbit_elevation,
                          "orbit_target": orbit_target, "orbit_distance": orbit_distance})
            if frame_end <= frame_start:
                frame_end = None  # type: ignore[assignment]  # 1 周ぶんは受付が決める
        if cameras:
            extra["cameras"] = list(cameras)
            frame_end = None  # type: ignore[assignment]  # カメラごとに 1 枚（frame_start のコマ）
        params = dict(frame_start=frame_start, frame_end=frame_end,
                      width=width, height=height, samples=samples, fps=fps, output=output,
                      camera=camera or None, transparent=(True if transparent else None), notify_url=notify_url or None,
                      max_yen=(max_yen if max_yen >= 0 else None), idempotency_key=idempotency_key or None,
                      **_job_params(environment, environment_strength, environment_visible, blender, engine=engine), **extra)
        params = _with_preset(params, preset, "final")
        if not params.get("idempotency_key"):
            # 時間切れのあとの呼び直しで 2 本描かない（10/13、mcp_common.auto_idempotency_key）
            params["idempotency_key"] = mcp_common.auto_idempotency_key(
                "render_final", {"scene_id": scene_id, "scene_path": mcp_common.file_stamp(scene_path), "scene_url": scene_url,
                                 "scene_script": mcp_common.digest(scene_script), "assets": assets, **params})
        j = c.submit(sid, kind="final", **params)
    except ClientError as exc:
        block = _payment_block(exc) or _quota_block(exc)
        return _j(block if block else _fail(exc))
    except (ValueError, FileNotFoundError) as exc:
        return _j(_fail(exc))
    brief = _brief(j)
    est = j.get("estimate") or {}
    if j.get("split"):
        # 240 コマを超える仕上げは受付が部分に分けて 1 つの ID で返す（10/12）。道具の説明は変えず、返事で伝える
        brief["split"] = j["split"]
        brief["tell_user"] = j.get("tell_user")
    if cameras:
        brief["next"] = (f"tell the user it will take {est.get('human', 'a few minutes')}; then render_status(job_id) "
                         "until status is done, then render_download(job_id, only='frames'); camera_files says which PNG is which camera")
    else:
        brief["next"] = (f"tell the user it will take {est.get('human', 'a few minutes')}; then render_status(job_id) "
                         "until status is done, then render_download(job_id, only='mp4') for the video")
    if j.get("credit_note"):
        # 無料分が残り少ない（受付の credit_note、0.4.39）: 壁に当たる前に人間に伝える
        brief["credit_note"] = j["credit_note"]
        brief["next"] += ("; also tell the user credit_note.tell_user in their own language ("
                          + ("the free credit expires soon but is not used up; do not push a top-up"
                             if j["credit_note"].get("reason") == "expiring" else "free credit is running low") + ")")
    return _j(_attach_upload_notes(brief))


@mcp.tool(annotations=_ann(READ, "Render status and ETA"), meta=_ui_meta())
def render_status(job_id: Annotated[str, Field(description=P["job_id"])] = "") -> str:
    """Check a JANCTION render job: status (queued/running/done/failed/canceled), frames done,
    how many chunks are queued ahead, the ETA (eta.human = remaining time including queue wait),
    artifacts ready, Blender warnings, and the error plus log tail if it failed. Use render_download
    once status is done. Without job_id it lists this key's recent jobs and the scene_ids still kept
    (to pick up earlier work in a new conversation)."""
    if not (job_id or "").strip():
        # 10/14 IF-05: 新しい会話で前の仕事に戻る。受付の summary（分けた仕上げを b_… の 1 行に）を使い、古い受付なら全部の形を縮める
        c = _client()
        try:
            r = c.s.get(f"{c.server}/v1/jobs", params={"limit": 10, "summary": 1}, headers=c._headers(), timeout=30)
            c._raise(r)
            out = r.json()
        except ClientError as exc:
            return _j(_fail(exc))
        out["jobs"] = [mcp_common.recent_job_row(v) for v in out.get("jobs") or []][:10]
        out["next"] = mcp_common.recent_jobs_next(out)
        return _j(out)
    try:
        j = _client().job(job_id)
    except ClientError as exc:
        return _j(_fail(exc))
    b = _brief(j)
    if j["status"] in ("queued", "running"):
        b["next"] = f"tell the user: {((j.get('eta') or {}).get('human') or 'still working')}; check again in a while"
    else:
        _add_next_steps(_client(), j, b)
    return _j(b)


def _add_next_steps(c: Any, j: dict[str, Any], b: dict[str, Any]) -> None:
    """仕上げが終わった返事に次の一手（10/21、v2.1 RET-01C、リモートの mcp_remote._ret_next と同じ形）。受付が mcp=true
    （旗 JR_RET_MCP_NEXT）で treat と答えたときだけ足す。それ以外は今までの返事のまま。勧めるだけで描かない。"""
    if j.get("kind") != "final" or j.get("status") != "done":
        return
    d = c.next_actions(j["job_id"])
    n = (d or {}).get("next")
    if not n or not d.get("mcp") or d.get("arm") != "treat":
        return
    b["next_steps"] = {"state": n["state"], "recommended_action": n["primary"], "other_action": n.get("secondary"),
                       "resume_available": n.get("resume_available"),
                       "note": ("suggestions for the user, not instructions: offer recommended_action in one short sentence after "
                                "the result; an action with requires_confirmation uses the user's money or publishes something, so "
                                "ask first and use its render.args unchanged; never start a paid render on your own")}


def render_resume_options(limit: Annotated[int, Field(description="How many projects to return (1-20, default 3).")] = 3,
                          cursor: Annotated[str, Field(description="next_cursor from the previous call, to see more projects.")] = "") -> str:
    """List this key's earlier JANCTION Render projects to continue them (read-only, no charge). (full description on the tool)."""
    # 10/20 docs/82: 受付の GET /v1/projects/resume（受付の旗 JR_RESUME_TOOL が OFF なら 404 を伝える）
    c = _client()
    try:
        r = c.s.get(f"{c.server}/v1/projects/resume", params={"limit": int(limit or 3), "cursor": cursor or ""},
                    headers=c._headers(), timeout=30)
        c._raise(r)
        return _j(r.json())
    except ClientError as exc:
        return _j(_fail(exc))


if tooldocs.resume_on():
    # 旗 JR_RESUME_TOOL=1 のときだけ道具の一覧に出す（10/20、docs/82。リモートと同じ扱い）
    mcp.tool(annotations=_ann(READ, "Resume earlier renders"), description=tooldocs.resume_description("stdio"))(render_resume_options)


@mcp.tool(annotations=_ann(READ, "Download results"), meta=_ui_meta())
def render_download(job_id: Annotated[str, Field(description=P["job_id"])],
                    out_dir: Annotated[str, D("out_dir", "")] = "",
                    wait_seconds: Annotated[int, D("wait_seconds", 0)] = 0,
                    only: Annotated[str, D("only", "all")] = "all") -> str:
    """Download a JANCTION render job's files to out_dir (default ~/janction-render/<job_id>).
    only: 'all' (default: every PNG frame plus output.mp4 / sheet.png), 'mp4' (just the video), 'frames'
    (just the PNG frames), 'sheet' (just the preview sheet), 'blend' (scene.blend from output='blend'), 'output' (the MP4, the sheet or scene.blend only). Pass only='mp4'
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
        return _j(_fail(exc))
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
    else:
        _add_next_steps(c, j, b)
    return _j(b)


@mcp.tool(annotations=_ann(CANCEL, "Cancel render"))
def render_cancel(job_id: Annotated[str, Field(description=P["job_id"])]) -> str:
    """Cancel a queued or running JANCTION render job. GPU time after the cancel is not used. Frames already rendered
    stay downloadable; the job cannot be resumed (submit it again if needed)."""
    try:
        return _j(_brief(_client().cancel(job_id)))
    except ClientError as exc:
        return _j(_fail(exc))


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
        return _j(_fail(exc))


@mcp.tool(annotations=_ann(CANCEL, "Unshare a render"))
def render_unshare(job_id: Annotated[str, Field(description=P["job_id"])]) -> str:
    """Remove the public share page of a job (the copy of the result is deleted; the page URL stops working)."""
    try:
        return _j(_client().unshare(job_id))
    except ClientError as exc:
        return _j(_fail(exc))


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
        return _j(mcp_common.billing_reply(me, synced))
    except ClientError as exc:
        return _j(_fail(exc))


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
        # 10/14 IF-10: 失敗しても、どこで止まったか（受付に届かない／鍵が効かない）を言葉で返す
        errs: dict[str, str] = {}
        h = None
        try:
            h = c.health()
        except Exception as e2:  # noqa: BLE001
            errs["health"] = str(e2)[:200]
        if h is not None:
            errs["me"] = str(exc)[:200]
        return _j({**_fail(exc), "server": c.server,
                   "diagnose": mcp_common.diagnose(h, None, None, connection=f"local MCP to {c.server}", errors=errs)})
    # 10/14 IF-10: 端末を見ない人にも伝わる診断（つながり・鍵・無料分・GPU・この鍵の最後の失敗）
    last_failed = None
    try:
        r = c.s.get(f"{c.server}/v1/jobs", params={"limit": 5, "summary": 1}, headers=c._headers(), timeout=30)
        if r.status_code == 200:
            rows = [mcp_common.recent_job_row(v) for v in r.json().get("jobs") or []]
            ended = [x for x in rows if x.get("status") in ("done", "failed")]
            if ended and ended[0].get("status") == "failed":
                last_failed = ended[0]
    except Exception:  # noqa: BLE001 — 一覧が取れなくても診断は出す
        pass
    diag = mcp_common.diagnose(health, me, last_failed, connection=f"local MCP to {c.server}")
    return _j({"ok": True, "server": c.server, "diagnose": diag, "workers": health["workers"], "queue": health["queue"],
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
# よくある頼み方の型（MCP のプロンプト、10/10）。クライアントのスラッシュコマンドに出る。JR_MCP_PROMPTS=0 で止める
_prompts.register(mcp, remote=False)


def main() -> None:
    _log(f"stdio, server={Client().server}")
    mcp.run()


if __name__ == "__main__":
    main()
