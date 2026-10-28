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

TOOL_ORDER = ("render_preview", "render_final", "render_review", "render_download", "render_status", "render_resume_options",
              "scene_info", "render_estimate",
              "render_info", "asset_search", "render_share", "render_unshare", "render_cancel", "billing")

# 上限（billing の既定値と同じ。tests/test_tooldocs.py が突き合わせる。stdio は手元で動くので受付の設定を読めない）
# 10/28: 数字の出所は pricing.yaml（→ terms_defaults.py、tools/terms_sync.py が作る）。手書きの数字を持たない
from . import terms_defaults as _TD

FREE_GPU_MINUTES_PER_KEY_PER_DAY = 10          # 旧 daily の形（JR_FREE_MODEL=daily）だけで使う。本番は welcome
FREE_MAX_FRAMES = _TD.FRAMES_PER_PART
RETENTION_HOURS = _TD.RETENTION_HOURS
PAID_RETENTION_DAYS = _TD.PAID_RETENTION_DAYS   # 合計 PAID_MIN_YEN 以上払った鍵（core.paid_ttl_seconds の既定 168 時間）
YEN_PER_GPU_SECOND = _TD.YEN_PER_GPU_SECOND     # 無料枠を超えた分の単価（10/8 から有料。billing.yen_per_gpu_second の既定値）
# ようこそクレジット（docs/46、JR_FREE_MODEL=welcome）。billing の既定値と同じ（tests/test_tooldocs.py が突き合わせる）
WELCOME_YEN = _TD.WELCOME_TOTAL_YEN             # network の形: 新しい鍵に 500 円分（カードの形の合計と同じ額）
WELCOME_DAYS = _TD.WELCOME_DAYS
FREE_PREVIEW_MINUTES_PER_DAY = _TD.PREVIEW_FREE_MINUTES_PER_DAY
# カードの形（JR_WELCOME_MODEL=card、docs/56 の 9。本番は 2026-10-12 から）: カードなしで 100 円分、請求なしのカード登録で 400 円分
WELCOME_CARDLESS_YEN = _TD.WELCOME_CARDLESS_YEN
WELCOME_CARD_YEN = _TD.WELCOME_CARD_BONUS_YEN


def free_model() -> str:
    """無料の形。受付は JR_FREE_MODEL（billing.free_model と同じ。受付は必ず設定する）、stdio は手元で動くので受付の設定を
    読めず、既定を使う。10/8 夜に受付をようこそクレジットへ切り替えたので、0.4.25 から既定は welcome。"""
    m = (os.environ.get("JR_FREE_MODEL") or "welcome").strip().lower()
    return m if m in ("daily", "welcome") else "welcome"


def welcome_model() -> str:
    """ようこそクレジットの形（billing.welcome_model と同じ名前）。受付は JR_WELCOME_MODEL を読む。stdio は受付の設定を読めないので、
    本番が 2026-10-12 に切り替えたカードの形を既定にする（料金ページ・FAQ・道具の説明が同じ数字を言うため。10/12 の実検証で
    料金ページは 100 円、道具の説明は 500 円と食い違っていた）。"""
    m = (os.environ.get("JR_WELCOME_MODEL") or "card").strip().lower()
    return m if m in ("network", "card") else "card"


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

_WHEN = ("WHEN TO USE: the user wants to render, preview, animate or turntable a Blender scene (a .blend, a bpy script you "
         "write, or a glTF/GLB/FBX/USD/OBJ file), or product shots / a 360-degree product video, and has no NVIDIA GPU or "
         "local rendering is slow.")
_DONT = ("DO NOT USE: to edit a scene open in the user's Blender (a local Blender MCP does that); for one still on a machine "
         "with its own NVIDIA GPU (local is faster); for non-Blender video or other GPU work.")
