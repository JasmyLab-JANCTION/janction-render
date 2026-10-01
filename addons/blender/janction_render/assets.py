"""Collect the external files a .blend references, as (relative name, absolute path) pairs.

The server places assets next to the scene file under the relative name, so
``//textures/wood.png`` must be sent as ``textures/wood.png``. Packed data needs
nothing. Absolute paths, paths above the .blend folder, missing files and names
the server rejects are reported as warnings instead.

``collect()`` works on plain objects (anything with ``filepath`` / ``packed_file``
attributes) so it can be tested without Blender; ``collect_from_bpy()`` feeds it
``bpy.data``.
"""
import glob
import os
import re
from typing import Any, Iterable, Optional

# Mirrors the server's ASSET_EXTENSIONS and asset-name rule (app.py). Unknown types are refused there.
ACCEPTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".exr", ".hdr", ".tif", ".tiff", ".webp", ".bmp", ".tga",
    ".bin", ".mtl", ".fbx", ".glb", ".gltf", ".obj", ".usd", ".usda", ".usdc", ".usdz", ".abc",
    ".mp4", ".mov", ".json", ".txt", ".csv", ".ttf", ".otf",
}
NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}(/[A-Za-z0-9_.\-]{1,120}){0,4}$")
MAX_ASSETS = 40


class Collected:
    def __init__(self) -> None:
        self.assets: list[tuple[str, str]] = []
        self.warnings: list[str] = []
        self._names: set[str] = set()

    def add(self, name: str, abs_path: str) -> None:
        if name not in self._names:
            self._names.add(name)
            self.assets.append((name, abs_path))

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)


def relative_name(filepath: str) -> Optional[str]:
    """'//textures/wood.png' -> 'textures/wood.png'. None when the path is not blend-relative."""
    if not filepath or not filepath.startswith("//"):
        return None
    name = filepath[2:].replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    return name


def _consider(block: Any, label: str, blend_dir: str, acc: Collected) -> None:
    filepath = str(getattr(block, "filepath", "") or "")
    if not filepath or filepath.startswith("<"):            # "<builtin>" font
        return
    if getattr(block, "packed_file", None) is not None:      # packed: travels inside the .blend
        return
    if getattr(block, "library", None) is not None:
        acc.warn(f"{label} {block.name}: linked from a library; libraries are not sent")
        return
    source = str(getattr(block, "source", "FILE") or "FILE")
    if source in ("GENERATED", "VIEWER"):
        return
    if source in ("SEQUENCE", "MOVIE"):
        acc.warn(f"{label} {block.name}: image sequences and movies are not sent ({filepath})")
        return
    rel = relative_name(filepath)
    if rel is None:
        acc.warn(f"{label} {block.name}: absolute path, not sent ({filepath}); use a relative path or pack it")
        return
    if not blend_dir:
        acc.warn(f"{label} {block.name}: save the .blend first so {filepath} can be found")
        return
    if ".." in rel.split("/"):
        acc.warn(f"{label} {block.name}: outside the .blend folder, not sent ({filepath})")
        return
    names = [rel]
    if source == "TILED" or "<UDIM>" in rel:
        pattern = os.path.join(blend_dir, rel.replace("<UDIM>", "[0-9][0-9][0-9][0-9]"))
        tiles = sorted(glob.glob(pattern))
        if not tiles:
            acc.warn(f"{label} {block.name}: no UDIM tiles found for {filepath}")
            return
        names = [os.path.relpath(t, blend_dir).replace("\\", "/") for t in tiles]
    for name in names:
        ext = os.path.splitext(name)[1].lower()
        if not NAME_RE.match(name):
            acc.warn(f"{label} {block.name}: the server only accepts names with letters, digits, . _ - "
                     f"and up to 4 folders ({name}); rename the file or pack it")
            continue
        if ext not in ACCEPTED_EXTENSIONS:
            acc.warn(f"{label} {block.name}: {ext or 'no extension'} files are not accepted ({name}); pack it")
            continue
        abs_path = os.path.normpath(os.path.join(blend_dir, name))
        if not os.path.isfile(abs_path):
            acc.warn(f"{label} {block.name}: file not found ({abs_path})")
            continue
        acc.add(name, abs_path)


def collect(images: Iterable[Any] = (), fonts: Iterable[Any] = (), cache_files: Iterable[Any] = (),
            blend_dir: str = "", libraries: Iterable[Any] = (), others: Iterable[tuple[str, Any]] = ()) -> Collected:
    """Walk the given datablocks. ``others`` are (label, block) pairs that can only be warned about."""
    acc = Collected()
    for img in images:
        _consider(img, "Image", blend_dir, acc)
    for font in fonts:
        _consider(font, "Font", blend_dir, acc)
    for cf in cache_files:
        _consider(cf, "Cache", blend_dir, acc)
    for lib in libraries:
        acc.warn(f"Library {getattr(lib, 'filepath', '') or lib.name}: linked .blend files are not sent; "
                 f"make the data local (Object > Relations > Make Local) to render it")
    for label, block in others:
        fp = str(getattr(block, "filepath", "") or "")
        if fp and getattr(block, "packed_file", None) is None:
            acc.warn(f"{label} {block.name}: not sent ({fp})")
    if len(acc.assets) > MAX_ASSETS:
        acc.warn(f"{len(acc.assets)} files referenced; the server takes {MAX_ASSETS} per scene, the rest are skipped")
        acc.assets = acc.assets[:MAX_ASSETS]
    return acc


def collect_from_bpy() -> Collected:
    import bpy

    blend_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else ""
    others: list[tuple[str, Any]] = []
    for label, coll in (("Sound", getattr(bpy.data, "sounds", ())), ("Volume", getattr(bpy.data, "volumes", ()))):
        others += [(label, b) for b in coll]
    return collect(images=bpy.data.images, fonts=bpy.data.fonts, cache_files=getattr(bpy.data, "cache_files", ()),
                   blend_dir=blend_dir, libraries=bpy.data.libraries, others=others)
