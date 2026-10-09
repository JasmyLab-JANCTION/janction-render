"""MCP のプロンプト（10/10、ほかの AI に呼んでもらうためのフック）。

クライアントのスラッシュコマンドや「+」のメニューに出る、よくある頼み方の型（Claude Code なら
/mcp__janction-render__turntable_video）。中身は「この道具をこの順で使い、仕上げの前に人に聞く」という指示だけで、
プロンプトを選んでも勝手に有料の仕上げは走らない。

stdio（mcp_server.py）は既定で出す（JR_MCP_PROMPTS=0 で止める）。リモート（server/mcp_remote.py）は
ディレクトリの審査中なので JR_MCP_PROMPTS=1 のときだけ出す（道具の数と説明は審査中に変えない決まり、10/3）。
"""
from __future__ import annotations

import os
from typing import Annotated, Any

from pydantic import Field

SAMPLE_URL = "https://render.janction.jp/samples/cube_scene.py"
_SCENE = "A .blend, a bpy .py script or a 3D file (GLB, FBX, OBJ, USD): a path on this computer or an https link"
_MODEL = "The 3D model: GLB, FBX, OBJ, USD or .blend, as a path on this computer or an https link"
UPLOAD_URL = "https://render.janction.jp/upload"

# 名前は Claude Code などがスラッシュコマンドにそのまま使う。変えると利用者の手順が壊れるので足すだけにする
NAMES = ("try_janction_render", "render_my_scene", "turntable_video", "product_shots", "scene_from_description",
         "blend_to_mp4", "render_for_free")