_FIRST = f"FIRST CALL: render_preview(scene_url='{SAMPLE_URL}', environment='compare') checks the connection."
def _free_offer(short: bool = False) -> str:
    """無料の形の 1 句（道具の説明で使う。short=True は指示文の LIMITS 用で、指示文を 1800 字に収める）。
    数字は料金ページ・FAQ・facts と同じ出所（billing の既定値）で、形（card / network）も同じ env を読む。"""
    if free_model() == "welcome" and welcome_model() == "card":
        if short:
            return (f"free: {WELCOME_CARDLESS_YEN} JPY of GPU time per new key (no card) + {WELCOME_CARD_YEN} JPY after saving a "
                    f"card (not charged), then {YEN_PER_GPU_SECOND} JPY per GPU-second")
        return (f"each new key gets {WELCOME_CARDLESS_YEN} JPY of GPU time free with no card ({WELCOME_DAYS} days) and "
                f"{WELCOME_CARD_YEN} JPY more once the user saves a card on a page that charges nothing (once per card); after that, "
                f"previews are free up to {FREE_PREVIEW_MINUTES_PER_DAY} GPU-minutes a day and finals cost {YEN_PER_GPU_SECOND} JPY "
                "per GPU-second (prepaid)")
    if free_model() == "welcome" and short:
        return f"free up to {WELCOME_YEN} JPY per new key ({WELCOME_DAYS} days), then {YEN_PER_GPU_SECOND} JPY per GPU-second"
    if free_model() == "welcome":
        return (f"each new key gets {WELCOME_YEN} JPY of GPU time free (welcome credit, {WELCOME_DAYS} days); after that, previews are "
                f"free up to {FREE_PREVIEW_MINUTES_PER_DAY} GPU-minutes a day and finals cost {YEN_PER_GPU_SECOND} JPY per "
                "GPU-second (prepaid)")
    return (f"{FREE_GPU_MINUTES_PER_KEY_PER_DAY} free GPU-minutes per key per day, then {YEN_PER_GPU_SECOND} JPY per "
            "GPU-second (prepaid)")


def _env_int_doc(name: str, default: int) -> int:
    try:
        v = int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default
    return v if v > 0 else default


# 受付と同じ env から読む（10/14、要件 IF-01: 手書きの定数だと env を変えた本番と食い違う）。stdio は既定値になる
FREE_MAX_FRAMES = _env_int_doc("JR_FREE_MAX_FRAMES", _TD.FRAMES_PER_PART)
MAX_FRAMES_PER_INSTRUCTION = max(FREE_MAX_FRAMES, _env_int_doc("JR_MAX_FRAMES_PER_INSTRUCTION", _TD.MAX_FRAMES_PER_INSTRUCTION))
RETENTION_HOURS = _env_int_doc("JR_TTL_HOURS", _TD.RETENTION_HOURS)
PAID_RETENTION_DAYS = round(_env_int_doc("JR_PAID_TTL_HOURS", _TD.PAID_RETENTION_DAYS * 24) / 24)


def _wh(pixels: int) -> str:
    """画素数を 16:9 の幅x高さで（server/capabilities._wh と同じ式。tests/test_capabilities.py が突き合わせる）。"""
    w = int(round((pixels * 16 / 9) ** 0.5))
    return f"{w}x{int(round(w * 9 / 16))}"


# 解像度の上限も受付と同じ env から（10/14、要件 AIO-01: 手書きの 1920x1080 / 3840x2160 だと JR_*_MAX_PIXELS を変えた本番と食い違う）
_FREE_PX = _env_int_doc("JR_FREE_MAX_PIXELS", 1920 * 1080)
FREE_MAX_SIZE = _wh(_FREE_PX)
PAID_MAX_SIZE = _wh(max(_FREE_PX, _env_int_doc("JR_PAID_MAX_PIXELS", 3840 * 2160)))   # 先払いのクレジットでの上限
PREVIEW_MAX_SIZE = "1280x720"          # 試し描きの上限（server/capabilities.PREVIEW_MAX と同じ）
PREVIEW_FRAMES_MAX = 4
UPLOAD_LINK_HOURS = _env_int_doc("JR_DROP_TTL_HOURS", 12)


