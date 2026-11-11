"""シーンのリンク（10/10、ほかの AI に呼んでもらうフック）。

GitHub・Hugging Face のファイルのページのリンク（…/blob/…）は HTML なので、そのままでは描けない。生のファイルの
URL（raw.githubusercontent.com・…/resolve/…）に直す。CLI（janction-render preview <リンク>）と受付の /go のページが使う。
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote, urlparse

# 受付が受ける拡張子（/v1/health の features.inputs と同じ）
SCENE_EXTS = (".blend", ".py", ".glb", ".gltf", ".fbx", ".obj", ".usd", ".usda", ".usdc", ".usdz", ".stl", ".ply", ".abc", ".spz")
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


# 11/10 監査: シーンのリンクに要らず、シェル（sh・PowerShell・cmd）が読む文字。/go はリンクをコマンドの 1 行に入れて見せるので断る
SHELL_CHARS = frozenset("$;|(){}!^\\*`")
_BAD_CHARS = frozenset("\r\n\t <>\"'") | SHELL_CHARS


def _ascii(u: str) -> str:
    """ASCII の外の文字（PowerShell が引用符と読む “ ” など）は %XX に直す。"""
    return "".join(c if 32 < ord(c) < 127 else quote(c, safe="") for c in u)


def scene_link(url: str) -> Optional[str]:
    """描けるシーンのリンクなら生のファイルの URL を、違えば None。https・長さ・拡張子・文字を見る（中身は受付が取りに行くときに見る）。"""
    u = raw_url(url)
    if any(c in _BAD_CHARS or ord(c) < 32 or ord(c) == 127 for c in u):
        return None
    u = _ascii(u)
    if not u.lower().startswith("https://") or len(u) > MAX_URL:
        return None
    path = urlparse(u).path.lower()
    return u if path.endswith(SCENE_EXTS) else None


def shell_quote(u: str) -> str:
    """見せるコマンドの 1 行に入れるリンク（11/10 監査）。scene_link が通したリンクを二重引用符で囲む。
    sh・bash・zsh・PowerShell・cmd のどれでも、残る記号（クエリの & など）は文字のまま渡る。"""
    if any(c in _BAD_CHARS or not 32 < ord(c) < 127 for c in u):
        raise ValueError("not a link that can be shown in a command")
    return f'"{u}"'
