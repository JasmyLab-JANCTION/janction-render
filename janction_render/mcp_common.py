"""リモート MCP（server/mcp_remote.py）と stdio MCP（mcp_server.py）が同じにしておくべきもの（10/12、docs/60 ARCH-02 / MCP-02:
22 の関数が二重に書かれ、既に 4 つが乖離していた）。ここは標準ライブラリだけに頼る（stdio の利用者は受付の依存を入れていない）。

- 用途のプリセットの名前と、道具の既定値をプリセットに譲る規則（preset_of / with_preset / FINAL_TOOL_DEFAULTS）
- 仕事の設定の組み立て（job_params）
- 引数の説明の共通部分（docs(flavor): ENV / POLYHAVEN / ORBIT / CAMERAS / OUTPUT / TRANSPARENT / ENGINE）。
  素材の引数名だけ違う（remote は asset_urls、stdio は assets）。
受付の server/jobs.py もプリセットの名前はここから取る。"""
from __future__ import annotations

import os
from typing import Any, Optional

PURPOSE_PRESETS = ("product", "turntable", "animation")
FINAL_TOOL_DEFAULTS = {"width": 1920, "height": 1080, "samples": 128, "output": "auto"}


def preset_of(preset: str) -> str:
    """道具の preset 引数を正す。知らない名前は ValueError（リモートは INVALID_INPUT、stdio も同じ文で返す）。"""
    p = (preset or "").strip().lower()
    if p and p not in PURPOSE_PRESETS:
        raise ValueError("preset must be '', 'product', 'turntable' or 'animation'")
    return p


def with_preset(body: dict[str, Any], preset: str, kind: str) -> dict[str, Any]:
    """用途のプリセット（10/12）: 道具の既定値のままの項目は本文から外し、受付のプリセットの既定（商品写真は 1440x1440 の PNG 4 枚、
    回転動画は 720p の MP4、アニメーションはシーンのコマ範囲）を効かせる。渡した値が既定と違えばそのまま勝つ。"""
    if not preset:
        return body
    out = dict(body)
    out["preset"] = preset
    if kind == "final":
        for k, dflt in FINAL_TOOL_DEFAULTS.items():
            if out.get(k) == dflt:
                out[k] = None
        if (out.get("frame_end") or 0) <= (out.get("frame_start") or 0):
            out["frame_end"] = None                      # 1 周ぶん・4 枚・シーンの範囲は受付が決める
            if preset == "animation":
                out["frame_start"] = None
    if preset in ("product", "turntable") and out.get("environment_visible") is True:
        out.pop("environment_visible", None)            # 既定の True は「指定なし」: プリセットの無地の背景を効かせる
    return out


def job_params(environment: str, environment_strength: float, environment_visible: bool, blender: str,
               orbit: bool = False, orbit_frames: int = 24, orbit_elevation: float = 18.0, orbit_target: str = "",
               orbit_distance: float = 1.0, engine: str = "") -> dict[str, Any]:
    """道具の引数のうち、渡されたものだけを受付の仕事の設定にする（既定のままの項目は送らない）。"""
    out: dict[str, Any] = {}
    if engine:
        out["engine"] = engine
    if environment:
        out.update({"environment": environment, "environment_strength": environment_strength,
                    "environment_visible": environment_visible})
    if blender:
        out["blender"] = blender
    if orbit:
        out.update({"orbit": True, "orbit_frames": orbit_frames, "orbit_elevation": orbit_elevation,
                    "orbit_target": orbit_target, "orbit_distance": orbit_distance})
    return out


# ------------------------------------------------------------------ 見積もりとシーンの読み取りの返事（両方の道具で同じ）

def estimate_body(kind: str, scene_id: str, frames: str, frame_start: int, frame_end: int, width: int, height: int, samples: int,
                  cameras: Any, preset: str) -> tuple[dict[str, Any], bool]:
    """render_estimate の引数から受付への本文を作る。戻り値は (本文, シーンの読み取りが先に要るか)。
    preset='animation' でコマの指定が無ければ、呼ぶ側が scene_info を済ませてから見積もる。"""
    from .client import parse_frames
    body: dict[str, Any] = {"kind": kind, "width": width, "height": height, "samples": samples}
    if scene_id:
        body["scene_id"] = scene_id
    if kind == "preview":
        body["frames"] = parse_frames(frames) if (frames or not preset) else None
    else:
        body.update({"frame_start": frame_start, "frame_end": frame_end})
    if cameras:
        body["cameras"] = list(cameras)
        if kind != "preview":
            body.pop("frame_end", None)
    needs_info = bool(preset == "animation" and scene_id
                      and (body.get("frames") is None if kind == "preview" else frame_end <= frame_start))
    body = {k: v for k, v in with_preset(body, preset, kind).items() if v is not None}
    return body, needs_info