def _limits() -> str:
    return (f"LIMITS: {_free_offer(short=True)}; up to {MAX_FRAMES_PER_INSTRUCTION:,} frames per call (parts of {FREE_MAX_FRAMES}), "
            f"{FREE_MAX_SIZE} free / {PAID_MAX_SIZE} prepaid; kept {RETENTION_HOURS} h ({PAID_RETENTION_DAYS} d if topped up).")


def _presets(flavor: str) -> str:
    """用途のプリセット（10/12、ChatGPT の実検証「用途別に背景・カメラ・光を自動で」）。モデルを持たない人の商品写真の手順
    （asset_search → render_preview(preset='product')）は asset_search の説明に書く（指示文は 1,800 字まで）。"""
    return ("PRESETS: preset='product' (4 studio shots, plain backdrop) | 'turntable' (360-degree MP4) | 'animation' (scene's "
            "frames); no model? asset_search.")


def product_recipe(flavor: str) -> str:
    """モデルを持たない人の商品写真: 素材検索から試し描きまでの 1 手（asset_search の説明と案内に使う）。"""
    a = _assets_param(flavor)
    return ("For product shots of something the user has no model for: asset_search('<item>'), then "
            f"render_preview(scene_script='import jr_assets; jr_assets.import_model(\"<id>\")', {a}=['polyhaven:<id>'], "
            "preset='product') gives 4 studio shots on a plain backdrop (import_model removes Blender's untouched startup cube first).")


def _free_left() -> str:
    """見積もり・仕上げの説明で「無料の残り」を指す言い方。"""
    if free_model() == "welcome":
        return (f"the free GPU time left (the welcome credit, or {FREE_PREVIEW_MINUTES_PER_DAY} preview GPU-minutes a day "
                "after it)")
    return "today's free quota"
_SCRIPTS = ("SCRIPTS: Blender 5.0 bpy; build only the scene, camera and frame range (the service sets resolution and samples); "
            "`import jr_assets; jr_assets.frame_camera()` fits every object; a script that raises renders nothing.")
_MORE = f"Examples and docs: {SITE}/examples, {SITE}/llms.txt"


def instructions(flavor: str) -> str:
    if flavor == "remote":
        head = "JANCTION Render: Blender rendering on cloud GPUs for AI agents (no local GPU or Blender needed, no sign-up)."
        flow = ("FLOW: render_preview (image in seconds + critic verdict with fix code; fix and preview again) -> ask the user "
                "-> render_estimate when the job is long or the quota is uncertain -> render_final -> render_download(job_id, "
                "wait_seconds=45) until the links come back; tell the user eta.human, and if the GPU is lent out tell them the "
                "wait, do not poll.")
        return " ".join([head, _WHEN, _DONT, _FIRST, flow, _presets(flavor), _limits(), _SCRIPTS, _more()])
    head = ("JANCTION Render: Blender rendering on cloud GPUs for AI agents, from the terminal (no local GPU or Blender; key "
            "made on first use).")
    local = "LOCAL FILES: scene_path (.blend, .py or 3D file); results in ~/janction-render/<job_id>."
    flow = ("FLOW: render_preview (image saved and shown + critic verdict with fix code; fix, repeat) -> ask the user "
            "-> render_estimate when long or the quota is uncertain -> render_final -> render_status (tell eta.human) "
            "-> render_download(job_id, only='mp4'); GPU lent out? say the wait, do not poll.")
    return " ".join([head, _WHEN, _DONT, _FIRST, local, flow, _presets(flavor), _limits(), _SCRIPTS, _more()])


def resume_on() -> bool:
    """render_resume_options を出すか（10/20、docs/82）。審査中のリモートの道具の一覧を変えないため、既定は出さない。"""
    return (os.environ.get("JR_RESUME_TOOL") or "").strip().lower() in ("1", "on", "yes", "true")


