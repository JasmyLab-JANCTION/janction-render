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
from typing import Any

if __package__ in (None, ""):
    # ファイルとして直接起動されたとき（claude mcp add ... server.py）
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from mcp.server.mcpserver import Image, MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer, Image  # type: ignore

from janction_render.brief import brief as _brief, estimate_brief
from janction_render.client import Client, ClientError, parse_frames

PREVIEW_WAIT_S = 240.0
INFO_WAIT_S = 150.0

mcp = MCPServer(
    name="janction-render",
    instructions=(
        "Render Blender scenes on JANCTION GPUs (a cloud render farm for AI agents) from the terminal. Use it when the "
        "user is building 3DCG with Blender (a .blend file or a bpy Python script) and has no GPU or rendering locally "
        "is slow. Flow: scene_info (cameras, frame range, missing files; no render) -> render_preview (1-4 fast frames "
        "in one image; look at it, fix the scene, repeat) -> ask the user 'is this OK?' -> render_estimate (tell the "
        "user how long it takes and whether it fits today's free quota) -> render_final (frames or MP4) -> "
        "render_status / render_download. Always tell the user the time estimate (estimate.human / eta.human). "
        "Blender 5.0 with Cycles on GPU. Inputs and results are deleted 24 hours after last use. Use it when: the user asks "
        "to render a Blender file or bpy script, an agent-made Blender scene needs its final image or video, the machine has "
        "no NVIDIA GPU or local rendering is slow, or many frames need GPU rendering. Do not use it for modeling without "
        "rendering or for non-Blender workloads."
    ),
)


def _log(msg: str) -> None:
    print(f"[janction-render] {msg}", file=sys.stderr, flush=True)


def _client() -> Client:
    return Client(client="mcp")


