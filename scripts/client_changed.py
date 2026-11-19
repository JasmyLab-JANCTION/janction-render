#!/usr/bin/env python3
"""Does this janction-render wheel differ from the latest one on PyPI? (2026-11-19)

The package on PyPI is the client side only: the CLI, the Python client and the stdio MCP server. A new version is published
only when that package changes. Updates to the hosted service (web pages, API, remote MCP, GPU workers) do not need one.

    python scripts/client_changed.py dist/janction_render-0.4.339-py3-none-any.whl

Compares every file in the wheel with the latest release on PyPI, ignoring the version number itself, the RECORD file and the
long description (README changes ride along with the next real client release). Prints `changed=true` or `changed=false`
(also to $GITHUB_OUTPUT when set) and the files that differ. Exit 0 either way; exit 1 when PyPI cannot be read.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import urllib.request
import zipfile

PROJECT = "janction-render"


def _norm_metadata(text: str) -> str:
    """METADATA without the long description (after the first blank line) and without the Version line."""
    head = text.split("\n\n", 1)[0]
    return "\n".join(line for line in head.splitlines() if not line.startswith("Version:"))


def wheel_files(data: bytes, version: str) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name.endswith("/RECORD"):
                continue
            body = z.read(name).replace(b"\r\n", b"\n")
            key =re.sub(r"-[0-9][^/]*\.dist-info/", "-X.dist-info/", name)
            if key.endswith(".dist-info/METADATA"):
                body = _norm_metadata(body.decode("utf-8", "replace")).encode("utf-8")
            if version:
                body = body.replace(version.encode("utf-8"), b"{VERSION}")
            out[key] = body.replace(b"\r\n", b"\n")
    return out


def diff(new: dict[str, bytes], old: dict[str, bytes]) -> list[str]:
    return sorted(k for k in set(new) | set(old) if new.get(k) != old.get(k))


def _version_of(path: str) -> str:
    m = re.search(r"janction_render-([0-9][^-]*)-", os.path.basename(path))
    return m.group(1) if m else ""


def latest_wheel() -> tuple[str, bytes]:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{PROJECT}/json", timeout=30) as r:
        info = json.load(r)
    version = info["info"]["version"]
    url = next(u["url"] for u in info["urls"] if u["filename"].endswith(".whl"))
    with urllib.request.urlopen(url, timeout=60) as r:
        return version, r.read()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = argv[1]
    with open(path, "rb") as f:
        new = wheel_files(f.read(), _version_of(path))
    try:
        old_version, old_bytes = latest_wheel()
    except Exception as exc:  # noqa: BLE001
        print(f"could not read the latest release from PyPI: {exc}", file=sys.stderr)
        return 1
    changed = diff(new, wheel_files(old_bytes, old_version))
    if _version_of(path) == old_version:
        changed = []          # this version is already on PyPI
    flag = "true" if changed else "false"
    print(f"changed={flag}")
    print(f"compared with {PROJECT} {old_version} on PyPI")
    for name in changed[:50]:
        print(f"  differs: {name}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"changed={flag}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