def _more() -> str:
    # 旗が on のときだけ、最後の 1 文に再開の道具を入れる（指示文を 1,800 字に収めるため、文の長さは今の _MORE と同じくらい）
    return "RESUME earlier work: render_resume_options. Docs: https://render.janction.jp/llms.txt" if resume_on() else _MORE


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
        "quota_left_today; tell the user both before asking to go on. Prices come before rendering: final_offers give each "
        "next render's time and price, and a paid one needs the user's approval. A script that raises comes back as a failure with the "
        "line (nothing is rendered). " + _NOT_HERE + " This service is for CPU-only "
        f"machines, animations, and scripts with no Blender installed. Limits: up to {PREVIEW_MAX_SIZE}; 1-{PREVIEW_FRAMES_MAX} frames tiled in one labeled "
        "image for the GPU time of one 720p frame. preset='product' | 'turntable' | 'animation' sets camera, light, backdrop and "
        "frames for that purpose. Other options are explained on each parameter: environment presets and 'compare', orbit "
        f"(turntable), cameras (several named cameras), engine, transparent, {a} with 'polyhaven:<id>' CC0 assets. "
        + ("Give the scene as scene_script (bpy code as text), scene_url (an https link to a .blend, .py or 3D file) or "
           "scene_id; reuse the returned scene_id in render_final." if remote else
           "Give the scene as scene_path (a local .blend, .py or 3D file), scene_script, scene_url or scene_id; the image is "
           "saved locally and shown."))
    final = (
        "Render the final frames or video of a Blender scene on cloud GPUs, after the user approved a preview: 'render the "
        "final', 'make the video', 'export the turntable MP4'. Call render_estimate first "
        f"when the time or {_free_left()} is uncertain, the job is longer than about 24 frames or above 720p, or the user "
        "asks how long it takes, and tell the user. For animations, keep the approved engine/look, test 10 contiguous final-path "
        "frames, then estimate again. Long jobs are rendered in chunks and joined into one video. "
        + ("Returns job_id and estimate.human at once (short jobs return the links directly); then call "
           "render_download(job_id, wait_seconds=45). " if remote else
           "Returns job_id and estimate.human at once; then render_status until done, and render_download(job_id, only='mp4') "
           "for the video. ")
        + "Use the same environment and blender as the approved preview. Render only what the user approved at the shown "
          "price (max_yen caps it). "
        # 10/13: ここが「240 コマ・1080p まで」のままで、AI が長いアニメや 4K を断っていた（受付は 3,000 コマ・先払いは 4K）
        f"Limits: up to {MAX_FRAMES_PER_INSTRUCTION:,} frames per call (over {FREE_MAX_FRAMES} runs as parts under one job id); "
        f"{FREE_MAX_SIZE} on free time, {PAID_MAX_SIZE} with prepaid credit; {_free_offer()}; ask before a render the "
        f"free time does not cover; files are deleted {RETENTION_HOURS} h after last use ({PAID_RETENTION_DAYS} days once topped "
        "up). preset='product' | 'turntable' | 'animation' fills the settings for that purpose. Options per parameter: "
        f"output (png, exr, mp4, webm, prores, gif, webp), orbit, cameras, transparent, engine, notify_url, {a} ('polyhaven:<id>'). "
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
        "asks how long it takes; tell the user the result. With scene_id the estimate uses measured render times and returns "
        "calibration.final_path_measured. If false, treat it as preliminary: run a short contiguous final-path test and "
        "estimate again before the full animation. It also says when to split a job.")
    status = (
        "Check a render job: status (queued / running / done / failed / canceled), frames done, the ETA (eta.human, including "
        "queue wait), files ready, Blender warnings, and the error with the log tail if it failed. Use it to report progress "
        "to the user; "
        + ("render_download(job_id, wait_seconds=45) waits and returns the links in one call." if remote else
           "call render_download once status is done.")
        # 10/14 IF-05: 新しい会話・つなぎ直しで前の仕事に戻る道
        + " Without job_id it lists this key's recent jobs and the scene_ids still kept, to pick up earlier work in a new "
          "conversation.")
    if remote:
        download = (
            "Get the download links of a job (no key needed, valid about 24 hours; call again for fresh links while the files are "
            f"kept, {RETENTION_HOURS} h after last use or {PAID_RETENTION_DAYS} days, normally, for paid keys) and show them to the user; in a terminal, "
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
        f"scene without uploading files; no GPU time. {product_recipe(flavor)} Each result has a spec 'polyhaven:<id>' to pass in {a}, its size in "
        "metres and the entry file. In the scene script: import jr_assets, then jr_assets.import_model('<id>', location=(x, y, "
        "z), scale=1.0) returns the objects, jr_assets.material('<id>') builds a material and jr_assets.apply(obj, mat) assigns "
        "it, jr_assets.world_hdri('<id>', strength=1.0) lights the world. 'polyhaven:<id>@2k' fetches 2k textures (1k by "
        "default).")
    # 10/28: 金額・特典・カードの語を道具の説明から外す（OpenAI の審査が billing の定義を「さらに審査が要る」で止めていた。
    # 10/15 の却下と同じ規則＝説明文に料金を書かない）。数字は道具の返事（summary・tell_user）にそのまま残る
    billing = (
        "Check what this key can still render for free and its credit (no GPU time): the free GPU time left and when it "
        "expires or resets, the balance, the price per GPU-second, any pending checkout link, and the offers that apply. "
        "Relay tell_user to the user in their language when it is present.")
    # 取り消し・共有・取り下げ・接続の確認（10/13: Glama の自動評価で render_cancel C・render_unshare B。副作用・権限・戻せるか・
    # 何が残るかが書かれていなかった。実装は routes_jobs.cancel_for・routes_shares.unshare_for・shares.remove）
    cancel = (
        "Stop a queued or running render job of this key (a j_... job, or a b_... job split into parts, which stops every part). "
        "Effects: queued frames are dropped; frames already rendered are charged and stay downloadable until the job expires; "
        "the rest of the GPU time held for the job is returned to the key at once. It cannot be undone or resumed: to render "
        "again, call render_final again (a new job). A job that is already done, failed or canceled is returned unchanged, and "
        "a job whose frames are all rendered and is being assembled into the video cannot be stopped (nothing more is charged). "
        "Only the key that started the job can stop it; any other job_id returns not_found. Ask the user before cancelling a "
        "render they asked for.")
    share = (
        "Publish a finished render as a public web page anyone with the link can open (for X, Discord or a client): the image "
        "or video, the render settings, an optional title and note, the user's request in their words (prompt), and the bpy "
        "script only if include_script=True. The page keeps its own copy of the result after the job's files expire, until "
        "render_unshare. listed=True only asks to appear in the public gallery; the operator reviews it first. Public: ask the "
        "user before sharing and return the url to them. Only the key that rendered the job can share it.")
    unshare = (
        "Take down the public share page of a job made with render_share. Effects: the page URL stops working, its copy of the "
        "image or video, the shared script and the shown request are deleted, and the page leaves the public gallery. This "
        "cannot be undone: sharing again makes a new page with a new URL. The job's own files are not touched (they expire on "
        "their usual schedule). Only the key that shared the job can take the page down; a job without a share page returns "
        "not_found.")
    info = (
        "Check the connection and the service before rendering (read-only, no GPU time, no charge): the server URL, whether GPU "
        "workers are online, the queue length and expected wait, and this key's usage. Use it before the first render or when "
        "renders seem stuck, and to decide whether to route a render here: workers_available > 0 means a preview comes back in seconds; gated means the GPU is lent out and "
        "gate says how long the wait usually is. "
        + ("It runs as the connected account (OAuth or the API key in the connector). " if remote else
           "It uses the API key in JANCTION_RENDER_API_KEY or ~/.janction-render.json (a free key is made on first use). ")
        + "Every call is rate-limited per key; a 429 response carries retry_after_s, wait that long. "
        # 10/14 IF-10: 端末の無い人の診断
        "diagnose.tell_user says in plain words whether the connection, the key, the free credit and the GPUs are fine and "
        "what the last failed render said; relay it when the user asks why something does not work.")
    return {"render_preview": preview, "render_final": final, "scene_info": scene_info, "render_estimate": estimate,
            "render_status": status, "render_download": download, "asset_search": assets, "billing": billing,
            "render_review": review_description(flavor), "render_cancel": cancel, "render_share": share,
            "render_unshare": unshare, "render_info": info, "render_resume_options": resume_description(flavor)}


