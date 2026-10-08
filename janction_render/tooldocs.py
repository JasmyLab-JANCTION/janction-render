"""MCP の指示文・道具の説明・引数の説明の新版（10/8、本人の LLMO 分析への対応。docs/40）。

切り替え: 環境変数 JR_TOOLDOCS=new | old。既定はリモート（server/mcp_remote.py）が old、stdio（mcp_server.py）が new。
リモートは Anthropic のコネクタディレクトリと OpenAI の審査が終わるまで道具の説明を変えない決まり（10/3、docs/28）なので、
出すかどうかは本人が受付の env に JR_TOOLDOCS=new を足して決める。old のときは各モジュールに書いてある今の文面のまま。

新版で決めたこと:
- 指示文は 1,800 字以内。先頭に「使う場面・使わない場面・最初の 1 手」。Claude Code は指示文を約 2,000 字で切る
  （10/8 に実測: リモート版 4,557 字は 2,025 字目、stdio 版 3,863 字は 2,032 字目で切れていた）
- 道具の説明は短く: 何をするか（利用者の言い回しで、英日）・使わない場面・上限・次の手。選択肢の細部は引数の説明へ
  （リモートの道具は引数の説明が空だった）
- 「常にこれを使え」のような断定的な誘導は書かない（研究で攻撃の手口として扱われ、審査と信頼を損なう）
- 道具の並びは試し描きから（先に並んだ道具が選ばれやすい。BiasBusters, ICLR'26）
- 事実の誤りを直す: "split across GPUs" → "rendered in chunks"（ベータ中は GPU 1 枚）、wait_seconds の上限 80 → 実際の 50 秒
"""
from __future__ import annotations

import copy
import os
from typing import Any

SAMPLE_URL = "https://render.janction.jp/samples/cube_scene.py"
SITE = "https://render.janction.jp"

TOOL_ORDER = ("render_preview", "render_final", "render_download", "render_status", "scene_info", "render_estimate",
              "render_info", "asset_search", "render_share", "render_unshare", "render_cancel", "billing")

# 上限（billing の既定値と同じ。tests/test_tooldocs.py が突き合わせる。stdio は手元で動くので受付の設定を読めない）
FREE_GPU_MINUTES_PER_KEY_PER_DAY = 10
FREE_MAX_FRAMES = 240
FREE_MAX_SIZE = "1920x1080"
RETENTION_HOURS = 24
YEN_PER_GPU_SECOND = 0.1      # 無料枠を超えた分の単価（10/8 から有料。billing.yen_per_gpu_second の既定値）
# ようこそクレジット（docs/46、JR_FREE_MODEL=welcome）。billing の既定値と同じ（tests/test_tooldocs.py が突き合わせる）
WELCOME_YEN = 500
WELCOME_DAYS = 14
FREE_PREVIEW_MINUTES_PER_DAY = 2


def free_model() -> str:
    """無料の形。受付は JR_FREE_MODEL（billing.free_model と同じ。受付は必ず設定する）、stdio は手元で動くので受付の設定を
    読めず、既定を使う。10/8 夜に受付をようこそクレジットへ切り替えたので、0.4.25 から既定は welcome。"""
    m = (os.environ.get("JR_FREE_MODEL") or "welcome").strip().lower()
    return m if m in ("daily", "welcome") else "welcome"


def enabled(flavor: str) -> bool:
    """新版を使うか。flavor は 'remote' か 'stdio'。"""
    v = (os.environ.get("JR_TOOLDOCS") or "").strip().lower()
    if v in ("new", "2", "on", "yes"):
        return True
    if v in ("old", "1", "off", "no"):
        return False
    return flavor == "stdio"


def _assets_param(flavor: str) -> str:
    return "asset_urls" if flavor == "remote" else "assets"


# ------------------------------------------------------------------ 指示文

_WHEN = ("WHEN TO USE: the user asks to render, preview, animate or turntable a Blender scene (a .blend, a bpy script you "
         "write, or a glTF/GLB/FBX/USD/OBJ file), or wants product shots or a 360-degree product video, and the machine has "
         "no NVIDIA GPU or rendering locally is slow.")
_DONT = ("DO NOT USE: to edit a scene open in the user's Blender (a local Blender MCP does that); for one still image on a "
         "machine with its own NVIDIA GPU (rendering locally is faster); for non-Blender video or general GPU compute.")
