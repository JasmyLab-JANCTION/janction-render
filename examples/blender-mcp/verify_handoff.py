#!/usr/bin/env python3
"""Check the hand-off from a Blender MCP server to JANCTION Render without opening a Blender window.

A Blender MCP server (ahujasid's mcp-for-blender, or Blender's own Lab MCP server) needs Blender's UI running, so this
script runs the very calls such a server makes, in a headless Blender:
  - build a small scene (a mug on a table, a camera, a light)
  - save a copy of the open file          (what the agent runs through execute_blender_code)
  - export the scene to GLB               (the same, with bpy.ops.export_scene.gltf)
then starts the janction-render MCP server over stdio, exactly as Claude Code / Claude Desktop / Cursor would, and
calls render_preview on both files. The preview images and the replies are written to --out.

    python examples/blender-mcp/verify_handoff.py
    python examples/blender-mcp/verify_handoff.py --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
    python examples/blender-mcp/verify_handoff.py --server-cmd "uvx --from janction-render[blend] janction-render-mcp"

Two previews use about 10 GPU seconds of the key's free daily time.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Runs inside Blender: blender -b -Y --python <this> -- <out.blend> <out.glb>
BUILD = r'''
import sys, math, bpy
blend, glb = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

def mat(name, rgb, rough, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.05))
table = bpy.context.object
table.name, table.scale = "Table", (3.0, 2.0, 0.1)
table.data.materials.append(mat("Wood", (0.35, 0.2, 0.1), 0.45))

bpy.ops.mesh.primitive_cylinder_add(radius=0.4, depth=0.9, location=(0, 0, 0.45), vertices=64)
mug = bpy.context.object
mug.name = "Mug"
mug.data.materials.append(mat("Glaze", (0.8, 0.82, 0.86), 0.15))
bpy.ops.mesh.primitive_torus_add(major_radius=0.22, minor_radius=0.05, location=(0.45, 0, 0.5), rotation=(math.pi / 2, 0, 0))
handle = bpy.context.object
handle.name = "Handle"
handle.data.materials.append(mug.data.materials[0])

bpy.ops.object.light_add(type="AREA", location=(2.0, -2.0, 3.0))
light = bpy.context.object
light.data.energy, light.data.size = 600, 2.0
light.rotation_euler = (math.radians(50), 0, math.radians(45))

bpy.ops.object.camera_add(location=(2.6, -2.6, 1.7))
cam = bpy.context.object
direction = mug.location - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
sc.camera = cam
sc.frame_start, sc.frame_end = 1, 24

world = bpy.data.worlds.new("World")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
sc.world = world

# What the agent sends through the Blender MCP server's execute_blender_code: save a copy, the open file stays as it is
bpy.ops.wm.save_as_mainfile(filepath=blend, copy=True)
# and, for objects only, a GLB (the README's second hand-off)
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", export_apply=True, export_animations=True)
print("JR_BUILT", {"blend": blend, "glb": glb, "blender": bpy.app.version_string})
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


def build_scene(blender: str, out: Path) -> tuple[Path, Path, str]:
    blend, glb = out / "handoff_scene.blend", out / "handoff_scene.glb"
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "jr_build.py"
        script.write_text(BUILD, encoding="utf-8")
        r = subprocess.run([blender, "-b", "-Y", "--python", str(script), "--", str(blend), str(glb)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    line = next((x for x in r.stdout.splitlines() if x.startswith("JR_BUILT ")), "")
    if r.returncode != 0 or not blend.is_file() or not glb.is_file() or not line:
        raise SystemExit(f"Blender could not build the scene (exit {r.returncode}):\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    version = line.split("'blender': '")[-1].split("'")[0]
    return blend, glb, version


async def call_janction(cmd: list[str], calls: list[tuple[str, dict]], out: Path) -> list[dict]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=cmd[0], args=cmd[1:], env=dict(os.environ), cwd=str(ROOT))
    results = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            for label, (name, args) in zip(("blend", "glb"), calls):
                if name not in tools:
                    raise SystemExit(f"the janction-render server has no tool {name!r}; tools: {sorted(tools)}")
                res = await session.call_tool(name, args)
                texts = [c.text for c in res.content if getattr(c, "type", "") == "text"]
                images = [c for c in res.content if getattr(c, "type", "") == "image"]
                saved = []
                for i, im in enumerate(images):
                    p = out / f"preview_{label}_{i}.png"
                    p.write_bytes(base64.b64decode(im.data))
                    saved.append(p.name)
                reply: dict = {}
                for t in texts:
                    try:
                        reply = json.loads(t)
                        break
                    except ValueError:
                        continue
                results.append({"input": label, "tool": name, "args": {k: v for k, v in args.items() if k != "scene_path"},
                                "is_error": bool(getattr(res, "isError", None) or getattr(res, "is_error", False)), "images": saved,
                                "job_id": reply.get("job_id"), "status": reply.get("status"),
                                "gpu_seconds": reply.get("gpu_seconds"), "verdict": (reply.get("critic") or {}).get("verdict"),
                                "text": None if reply else (texts[0][:500] if texts else None)})
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--blender", default=default_blender(), help="a local Blender (4.2 or newer); it only builds and saves")
    ap.add_argument("--server-cmd", default="",
                    help="how to start the janction-render MCP server over stdio (default: this repository's "
                         "janction_render.mcp_server with the current Python)")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "janction-blender-mcp-handoff"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    blend, glb, version = build_scene(a.blender, out)
    # A .blend saved by Blender 5.1 or newer needs the service's Blender 5.2; older files open in the default 5.0
    major_minor = tuple(int(x) for x in version.split(" ")[0].split(".")[:2])
    blend_args = {"scene_path": str(blend), "frames": "1"}
    if major_minor >= (5, 1):
        blend_args["blender"] = "5.2"
    calls = [("render_preview", blend_args),
             ("render_preview", {"scene_path": str(glb), "environment": "studio"})]
    cmd = shlex.split(a.server_cmd) if a.server_cmd else [sys.executable, "-m", "janction_render.mcp_server"]
    results = asyncio.run(call_janction(cmd, calls, out))
    summary = {"blender_used_to_build": version, "out": str(out), "results": results}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    ok = all(not r["is_error"] and r["images"] for r in results)
    print("hand-off OK: both files rendered" if ok else "hand-off FAILED: see the replies above", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