def resume_description(flavor: str) -> str:
    """render_resume_options の説明（10/20、docs/82）。「必ず使え」は書かない。使う場面・使わない場面・副作用なしを先に。"""
    who = ("It runs as the connected account. If the user rendered from another AI before and nothing comes back, they may be on "
           "another account: reconnecting with 'sign in with email' or their existing key (jr_...) reaches the same one."
           if flavor == "remote" else
           "It uses the API key in JANCTION_RENDER_API_KEY or ~/.janction-render.json.")
    return (
        "List this account's earlier JANCTION Render projects so the user can continue them: past Blender renders, their saved "
        "settings (resolution, samples, frames, engine, Blender version), whether the scene file and the result are still stored, "
        "and ready-to-use arguments for the next call. Use it when the user wants to resume or redo an earlier render, reuse "
        "earlier settings ('same settings as last time', 'continue my previous render', '前回と同じ設定で', '前に作った動画をまた'), "
        "or asks what they rendered before. Do not use it for unrelated conversations, general Blender questions, or a new render "
        "that does not mention earlier work (use render_preview). Read-only: it does not start a render and charges nothing. "
        "Returns up to 3 projects (pass next_cursor as cursor for more); with no history it says so. Then tell the user the "
        "options, ask which one, and call the tool in that option's 'first' (render_preview); ask before render_final. "
        + who)


