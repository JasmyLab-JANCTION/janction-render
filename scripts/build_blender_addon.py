"""Zip the Blender add-on for "Install from Disk".

Blender accepts a zip whose root holds blender_manifest.toml, which is what
this writes (no wrapping folder):

    python scripts/build_blender_addon.py                      # -> dist/janction_render-<version>.zip
    python scripts/build_blender_addon.py --output-dir out/    # somewhere else

The official alternative, which also validates the manifest:

    blender --command extension build --source-dir addons/blender/janction_render --output-dir dist
"""
from __future__ import annotations

import argparse
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "addons" / "blender" / "janction_render"
OFFICIAL = "blender --command extension build --source-dir addons/blender/janction_render --output-dir dist"
SKIP_DIRS = {"__pycache__", ".git", "tests"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".zip"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}


def read_manifest(source: Path) -> dict:
    return tomllib.loads((source / "blender_manifest.toml").read_text(encoding="utf-8"))


def wanted(path: Path, source: Path) -> bool:
    rel = path.relative_to(source)
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    return path.suffix not in SKIP_SUFFIXES and path.name not in SKIP_NAMES


def build(source: Path = SOURCE, output_dir: Path | None = None, quiet: bool = False) -> Path:
    """Write <output_dir>/<id>-<version>.zip with the manifest at the zip root and return its path."""
    manifest = read_manifest(source)
    out_dir = output_dir or (ROOT / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{manifest['id']}-{manifest['version']}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(source.rglob("*")):
            if p.is_file() and wanted(p, source):
                zf.write(p, p.relative_to(source).as_posix())
                if not quiet:
                    print(" +", p.relative_to(source).as_posix())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-dir", type=Path, default=SOURCE)
    ap.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = ap.parse_args(argv)
    if not (args.source_dir / "blender_manifest.toml").is_file():
        print(f"no blender_manifest.toml in {args.source_dir}", file=sys.stderr)
        return 1
    out = build(args.source_dir, args.output_dir)
    print("wrote", out)
    print("official alternative:", OFFICIAL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