def enabled(remote: bool) -> bool:
    """出すか。stdio は既定で出す、リモートは JR_MCP_PROMPTS=1 のときだけ。"""
    raw = (os.environ.get("JR_MCP_PROMPTS") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if remote:
        return raw in ("1", "true", "yes", "on")
    return True


def _scene_hint(remote: bool) -> str:
    if remote:
        return (f"If it is a file on my computer, you cannot read it from here: ask me to drop it at {UPLOAD_URL} "
                "(no sign-up, the link lasts 12 hours) and pass the link as scene_url. ")
    return "If it is a local file, pass it as scene_path; an https link goes in scene_url. "


_CONFIRM = ("Before any render_final, call render_estimate, tell me the time and the cost it shows, and wait for my yes. "
            "While a final runs, poll render_status and tell me eta.human; if it says the GPU is lent out, tell me the wait "
            "instead of polling.")


def try_text() -> str:
    return (f"Check that JANCTION Render works here: call render_preview with scene_url='{SAMPLE_URL}' and "
            "environment='compare', show me the image (four lighting presets in one picture), and tell me in one short "
            "paragraph what you can render for me next: my own .blend, a 3D model file (GLB, FBX, OBJ, USD), or a scene you "
            "write as a bpy script from my description. Do not start a final render.")


def render_scene_text(scene: str, notes: str, remote: bool) -> str:
    extra = f" What I want: {notes.strip()}." if notes.strip() else ""
    return (f"Render my Blender scene with JANCTION Render: {scene.strip()}.{extra} " + _scene_hint(remote)
            + "Start with scene_info, then render_preview. Show me the preview and the critic verdict; if the critic "
            "returns fixes, apply them and preview again. " + _CONFIRM)


def turntable_text(model: str, seconds: str, background: str, remote: bool) -> str:
    try:
        frames = max(24, min(240, int(round(float(seconds or "4") * 24))))
    except ValueError:
        frames = 96
    bg = (background or "studio").strip().lower()
    env = "transparent=True (no environment)" if bg == "transparent" else f"environment='{bg}'"
    out = "output='webm'" if bg == "transparent" else "output='mp4'"
    return (f"Make a 360-degree turntable video of this 3D model with JANCTION Render: {model.strip()}. " + _scene_hint(remote)
            + f"Preview first with orbit=True and {env} (it shows 0, 90, 180 and 270 degrees in one image). If the model "
            f"is cut off or too small, adjust orbit_distance and preview again. Then the final: orbit=True, orbit_frames={frames} "
            f"at 24 fps (about {frames // 24} seconds), {env}, {out}. " + _CONFIRM + " Give me the download link at the end.")


def product_shots_text(model: str, background: str, remote: bool) -> str:
    bg = (background or "transparent").strip().lower()
    env = "transparent=True" if bg == "transparent" else f"environment='{bg}'"
    return (f"Make four product shots of this 3D model with JANCTION Render: {model.strip()}. " + _scene_hint(remote)
            + f"Preview with orbit=True and {env} to check the four angles (0, 90, 180, 270 degrees). Then render_final with "
            f"orbit=True, orbit_frames=4, output='png', {env}, at 1920x1080: one PNG per angle. " + _CONFIRM)


def from_description_text(description: str) -> str:
    return (f"Build this 3D scene as a Blender 5.0 bpy script and render it with JANCTION Render: {description.strip()}. "
            "Write the script yourself (scene_script): objects, materials on the Principled BSDF, a light and a camera; "
            "end with `import jr_assets; jr_assets.frame_camera()` so everything is in frame; leave resolution and samples "
            "to the service. Call render_preview, look at the image and the critic verdict, fix the script and preview "
            "again until it looks right. " + _CONFIRM)


def blend_to_mp4_text(scene: str, frames: str, resolution: str, remote: bool) -> str:
    fr = (frames or "").strip()
    res = (resolution or "1920x1080").strip().lower()
    span = f"frames {fr}" if fr else "the scene's own frame range"
    return (f"Render this Blender animation to an MP4 with JANCTION Render: {scene.strip()}. " + _scene_hint(remote)
            + f"Use {span} at {res}. Start with scene_info (frame range, cameras, missing files), then render_preview with "
            "four frames spread over the range (frames='1-N' tiles them in one image). A job can hold up to 240 frames at "
            "1080p, so split a longer range into several jobs and tell me the plan. " + _CONFIRM)


def free_text(scene: str, remote: bool) -> str:
    what = (f"this scene: {scene.strip()}. " + _scene_hint(remote) if scene.strip() else
            f"a scene I describe, or the sample {SAMPLE_URL} if I have none yet. ")
    return ("Render with JANCTION Render using only the free GPU time, " + what
            + "First call billing and tell me how much free time this key has. Then render_preview (previews are the cheapest "
            "way to check the scene). Before any render_final, call render_estimate: start the final only if it fits in the "
            "free time and I say yes. If it does not fit, tell me what would (fewer frames, a smaller size, fewer samples, or "
            "waiting for the daily reset) and what the full render would cost.")


def register(mcp: Any, remote: bool = False) -> list[str]:
    """MCP サーバー（mcp.server の MCPServer / FastMCP）にプロンプトを足す。足した名前を返す（出さないときは空）。"""
    if not enabled(remote):
        return []

    @mcp.prompt(name="try_janction_render", title="Try JANCTION Render (first render)",
                description="Check the connection with a sample scene: one preview image showing four lighting presets, "
                            "in a few seconds. Free; no final render.")
    def try_janction_render() -> str:
        return try_text()

    @mcp.prompt(name="render_my_scene", title="Render my Blender scene",
                description="Preview a .blend, a bpy script or a 3D file on a cloud GPU, fix what the critic finds, then "
                            "render the final after you confirm the estimate.")
    def render_my_scene(scene: Annotated[str, Field(description=_SCENE)],
                        notes: Annotated[str, Field(description="Optional: what you want (a still, an animation, a look)")] = "") -> str:
        return render_scene_text(scene, notes, remote)

    @mcp.prompt(name="turntable_video", title="360-degree turntable video",
                description="A turntable MP4 (or a transparent WebM) of a 3D model: GLB, FBX, OBJ, USD or .blend. Preview "
                            "first, final after you confirm.")
    def turntable_video(model: Annotated[str, Field(description=_MODEL)],
                        seconds: Annotated[str, Field(description="Length of one turn in seconds (1-10, default 4)")] = "4",
                        background: Annotated[str, Field(description="studio, sunset, overcast, night or transparent")] = "studio") -> str:
        return turntable_text(model, seconds, background, remote)

    @mcp.prompt(name="product_shots", title="Product shots from four angles",
                description="Four PNGs (front, side, back, side) of a 3D model, on a transparent background or a studio "
                            "light. Preview first, final after you confirm.")
    def product_shots(model: Annotated[str, Field(description=_MODEL)],
                      background: Annotated[str, Field(description="transparent (default), studio, sunset, overcast or night")] = "transparent") -> str:
        return product_shots_text(model, background, remote)

    @mcp.prompt(name="scene_from_description", title="Make a 3D scene from a description",
                description="The assistant writes the Blender scene as a bpy script, previews it on a cloud GPU and "
                            "iterates with the critic. No Blender or GPU needed on your side.")
    def scene_from_description(description: Annotated[str, Field(description="The scene in your own words: objects, colors, mood, camera")]) -> str:
        return from_description_text(description)

    @mcp.prompt(name="blend_to_mp4", title="Render a Blender animation to MP4",
                description="An animated .blend to MP4 on cloud GPUs: reads the scene, previews four frames, plans jobs of "
                            "up to 240 frames, then renders after you confirm.")
    def blend_to_mp4(scene: Annotated[str, Field(description=_SCENE)],
                     frames: Annotated[str, Field(description="Frame range such as 1-120 (empty: the scene's own range)")] = "",
                     resolution: Annotated[str, Field(description="WIDTHxHEIGHT, up to 1920x1080 (default 1920x1080)")] = "1920x1080") -> str:
        return blend_to_mp4_text(scene, frames, resolution, remote)

    @mcp.prompt(name="render_for_free", title="Render within the free GPU time",
                description="Checks the free GPU time of this key first and keeps the render inside it; if the final would "
                            "not fit, says what would and what it would cost. No sign-up or card.")
    def render_for_free(scene: Annotated[str, Field(description="Optional: " + _SCENE)] = "") -> str:
        return free_text(scene, remote)

    return list(NAMES)