_FIRST = f"FIRST CALL: render_preview(scene_url='{SAMPLE_URL}', environment='compare') checks the connection in a few seconds."
def _free_offer(short: bool = False) -> str:
    """無料の形の 1 句（道具の説明で使う。short=True は指示文の LIMITS 用で、指示文を 1800 字に収める）。"""
    if free_model() == "welcome" and short:
        return f"{WELCOME_YEN} JPY welcome credit per new key ({WELCOME_DAYS} days), then {YEN_PER_GPU_SECOND} JPY per GPU-second"
    if free_model() == "welcome":
        return (f"each new key starts with a {WELCOME_YEN} JPY welcome credit ({WELCOME_DAYS} days); after that, previews are "
                f"free up to {FREE_PREVIEW_MINUTES_PER_DAY} GPU-minutes a day and finals cost {YEN_PER_GPU_SECOND} JPY per "
                "GPU-second (prepaid)")
    return (f"{FREE_GPU_MINUTES_PER_KEY_PER_DAY} free GPU-minutes per key per day, then {YEN_PER_GPU_SECOND} JPY per "
            "GPU-second (prepaid)")


def _limits() -> str:
    return (f"LIMITS: {_free_offer(short=True)}; up to {FREE_MAX_FRAMES} frames and {FREE_MAX_SIZE} per job; files are deleted "
            f"{RETENTION_HOURS} hours after last use.")


def _free_left() -> str:
    """見積もり・仕上げの説明で「無料の残り」を指す言い方。"""
    if free_model() == "welcome":
        return (f"the free GPU time left (the welcome credit, or {FREE_PREVIEW_MINUTES_PER_DAY} preview GPU-minutes a day "
                "after it)")
    return "today's free quota"
_SCRIPTS = ("SCRIPTS: Blender 5.0 API; build the scene, camera and frame range only (the service sets resolution, samples "
            "and the GPU). `import jr_assets; jr_assets.frame_camera()` fits every object in the frame.")
_MORE = f"Examples with their bpy scripts: {SITE}/examples (pass any as scene_url). More: {SITE}/llms.txt"


def instructions(flavor: str) -> str:
    if flavor == "remote":
        head = "JANCTION Render: Blender rendering on cloud GPUs for AI agents (no local GPU or Blender needed, no sign-up)."
        flow = ("FLOW: render_preview (an image in seconds plus a critic verdict with fix code; apply the fixes and preview "
                "again) -> ask the user -> render_estimate when the job is long or the quota is uncertain -> render_final -> "
                "render_download(job_id, wait_seconds=45) until the links come back. Tell the user eta.human; if it says the "
                "GPU is lent out, tell the user the wait instead of polling.")
        return " ".join([head, _WHEN, _DONT, _FIRST, flow, _limits(), _SCRIPTS, _MORE])
    head = ("JANCTION Render: Blender rendering on cloud GPUs for AI agents, from the terminal (no local GPU or Blender "
            "needed; a key is created on first use).")
    local = "LOCAL FILES: pass scene_path (a .blend, a .py or a 3D file); results are saved under ~/janction-render/<job_id>."
    flow = ("FLOW: render_preview (the image is saved and shown, plus a critic verdict with fix code; apply the fixes and "
            "preview again) -> ask the user -> render_estimate when the job is long or the quota is uncertain -> render_final "
            "-> render_status (tell the user eta.human) -> render_download(job_id, only='mp4') when done. If eta says the GPU "
            "is lent out, tell the user the wait instead of polling.")
    return " ".join([head, _WHEN, _DONT, _FIRST, local, flow, _limits(), _SCRIPTS, _MORE])


# ------------------------------------------------------------------ 道具の説明

_NOT_HERE = ("When not to use: editing a scene open in the user's Blender belongs to a local Blender MCP, and a single still "
             "on a machine with its own NVIDIA GPU usually renders faster locally.")


