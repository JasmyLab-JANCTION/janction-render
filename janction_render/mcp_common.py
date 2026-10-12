"""リモート MCP（server/mcp_remote.py）と stdio MCP（mcp_server.py）が同じにしておくべきもの（10/12、docs/60 ARCH-02 / MCP-02:
22 の関数が二重に書かれ、既に 4 つが乖離していた）。ここは標準ライブラリだけに頼る（stdio の利用者は受付の依存を入れていない）。

- 用途のプリセットの名前と、道具の既定値をプリセットに譲る規則（preset_of / with_preset / FINAL_TOOL_DEFAULTS）
- 仕事の設定の組み立て（job_params）
- 引数の説明の共通部分（docs(flavor): ENV / POLYHAVEN / ORBIT / CAMERAS / OUTPUT / TRANSPARENT / ENGINE）。
  素材の引数名だけ違う（remote は asset_urls、stdio は assets）。
受付の server/jobs.py もプリセットの名前はここから取る。"""
from __future__ import annotations

from typing import Any

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
