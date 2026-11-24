"""納品の目録 package.json を手元のフォルダと照らす（11/24 に server/package.py から分けた）。

`janction-render verify-package <フォルダ>`（cli.py）が読む。公開版（PyPI）には受付（server/）が入らないので、照らす部分だけを
ここに置く（11/13 から 11/24 まで、公開版の verify-package は server を読もうとして落ちていた）。受付の server/package.py もここを使う。

長い仕上げ（241 コマ以上を部分に分けて 1 つの b_… で返す）は、部分のコマが part-01_frame_0001.png の名前で落ちる。目録は
frame_0001.png で書くので、part-NN_ を外した名前でも照らす。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

NAME = "package.json"
SCHEMA = "jr-package-1"
_DELIVERABLE = re.compile(r"^(frame_\d+\.(png|exr|jpg|webp)|output\.[a-z0-9]+|social_[a-z]+\.mp4|fo[A-Za-z0-9_.-]+|scene\.blend)$")
_QC = re.compile(r"^(report\.json|report_sheet\.png|compare\.(mp4|gif|png|json)|compare_outside\.png)$")
_INFO = re.compile(r"^[a-z_]+\.json$")
_SKIP = {NAME, "upload.json", "log.txt"}
_PART = re.compile(r"^part-\d{2,}_(.+)$")


def role_of(name: str) -> Optional[str]:
    if name in _SKIP or name.startswith((".", "joined_post")):
        return None
    if _DELIVERABLE.match(name):
        return "deliverable"
    if _QC.match(name):
        return "qc"
    if _INFO.match(name):
        return "info"
    return None


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _local_files(folder: Path, listed: dict[str, Any]) -> dict[str, Path]:
    """目録の名前 → 手元のファイル。同じ名前が無ければ part-NN_<名前>（長い仕上げの部分のコマ）。目録に無い部分の
    ファイル（部分ごとの控え）は目録の外として扱わない。"""
    out: dict[str, Path] = {}
    for p in folder.iterdir():
        if p.is_file() and p.name in listed:
            out[p.name] = p
    for p in sorted(folder.iterdir(), key=lambda x: x.name):
        m = _PART.match(p.name) if p.is_file() else None
        if m and m.group(1) in listed and m.group(1) not in out:
            out[m.group(1)] = p
    return out


def verify(folder: Path) -> dict[str, Any]:
    """手元のフォルダを package.json と照らす。{ok, missing, changed, extra, checked}。"""
    m = json.loads((folder / NAME).read_text(encoding="utf-8"))
    if m.get("schema") != SCHEMA:
        raise ValueError(f"{NAME} is not a {SCHEMA} manifest")
    listed = {f["name"]: f for f in m.get("files") or []}
    have = _local_files(folder, listed)
    missing, changed = [], []
    for name, f in listed.items():
        p = have.get(name)
        if p is None:
            missing.append(name)
        elif p.stat().st_size != f.get("size") or (f.get("sha256") and sha256_of(p) != f["sha256"]):
            changed.append(name)
    extra = sorted(p.name for p in folder.iterdir()
                   if p.is_file() and role_of(p.name) == "deliverable" and p.name not in listed)
    return {"ok": not (missing or changed or extra), "missing": missing, "changed": changed, "extra": extra,
            "checked": len(listed), "job_id": m.get("job_id"), "sku": m.get("sku") or ""}