def descriptions(flavor: str, wait_cap_s: int = 50) -> dict[str, str]:
    a = _assets_param(flavor)
    remote = flavor == "remote"
    preview = (
        "Show what a Blender scene looks like: a fast, low-cost preview render on a cloud GPU, back as an image in seconds. "
        "Typical requests: 'render this .blend', 'show me the scene', 'preview the turntable', 'I have no GPU', 'Blender is too "
        "slow on my laptop', 'Blenderでレンダリングして', 'GPUがない', 'ターンテーブル', '商品の360度動画'. Also use it after writing a "
        "bpy script, to see what it builds. Each preview returns a critic verdict (ok / check / fix) with fix code: apply the "
        "fixes and preview again before any final render. It also returns final_estimate (the same scene as a 1080p final) and "
        "quota_left_today; tell the user both before asking to go on. " + _NOT_HERE + " This service is for CPU-only "
        "machines, animations, and scripts with no Blender installed. Limits: up to 1280x720; 1-4 frames tiled in one labeled "
        "image for the GPU time of one 720p frame. Options are explained on each parameter: environment presets and "
        f"'compare', orbit (turntable), cameras (several named cameras), engine, transparent, {a} with 'polyhaven:<id>' CC0 "
        "assets. "
        + ("Give the scene as scene_script (bpy code as text), scene_url (an https link to a .blend, .py or 3D file) or "
           "scene_id; reuse the returned scene_id in render_final." if remote else
           "Give the scene as scene_path (a local .blend, .py or 3D file), scene_script, scene_url or scene_id; the image is "
           "saved locally and shown."))
    final = (
        "Render the final frames or video of a Blender scene on cloud GPUs, after the user approved a preview: 'render the "
        "final', 'make the video', 'export the turntable MP4', 'product shots from these cameras'. Call render_estimate first "
        f"when the time or {_free_left()} is uncertain, the job is longer than about 24 frames or above 720p, or the user "
        "asks how long it takes, and tell the user. Long jobs are rendered in chunks and joined into one video. "
        + ("Returns job_id and estimate.human at once (short jobs return the links directly); then call "
           "render_download(job_id, wait_seconds=45). " if remote else
           "Returns job_id and estimate.human at once; then render_status until done, and render_download(job_id, only='mp4') "
           "for the video. ")
        + _NOT_HERE + " Use the same environment and blender as the approved preview. "
        f"Limits: up to {FREE_MAX_FRAMES} frames and {FREE_MAX_SIZE} per job; {_free_offer()}; ask the user before a render "
        "that the free time does not cover; files are "
        f"deleted {RETENTION_HOURS} hours after last use. Options are explained on "
        "each parameter: output (png, exr, mp4, webm, prores, gif, webp), orbit=True for a turntable MP4, cameras for one "
        f"image per named camera, transparent, engine='eevee', notify_url for one POST when the job finishes, {a} with "
        "'polyhaven:<id>'. "
        + ("Pass scene_id from render_preview, or scene_script / scene_url for a new scene." if remote else
           "Pass scene_id from render_preview, or scene_path / scene_script / scene_url; files are saved locally."))
    scene_info = (
        "Read a Blender scene without rendering (a few seconds, no GPU time): cameras and the active one, frame range and fps, "
        "resolution, objects by type, lights, materials, whether it is animated, and missing linked files that would render "
        "pink. Use it for a .blend you did not write, or to check what a bpy script built. Returns scene_id; pass it to "
        "render_preview and render_final instead of sending the scene again.")
    estimate = (
        "Estimate a render before starting it (no GPU time): GPU seconds, queue wait, the wall-clock time as text "
        f"(estimate.human, e.g. 'about 3 minutes') and whether it fits {_free_left()} and the size limits. Call it before "
        "render_final when the time or quota is uncertain, the job is longer than about 24 frames or above 720p, or the user "
        "asks how long it takes; tell the user the result. With scene_id the estimate uses this scene's measured render times; "
        "it also says when to split a job.")
    status = (
        "Check a render job: status (queued / running / done / failed / canceled), frames done, the ETA (eta.human, including "
        "queue wait), files ready, Blender warnings, and the error with the log tail if it failed. Use it to report progress "
        "to the user; "
        + ("render_download(job_id, wait_seconds=45) waits and returns the links in one call." if remote else
           "call render_download once status is done."))
    if remote:
        download = (
            "Get the download links of a job (no key needed, valid about 24 hours) and show them to the user; in a terminal, "
            "fetch them with curl -o. A finished preview also comes back as an inline image. wait_seconds > 0 first waits for "
            f"the job (the service waits at most {wait_cap_s} s per call; call again while it is still running). only picks "
            "the files: 'output' (default: the MP4 or the preview sheet, plus the first frames), 'mp4', 'sheet', 'frames' or "
            "'all'.")
    else:
        download = (
            "Download a job's files to out_dir (default ~/janction-render/<job_id>) and return the local paths. only picks the "
            "files: 'all' (default), 'mp4' (just the video; use it when the user wants the video, to skip hundreds of frames), "
            "'frames', 'sheet' or 'output'. wait_seconds > 0 first waits that long for the job to finish.")
    assets = (
        "Find free CC0 3D models, PBR textures or HDRIs on Poly Haven by words ('wooden chair', 'forest hdri') to furnish a "
        f"scene without uploading files; no GPU time. Each result has a spec 'polyhaven:<id>' to pass in {a}, its size in "
        "metres and the entry file. In the scene script: import jr_assets, then jr_assets.import_model('<id>', location=(x, y, "
        "z), scale=1.0) returns the objects, jr_assets.material('<id>') builds a material and jr_assets.apply(obj, mat) assigns "
        "it, jr_assets.world_hdri('<id>', strength=1.0) lights the world. 'polyhaven:<id>@2k' fetches 2k textures (1k by "
        "default).")
    return {"render_preview": preview, "render_final": final, "scene_info": scene_info, "render_estimate": estimate,
            "render_status": status, "render_download": download, "asset_search": assets}