def estimate_next(est: dict[str, Any]) -> str:
    """見積もりの返事の next（エージェントへの次の一手）。上限の言い方は docs/60 BRAND-02 に合わせる。"""
    q = est.get("quota") or {}
    cost = est.get("cost") or {}
    if q and q.get("fits_size") is False:
        most = q.get("max_frames_per_instruction") or q.get("max_frames_per_job")
        return (f"too big: at most {most} frames per render_final call (longer than {q.get('max_frames_per_job')} frames runs as "
                "parts under one job id) and 1920x1080 on free time, 3840x2160 for keys with prepaid credit; split the frame range "
                "into several calls or lower the size")
    if q and not q.get("fits_today", True) and q.get("mode") == "free_allowance":
        # 有料モード: 無料枠を超えた分は残高から（10/8）。額と残高を言ってから
        return (f"this goes past the free GPU time left: about {cost.get('estimated_yen')} JPY would be charged from credit "
                f"(balance {cost.get('balance_yen')} JPY). Tell the user the time and the price and ask before "
                "render_final; a smaller job (fewer frames, lower resolution or samples) may stay free")
    if q and not q.get("fits_today", True):
        return ("this does not fit today's remaining free GPU time; propose fewer frames, lower resolution or samples, "
                "or wait until resets_at")
    return "tell the user the estimate and ask before calling render_final"


def scene_info_reply(j: dict[str, Any], assets_param: str) -> dict[str, Any]:
    """scene_info の返事（info に scene_id・エンジンの注意・警告・欠けたファイルの案内・次の一手）。assets_param は素材の渡し方の文
    （remote: 'asset_urls'、stdio: 'assets=[...]'）。"""
    from .brief import scene_next, trim
    info = dict(j.get("info") or {})
    info["scene_id"] = j.get("scene_id")
    if info.get("engine") and info["engine"] != "CYCLES":
        info["engine_note"] = "JANCTION renders with CYCLES; the scene's engine setting is not used"
    if j.get("warnings"):
        info["blender_warnings"] = j["warnings"]
    if info.get("missing_files"):
        info["note"] = (f"missing_files will render pink/black; send them with {assets_param} (kept next to the scene), "
                        "pack them into the .blend (File > External Data > Pack) or fix the paths")
    if isinstance(info.get("object_names"), list):
        info["object_names"] = trim(info["object_names"], 30)
    info.update(scene_next(info))          # 次の一手: シーンの縦横比に合わせた試し描き（10/9）
    return info


