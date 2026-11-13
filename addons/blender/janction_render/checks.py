"""Local pre-render checks (11/13, v2 QAD-01). Run inside Blender with no network and nothing sent.

Each check returns (level, code, text): level is "block" (the render would fail or be refused), "warn" (it would
render, but probably not as intended) or "info". The add-on shows them under Files and before Preview / Final.
The service still runs its own checks after upload; these only catch what Blender already knows locally.
"""
from __future__ import annotations

from typing import Any

WORKER_BLENDER_MAX = (5, 3)          # the newest Blender the service renders with (add-on's VERSION_ITEMS)
MAX_PIXELS_PAID = 3840 * 2160
MAX_FRAMES = 3000
ENGINES_OK = {"CYCLES", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"}
SIM_MODIFIERS = {"CLOTH", "SOFT_BODY", "PARTICLE_SYSTEM"}   # fluid caches are checked by the service after upload


def run(scene: Any, blender_version: tuple = (5, 0, 0)) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    r = scene.render
    # camera
    cam = getattr(scene, "camera", None)
    if cam is None:
        cams = [o for o in getattr(scene, "objects", []) if getattr(o, "type", "") == "CAMERA"]
        if not cams:
            out.append(("warn", "no_camera", "No camera: the service will place one automatically (add a camera to choose the view)"))
        else:
            out.append(("info", "no_active_camera", f"No active camera: the service will use {cams[0].name}"))
    # version
    ver = tuple(blender_version[:2])
    if ver > WORKER_BLENDER_MAX:
        out.append(("block", "blender_too_new", f"Saved with Blender {ver[0]}.{ver[1]}: the service renders up to "
                                                f"{WORKER_BLENDER_MAX[0]}.{WORKER_BLENDER_MAX[1]}; save a copy with a supported version"))
    # engine
    engine = str(getattr(r, "engine", ""))
    if engine and engine not in ENGINES_OK:
        out.append(("block", "engine_unsupported", f"Render engine {engine} is not available on the service (use Cycles or EEVEE)"))
    # size
    pct = max(1, int(getattr(r, "resolution_percentage", 100))) / 100.0
    w, h = int(r.resolution_x * pct), int(r.resolution_y * pct)
    if w * h > MAX_PIXELS_PAID:
        out.append(("warn", "too_large", f"{w}x{h} is above 3840x2160; one render is limited to 4K (stills may go to 8K when "
                                         "the service offers it)"))
    elif w * h > 1920 * 1080:
        out.append(("info", "above_1080p", f"{w}x{h} is above 1920x1080: needs prepaid credit (free time renders up to 1080p)"))
    # frames
    fs, fe = int(scene.frame_start), int(scene.frame_end)
    if fe - fs + 1 > MAX_FRAMES:
        out.append(("warn", "too_many_frames", f"{fe - fs + 1} frames: one render takes at most {MAX_FRAMES}; only {fs}-{fs + MAX_FRAMES - 1} "
                                               "will be sent"))
    # simulations that are not baked (they would simulate differently per part on several GPUs)
    unbaked = []
    for o in getattr(scene, "objects", []):
        for m in getattr(o, "modifiers", []) or []:
            kind = getattr(m, "type", "")
            if kind not in SIM_MODIFIERS:
                continue
            if kind == "PARTICLE_SYSTEM":
                cache = getattr(getattr(m, "particle_system", None), "point_cache", None)
            else:                                    # cloth / soft body keep it on the modifier
                cache = getattr(m, "point_cache", None)
            if cache is not None and not getattr(cache, "is_baked", False):
                unbaked.append(f"{o.name} ({kind.lower()})")
    if unbaked and fe > fs:
        out.append(("warn", "sim_unbaked", "Not baked: " + ", ".join(unbaked[:4]) + (" and more" if len(unbaked) > 4 else "")
                    + ". Bake them (Physics > Cache > Bake) so every frame matches"))
    return out


def summary(checks: list[tuple[str, str, str]]) -> str:
    n_block = sum(1 for c in checks if c[0] == "block")
    n_warn = sum(1 for c in checks if c[0] == "warn")
    if not checks:
        return "Local checks: nothing found"
    return f"Local checks: {n_block} blocking, {n_warn} warning(s)"
