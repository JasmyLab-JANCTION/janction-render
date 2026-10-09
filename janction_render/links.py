"""シーンのリンク（10/10、ほかの AI に呼んでもらうフック）。

GitHub・Hugging Face のファイルのページのリンク（…/blob/…）は HTML なので、そのままでは描けない。生のファイルの
URL（raw.githubusercontent.com・…/resolve/…）に直す。CLI（janction-render preview <リンク>）と受付の /go のページが使う。
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

# 受付が受ける拡張子（/v1/health の features.inputs と同じ）
SCENE_EXTS = (".blend", ".py", ".glb", ".gltf", ".fbx", ".obj", ".usd", ".usda", ".usdc", ".usdz", ".stl", ".ply", ".abc")
MAX_URL = 1000

_GITHUB_BLOB = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/(?:blob|raw)/(.+)$")
_HF_BLOB = re.compile(r"^https://huggingface\.co/(.+?)/blob/(.+)$")


def is_link(s: str) -> bool:
    return str(s or "").strip().lower().startswith(("https://", "http://"))


def raw_url(url: str) -> str:
    """ファイルのページのリンクを、生のファイルの URL に直す。直す必要が無ければそのまま。"""
    u = str(url or "").strip()
    m = _GITHUB_BLOB.match(u)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    m = _HF_BLOB.match(u)
    if m:
        return f"https://huggingface.co/{m.group(1)}/resolve/{m.group(2)}"
    return u


def scene_link(url: str) -> Optional[str]:
    """描けるシーンのリンクなら生のファイルの URL を、違えば None。https・長さ・拡張子を見る（中身は受付が取りに行くときに見る）。"""
    u = raw_url(url)
    if not u.lower().startswith("https://") or len(u) > MAX_URL or any(c in u for c in "\r\n\t <>\"'`"):
        return None
    path = urlparse(u).path.lower()
    return u if path.endswith(SCENE_EXTS) else None
