"""JANCTION Render demo: a 3D model in, four studio shots out (a preview from cloud GPUs).

The Space creates its own API key on start and renders previews only, with max_yen=0, so a render never costs anything:
when the free daily preview time runs out, it says so and points to render.janction.jp.
"""
import os
import threading
import time

import gradio as gr
import requests

BASE = "https://render.janction.jp"
SITE = f"{BASE}/?src=hf-space"
UA = {"User-Agent": "janction-render-hf-space/1.0"}
_key_lock = threading.Lock()
_key = {"value": os.environ.get("JANCTION_RENDER_API_KEY", "")}


def _api_key() -> str:
    with _key_lock:
        if not _key["value"]:
            r = requests.post(f"{BASE}/v1/keys", json={"label": "hf-space", "source": "hf-space"}, headers=UA, timeout=30)
            r.raise_for_status()
            _key["value"] = r.json()["api_key"]
        return _key["value"]


def _h() -> dict:
    return {**UA, "X-API-Key": _api_key()}


def _error_text(r: requests.Response) -> str:
    try:
        j = r.json()
    except ValueError:
        return f"HTTP {r.status_code}"
    return str(j.get("tell_user") or j.get("detail") or j.get("message") or j.get("error") or r.status_code)


def render(model_path, environment):
    if not model_path:
        raise gr.Error("Drop a 3D model first (GLB, glTF, FBX, OBJ, STL or USD).")
    if os.path.getsize(model_path) > 90 * 1024 * 1024:
        raise gr.Error(f"This demo takes files up to 90 MB. Larger files: {SITE}")
    with open(model_path, "rb") as f:
        r = requests.post(f"{BASE}/v1/files?src=hf-space", headers=_h(),
                          files={"file": (os.path.basename(model_path), f)}, timeout=300)
    if r.status_code >= 400:
        raise gr.Error(f"Upload failed: {_error_text(r)}")
    scene_id = r.json()["scene_id"]
    body = {"scene_id": scene_id, "kind": "preview", "preset": "product", "environment": environment, "max_yen": 0}
    r = requests.post(f"{BASE}/v1/jobs?src=hf-space", headers=_h(), json=body, timeout=60)
    if r.status_code in (402, 403, 429):
        raise gr.Error(f"Today's free demo time is used up. Render it yourself, free to start: {SITE}")
    if r.status_code >= 400:
        raise gr.Error(f"Render refused: {_error_text(r)}")
    job = r.json()
    deadline = time.time() + 240
    while job.get("status") not in ("done", "failed", "canceled") and time.time() < deadline:
        time.sleep(3)
        job = requests.get(f"{BASE}/v1/jobs/{job['job_id']}", headers=_h(), timeout=30).json()
    if job.get("status") != "done":
        msg = (job.get("error") or {}).get("message") if isinstance(job.get("error"), dict) else job.get("error")
        raise gr.Error(f"The render did not finish ({job.get('status')}): {msg or 'try again in a minute'}")
    arts = job.get("artifacts") or []
    img = next((a for a in arts if str(a.get("name", "")).endswith((".png", ".jpg", ".webp")) and "sheet" in a.get("name", "")), None) \
        or next((a for a in arts if str(a.get("name", "")).endswith((".png", ".jpg", ".webp"))), None)
    if img is None:
        raise gr.Error("No image came back. Try again, or render it at " + SITE)
    gpu = job.get("gpu_seconds") or (job.get("usage") or {}).get("gpu_seconds")
    note = f"Rendered with Blender Cycles on an NVIDIA GPU{f' in {gpu:.1f} GPU-seconds' if isinstance(gpu, (int, float)) else ''}. " \
           f"Full-size shots, 360-degree turntable MP4s and your own AI agent: {SITE}"
    return img.get("view_url") or img.get("url"), note


with gr.Blocks(title="JANCTION Render: 3D model to product shots") as demo:
    gr.Markdown("# 3D model to studio product shots\nDrop a GLB, glTF, FBX, OBJ, STL or USD file. "
                "Four studio shots come back in one image, rendered with Blender Cycles on cloud GPUs. "
                f"No Blender or GPU needed. [render.janction.jp]({SITE})")
    with gr.Row():
        with gr.Column():
            model = gr.File(label="3D model", file_types=[".glb", ".gltf", ".fbx", ".obj", ".stl", ".usd", ".usdz", ".usdc"],
                            type="filepath")
            env = gr.Radio(["studio", "sunset", "overcast", "night"], value="studio", label="Lighting")
            go = gr.Button("Render 4 studio shots", variant="primary")
        with gr.Column():
            out = gr.Image(label="Front, side, back, side")
            info = gr.Markdown()
    go.click(render, [model, env], [out, info], concurrency_limit=2)

demo.queue(max_size=20).launch()