# ------------------------------------------------------------------ 引数の説明

def _script_notes(flavor: str) -> str:
    return (" Blender 5.0 API notes: materials are node-based, so set a colour on the Principled BSDF "
            "(mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (r, g, b, 1)); mat.diffuse_color only "
            "affects the viewport; do not set Material.use_nodes. Animate with obj.keyframe_insert() (action.fcurves no longer "
            "exists; set bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR' first for constant speed). "
            "Build the scene, camera and frame range only; leave resolution, samples and denoising to the service. Helpers: "
            "`import jr_assets`, then jr_assets.frame_camera(margin=1.1) points the camera at every object and fits them in the "
            "frame; jr_assets.import_model('<id>'), jr_assets.material('<id>') and jr_assets.world_hdri('<id>') use Poly Haven "
            f"assets passed in {_assets_param(flavor)}.")


def param_docs(flavor: str, wait_cap_s: int = 50) -> dict[str, str]:
    remote = flavor == "remote"
    return {
        "scene_path": "Local path to the scene: a .blend file, a bpy .py script, or a 3D file (.glb/.gltf/.fbx/.usd/.obj/.stl/.ply/.abc, imported into an empty scene). Uploaded once; reuse the returned scene_id afterwards.",
        "scene_id": "scene_id returned by an earlier call (reuses the uploaded scene without sending it again).",
        "scene_script": "The scene as bpy Python code (text). No file and no local Blender needed; the service runs it in Blender 5.0." + _script_notes(flavor),
        "scene_url": f"https link to a .blend, a .py script or a 3D file (.glb/.gltf/.fbx/.usd/.obj/.stl/.ply/.abc); the service fetches it (e.g. the sample {SAMPLE_URL}, or a 12-hour /upload link). A .gltf or .obj also brings its .bin / .mtl / textures from the same folder.",
        "asset_urls": "Extra files sent with the scene: https links (textures, glTF .bin) or 'polyhaven:<id>' CC0 assets from asset_search ('polyhaven:<id>@2k' for 2k textures). A .blend finds them through relative paths (same folder); a script through os.environ['JR_ASSETS_DIR'] or the jr_assets helpers.",
        "assets": "Extra files sent with the scene: local paths (textures, glTF .bin), https links, or 'polyhaven:<id>' CC0 assets from asset_search. A .blend finds them through relative paths (same folder); a script through os.environ['JR_ASSETS_DIR'] or the jr_assets helpers.",
        "blender": "Blender version: '' (5.0, default) or '5.2' when the worker has it.",
        "frames": "Preview frames: '' = frame 1; '12' = one frame; '1,8,16,24' or '1-24' = up to 4 frames tiled in one labeled image (to judge camera motion and animation; same GPU time as one 720p frame).",
        "camera": "Name of the camera object to render from (default: the scene's active camera, or an automatic camera if there is none). Ignored with orbit=True; not combinable with cameras.",
        "cameras": "Several camera object names (up to 8) rendered from the same frame in one job: the preview tiles them in one labeled sheet, the final returns one PNG/EXR per camera (camera_files maps names to files). For product shots from fixed angles. Not combinable with orbit, environment='compare' or camera.",
        "width": "Output width in pixels (previews are capped at 1280x720 keeping the aspect ratio; a final frame can have at most 1920x1080 pixels).",
        "height": "Output height in pixels (previews are capped at 1280x720 keeping the aspect ratio; a final frame can have at most 1920x1080 pixels).",
        "samples": "Cycles samples per pixel (preview: up to 32, default 16; final: default 128).",
        "out_dir": "Local folder to save the files in (default ~/janction-render/<job_id>).",
        "environment": "Lighting preset: '' (the scene's own world), 'studio', 'sunset', 'overcast' or 'night' (bundled HDRIs; a good first render for scenes without lighting work), or 'compare' (preview only: all four in one labeled 2x2 image, to pick one).",
        "environment_strength": "Multiplier for the HDRI preset's brightness (default 1.0).",
        "environment_visible": "False hides the HDRI from the camera (flat grey backdrop, HDRI lighting only).",
        "orbit": "True: turntable; an orbit camera circles the scene once (the scene's own camera is not used). Flat floors and walls are ignored when framing. A preview without frames shows 0/90/180/270 degrees; a final without frame_end renders the whole turn as an MP4. Best for imported models and product videos.",
        "orbit_frames": "Number of frames for one full turn (default 24).",
        "orbit_elevation": "Orbit camera elevation in degrees (default 18).",
        "orbit_target": "Object name or 'x,y,z' to centre the orbit on (default: the scene's main objects).",
        "orbit_distance": "Multiplier for the orbit camera distance (default 1.0).",
        "engine": "'' or 'cycles' (path tracing, default) | 'eevee' (real-time rasterizer: about half the per-frame cost on animations of a few dozen frames or more; each job pays about 7 s of shader compilation, so previews stay on Cycles).",
        "transparent": "True renders on a transparent background (alpha) for product shots and overlays; png / exr / webm / gif / webp keep it, mp4 and prores cannot. The preview sheet shows it over dark grey.",
        "frame_start": "First frame to render (inclusive).",
        "frame_end": "Last frame to render (inclusive); equal to frame_start for a single image. With orbit=True and no frame_end, one full turn is rendered.",
        "fps": "Frames per second of the video output (default 24).",
        "output": "'auto' (mp4 for a frame range, png for one frame) | 'png' | 'exr' (16-bit linear frames for compositing) | 'mp4' (H.264) | 'webm' (VP9) | 'prores' (Apple ProRes 422 HQ .mov, for editing) | 'gif' | 'webp' (animated, at most 960 px wide; good for chat and web).",
        "notify_url": "Optional https URL that receives one JSON POST when the final render finishes (job.done / job.failed, with download links), so nobody has to poll.",
        "kind": "'final' (frame_start..frame_end at width x height, samples) or 'preview' (frames like '1-24').",
        "job_id": "The job_id returned by render_preview or render_final (looks like j_...).",
        "wait_seconds": (f"Wait for the job to finish before returning the links (0 = do not wait). The service waits at most {wait_cap_s} s per call; call again while the job is still running."
                         if remote else "Wait up to this many seconds for the job to finish before downloading (0 = do not wait)."),
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


# 道具ごとに引数の名前と説明の鍵が違うもの
PARAM_ALIAS = {("asset_search", "kind"): "kind_assets"}


# ------------------------------------------------------------------ 当てはめ

def plan(server: Any, flavor: str, wait_cap_s: int = 50) -> dict[str, Any]:
    """新版を当てたあとの指示文と道具（並び順どおり、説明と引数の説明つき）。server 自体は変えない（テストと比較用）。"""
    tools = server._tool_manager._tools   # noqa: SLF001 — SDK に公開の差し替え口が無い
    descs = descriptions(flavor, wait_cap_s)
    params = param_docs(flavor, wait_cap_s)
    names = [n for n in TOOL_ORDER if n in tools] + [n for n in tools if n not in TOOL_ORDER]
    out = []
    for n in names:
        t = tools[n]
        schema = copy.deepcopy(t.parameters)
        for pname, prop in (schema.get("properties") or {}).items():
            key = PARAM_ALIAS.get((n, pname), pname)
            if key in params and isinstance(prop, dict):
                prop["description"] = params[key]
        out.append({"name": n, "description": descs.get(n, t.description), "parameters": schema})
    return {"instructions": instructions(flavor), "tools": out}


def apply(server: Any, flavor: str, wait_cap_s: int = 50) -> bool:
    """JR_TOOLDOCS が new なら、登録済みの道具の説明・引数の説明・並びと指示文を新版に差し替える。差し替えたら True。
    SDK の形が変わって当てられないときは何もしない（今の文面のまま動く）。"""
    if not enabled(flavor):
        return False
    try:
        p = plan(server, flavor, wait_cap_s)
        tools = server._tool_manager._tools   # noqa: SLF001
        ordered = {}
        for item in p["tools"]:
            t = tools[item["name"]]
            t.description = item["description"]
            t.parameters = item["parameters"]
            ordered[item["name"]] = t
        tools.clear()
        tools.update(ordered)
        server._lowlevel_server.instructions = p["instructions"]   # noqa: SLF001
    except Exception:  # noqa: BLE001
        return False
    return True