def billing_reply(me: dict[str, Any], synced: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """billing 道具の返事（GET /v1/me の形から）。無料ベータ / ようこそ / 毎日の無料枠 / 旧形 の 4 通りを両方の道具で同じに。"""
    from .brief import plan_fields, welcome_billing
    synced = synced or {}
    q = me.get("quota") or {}
    prefix = me.get("prefix")
    if q and q.get("mode", "free_beta") == "free_beta":
        return {"mode": "free_beta", "note": "no charges during the free beta; daily GPU-time quota per key",
                "gpu_seconds_used_today": q["gpu_seconds_used_today"], "gpu_seconds_per_day": q["gpu_seconds_per_day"],
                "gpu_seconds_left_today": max(0, q["gpu_seconds_per_day"] - q["gpu_seconds_used_today"]),
                "resets_at": q["resets_at"], "max_frames_per_job": q["max_frames_per_job"], "max_pixels": q["max_pixels"],
                **({"key_prefix": prefix} if prefix else {})}
    if q and q.get("welcome"):
        # ようこそクレジット（10/8 夜 本人の判断、docs/46）: 残りの円と期限、期間の後の試し描き、最初のチャージの特典
        return welcome_billing(q["welcome"], me, synced)
    if q:
        # 有料（10/8〜）: 毎日の無料枠と、超えた分を払う残高の両方
        yen = me["billing"]["yen_per_gpu_second"]
        out = {"mode": "free_allowance",
               "note": (f"the first {q['gpu_seconds_per_day'] // 60} GPU-minutes of each day are free; beyond that "
                        f"{yen} JPY per GPU-second from prepaid credit (only the part over the free time is charged)"),
               "gpu_seconds_used_today": q["gpu_seconds_used_today"], "gpu_seconds_per_day": q["gpu_seconds_per_day"],
               "gpu_seconds_left_today": max(0, q["gpu_seconds_per_day"] - q["gpu_seconds_used_today"]),
               "resets_at": q["resets_at"], "max_frames_per_job": q["max_frames_per_job"], "max_pixels": q["max_pixels"],
               "balance_yen": me["balance_yen"], "held_yen": me.get("held_yen", 0), "held_jobs": me.get("held_jobs", 0),
               "yen_per_gpu_second": yen, "min_topup_yen": me["billing"]["min_topup_yen"],
               "pending_checkout_url": me["billing"]["pending_checkout_url"], "charged_yen_total": me["charged_yen_total"],
               "topup_options": (me["billing"].get("topup_options") or {}).get("options"),
               "just_credited": synced.get("credited", []), **plan_fields(me)}
        if me.get("usd_indicative") is not None:
            out["usd_indicative"] = me["usd_indicative"]
        if prefix:
            out["key_prefix"] = prefix
        return out
    out = {"balance_yen": me["balance_yen"], "free_previews_left": me["free_previews_left"],
           "yen_per_gpu_second": me["billing"]["yen_per_gpu_second"], "min_topup_yen": me["billing"]["min_topup_yen"],
           "billing_enabled": me["billing"]["enabled"], "just_credited": synced.get("credited", []),
           "pending_checkout_url": me["billing"]["pending_checkout_url"], "charged_yen_total": me["charged_yen_total"]}
    if prefix:
        out["key_prefix"] = prefix
    return out


# ------------------------------------------------------------------ 引数の説明（道具の description の末尾に足す）

_ENGINE_DOC = (" engine: '' or 'cycles' (path tracing, the default) | 'eevee' (Blender's real-time rasterizer: about half the "
               "per-frame cost on animations, but every job pays about 7 s of shader compilation, so it only pays off for a few dozen "
               "frames or more; previews are faster on Cycles; HDRI presets work; no caustics or accurate bounce light).")
_TRANSPARENT_DOC = (" transparent=True: transparent background (alpha) instead of the world/HDRI backdrop; the preview sheet "
                    "shows it over dark grey.")
_ORBIT_DOC = (" orbit=True: turntable; an orbit camera circles the scene once over orbit_frames frames (default 24, "
              "elevation orbit_elevation deg, default 18). Flat floors/walls are ignored when framing; orbit_target = an "
              "object name or 'x,y,z' centres on that, orbit_distance scales the distance (1.0). A preview without frames "
              "shows 0/90/180/270 deg; a final without frame_end renders the whole turn as an MP4. Best for imported models.")
_CAMERAS_DOC = (" cameras=['Front','Top','Iso']: render the same frame from several named camera objects in one job (up to 8). "
                "A preview tiles them in one labeled sheet; a final returns one PNG/EXR per camera (frame_0001.. in that order; "
                "camera_files maps camera name -> file). For product shots from fixed angles use this instead of one job per "
                "camera. Not combinable with orbit, environment='compare' or camera.")
_OUTPUT_DOC = {
    "remote": (" output: 'auto' (mp4 for a frame range, png for one frame) | 'png' | 'exr' (16-bit linear OpenEXR frames for "
               "compositing) | 'mp4' (H.264) | 'webm' (VP9) | 'prores' (Apple ProRes 422 HQ in a .mov, for editing) | 'gif' | 'webp' "
               "(animated, at most 960 px wide; good for chat and web). transparent=True renders on a transparent background "
               "(alpha; for product shots and overlays): png / exr frames, webm, gif and webp keep it, mp4 and prores cannot. "
               "notify_url (render_final): an https URL that receives one JSON POST when the job finishes "
               "(event job.done / job.failed, artifacts with download links), so nobody has to poll."),
    "stdio": (" output: 'auto' (mp4 for a frame range, png for one frame) | 'png' | 'exr' (16-bit linear OpenEXR frames) | "
              "'mp4' (H.264) | 'webm' (VP9) | 'prores' (ProRes 422 HQ .mov) | 'gif' | 'webp' (animated, at most 960 px wide; "
              "good for chat and web). transparent=True renders on a transparent background (alpha): png / exr frames, webm, gif "
              "and webp keep it, mp4 and prores cannot. notify_url: an https URL that receives one JSON POST when the job "
              "finishes (event job.done / job.failed, artifacts with download links)."),
}
_ENV_DOC = {
    "remote": (" environment: '' keeps the scene's own world; 'studio' | 'sunset' | 'overcast' | 'night' replaces it with a "
               "bundled HDRI (a good first render for scenes without lighting work); 'compare' (render_preview only) renders the "
               "first frame under all four presets in one 2x2 image with labels, so you can pick one; environment_strength scales it (1.0); "
               "environment_visible=False hides the HDRI from the camera (flat grey backdrop, HDRI lighting only). blender: '' "
               "(5.0) or '5.2'. asset_urls: https links to images or glTF .bin files sent with the scene; a .blend finds them "
               "through relative paths (same folder), a script through os.environ['JR_ASSETS_DIR']."),
    "stdio": ("environment: '' keeps the scene's own world; 'studio' | 'sunset' | 'overcast' | 'night' replaces it with a "
              "bundled HDRI (good first render for scenes without lighting work); 'compare' (render_preview only) renders the "
              "first frame under all four presets in one 2x2 image with labels, so you can pick one; environment_strength scales it (1.0); "
              "environment_visible=False hides the HDRI from the camera (flat grey backdrop, HDRI lighting only). "
              "blender: '' (5.0) or '5.2' to render with Blender 5.2 when available. assets: local files (images, glTF "
              ".bin, ...) sent along with the scene; a .blend finds them through relative paths, a script through "
              "os.environ['JR_ASSETS_DIR']."),
}
_POLYHAVEN_TAIL = ("Import a model with "
                   "bpy.ops.import_scene.gltf(filepath=os.path.join(os.environ['JR_ASSETS_DIR'], '<id>', '<id>_1k.gltf')). "
                   "Inside the scene script, `import jr_assets` gives helpers: jr_assets.import_model('<id>', location=(x,y,z), scale=1.0) imports a Poly Haven model (or any file under JR_ASSETS_DIR) and returns the objects; jr_assets.material('<id>', scale=1.0) builds a Principled material from a Poly Haven texture set (diff / nor_gl / rough / arm / disp); jr_assets.apply(obj, mat) assigns it; jr_assets.world_hdri('<id>', strength=1.0) uses a Poly Haven HDRI as the world.")
_POLYHAVEN_DOC = {
    "remote": (" asset_urls may also hold 'polyhaven:<id>' (a CC0 model, texture or HDRI from polyhaven.com, fetched by the "
               "service into JR_ASSETS_DIR/<id>/; find ids with asset_search). " + _POLYHAVEN_TAIL),
    "stdio": (" assets may also hold 'polyhaven:<id>' (a CC0 model, texture or HDRI from polyhaven.com, fetched by the "
              "service into JR_ASSETS_DIR/<id>/; find ids with asset_search) or an https URL. " + _POLYHAVEN_TAIL),
}


def docs(flavor: str) -> dict[str, str]:
    """{ENV_DOC, POLYHAVEN_DOC, ORBIT_DOC, CAMERAS_DOC, OUTPUT_DOC, TRANSPARENT_DOC, ENGINE_DOC}。ENV_DOC は POLYHAVEN_DOC を含む。"""
    f = "remote" if flavor == "remote" else "stdio"
    return {"ENV_DOC": _ENV_DOC[f] + _POLYHAVEN_DOC[f], "POLYHAVEN_DOC": _POLYHAVEN_DOC[f], "ORBIT_DOC": _ORBIT_DOC,
            "CAMERAS_DOC": _CAMERAS_DOC, "OUTPUT_DOC": _OUTPUT_DOC[f], "TRANSPARENT_DOC": _TRANSPARENT_DOC, "ENGINE_DOC": _ENGINE_DOC}


def auto_idempotency_key(tool: str, body: dict[str, Any], now: Optional[float] = None, window_s: int = 120) -> str:
    """render_final にキーが無いときの自動の Idempotency-Key（10/13）。MCP の呼び出しが時間切れになって AI が同じ
    render_final を呼び直すと、同じ仕事が 2 本描かれて 2 回引かれていた。同じ中身・同じ 2 分の枠なら同じキーになり、
    受付は最初の仕事を返す。中身が 1 つでも違えば別のキー（＝別の仕事）。"""
    import hashlib
    import json as _json
    import time as _time

    t = _time.time() if now is None else now
    blob = _json.dumps({"tool": tool, "body": body}, sort_keys=True, separators=(",", ":"), default=str)
    return f"auto:{int(t // window_s)}:" + hashlib.sha256(blob.encode()).hexdigest()[:32]


def digest(text: str) -> str:
    """長い引数（scene_script）をキーに入れるための短い要約。"""
    import hashlib

    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()[:24] if text else ""


def file_stamp(path: str) -> str:
    """手元のファイルの「同じもの」の目印（パス・大きさ・更新時刻）。中身を読まずに済ませる。"""
    if not path:
        return ""
    try:
        st = os.stat(os.path.expanduser(path))
        return f"{os.path.abspath(os.path.expanduser(path))}:{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return path