def review_description(flavor: str) -> str:
    """render_review の説明（10/9）。リモートは審査中は出さない（JR_REVIEW_TOOL=1 のときだけ登録）ので、stdio と同じ新しい文面を使う。"""
    given = ("scene_script, scene_url or scene_id" if flavor == "remote" else "scene_path, scene_script, scene_url or scene_id")
    return (
        "Check a 3D model or a generated Blender scene by looking at it from 4 sides: a turntable preview (0, 90, 180 and 270 "
        "degrees) under neutral studio light on a cloud GPU, back with pass / warning / fail, a score, the checks it ran "
        "(texture files found, objects visible and not hidden behind a floor or wall, camera not inside an object, framing, "
        "exposure, light) with fix code for each problem, and the 4 views tiled in one image. Typical requests: 'check this "
        "model', 'does the scene look right', 'QA this GLB', 'モデルを確認して', '見た目をチェックして'. Use it after writing a "
        "bpy script, generating or converting a model (.glb/.gltf/.fbx/.usd/.obj/.stl/.ply/.abc) or changing materials, before "
        "showing the result to the user or rendering a final; apply the fixes and call it again. The checks cannot judge "
        "whether the shape matches the request: look at the views for that. It costs the same as one preview. To check a shot "
        f"through the scene's own camera and lights, use render_preview (its critic runs the same checks). Give the scene as {given}.")


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
        "resume_limit": "How many projects to return (1-20, default 3).",
        "resume_cursor": "next_cursor from the previous call, to see more projects. Leave empty for the newest.",
        "scene_script": "The scene as bpy Python code (text). No file and no local Blender needed; the service runs it in Blender 5.0 (5.2 with blender='5.2')." + _script_notes(flavor),
        "scene_url": f"https link to a .blend, a .py script or a 3D file (.glb/.gltf/.fbx/.usd/.obj/.stl/.ply/.abc); the service fetches it (e.g. the sample {SAMPLE_URL}, or a {UPLOAD_LINK_HOURS}-hour /upload link). A .gltf or .obj also brings its .bin / .mtl / textures from the same folder.",
        "asset_urls": "Extra files sent with the scene: https links (textures, glTF .bin) or 'polyhaven:<id>' CC0 assets from asset_search ('polyhaven:<id>@2k' for 2k textures). A .blend finds them through relative paths (same folder); a script through os.environ['JR_ASSETS_DIR'] or the jr_assets helpers.",
        "assets": "Extra files sent with the scene: local paths (textures, glTF .bin), https links, or 'polyhaven:<id>' CC0 assets from asset_search. A .blend finds them through relative paths (same folder); a script through os.environ['JR_ASSETS_DIR'] or the jr_assets helpers.",
        "blender": "Blender version: '' (default: a .blend opens with the version it was saved in, other scenes with 5.0) or '5.0' / '5.2' (also '4.5', '4.2', '3.6'; a script that stops on Blender 5 because of an older API is rendered again on those automatically) to choose.",
        "frames": f"Preview frames: '' = frame 1; '12' = one frame; '1,8,16,24' or '1-24' = up to {PREVIEW_FRAMES_MAX} frames tiled in one labeled image (to judge camera motion and animation; same GPU time as one 720p frame).",
        "camera": "Name of the camera object to render from (default: the scene's active camera, or an automatic camera if there is none). Ignored with orbit=True; not combinable with cameras.",
        "cameras": "Several camera object names (up to 8) rendered from the same frame in one job: the preview tiles them in one labeled sheet, the final returns one PNG/EXR per camera (camera_files maps names to files). For product shots from fixed angles. Not combinable with orbit, environment='compare' or camera.",
        "width": f"Output width in pixels (previews are capped at {PREVIEW_MAX_SIZE} keeping the aspect ratio; a final frame can have at most {FREE_MAX_SIZE} pixels on free time, {PAID_MAX_SIZE} on prepaid credit).",
        "height": f"Output height in pixels (previews are capped at {PREVIEW_MAX_SIZE} keeping the aspect ratio; a final frame can have at most {FREE_MAX_SIZE} pixels on free time, {PAID_MAX_SIZE} on prepaid credit).",
        "samples": "Cycles samples per pixel (preview: up to 32, default 16; final: default 128).",
        "out_dir": "Local folder to save the files in (default ~/janction-render/<job_id>).",
        "environment": "Lighting preset: '' (the scene's own world), 'studio', 'sunset', 'overcast' or 'night' (bundled HDRIs; a good first render for scenes without lighting work), or 'compare' (preview only: all four in one labeled 2x2 image, to pick one).",
        "environment_review": "Light for the review: 'studio' (default; the same neutral light every time), 'sunset', 'overcast', 'night', or '' for the scene's own lights.",
        "environment_strength": "Multiplier for the HDRI preset's brightness (default 1.0).",
        "environment_visible": "False hides the HDRI from the camera (flat grey backdrop, HDRI lighting only).",
        "orbit": "True: turntable; an orbit camera circles the scene once (the scene's own camera is not used). Flat floors and walls are ignored when framing. A preview without frames shows 0/90/180/270 degrees; a final without frame_end renders the whole turn as an MP4. Best for imported models and product videos.",
        "orbit_frames": "Number of frames for one full turn (default 24).",
        "preset": "Purpose preset: 'product' (4 studio shots at 0/90/180/270 deg on a plain backdrop; the final gives 4 PNGs at 1440x1440), 'turntable' (one full turn as an MP4, studio light, plain backdrop), 'animation' (the scene's own camera, lights and frame range; the scene is read first when the range is unknown), or '' (none). It fills what you do not pass; environment, orbit_frames, width/height and the frames still win when given.",
        "orbit_elevation": "Orbit camera elevation in degrees (default 18).",
        "max_yen": "Ceiling for this job in JPY (-1 = none): the job is refused before anything is reserved when its reservation would exceed it. 0 means 'only if it fits the free time'.",
        "storage_project": "JANCTION Storage project id to continue (from a Storage project's Render again); the result is saved into that project when saving to Storage is on for this key, otherwise ignored.",
        "idempotency_key": "Any string up to 128 characters that identifies this order: sending the same key again returns the first job instead of rendering twice (a different body with the same key is refused).",
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
        "job_id": "The job_id returned by render_preview or render_final (j_...; a long final split into parts is b_...). Only this key's jobs; in render_status, leave it empty to list them.",
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
PARAM_ALIAS = {("asset_search", "kind"): "kind_assets", ("render_review", "environment"): "environment_review",
               ("render_resume_options", "limit"): "resume_limit", ("render_resume_options", "cursor"): "resume_cursor"}


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