def _out_root() -> Path:
    return Path(os.environ.get("JANCTION_RENDER_OUT") or (Path.home() / "janction-render"))


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _quota_block(exc: ClientError) -> Optional[dict[str, Any]]:
    """無料ベータの 1 日の上限に当たった（429 quota_exceeded）ときの返事。"""
    if exc.status != 429 or exc.error != "quota_exceeded":
        return None
    x = exc.extra
    return {"quota_exceeded": True, "detail": exc.detail, "scope": x.get("scope"),
            "gpu_seconds_used_today": x.get("gpu_seconds_used_today"), "gpu_seconds_per_day": x.get("gpu_seconds_per_day"),
            "resets_at": x.get("resets_at"),
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


def _resolve_scene(c: Client, scene_path: str, scene_id: str, scene_script: str = "") -> str:
    if scene_id:
        return scene_id
    if scene_script.strip():
        up = c.upload_text("scene.py", scene_script)
        _log(f"uploaded inline script -> {up['scene_id']} ({up['size']} bytes)")
        return up["scene_id"]
    if not scene_path:
        raise ValueError("pass scene_path (a .blend or a bpy .py script), scene_script (bpy code as text), "
                         "or scene_id from a previous call")
    up = c.upload(scene_path)
    _log(f"uploaded {up['name']} -> {up['scene_id']} ({up['size']} bytes)")
    return up["scene_id"]


@mcp.tool()
def scene_info(scene_path: str = "", scene_id: str = "", scene_script: str = "") -> str:
    """Read a Blender scene WITHOUT rendering: cameras (and which is active), frame range and fps,
    resolution, engine, objects by type, lights, materials, whether it is animated, and any linked
    files that are missing (textures etc. that would render pink). Takes a few seconds, no GPU.

    Give the scene as scene_path (.blend or .py file), scene_script (bpy Python code as text, no
    file needed), or scene_id from a previous call. Call this first for a .blend you did not write
    yourself, or after writing a bpy script to check what it produced. Use the camera names and
    frame range in render_preview / render_final. Returns scene_id to reuse in the next calls.
    """
    c = _client()
    try:
        sid = _resolve_scene(c, scene_path, scene_id, scene_script)
        j = c.submit(sid, kind="info")
        if j["status"] != "done":
            j = c.wait(j["job_id"], timeout=INFO_WAIT_S)
    except (ClientError, ValueError, FileNotFoundError) as exc:
        return _j({"ok": False, "error": str(exc)})
    if j["status"] != "done":
        b = _brief(j)
        b["hint"] = "still queued (a GPU worker may be busy); call scene_info again in a moment" \
            if j["status"] in ("queued", "running") else "fix the scene and try again"
        return _j(b)
    info = dict(j.get("info") or {})
    info["scene_id"] = j["scene_id"]
    if info.get("engine") and info["engine"] != "CYCLES":
        info["engine_note"] = "JANCTION renders with CYCLES; the scene's engine setting is not used"
    if j.get("warnings"):
        info["blender_warnings"] = j["warnings"]
    if info.get("missing_files"):
        info["note"] = "missing_files will render pink/black; pack them into the .blend (File > External Data > Pack) or fix the paths"
    return _j(info)


@mcp.tool(structured_output=False)
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
) -> list[Any]:
    """Render a fast, cheap preview of a Blender scene on a JANCTION GPU and show the image.

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
    """
    c = _client()
    try:
        frame_list = parse_frames(frames)
        sid = _resolve_scene(c, scene_path, scene_id, scene_script)
        j = c.submit(sid, kind="preview", frames=frame_list, camera=camera or None,
                     width=width, height=height, samples=samples)
        _log(f"preview job {j['job_id']} submitted frames={frame_list}")
        j = c.wait(j["job_id"], timeout=PREVIEW_WAIT_S)
    except ClientError as exc:
        block = _payment_block(exc) or _quota_block(exc)
        return [_j(block if block else {"ok": False, "error": str(exc)})]
    except (ValueError, FileNotFoundError) as exc:
        return [_j({"ok": False, "error": str(exc)})]
    brief = _brief(j)
    if j["status"] != "done":
        brief["hint"] = ("still running: call render_status(job_id) and then render_download"
                         if j["status"] in ("queued", "running")
                         else "fix the scene and try again")
        return [_j(brief)]
    out = Path(out_dir) if out_dir else _out_root() / j["job_id"]
    paths = c.download(j["job_id"], out)
    show = next((p for p in paths if p.name == "sheet.png"), None) or next((p for p in paths if p.suffix == ".png"), None)
    brief["files"] = [str(p) for p in paths]
    brief["next"] = ("look at the image; if the scene needs changes, edit it and call render_preview again; "
                     "if it looks right, ask the user before calling render_final")
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
    times. Tell the user the result before calling render_final."""
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


@mcp.tool()
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
) -> str:
    """Render the final frames (or a video) of a Blender scene on JANCTION GPUs.

    Call this after the user approved a preview. Pass scene_id from render_preview (or scene_path /
    scene_script to upload a new .blend / bpy script). frame_start..frame_end are inclusive; several frames are
    split across GPUs and joined into output.mp4 (output='mp4', fps), a single frame gives a PNG
    (output='png'; 'auto' picks). Returns job_id and a time estimate right away; the render runs
    in the background: poll with render_status, then fetch with render_download. Inputs and
    results are deleted 24 hours after last use, so download them.
    """
    c = _client()
    try:
        sid = _resolve_scene(c, scene_path, scene_id, scene_script)
        j = c.submit(sid, kind="final", frame_start=frame_start, frame_end=frame_end,
                     width=width, height=height, samples=samples, fps=fps, output=output,
                     camera=camera or None)
    except ClientError as exc:
        block = _payment_block(exc) or _quota_block(exc)
        return _j(block if block else {"ok": False, "error": str(exc)})
    except (ValueError, FileNotFoundError) as exc:
        return _j({"ok": False, "error": str(exc)})
    brief = _brief(j)
    est = j.get("estimate") or {}
    brief["next"] = (f"tell the user it will take {est.get('human', 'a few minutes')}; then render_status(job_id) "
                     "until status is done, then render_download(job_id)")
    return _j(brief)


@mcp.tool()
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


@mcp.tool()
def render_download(job_id: str, out_dir: str = "", wait_seconds: int = 0) -> str:
    """Download a JANCTION render job's files (PNG frames, sheet.png and/or output.mp4) to out_dir
    (default ~/janction-render/<job_id>). wait_seconds > 0 first waits up to that long for the job
    to finish. Returns the local file paths."""
    c = _client()
    try:
        j = c.wait(job_id, timeout=float(wait_seconds)) if wait_seconds > 0 else c.job(job_id)
        if j["status"] != "done" and not j["artifacts"]:
            b = _brief(j)
            b["hint"] = "nothing to download yet"
            return _j(b)
        out = Path(out_dir) if out_dir else _out_root() / job_id
        paths = c.download(job_id, out)
    except ClientError as exc:
        return _j({"ok": False, "error": str(exc)})
    b = _brief(j)
    b["files"] = [str(p) for p in paths]
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
    length, and this key's usage. Call this if renders seem stuck or before the first render."""
    c = _client()
    try:
        health = c.health()
        me = c.me()
    except (ClientError, Exception) as exc:  # noqa: BLE001
        return _j({"ok": False, "server": c.server, "error": str(exc)})
    return _j({"ok": True, "server": c.server, "workers": health["workers"], "queue": health["queue"],
               "key": me, "downloads_go_to": str(_out_root()),
               "remote_mcp": f"{c.server}/mcp (Streamable HTTP; for Claude.ai, ChatGPT, Cursor: add this URL as a connector)"})


def main() -> None:
    _log(f"stdio, server={Client().server}")
    mcp.run()


if __name__ == "__main__":
    main()
