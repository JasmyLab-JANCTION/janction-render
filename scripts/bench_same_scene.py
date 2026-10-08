#!/usr/bin/env python3
"""Same-scene benchmark: render public Blender demo scenes on JANCTION Render with fixed settings, so anyone can
render the very same files with the very same settings elsewhere (a local GPU, another service) and compare.

Scenes (from download.blender.org, checked by sha256; no people in them):
  classroom  "Classroom" by Christophe Seux, CC0      https://download.blender.org/demo/test/classroom.zip
  pavillon   "Barcelona Pavillion" by eMirage, CC-BY  https://download.blender.org/demo/test/pabellon_barcelona_v1.scene_.zip

For each scene it:
  1. downloads and unzips the archive (cached in --work), checks the sha256
  2. makes one self-contained .blend with a local Blender (no rendering, no GPU): linked libraries are made local,
     missing textures are looked up in the scene's folder, every image is packed, Python in the file is not run
     (the service takes one .blend plus image files, not linked .blend libraries)
  3. creates a fresh key (no sign-up: POST /v1/keys) and uploads that file
  4. renders one preview frame (1280x720, 16 samples)          -> time from "new key" to "first image on disk"
  5. renders frames 1-3 as a final (1920x1080, 128 samples, denoise, PNG) -> GPU seconds per frame
and writes one JSON file with the settings, the timings and the price at the current rate.
Both renders ask for Blender 5.2 on the service, the version the self-contained file is saved with.

    python scripts/bench_same_scene.py                                  # both scenes, public server
    python scripts/bench_same_scene.py --scenes classroom --out bench.json
    python scripts/bench_same_scene.py --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
    python scripts/bench_same_scene.py --server http://localhost:8340   # your own receptionist

To compare with another renderer: download the same zip (the sha256 is in SCENES), open the .blend in Blender 5.2,
render frames 1-3 of the scene that opens (the active scene) at 1920x1080 with 128 samples and denoising on, and
compare the render time per frame and the price per frame. Making the file self-contained does not change the image.
The stills render the same image for frames 1, 2 and 3; three frames only average out start-up noise.

It names itself "benchmark-same-scene", so the operator's metrics leave these renders out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from janction_render import __version__  # noqa: E402
from janction_render.client import Client  # noqa: E402

CLIENT_NAME = "benchmark-same-scene"
DEFAULT_SERVER = "https://render.janction.jp"

SCENES: dict[str, dict[str, Any]] = {
    "classroom": {
        "title": "Classroom",
        "author": "Christophe Seux",
        "license": "CC0",
        "page": "https://www.blender.org/download/demo-files/",
        "url": "https://download.blender.org/demo/test/classroom.zip",
        "sha256": "0f0ecc58d45f12b2f4272a53e2d8e69135518e16e956b118f10c20d8dcfdf5e6",
        "blend": "classroom/classroom.blend",
        "search": "classroom",
    },
    "pavillon": {
        "title": "Barcelona Pavillion",
        "author": "eMirage",
        "license": "CC-BY",
        "page": "https://www.blender.org/download/demo-files/",
        "url": "https://download.blender.org/demo/test/pabellon_barcelona_v1.scene_.zip",
        "sha256": "0a85bf512329f1780563069512b934d679a6c543eeb1a4ec4f60cddeab706697",
        "blend": "3d/pavillon_barcelone_v1.2.blend",
        "search": "3d",
    },
}

BLENDER_ON_SERVICE = "5.2"
PREVIEW = {"kind": "preview", "frames": [1], "width": 1280, "height": 720, "samples": 16, "blender": BLENDER_ON_SERVICE}
FINAL = {"kind": "final", "frame_start": 1, "frame_end": 3, "width": 1920, "height": 1080, "samples": 128,
         "denoise": True, "output": "png", "blender": BLENDER_ON_SERVICE}

# Runs inside a local Blender (blender -b -Y <file> --python <this> -- <out.blend> <folder to search>).
PACK_SCRIPT = r'''
import sys, bpy
out, search = sys.argv[sys.argv.index("--") + 1:][:2]
made_local = 0
for _ in range(6):                                   # making one ID local can expose more linked ones
    linked = [i for i in bpy.data.user_map().keys() if getattr(i, "library", None) is not None]
    if not linked:
        break
    for i in linked:
        try:
            i.make_local()
            made_local += 1
        except Exception:
            pass
# Linked data nothing local uses (an unused collection kept in a library) cannot be made local; drop it, then the
# empty libraries. Data that a local block still uses is never dropped (still_linked then stops the benchmark).
um = bpy.data.user_map()
left = {i for i in um.keys() if getattr(i, "library", None) is not None}
unused = [i for i in left if all(u in left for u in um.get(i, ()))]
removed_unused = len(unused)
if unused:
    bpy.data.batch_remove(unused)
for lib in list(bpy.data.libraries):
    if not any(getattr(i, "library", None) == lib for i in bpy.data.user_map().keys()):
        bpy.data.libraries.remove(lib)
bpy.ops.file.find_missing_files(directory=search)
import os
missing, packed = [], 0
for im in bpy.data.images:                           # pack one by one: pack_all stops at the first missing file
    if im.packed_file or not im.filepath or im.source not in ("FILE", "SEQUENCE", "TILED"):
        continue
    if not os.path.isfile(bpy.path.abspath(im.filepath)):
        missing.append(os.path.basename(im.filepath) or im.name)   # missing from the archive itself: renders the same anywhere
        continue
    try:
        im.pack()
        packed += 1
    except Exception:
        missing.append(os.path.basename(im.filepath) or im.name)
for f in bpy.data.fonts:
    if f.filepath and f.filepath != "<builtin>" and not f.packed_file and os.path.isfile(bpy.path.abspath(f.filepath)):
        try:
            f.pack()
        except Exception:
            pass
left = sum(1 for i in bpy.data.user_map().keys() if getattr(i, "library", None) is not None)
bpy.ops.wm.save_as_mainfile(filepath=out, compress=True, copy=True)
print("JR_PACK", {"made_local": made_local, "removed_unused_linked": removed_unused, "still_linked": left,
                  "libraries_left": len(bpy.data.libraries), "images": len(bpy.data.images), "packed": packed,
                  "missing_images": sorted(set(missing)), "scene": bpy.context.scene.name,
                  "blender": bpy.app.version_string})
'''


def default_blender() -> str:
    env = os.environ.get("BLENDER")
    if env:
        return env
    for p in ("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe",
              "/Applications/Blender.app/Contents/MacOS/Blender"):
        if Path(p).is_file():
            return p
    return shutil.which("blender") or "blender"


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(scene: dict[str, Any], work: Path) -> Path:
    """Download (once) and unzip; return the folder the archive was unpacked into."""
    work.mkdir(parents=True, exist_ok=True)
    zpath = work / Path(scene["url"]).name
    if not zpath.is_file() or sha256_of(zpath) != scene["sha256"]:
        with requests.get(scene["url"], stream=True, timeout=600) as r:
            r.raise_for_status()
            with zpath.open("wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
    got = sha256_of(zpath)
    if got != scene["sha256"]:
        raise SystemExit(f"{zpath.name}: sha256 {got} does not match {scene['sha256']} (the file on the mirror changed)")
    out = work / zpath.stem
    if not (out / scene["blend"]).is_file():
        with zipfile.ZipFile(zpath) as z:
            for info in z.infolist():
                target = (out / info.filename).resolve()
                if not str(target).startswith(str(out.resolve())):   # no paths outside the folder
                    raise SystemExit(f"{zpath.name}: unsafe path {info.filename}")
            z.extractall(out)
    return out


def self_contained(name: str, scene: dict[str, Any], root: Path, blender: str) -> tuple[Path, dict[str, Any]]:
    """One .blend with the linked libraries made local and every image packed, made by a local Blender.
    The script is written outside the downloaded folder, and -Y keeps Python stored in the .blend from running."""
    out = root.parent / f"{name}_selfcontained.blend"
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "jr_pack.py"
        script.write_text(PACK_SCRIPT, encoding="utf-8")
        r = subprocess.run([blender, "-b", "-Y", str(root / scene["blend"]), "--python", str(script), "--",
                            str(out), str(root / scene["search"])],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    report: dict[str, Any] = {}
    for line in r.stdout.splitlines():
        if line.startswith("JR_PACK "):
            import ast
            report = ast.literal_eval(line[len("JR_PACK "):])
    if r.returncode != 0 or not out.is_file() or not report:
        raise SystemExit(f"{name}: Blender could not make a self-contained file (exit {r.returncode}):\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    if report.get("still_linked"):
        raise SystemExit(f"{name}: {report['still_linked']} linked data-blocks are still linked: {report}")
    return out, report


def new_key(server: str) -> tuple[str, float]:
    t0 = time.time()
    r = requests.post(f"{server}/v1/keys", json={"label": f"{CLIENT_NAME} {time.strftime('%Y-%m-%d')}"},
                      headers={"X-Client": f"{CLIENT_NAME} {__version__}"}, timeout=30)
    r.raise_for_status()
    return r.json()["api_key"], t0


def run_job(c: Client, scene_id: str, params: dict[str, Any], out_dir: Path, timeout: float) -> dict[str, Any]:
    t_submit = time.time()
    j = c.submit(scene_id, **params)
    done = c.wait(j["job_id"], timeout=timeout)
    t_done = time.time()
    files = c.download(j["job_id"], out_dir / j["job_id"], only="frames") if done.get("status") == "done" else []
    t_files = time.time()
    frames = (params.get("frame_end", 0) - params.get("frame_start", 0) + 1) if params["kind"] == "final" else len(params["frames"])
    gpu_s = float(done.get("gpu_seconds") or 0.0)
    return {
        "job_id": j["job_id"],
        "status": done.get("status"),
        "params": params,
        "frames": frames,
        "gpu_seconds": round(gpu_s, 2),
        "gpu_seconds_per_frame": round(gpu_s / max(frames, 1), 2),
        "wall_seconds_submit_to_done": round(t_done - t_submit, 1),
        "wall_seconds_submit_to_files": round(t_files - t_submit, 1),
        "estimate_seconds": (j.get("estimate") or {}).get("seconds"),
        "device": done.get("device"),
        "blender": done.get("blender") or (done.get("worker") or {}).get("blender"),
        "warnings": done.get("warnings") or [],
        "error": done.get("error"),
        "files": [p.name for p in files],          # names only: no local paths in the published JSON
        "_t_files": t_files,
    }


def bench_scene(name: str, server: str, work: Path, timeout: float, rate: float, blender: str) -> dict[str, Any]:
    scene = SCENES[name]
    root = fetch(scene, work)
    blend, pack = self_contained(name, scene, root, blender)
    key, t_key = new_key(server)
    c = Client(server=server, api_key=key, client=CLIENT_NAME)
    t_up = time.time()
    up = c.upload(blend, trace_assets=False)
    t_up_done = time.time()
    preview = run_job(c, up["scene_id"], dict(PREVIEW), work / "out", timeout)
    final = run_job(c, up["scene_id"], dict(FINAL), work / "out", timeout)
    first_image = preview.pop("_t_files") - t_key
    final.pop("_t_files")
    return {
        "scene": name,
        "title": scene["title"],
        "author": scene["author"],
        "license": scene["license"],
        "source": scene["url"],
        "sha256": scene["sha256"],
        "blend": scene["blend"],
        "self_contained": {"made_local": pack.get("made_local"),
                           "removed_unused_linked": pack.get("removed_unused_linked"), "images": pack.get("images"),
                           "packed_images": pack.get("packed"),
                           "missing_images": pack.get("missing_images"), "active_scene": pack.get("scene"),
                           "saved_with_blender": pack.get("blender")},
        "upload": {"files": 1, "bytes": blend.stat().st_size, "seconds": round(t_up_done - t_up, 1)},
        "seconds_new_key_to_first_image": round(first_image, 1),
        "preview": preview,
        "final": final,
        "yen_per_frame_at_rate": round(final["gpu_seconds_per_frame"] * rate, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--server", default=os.environ.get("JANCTION_RENDER_SERVER") or DEFAULT_SERVER)
    ap.add_argument("--scenes", default=",".join(SCENES), help="comma-separated: " + ", ".join(SCENES))
    ap.add_argument("--work", default=str(Path.home() / ".cache" / "janction-render-bench"))
    ap.add_argument("--out", default="", help="write the results here (JSON); prints them either way")
    ap.add_argument("--timeout", type=float, default=1800.0, help="seconds to wait for each job")
    ap.add_argument("--blender", default=default_blender(),
                    help="local Blender 5.2 used only to make the self-contained .blend (it does not render)")
    a = ap.parse_args()
    server = a.server.rstrip("/")
    names = [x.strip() for x in a.scenes.split(",") if x.strip()]
    for n in names:
        if n not in SCENES:
            raise SystemExit(f"unknown scene {n!r}; choose from {', '.join(SCENES)}")
    pricing: dict[str, Any] = {}
    try:
        pricing = requests.get(f"{server}/pricing.json", timeout=15).json()
    except (requests.RequestException, ValueError):
        pass
    rate = float(pricing.get("yen_per_gpu_second") or (pricing.get("planned") or {}).get("yen_per_gpu_second") or 0.1)
    version: dict[str, Any] = {}
    try:
        version = requests.get(f"{server}/version.json", timeout=15).json()
    except (requests.RequestException, ValueError):
        pass
    results = {
        "benchmark": "same-scene",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "server": server,
        "service_version": version.get("current_version"),
        "client": f"{CLIENT_NAME} {__version__} (Python {platform.python_version()})",
        "yen_per_gpu_second": rate,
        "settings": {"preview": PREVIEW, "final": FINAL},
        "how_to_reproduce": ("Download the zip (check the sha256), open the .blend in Blender 5.2, render frames 1-3 of the "
                             "active scene at 1920x1080, 128 samples, denoising on, PNG; compare seconds and price per frame. "
                             "This script also makes the self-contained copy it uploads (libraries made local, images packed)."),
        "scenes": [],
    }
    for n in names:
        print(f"[{n}] downloading, uploading and rendering ...", file=sys.stderr)
        r = bench_scene(n, server, Path(a.work), a.timeout, rate, a.blender)
        results["scenes"].append(r)
        f = r["final"]
        print(f"[{n}] first image {r['seconds_new_key_to_first_image']} s after a new key; final {f['status']}: "
              f"{f['gpu_seconds_per_frame']} GPU s/frame, {r['yen_per_frame_at_rate']} JPY/frame", file=sys.stderr)
    text = json.dumps(results, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if all(s["final"]["status"] == "done" for s in results["scenes"]) else 1


if __name__ == "__main__":
    sys.exit(main())
