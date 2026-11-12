"""受付を呼ぶ側の共通部分。MCP とコマンドの両方がこれを使う（要件 F-01）。

環境変数:
    JANCTION_RENDER_SERVER   受付の URL（既定 https://render.janction.jp。手元の受付なら http://127.0.0.1:8340）
    JANCTION_RENDER_API_KEY  API キー。無ければ受付に一時キーをもらい ~/.janction-render.json に覚える
"""
from __future__ import annotations

import hashlib
import json
import re
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from urllib.parse import urlsplit

DEFAULT_SERVER = "https://render.janction.jp"   # 10/7 夜: 既定を公開サービスに（uvx で入れた人がそのまま使える）。手元の受付は JANCTION_RENDER_SERVER=http://127.0.0.1:8340
LOCAL_SERVER = "http://127.0.0.1:8340"
CACHE = Path.home() / ".janction-render.json"

# 送れるシーン: .blend、bpy スクリプト、こちらの Blender が読み込める 3D ファイル
SCENE_SUFFIXES = (".blend", ".py", ".fbx", ".glb", ".gltf", ".obj", ".stl", ".ply", ".usd", ".usda", ".usdc", ".usdz", ".abc", ".spz")
ONLY_CHOICES = ("all", "mp4", "frames", "sheet", "output", "video", "blend")
ARCHIVE_MIN_FILES = 8   # これ以上の数のファイルは zip で 1 回で取る（1 枚ずつだと入口の回数制限 429 に当たる、10/9）
# zip は約 1 GiB ずつの区切りで取る（10/14 受け取り側の 5 GB 試験: 1 本の zip は途中から取り直せず、切れると全部を 1 枚ずつ取り直していた）
ARCHIVE_PART_BYTES = 1 << 30
DOWNLOAD_TRIES = 3
# 公開の受付（render.janction.jp）の前に立つ Cloudflare は、1 回の送信を 100 MB までしか通さない（無料プラン）。超えると受付に
# 届かず HTML の 413 になるので、送る前に断ってリンク（scene_url / asset_urls）で渡すよう言う。素材は 100 MB ずつに分けて送る
# （10/12）。手元や自前の受付には掛けない。JANCTION_RENDER_MAX_UPLOAD_MB で変えられる（0 で見ない）
EDGE_UPLOAD_MB = 100
# この大きさを超えるシーンは分けて送る（10/13）。Cloudflare の 100 MB が 10^8 バイトなら 95.4 MiB から先は 1 回では通らない
RESUMABLE_ABOVE = 64 * 1024 * 1024


ASSET_LINK_MAX_BYTES = 128 * 1024 * 1024   # 受付の素材 1 つの上限（JR_MAX_ASSET_MB の既定値。リンクで渡しても同じ）
# 1 回の素材の送信に入れるファイルの数（11/9）。連番・キャッシュは小さいファイルが数百〜数千あり、全部を 1 回にすると受付の
# multipart の上限（1000 ファイル）に当たる
ASSET_BATCH_FILES = 100
# 受付の素材の型（server/core.py ASSET_EXTENSIONS の写し）と、旗 JR_PRO_ASSETS の受付だけが受ける型（server/pro_assets.py）。
# 旗の無い受付は 400 unsupported を返すので、新しい型は別に送り、断られたら missing_assets に理由を書いて描画は続ける
BASE_ASSET_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".exr", ".hdr", ".tif", ".tiff", ".webp", ".bmp", ".tga",
                                   ".bin", ".mtl", ".fbx", ".glb", ".gltf", ".obj", ".usd", ".usda", ".usdc", ".usdz",
                                   ".abc", ".mp4", ".mov", ".json", ".txt", ".csv", ".ttf", ".otf"})
PRO_ASSET_EXTENSIONS = frozenset({".vdb", ".bphys", ".blob", ".uni", ".gz", ".avi", ".mkv", ".webm"})
# 旗 JR_LINKED_BLEND の受付だけが受ける型（リンクした .blend、11/9 夜、server/linked_blend.py）。旗の無い受付は 400 unsupported
LIBRARY_ASSET_EXTENSIONS = frozenset({".blend"})
LIBRARY_FILES_MAX = 500      # リンクした .blend 1 つが読むファイルとして送る数の上限（材質の大きなライブラリで送りすぎない）
_ASSET_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}(/[A-Za-z0-9_.\-]{1,120}){0,4}$")
# ワーカーは .blend を scene.blend として開くので、既定の点のキャッシュ（//blendcache_<名前>/）は blendcache_scene/ で送る
WORKER_SCENE_STEM = "scene"
SEQUENCE_FILES_MAX = 5000
_FRAME_NAME_RE = re.compile(r"^(part-\d+_)?frame_")


PART_SECONDS = 60.0          # 1 つの部分が送り終わるまでの目安（途中の入口が 100 秒あまりで切るので、その内側）
PART_MIN = 1024 * 1024


def _fit_part(part: int, moved: int, seconds: float, cut: bool = False) -> int:
    """遅い回線では部分を小さくする（10/14）。送れた量と秒から、PART_SECONDS で送り終わる大きさ（256 KiB 単位、1 MiB 以上、今以下）。
    切れた（cut）か 90 秒を超えたときだけ縮める。速い回線では今の大きさのまま。"""
    if moved <= 0 or not (cut or seconds > 90):
        return part
    fit = int(moved / max(seconds, 0.001) * PART_SECONDS) // (256 * 1024) * (256 * 1024)
    return max(PART_MIN, min(part, fit))


def _have(dest: Path, a: dict[str, Any]) -> bool:
    """dest にもう同じ大きさのファイルがあるか（大きさの分からない古い受付では、無いものとして取り直す）。"""
    n = a.get("size")
    try:
        return n is not None and dest.is_file() and dest.stat().st_size == int(n)
    except (OSError, ValueError):
        return False


def select_artifacts(artifacts: list[dict[str, Any]], only: Optional[str] = None) -> list[dict[str, Any]]:
    """成果物の絞り込み: all / mp4（output.mp4 だけ）/ frames（PNG のコマだけ）/ sheet（4 コマ並べだけ）/ output（mp4 か sheet）。"""
    o = (only or "all").strip().lower()
    if o in ("", "all"):
        return list(artifacts)
    if o in ("mp4", "video"):
        videos = [a for a in artifacts if a["name"].endswith((".mp4", ".webm", ".mov"))]
        # 部分に分けた仕上げ（b_…）は、部分ごとの動画（part-01_output.mp4 …）とつないだ 1 本（output.mp4）が並ぶ。1 本を返す
        whole = [a for a in videos if a["name"] in ("output.mp4", "output.webm", "output.mov")]
        return whole or videos
    if o == "frames":
        # 部分に分けた仕上げのコマは part-01_frame_0001.png の名前（10/13）
        return [a for a in artifacts if _FRAME_NAME_RE.match(a["name"])]
    if o == "sheet":
        return [a for a in artifacts if a["name"] == "sheet.png"]
    if o == "blend":
        return [a for a in artifacts if a["name"] == "scene.blend"]
    if o == "output":
        picked = [a for a in artifacts if a["name"] in ("output.mp4", "output.webm", "output.mov", "sheet.png", "scene.blend")]
        return picked or [a for a in artifacts if _FRAME_NAME_RE.match(a["name"])][:1]
    raise ValueError("only must be one of: " + ", ".join(ONLY_CHOICES))


def ref_problem(ref: str) -> Optional[str]:
    """3D ファイルの中の外部参照 1 本が「シーンのフォルダの中の相対パス」かを見る。良ければ None、悪ければ理由。
    data: URI（中身が埋め込み）は良い。読み込み側（glTF は unquote してから開く）と同じに、%xx を戻し、\\ を / にしてから見る。"""
    import re as _re
    from urllib.parse import unquote

    s = (ref or "").strip()
    if not s or s[:5].lower() == "data:":
        return None
    for _ in range(4):
        d = unquote(s)
        if d == s:
            break
        s = d
    if any(ord(c) < 32 or ord(c) == 127 for c in s):
        return "control characters in a file path"
    s = s.replace("\\", "/")
    if _re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", s):
        return "URLs and drive letters are not accepted; refer to files by a relative name"
    if s.startswith("/"):
        return "absolute paths are not accepted; refer to files by a relative name"
    if ".." in s.split("/"):
        return "paths may not go above the scene's folder (..)"
    return None


# ------------------------------------------------------------------ glTF の JSON を読む守り（11/10 監査）
# json.loads は "[]," の並びのような形で元の約 20 倍のメモリを使う（6 MB が 129 MB）。受付の箱は 2 GB なので、100 MB の .gltf で
# 落ちていた。読む前に、文字の数から読んだあとの大きさを多めに見積もり、上限を超えるものは読まずに断る。data: の URI（埋め込みの
# 中身）は参照の検査には要らないので、空にしてから読める（blank_data_uris）。深すぎる入れ子も断る（GltfJsonRefused、ValueError の仲間）。
# 受付（refcheck・gltf_fix・importstats）とこの手元の道具が同じものを使う。

class RefScanRefused(ValueError):
    """参照の検査に回せないファイル（11/10 監査）。文は利用者にそのまま返してよい（何が問題で、どう直すか）。"""


class GltfJsonRefused(RefScanRefused):
    """glTF の JSON を読まずに断った（大きすぎる・入れ子が深すぎる・ほかの大きいものを読んでいて待ちきれない）。"""


import threading as _threading  # noqa: E402

REFS_MAX = 20000            # 1 つのファイルの外部参照の数の上限（ふつうは数十、多くても数千）
GLTF_DEPTH_MAX = 128        # 入れ子の深さの上限（glTF の実物は 10 前後）
_DATA_URI_RE = re.compile(r'"data:[^"\\]*+(?:\\.[^"\\]*+)*+"', re.S)
_json_budget_lock = _threading.Condition()   # 同時に読んでいる見積もりの合計（受付のスレッドが並んで大きいものを読まないように）
_json_inflight = 0


def gltf_json_max_bytes() -> int:
    """glTF の JSON を読むときのメモリの見積もりの上限（JR_GLTF_JSON_MAX_MB、既定 768）。プロセスの中で同時に読む分の合計も同じ上限。
    11/4 の 502 MB の GLB（JSON 53 MB、ノード 8 万）が見積もりで 600 MB ほど。"""
    try:
        mb = int(os.environ.get("JR_GLTF_JSON_MAX_MB") or 768)
    except ValueError:
        mb = 768
    return max(16, mb) * 1024 * 1024


def gltf_json_cost(text: str) -> int:
    """json.loads のあとのメモリの見積もり（バイト）。入れ物・値・キー・文字列の数を文字の数から数える（C の速さ）。
    係数は Python 3.12 で形ごと（空の [] や {} の並び・大きい整数・重ならないキーなど）に測った実際の量を下回らないように決めた。
    文字列の中の記号も数えるので、ふつうの glTF では実際の 2 倍ほどに出る（断る側に倒れる）。"""
    lists, dicts = text.count("["), text.count("{")
    values = text.count(",") + lists + dicts + 1
    return len(text) + 48 * lists + 64 * dicts + 40 * values + 96 * text.count(":") + 24 * (text.count('"') // 2)


def _json_reserve(cost: int, wait_s: float) -> None:
    global _json_inflight
    cap = gltf_json_max_bytes()
    deadline = time.monotonic() + wait_s
    with _json_budget_lock:
        while _json_inflight and _json_inflight + cost > cap:
            left = deadline - time.monotonic()
            if left <= 0:
                raise GltfJsonRefused("other large glTF files are being checked right now; send this file again in a minute")
            _json_budget_lock.wait(left)
        _json_inflight += cost


def _json_release(cost: int) -> None:
    global _json_inflight
    with _json_budget_lock:
        _json_inflight = max(0, _json_inflight - cost)
        _json_budget_lock.notify_all()


def load_gltf_json(text: str, *, blank_data_uris: bool = False, wait_s: float = 30.0) -> Any:
    """glTF の JSON を、メモリの見積もりが上限に収まるときだけ読む。断るときは GltfJsonRefused、壊れた JSON は json の ValueError。
    blank_data_uris=True は data: の URI の中身を空にしてから読む（参照を見るだけのとき）。"""
    import json as _json

    if text[:1] == "﻿":
        text = text[1:]                     # 頭の BOM（Blender は読める。json.loads は str の BOM を断る）
    if blank_data_uris and '"data:' in text:
        text = _DATA_URI_RE.sub('"data:"', text)
    cost = gltf_json_cost(text)
    cap = gltf_json_max_bytes()
    if cost > cap:
        raise GltfJsonRefused(f"the glTF JSON is too large or has too many entries to check (about {cost // (1024 * 1024)} MB once "
                              f"read, the limit is {cap // (1024 * 1024)} MB); export it as .glb with the mesh data in the "
                              "binary chunk, or split the scene")
    _json_reserve(cost, wait_s)
    try:
        return _json.loads(text)
    except RecursionError:
        raise GltfJsonRefused("the glTF JSON is nested too deeply to read; export the file again") from None
    except MemoryError:
        raise GltfJsonRefused("the glTF JSON is too large to read; export it as .glb, or split the scene") from None
    finally:
        _json_release(cost)


def _gltf_uris(doc: Any, strict: bool) -> list[str]:
    """文書の順に uri の文字列を全部（buffers / images の uri が本筋。拡張の中の uri も同じに扱う）。再帰しない（深い入れ子で落ちない）。"""
    out: list[str] = []
    ref = object()
    stack: list[tuple[Any, Any]] = [(doc, 0)]
    while stack:
        o, depth = stack.pop()
        if depth is ref:
            out.append(o)
            if len(out) > REFS_MAX:
                if strict:
                    raise RefScanRefused(f"the file refers to more than {REFS_MAX:,} other files; merge buffers and textures")
                return out[:REFS_MAX]
            continue
        if depth > GLTF_DEPTH_MAX:
            if strict:
                raise GltfJsonRefused(f"the glTF JSON is nested more than {GLTF_DEPTH_MAX} levels deep; export the file again")
            continue
        if isinstance(o, dict):
            for k, v in reversed(list(o.items())):
                stack.append((v, ref) if k == "uri" and isinstance(v, str) else (v, depth + 1))
        elif isinstance(o, list):
            stack.extend((v, depth + 1) for v in reversed(o))
    return out


def _raw_refs(kind: str, text: str, strict: bool = False) -> list[str]:
    """glTF（JSON）・OBJ（mtllib）・MTL（map_*）・USDA（@...@）に書かれた外部参照を、良し悪しを見ずに全部。
    strict=True（受付の検査）は、大きすぎる・入れ子が深すぎる・参照が多すぎるファイルを RefScanRefused で断る。False（手元の道具）は
    読めなければ空、多すぎれば先頭の REFS_MAX 本。JSON として壊れたものはどちらも今までどおり空（読み込む側の Blender も同じ
    json で読むので、外を指す参照は届かない。読み込みの段で失敗として返る）。"""
    import re as _re

    out: list[str] = []
    if kind == "gltf":
        try:
            doc = load_gltf_json(text, blank_data_uris=True)
        except RefScanRefused:
            if strict:
                raise
            return out
        except ValueError:
            return out
        return _gltf_uris(doc, strict)
    if kind == "obj":
        for line in text.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "mtllib":
                out.extend(parts[1].split())
    elif kind == "mtl":
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0].lower() in ("map_kd", "map_ks", "map_ka", "map_ns", "map_d", "map_bump", "bump",
                                                        "disp", "decal", "norm", "map_ke", "refl"):
                out.append(parts[-1])
    elif kind == "usda":
        for m in _re.finditer(r"@@@(.+?)@@@|@([^@\r\n]+)@", text):
            out.append(m.group(1) or m.group(2))
            if len(out) > REFS_MAX:
                break
    if len(out) > REFS_MAX:
        if strict:
            raise RefScanRefused(f"the file refers to more than {REFS_MAX:,} other files; merge them or pack them into one file")
        del out[REFS_MAX:]
    return out


def companion_refs(kind: str, text: str, strict: bool = False) -> list[str]:
    """glTF（JSON）か OBJ の中で参照している外部ファイルの相対パス（data: URI とフォルダの外を指すものは除く）。
    OBJ は mtllib の .mtl だけを返す（.mtl の中の画像は kind="mtl" で）。重なりは集合で除く（11/10 監査: 一覧で探すと 2 乗だった）。"""
    out: list[str] = []
    if kind not in ("gltf", "obj", "mtl"):
        return out
    seen: set[str] = set()
    for ref in _raw_refs(kind, text, strict):
        ref = (ref or "").strip().replace("\\", "/")
        if not ref or ref in seen or ref[:5].lower() == "data:" or ref_problem(ref):
            continue
        seen.add(ref)
        out.append(ref)
    return out


def unsafe_refs(kind: str, text: str, strict: bool = False) -> list[tuple[str, str]]:
    """フォルダの外・絶対パス・URL などを指す参照の [(参照, 理由)]。受付とワーカーが読み込みの前に弾く。
    受付は strict=True（読めないものは RefScanRefused）。重なりは集合で除く（11/10 監査）。"""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for ref in _raw_refs(kind, text, strict):
        if ref in seen:
            continue
        seen.add(ref)
        why = ref_problem(ref)
        if why:
            out.append((ref, why))
    return out


def companion_kind(name: str) -> str:
    ext = Path(name).suffix.lower()
    return {".gltf": "gltf", ".obj": "obj", ".mtl": "mtl", ".usda": "usda"}.get(ext, "")


def sha256_of(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_pro_asset(name: str) -> bool:
    """旗 JR_PRO_ASSETS の受付だけが受ける型か（.vdb・.bphys・.blob・.uni・.bobj.gz・.avi など）。"""
    ext = Path(name).suffix.lower()
    return ext in PRO_ASSET_EXTENSIONS and ext not in BASE_ASSET_EXTENSIONS


def is_library_asset(name: str) -> bool:
    """旗 JR_LINKED_BLEND の受付だけが受ける型（リンクした .blend）か。"""
    return Path(name).suffix.lower() in LIBRARY_ASSET_EXTENSIONS


def asset_name_problem(name: str) -> Optional[str]:
    """受付が受けない名前・型なら理由（送らずに missing に入れる。送ると 400 で全体が止まる）。"""
    ext = Path(name).suffix.lower()
    if not _ASSET_NAME_RE.match(name) or ".." in name.split("/"):
        return "the name has characters the service does not take (letters, digits, . _ - and up to 4 folders)"
    if ext == ".gz" and not name.lower().endswith(".bobj.gz"):
        return ".gz files other than fluid meshes (.bobj.gz) are not accepted"
    if ext not in BASE_ASSET_EXTENSIONS and ext not in PRO_ASSET_EXTENSIONS:
        return f"{ext or 'no extension'} files are not accepted; pack it into the .blend"
    return None


def _sequence_files(p: Path) -> list[Path]:
    """blender-asset-tracer の連番（最初のコマ・* のパターン・フォルダ）を実際のファイルに（11/9）。"""
    try:
        from blender_asset_tracer.trace import file_sequence  # type: ignore
        out = []
        for f in file_sequence.expand_sequence(p):
            out.append(Path(f))
            if len(out) >= SEQUENCE_FILES_MAX:
                break
        return [f for f in out if f.is_file()]
    except Exception:  # noqa: BLE001 — 無い・展開できない
        return []


def trace_blend_assets(blend: Path, asset_roots: Any = ()) -> tuple[list[tuple[str, Path]], list[str]]:
    """trace_blend の素材と見つからなかった物だけ（リンクした .blend の付け替えの組は返さない。11/9 夜より前の形）。"""
    found, missing, _map = trace_blend(blend, asset_roots)
    return found, missing


def _norm(p: Any) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def _under(path: Any, folder: Any) -> bool:
    a, b = _norm(path), _norm(folder)
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def _mount_of(p: Path) -> Path:
    """p を含むいちばん深いマウント（ドライブ・UNC の共有・/mnt/nas や /Volumes/NAS など）。"""
    q = Path(os.path.abspath(str(p)))
    while not os.path.ismount(str(q)) and q.parent != q:
        q = q.parent
    return q


def asset_root_list(asset_roots: Any) -> tuple[list[Path], list[str]]:
    """--asset-root / asset_roots のフォルダ（絶対の道に直す）と、使わなかった物の理由。無いフォルダ・ドライブや共有の
    まるごと・ファイルシステムの根は広すぎるので使わない（アドオンの Asset folders と同じ決まり）。"""
    roots: list[Path] = []
    notes: list[str] = []
    for r in asset_roots or ():
        raw = str(r or "").strip().strip('"')
        if not raw:
            continue
        q = Path(os.path.abspath(os.path.expanduser(raw)))
        if not q.is_dir():
            notes.append(f"--asset-root {raw} (not a folder on this computer)")
        elif os.path.ismount(str(q)) or q.parent == q:
            notes.append(f"--asset-root {raw} (a whole drive or share is too wide; name the project folders)")
        else:
            roots.append(q)
    return roots, notes


def outside_problem(path: Any, base: Path, roots: list[Path]) -> Optional[str]:
    """.blend のフォルダ（base）の外のファイルを送ってよいか（11/9 夜、アドオンと同じ安全側）。よければ None、だめなら
    missing_assets に書く理由。外の物は利用者が --asset-root（asset_roots）で書いたフォルダの下だけ。ネットワークの共有や別の
    マウントの上の物は、その共有・マウントの中のフォルダを書いたときだけ（上のフォルダを書いても共有の中までは広げない）。"""
    if _under(path, base):
        return None
    parent = Path(os.path.abspath(str(path))).parent
    mount = _mount_of(Path(path))
    for root in roots:
        if _under(path, root) and _under(root, mount):
            return None
    return f"outside the .blend folder, so it was not sent; send it with --asset-root {parent}"


def _container(usage: Any) -> Optional[Path]:
    """BAT の使い方の行が書かれている .blend（シーンか、リンクした .blend）。分からなければ None。"""
    fp = getattr(getattr(getattr(usage, "block", None), "bfile", None), "filepath", None)
    return Path(fp) if fp else None


def trace_blend(blend: Path, asset_roots: Any = ()) -> tuple[list[tuple[str, Path]], list[str], Optional[dict[str, Any]]]:
    """.blend が参照する外部ファイル（画像・ライブラリなど）を手元で調べる（blender-asset-tracer があるとき）。

    返すのは ([(送るときの名前, 場所)], [見つからなかったパス])。名前は .blend からの相対パス（//textures/a.png → textures/a.png）。
    .blend の外（上の階層や絶対パス）にあるものは送れないので「見つからなかった」に入れる。
    11/9: 連番（画像・VDB）・焼いたキャッシュ（点のキャッシュ・ジオメトリノードのベイク・流体）も、あるファイルを全部送る
    （Blender のアドオンと同じ決まり。手元の Blender が無いので、使うコマだけには絞らない）。既定の点のキャッシュ
    //blendcache_<名前>/ はワーカーの名前 blendcache_scene/ で送る。受付が受けない名前・型は送らずに理由を書く。
    11/9 夜（受付の旗 JR_LINKED_BLEND）: リンクした .blend（入れ子も。BAT はライブラリの中までたどる）と、その中の画像などは
    libplan（アドオンと同じファイル）で置く。.blend のフォルダの中は相対の名前のまま、外は lib/<フォルダの hash>/ に。置いた場所で
    解けないライブラリの道は付け替えの組にして 3 つ目に返す（jr_libraries.json の中身。無ければ None）。
    .blend のフォルダの外のライブラリとその中の物は、asset_roots（CLI の --asset-root）に書いたフォルダの下だけ送る（アドオンの
    Asset folders と同じ安全側。ネットワークの共有は、その共有の中のフォルダを書いたときだけ）。送らなかった物は理由を書く。
    """
    try:
        from blender_asset_tracer import trace  # type: ignore
    except Exception:  # noqa: BLE001 — 入っていなければ調べない（受付の scene_info が GPU 側で知らせる）
        return [], [], None
    found: list[tuple[str, Path]] = []
    missing: list[str] = []
    seen: set[str] = set()
    names: set[str] = set()
    blend = Path(blend).resolve()
    base = blend.parent
    cache_dir = f"blendcache_{blend.stem}/"

    def take(p: Path, shown: str, point_cache: bool = False) -> None:
        try:
            rel = p.resolve().relative_to(base).as_posix()
        except ValueError:
            missing.append(f"{shown} (outside the .blend folder; cannot be sent)")
            return
        if point_cache and rel.startswith(cache_dir):
            # 既定の点のキャッシュだけ（Blender が .blend の名前から道を作る）。ジオメトリノードのベイクの道は .blend に
            # そのまま書いてあるので名前を変えない
            rel = f"blendcache_{WORKER_SCENE_STEM}/" + rel[len(cache_dir):]
        why = asset_name_problem(rel)
        if why:
            missing.append(f"{rel} ({why})")
            return
        if rel not in names:
            names.add(rel)
            found.append((rel, p))

    libs: list[tuple[Path, str, Optional[Path]]] = []     # (ライブラリ, 親に書かれた道, 親の .blend。None はシーン)
    owned: list[tuple[Any, Path]] = []                    # (使い方の行, それを持つリンクした .blend)
    scene_key = os.path.normcase(str(blend))
    try:
        for usage in trace.deps(blend):
            try:
                p = Path(usage.abspath)
            except Exception:  # noqa: BLE001
                continue
            box = _container(usage)
            in_lib = box is not None and os.path.normcase(str(Path(box).resolve())) != scene_key
            if getattr(getattr(usage, "block", None), "code", b"") == b"LI":
                libs.append((p, str(usage.asset_path), Path(box).resolve() if in_lib else None))
                continue
            if in_lib:
                owned.append((usage, Path(box).resolve()))
                continue
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            if usage.is_sequence:
                files = _sequence_files(p)
                if not files:
                    missing.append(f"{usage.asset_path} (no files of this sequence or cache were found)")
                # blender-asset-tracer は既定の点のキャッシュを //blendcache_<名前>/<名前>_*.bphys のパターンで返す
                shown = str(usage.asset_path)
                pc = shown.startswith(f"//{cache_dir}") and "*" in shown and shown.endswith(".bphys")
                for f in files:
                    take(f, shown, point_cache=pc)
                continue
            if not p.exists():
                missing.append(str(usage.asset_path))
                continue
            take(p, str(usage.asset_path))
    except Exception as exc:  # noqa: BLE001
        if "zstandard" in str(exc).lower() or "zstd" in str(exc).lower():
            # Blender 4.x 以降の圧縮 .blend は zstandard が無いと読めない（黙って素材なしで送っていた）
            missing.append("textures and caches could not be listed: this .blend is compressed; "
                           "pip install 'janction-render[blend]' (it brings zstandard)")
        return found, missing, None
    if not libs:
        return found, missing, None
    roots, notes = asset_root_list(asset_roots)
    missing += notes
    refused: set[str] = set()

    def allowed(path: Path, shown: str) -> bool:
        why = outside_problem(path, base, roots)
        if why is None:
            return True
        if _norm(path) not in refused:
            refused.add(_norm(path))
            missing.append(f"{shown} ({why})")
        return False
    # 送る親から順に、フォルダの決まりで送れるライブラリだけ（送れない親の中の物は数えない。親の理由が出る）
    # 手元に無いライブラリは libplan が「見つからない」と言う（フォルダの話にしない）
    sendable: set[str] = set()
    for _ in range(len(libs) + 1):
        grew = False
        for lp, ref, parent in libs:
            if _norm(lp) in sendable or (parent is not None and _norm(parent) not in sendable):
                continue
            if not lp.is_file() or allowed(lp, ref):
                sendable.add(_norm(lp))
                grew = True
        if not grew:
            break
    libs = [x for x in libs if _norm(x[0]) in sendable and (x[2] is None or _norm(x[2]) in sendable)]
    owned = [(u, b) for u, b in owned if _norm(b) in sendable]
    # BAT はリンクしたコレクションの中の物から先（材質の画像など）をたどらないことがある（Blender 5.2 の .blend で、コレクションを
    # リンクしたシーンからライブラリの画像が出なかった）。ライブラリの .blend をそれぞれ調べ直して、そのファイルが読む物を足す
    seen_owned = {(os.path.normcase(str(b)), os.path.normcase(str(u.abspath))) for u, b in owned}
    for lib in sorted({lp.resolve() for lp, _r, _par in libs if lp.is_file() and _norm(lp.resolve()) in sendable}):
        added = 0
        try:
            for usage in trace.deps(lib):
                box = _container(usage)
                if box is None or os.path.normcase(str(Path(box).resolve())) != os.path.normcase(str(lib)):
                    continue
                if getattr(getattr(usage, "block", None), "code", b"") == b"LI":
                    continue
                key = (os.path.normcase(str(lib)), os.path.normcase(str(usage.abspath)))
                if key in seen_owned:
                    continue
                seen_owned.add(key)
                owned.append((usage, lib))
                added += 1
                if added >= LIBRARY_FILES_MAX:
                    missing.append(f"{lib.name} (this linked .blend uses more than {LIBRARY_FILES_MAX} files; only the first "
                                   f"{LIBRARY_FILES_MAX} are sent: pack its textures into it in Blender)")
                    break
        except Exception:  # noqa: BLE001 — 調べられなくても、BAT が最初に返した分は送る
            missing.append(f"{lib.name} (the files this linked .blend uses could not be listed)")
    from . import libplan
    plan = libplan.Plan(str(blend), sha_of=lambda x: sha256_of(Path(x)))
    for lp, ref, parent in libs:
        plan.add_library(str(lp), ref, str(parent) if parent is not None else None)
    for usage, box in owned:
        ref = str(usage.asset_path)
        files = _sequence_files(Path(usage.abspath)) if usage.is_sequence else [Path(usage.abspath)]
        if usage.is_sequence and not files:
            missing.append(f"{ref} (inside a linked .blend: no files of this sequence or cache were found)")
        files = [f for f in files if allowed(f, ref)]
        for f in files:
            fref = ref
            if usage.is_sequence and ref.startswith("//"):
                try:
                    fref = "//" + os.path.relpath(f, box.parent).replace("\\", "/")
                except ValueError:
                    fref = str(f)
            plan.add_dependency(str(f), fref, str(box))
    plan.solve()
    for name, ap in plan.files:
        why = None if is_library_asset(name) else asset_name_problem(name)
        if why:
            missing.append(f"{name} ({why})")
        elif name not in names:
            names.add(name)
            found.append((name, Path(ap)))
    for path, why in plan.problems:
        missing.append(f"{path} ({why})" if path else why)
    return found, missing, plan.map_document()


def parse_frames(spec: str, default: int = 1, count: int = 4) -> list[int]:
    """試し描きのコマの指定を配列にする。

    '1,8,16,24' → そのまま／'1-24' → 両端を含む count コマを等間隔で／'12' → [12]／'' → [default]
    """
    s = (spec or "").strip()
    if not s:
        return [int(default)]
    if "," in s:
        vals = [int(x) for x in s.split(",") if x.strip()]
    elif "-" in s:
        a, b = s.split("-", 1)
        a, b = int(a), int(b)
        if b < a:
            raise ValueError("frames: end must be >= start")
        n = min(count, b - a + 1)
        vals = [a + round(i * (b - a) / (n - 1)) for i in range(n)] if n > 1 else [a]
    else:
        vals = [int(s)]
    out: list[int] = []
    for v in vals:
        if v < 0:
            raise ValueError("frames must be >= 0")
        if v not in out:
            out.append(v)
    return out


class ClientError(RuntimeError):
    def __init__(self, status: int, error: str, detail: str, extra: Optional[dict[str, Any]] = None):
        super().__init__(f"{error}: {detail}" if detail else error)
        self.status = status
        self.error = error
        self.detail = detail
        self.extra = extra or {}   # 402 のときは checkout_url / needed_yen / balance_yen など

    def agent_fields(self) -> dict[str, Any]:
        """受付が返した code / retryable / recommended_action / possible_fix（10/11）。古い受付や受付に届かないときは
        状態コードから決める（5xx と届かない = INTERNAL_ERROR か WORKERS_UNAVAILABLE、待って再送）。"""
        x = self.extra or {}
        out = {k: x[k] for k in ("code", "retryable", "recommended_action", "possible_fix", "retry_after_s", "resets_at_iso")
               if x.get(k) is not None}
        if "code" not in out:
            if self.error == "network_blocked":   # 11/2: 箱のプロキシが断った。待っても通らないので、道を替える
                out.update({"code": "NETWORK_BLOCKED", "retryable": False, "recommended_action": "SWITCH_ROUTE",
                            "possible_fix": x.get("hint")})
            elif self.error == "server_unreachable" or self.status >= 500:
                out.update({"code": "WORKERS_UNAVAILABLE" if self.error == "server_unreachable" else "INTERNAL_ERROR",
                            "retryable": True, "recommended_action": "WAIT_AND_RETRY"})
            else:
                out.update({"code": re.sub(r"[^A-Z0-9_]", "_", (self.error or "error").upper())[:40],
                            "retryable": self.status == 429, "recommended_action": "READ_DETAIL"})
        return out

    def payment(self) -> Optional[dict[str, Any]]:
        """残高不足（402）なら、決済ページのリンクなどをまとめて返す。"""
        if self.status != 402:
            return None
        out = {"payment_required": True, "detail": self.detail, "code": "INSUFFICIENT_CREDIT", "retryable": False,
               "recommended_action": "TOP_UP",
               **{k: self.extra.get(k) for k in ("needed_yen", "balance_yen", "topup_yen", "checkout_url",
                                                 "session_id", "yen_per_gpu_second", "how")}}
        for k in ("tell_user", "this_job_yen", "renders_per_topup"):   # 人間に伝える 1 文と、成果物の単位の値段（0.4.39）
            if self.extra.get(k) is not None:
                out[k] = self.extra[k]
        # ようこそクレジット（docs/46）の受付なら付いてくる。card_offer はカード登録（0 円）で無料の GPU 時間が足される鍵の案内、
        # topup_options はチャージの選択肢（docs/62 P0-1: REST の 402 と同じものを AI に渡す）
        # resume: 402 で預かった注文（o_…）。払うとその仕事が自動で始まり、render_status(o_…) で追える（10/14）
        for k in ("welcome", "first_topup_bonus", "card_offer", "topup_options", "topup_credit_yen", "resume"):
            if self.extra.get(k):
                out[k] = self.extra[k]
        if self.extra.get("accepts"):
            # x402（USDC）でも払える受付。対応しているエージェントは accepts から X-PAYMENT を組む
            out["x402"] = {"x402Version": self.extra.get("x402Version"), "accepts": self.extra["accepts"],
                           "how": self.extra.get("how_x402")}
        return out


class _Session(requests.Session):
    """受付に届かない（接続拒否・名前解決・タイムアウト）を ClientError(server_unreachable) にそろえる。

    MCP の道具とコマンドは ClientError だけを拾うので、これが無いと requests の例外がそのまま上がり、
    利用者には原因の無い「Error executing tool」しか見えない（2026-10-06、向き先が既定のローカルのままで発覚）。
    """

    def __init__(self, server: str) -> None:
        super().__init__()
        self._server = server

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        try:
            return super().request(method, url, *args, **kwargs)
        except requests.RequestException as exc:
            raise unreachable_error(self._server, url, exc) from exc

    def rebuild_auth(self, prepared_request: Any, response: Any) -> None:
        """転送（3xx）で受付の外へ行くときは、鍵（X-API-Key）を付けて行かない（11/10 監査。requests が外すのは Authorization だけ）。"""
        super().rebuild_auth(prepared_request, response)
        if not same_origin(prepared_request.url, self._server):
            prepared_request.headers.pop("X-API-Key", None)


CLOUD_SANDBOX_GUIDE = f"{DEFAULT_SERVER}/claude-code-blender#cloud-sessions"


def network_blocked(exc: BaseException) -> bool:
    """この環境のプロキシが宛先を断った（11/2）。Claude Code の Web 版などのクラウドの箱は、許可リストに無い宛先への CONNECT に
    403 を返す。受付が落ちているのではなく、待っても通らないので、ほかの「届かない」と分ける。"""
    if not isinstance(exc, requests.exceptions.ProxyError):
        return False
    text = str(exc)
    return ("403" in text or "Forbidden" in text or "not allowed" in text.lower()
            or os.environ.get("CLAUDE_CODE_REMOTE") == "true")


def _blocked_hint(host: str) -> str:
    return (f"The request did not leave this environment: its network proxy refused {host} (a sandbox allowlist, "
            "not an outage of the render service), so retrying will not help. "
            "Fix, in this order: (1) if this session has the JANCTION Render tools from a claude.ai connector, use those "
            "instead (they do not go through this proxy; pass a bpy script as scene_script, a file on the web as scene_url). "
            "If it does not, tell the user the one-time setup: on claude.ai, Plugins (older menu: Customize -> Connectors) -> Add custom connector -> "
            f"{DEFAULT_SERVER}/mcp -> Connect (creates a free key); no network setting changes. "
            f"(2) Only for a .blend that exists only in this sandbox: the user allows {host} in the environment's network "
            "settings (Claude Code on the web: Network access -> Custom -> Allowed domains, keeping the defaults; a running "
            "session follows within about a minute), then try once more. "
            f"Steps: {CLOUD_SANDBOX_GUIDE}")


def unreachable_error(server: str, url: str, exc: BaseException) -> ClientError:
    """requests の接続系の例外を、向き先と直し方の付いた ClientError にする。"""
    parts = urlsplit(url)
    target = f"{parts.scheme}://{parts.netloc}" if parts.netloc else server
    if network_blocked(exc):
        host = parts.hostname or urlsplit(server).hostname or server
        hint = _blocked_hint(host)
        return ClientError(0, "network_blocked", f"could not reach {target}: {hint}",
                           extra={"server": server, "url": url, "retryable": False, "hint": hint,
                                  "guide": CLOUD_SANDBOX_GUIDE})
    if isinstance(exc, (requests.exceptions.InvalidURL, requests.exceptions.MissingSchema, requests.exceptions.InvalidSchema)):
        code, hint = "bad_server_url", f"JANCTION_RENDER_SERVER must be an http(s) URL, got {server!r}"
    elif server.rstrip("/") == LOCAL_SERVER:
        code = "server_unreachable"
        hint = ("JANCTION_RENDER_SERVER points at a local dev server that is not running. "
                "Unset it (or set JANCTION_RENDER_SERVER=https://render.janction.jp) to use the public service")
    elif server.rstrip("/") == DEFAULT_SERVER:
        code = "server_unreachable"
        hint = ("could not reach the public service; check your network and the status page https://render.janction.jp/status. "
                "For a local dev server set JANCTION_RENDER_SERVER=http://127.0.0.1:8340")
    else:
        code = "server_unreachable"
        hint = "check the URL and your network; the service status is at https://render.janction.jp/status"
    return ClientError(0, code, f"could not reach {target} ({type(exc).__name__}). {hint}",
                       extra={"server": server, "url": url, "retryable": True, "hint": hint})


class Client:
    def __init__(self, server: Optional[str] = None, api_key: Optional[str] = None, client: str = "") -> None:
        from . import __version__

        self.server = (server or os.environ.get("JANCTION_RENDER_SERVER") or DEFAULT_SERVER).rstrip("/")
        self._key = (api_key or os.environ.get("JANCTION_RENDER_API_KEY") or "").strip() or None
        self.s = _Session(self.server)
        # 受付に名乗る（どの入口から来たかを数える。個人を特定するものは入れない）。
        # JANCTION_RENDER_CLIENT で上書きできる（運営の確認・テストを smoke/… と名乗らせて評価票から外す、10/7）
        self.s.headers["X-Client"] = f"{(os.environ.get('JANCTION_RENDER_CLIENT') or '').strip() or client or 'api'} {__version__}"

    # ---- 鍵 ----------------------------------------------------------------

    def key(self) -> str:
        if self._key:
            return self._key
        cache = self._read_cache()
        cached = cache.get(self.server)
        if cached:
            self._key = cached
            return cached
        r = self.s.post(f"{self.server}/v1/keys", json={"label": self.s.headers.get("X-Client", "auto")}, timeout=15)
        self._raise(r)
        self._key = r.json()["api_key"]
        first = r.json().get("first_render")
        if isinstance(first, dict) and first.get("cli"):
            # 10/21 v2.1 ACT-01: 鍵を作っただけで離れる人が多い（Phase 0 で API・CLI 19 本）。最初の 1 枚の道を標準エラーに 1 行
            print(f"janction-render: a new key was saved; nothing has rendered yet. To check rendering works: {first['cli']}",
                  file=sys.stderr)
        cache[self.server] = self._key
        self._write_cache(cache)
        return self._key

    def forget_key(self) -> None:
        cache = self._read_cache()
        cache.pop(self.server, None)
        self._write_cache(cache)
        self._key = None

    @staticmethod
    def _read_cache() -> dict[str, str]:
        try:
            data = json.loads(CACHE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write_cache(cache: dict[str, str]) -> None:
        try:
            write_private(CACHE, json.dumps(cache, indent=1))   # 11/10 監査: 最初から 0600 で作って置き換える
        except OSError:
            pass

    # ---- 共通 --------------------------------------------------------------

    @staticmethod
    def _raise(r: requests.Response) -> None:
        if r.status_code < 400:
            return
        if r.status_code == 403 and r.headers.get("x-deny-reason") == "host_not_allowed":
            # 11/2: 箱のプロキシが TLS を開いて 403 を返す形（Claude Code の Web 版の説明: x-deny-reason: host_not_allowed）
            raise unreachable_error(DEFAULT_SERVER, r.url or DEFAULT_SERVER,
                                    requests.exceptions.ProxyError("403 Forbidden (x-deny-reason: host_not_allowed)"))
        try:
            body = r.json()
        except ValueError:
            raise ClientError(r.status_code, f"http_{r.status_code}", r.text[:300])
        raise ClientError(r.status_code, str(body.get("error", r.status_code)), str(body.get("detail", "")),
                          extra=body if isinstance(body, dict) else None)

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.key()}

    def _headers_for(self, url: str) -> dict[str, str]:
        """鍵は、つないでいる受付と同じ origin（scheme・ホスト・ポート）への頼みにだけ付ける（11/10 監査）。"""
        return self._headers() if same_origin(url, self.server) else {}

    def _req(self, method: str, path: str, timeout: float = 30.0, **kw: Any) -> Any:
        r = self.s.request(method, f"{self.server}{path}", headers=self._headers(), timeout=timeout, **kw)
        if r.status_code == 401 and not os.environ.get("JANCTION_RENDER_API_KEY"):
            # 覚えていた一時キーが受付側で消えた（受付の作り直しなど）。1 回だけ取り直す。
            self.forget_key()
            r = self.s.request(method, f"{self.server}{path}", headers=self._headers(), timeout=timeout, **kw)
        self._raise(r)
        return r.json()

    # ---- 機能 --------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        r = self.s.get(f"{self.server}/v1/health", timeout=10)
        self._raise(r)
        return r.json()

    def me(self) -> dict[str, Any]:
        return self._req("GET", "/v1/me")

    def lookup(self, sha256: str) -> Optional[dict[str, Any]]:
        """同じ中身を送ってあれば、その scene_id（無ければ None）。"""
        r = self.s.get(f"{self.server}/v1/files/lookup", params={"sha256": sha256}, headers=self._headers(), timeout=30)
        if r.status_code == 404:
            return None
        self._raise(r)
        return r.json()

    def upload(self, path: str | Path, assets: Optional[list[str | Path]] = None,
               trace_assets: bool = True,
               progress: Optional[Callable[[int, int], None]] = None, asset_roots: Any = (), *,
               _own_file: bool = False) -> dict[str, Any]:
        """シーンを送る。同じ中身を送ってあれば送り直さない（sha256 で照合）。

        assets: 一緒に送る素材（画像など）。.blend は blender-asset-tracer があれば参照する外部ファイルを自動で集める。
        返り値に assets（送った素材）と missing_assets（見つからなかった参照）が入る。
        11/10 監査: 隠しのファイル・フォルダ（. で始まる名前）は送らない。素材は種類を決めた拡張子だけで、文字のファイル
        （.json .txt .csv .py）はシーンのフォルダ（とその下）にあるものだけ（local_file_problem）。指定した素材が外れれば
        何も送らずに ValueError。.blend などから自動で集めた素材が外れれば送らず、返り値の refused_assets に理由を入れる。
        """
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"{p} is not a file")
        if p.suffix.lower() not in SCENE_SUFFIXES:
            raise ValueError("scene must be a .blend file, a Blender Python script (.py), or a 3D file "
                             "(" + ", ".join(SCENE_SUFFIXES[2:]) + ")")
        if not _own_file:         # upload_text が一時フォルダに書いたスクリプトは、置き場所を見ない
            why = local_file_problem(p, scene=True)
            if why:
                raise ValueError(f"refused to send the scene {p}: {why}")
        check_local_files(assets or [], p.parent)
        digest = sha256_of(p)
        out: Optional[dict[str, Any]] = None
        reused = False
        upload_method = "single_request"
        try:
            out = self.lookup(digest)
            reused = out is not None
        except ClientError:
            out = None
        if out is None:
            cap = self.upload_cap_bytes()
            if cap and p.stat().st_size > min(cap, RESUMABLE_ABOVE):
                # 1 回で送れる大きさ（Cloudflare の 100 MB）に近い・超える: 分けて送る（/v1/uploads、10/13）。受付が古ければ前のとおり断る
                upload_method = "resumable_parts"
                done = self.upload_resumable(p, digest, progress=progress)
                if done is None:
                    raise self._too_large(f"the scene file {p.name}", p.stat().st_size, cap, "scene_url")
                out = done.get("scene") or done
            else:
                if progress:
                    progress(0, p.stat().st_size)
                with p.open("rb") as fh:
                    r = self.s.post(f"{self.server}/v1/files", headers=self._headers(),
                                    files={"file": (p.name, fh, "application/octet-stream")}, timeout=1800)
                self._raise(r)
                out = r.json()
                if progress:
                    progress(p.stat().st_size, p.stat().st_size)
        else:
            upload_method = "reused_existing"
        items: list[tuple[str, Path]] = []
        missing: list[str] = []
        lib_map: Optional[dict[str, Any]] = None
        if p.suffix.lower() == ".blend" and trace_assets:
            items, missing, lib_map = trace_blend(p, asset_roots)
            try:
                import blender_asset_tracer  # type: ignore  # noqa: F401
            except Exception:  # noqa: BLE001
                # 素材を集める部品が無いと、.blend の横のテクスチャを黙って送らなかった（10/14、要件 AS-03）
                out["asset_note"] = ("textures next to the .blend were not looked for: pip install 'janction-render[blend]' to "
                                     "send them automatically, or pack them into the .blend (File > External Data > Pack Resources)")
        elif companion_kind(p.name) in ("gltf", "obj") and trace_assets:
            # glTF の .bin と画像、OBJ の .mtl とその画像を、ファイルの横から集める
            base = p.parent
            queue = companion_refs(companion_kind(p.name), p.read_text(encoding="utf-8", errors="replace"))
            seen: set[str] = set()
            while queue:
                rel = queue.pop(0)
                if rel in seen:
                    continue
                seen.add(rel)
                fp = base / rel
                if not fp.is_file():
                    missing.append(rel)
                    continue
                items.append((rel, fp))
                if companion_kind(rel) == "mtl":
                    folder = Path(rel).parent.as_posix()
                    for sub in companion_refs("mtl", fp.read_text(encoding="utf-8", errors="replace")):
                        queue.append(sub if folder in ("", ".") else f"{folder}/{sub}")
        # 11/10 監査: シーンの中の参照から集めた素材も、同じ決まりで見る（送らない物は理由つきで返す）
        refused: list[dict[str, str]] = []
        kept: list[tuple[str, Path]] = []
        for name, fp in items:
            why = local_file_problem(fp, Path(p).parent)
            if why:
                refused.append({"path": str(fp), "why": why})
            else:
                kept.append((name, fp))
        items = kept
        for a in assets or []:
            ap = Path(a)
            if not ap.is_file():
                raise FileNotFoundError(f"asset {ap} is not a file")
            try:
                name = ap.resolve().relative_to(p.resolve().parent).as_posix()
            except ValueError:
                name = ap.name
            items.append((name, ap))
        # 素材は名前と中身で照らす（10/10: 同じ台本＋同じ名前の別の model.glb が、前の素材のまま描かれた）。
        # 受付が sha256 を返さない古い版なら大きさで比べ、違えば送り直す（受付は同じ名前を置き換える）
        already = {a["name"]: a for a in out.get("assets") or []}

        def _same(name: str, ap: Path) -> bool:
            a = already.get(name)
            if a is None:
                return False
            if a.get("sha256"):
                return a["sha256"] == sha256_of(ap)
            return int(a.get("size") or -1) == ap.stat().st_size

        todo = [(n, ap) for n, ap in items if not _same(n, ap)]
        # 11/9: 新しい型（連番の VDB・焼いたキャッシュなど、旗 JR_PRO_ASSETS）は別に送る。受付が受けなければ外して理由を書く
        pro = [(n, ap) for n, ap in todo if is_pro_asset(n)]
        # 11/9 夜: リンクした .blend（旗 JR_LINKED_BLEND）も別に送る。受付が受けなければ外し、付け替えの組も送らない
        libs = [(n, ap) for n, ap in todo if is_library_asset(n)]
        todo = [(n, ap) for n, ap in todo if not is_pro_asset(n) and not is_library_asset(n)]
        scene_id = out["scene_id"]
        if todo:
            out = self.upload_assets(scene_id, todo)
        if pro:
            try:
                out = self.upload_assets(scene_id, pro)
            except ClientError as exc:
                if exc.status != 400 or exc.error != "unsupported":
                    raise
                missing += [f"{n} (this server does not take {Path(n).suffix.lower()} files yet)" for n, _ in pro]
        if libs:
            try:
                out = self.upload_assets(scene_id, libs)
            except ClientError as exc:
                if exc.status != 400 or exc.error != "unsupported":
                    raise
                missing += [f"{n} (this server does not take linked .blend files yet; make the linked data local in "
                            "Blender (Object > Relations > Make Local > All) or Append it, then save)" for n, _ in libs]
                lib_map = None
        if lib_map:
            out = self._send_library_map(scene_id, lib_map, already) or out
        out["missing_assets"] = missing
        if refused:
            out["refused_assets"] = refused
        # Keep the user's name separate from the server-safe stored name.  This
        # avoids making a normalized filename look like a different upload.
        out["original_name"] = p.name
        out["stored_name"] = out.get("name") or p.name
        out["upload_bytes"] = p.stat().st_size
        out["upload_method"] = upload_method
        out["reused_existing"] = reused
        return out

    def _send_library_map(self, scene_id: str, doc: dict[str, Any], already: dict[str, Any]) -> Optional[dict[str, Any]]:
        """リンクした .blend の付け替えの組（jr_libraries.json）を素材として送る（同じ中身が受付にあれば送らない）。"""
        import hashlib
        import tempfile
        from .libplan import MAP_NAME
        raw = json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if (already.get(MAP_NAME) or {}).get("sha256") == hashlib.sha256(raw).hexdigest():
            return None
        with tempfile.TemporaryDirectory(prefix="jr-libmap-") as d:
            f = Path(d) / MAP_NAME
            f.write_bytes(raw)
            return self.upload_assets(scene_id, [(MAP_NAME, f)])

    def preflight(self, scene_id: str, **settings: Any) -> dict[str, Any]:
        """Return the shared render-readiness diagnosis without rendering or charging."""
        return self._req("POST", f"/v1/scenes/{scene_id}/preflight", json=settings)

    # ---- 分けて送る（10/13、docs/67。最大 5 GiB の .blend）----------------------------------------

    _RESUME_FILE = Path.home() / ".janction-render-uploads.json"

    def _resume_get(self, ident: str) -> Optional[str]:
        try:
            return json.loads(self._RESUME_FILE.read_text(encoding="utf-8")).get(ident)
        except (OSError, ValueError, AttributeError):
            return None

    def _resume_set(self, ident: str, url: Optional[str]) -> None:
        try:
            data = json.loads(self._RESUME_FILE.read_text(encoding="utf-8")) if self._RESUME_FILE.exists() else {}
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        if url:
            data[ident] = url
        else:
            data.pop(ident, None)
        try:
            write_private(self._RESUME_FILE, json.dumps(data))
        except OSError:
            pass

    def upload_resumable(self, path: str | Path, digest: str = "",
                         progress: Optional[Callable[[int, int], None]] = None, part_bytes: int = 0,
                         scene_id: str = "", asset: str = "", auth: Optional[dict[str, str]] = None,
                         mode: str = "") -> Optional[dict[str, Any]]:
        """100 MB を超えるファイルを部分に分けて送る（POST /v1/uploads → PATCH、tus 1.0）。返り値は受付の状態（scene_id・scene）。
        通信が切れたら位置を聞き直して続きから送る。途中で止めても、同じコマンドをもう一度打てば続きから（~/.janction-render-uploads.json）。
        受付が分けて送る道を持っていなければ None。auth を渡すと鍵の代わりにそれを付ける（{} は鍵なし＝/d/ のリンク、
        {"X-Upload-Token": …} は AI が出したリンク。10/21 docs/90）。mode は続きの控えを鍵の送信と分ける印。"""
        import base64

        p = Path(path)
        size = p.stat().st_size
        digest = digest or sha256_of(p)
        hdr = self._headers() if auth is None else dict(auth)
        ident = f"{self.server}|{digest}|{size}" + (f"|{scene_id}|{asset}" if asset else "") + (f"|{mode}" if mode else "")
        tus = {"Tus-Resumable": "1.0.0"}
        url, off = self._resume_get(ident), 0
        if url:
            try:
                h = self.s.head(url, headers={**hdr, **tus}, timeout=30)
                if h.status_code == 200 and int(h.headers.get("Upload-Length") or -1) == size:
                    off = int(h.headers.get("Upload-Offset") or 0)
                else:
                    url = None
            except (ClientError, ValueError):
                url = None
        part = part_bytes
        if not url:
            meta = (f"filename {base64.b64encode(p.name.encode('utf-8')).decode()},"
                    f"sha256 {base64.b64encode(digest.encode()).decode()}")
            if asset:
                # 素材（UP-07）: 足す先のシーンと、シーンからの相対の場所
                meta += (f",scene_id {base64.b64encode(scene_id.encode()).decode()},"
                         f"asset {base64.b64encode(asset.encode('utf-8')).decode()}")
            r = self.s.post(f"{self.server}/v1/uploads", timeout=60,
                            headers={**hdr, **tus, "Upload-Length": str(size), "Upload-Metadata": meta})
            if r.status_code in (404, 405):
                return None
            self._raise(r)
            url = f"{self.server}{r.headers['Location']}"
            part = part or int(r.json().get("part_bytes") or 0)
            self._resume_set(ident, url)
        part = part or 32 * 1024 * 1024
        tries = 0
        if progress:
            progress(off, size)
        with p.open("rb") as fh:
            while True:
                fh.seek(off)
                data = fh.read(part)
                part_sum = "sha256 " + base64.b64encode(hashlib.sha256(data).digest()).decode()
                sent_from, t_part = off, time.monotonic()
                try:
                    r = self.s.patch(url, data=data, timeout=600, headers={
                        **hdr, **tus, "Upload-Offset": str(off), "Content-Type": "application/offset+octet-stream",
                        "Upload-Checksum": part_sum})
                except ClientError:
                    r = None                       # つながらない・切れた: 待って位置を聞き直す
                if r is not None and r.status_code == 200:
                    self._resume_set(ident, None)
                    if progress:
                        progress(size, size)
                    return r.json()
                if r is not None and r.status_code == 204:
                    off, tries = int(r.headers.get("Upload-Offset") or off), 0
                    part = _fit_part(part, off - sent_from, time.monotonic() - t_part)
                    if progress:
                        progress(off, size)
                    continue
                if r is not None and r.status_code == 409 and r.headers.get("Upload-Offset") is not None:
                    off = int(r.headers["Upload-Offset"])
                    continue
                if r is not None and r.status_code == 460:
                    r = None                       # 部分が途中で化けた: 同じ位置から送り直す（回数に数える）
                if r is not None and r.status_code < 500 and r.status_code not in (408, 409, 429) or                         r is not None and r.status_code == 507:
                    if r.status_code == 404:
                        self._resume_set(ident, None)
                    self._raise(r)
                tries += 1
                if tries > 8:
                    raise ClientError(0, "upload_interrupted",
                                      f"the upload of {p.name} kept failing at {off} of {size} bytes; run the same command again "
                                      "to continue from there", extra={"retryable": True, "offset": off})
                time.sleep(min(30.0, 2.0 ** tries))
                try:
                    h = self.s.head(url, headers={**hdr, **tus}, timeout=30)
                    if h.status_code == 200:
                        off = int(h.headers.get("Upload-Offset") or off)
                        if off > sent_from:
                            # 切れたが届いた分はある（10/14 本番、2 Mbps: 32 MiB の部分が毎回 130 秒ほどで切られ、届いた分だけ
                            # 進んでいた）。進んでいる間は失敗に数えず、部分をその速さで 60 秒に収まる大きさにする
                            tries = 0
                            part = _fit_part(part, off - sent_from, time.monotonic() - t_part, cut=True)
                            if progress:
                                progress(off, size)
                    elif h.status_code == 404:
                        self._resume_set(ident, None)
                        self._raise(h)
                except ClientError as exc:
                    if exc.status:
                        raise

    def send_for_ai(self, path: str | Path, progress: Optional[Callable[[int, int], None]] = None,
                    upload_url: str = "") -> dict[str, Any]:
        """手元のファイルを、チャットやエージェントの AI（リモートの MCP、別の鍵）が使える形で送る（10/21、docs/90 FR-03）。
        upload_url なし: 鍵を使わずに送り、12 時間の https のリンク（/d/…）を返す。AI はそれを scene_url に渡し、自分の鍵のシーンにする。
        upload_url あり（AI の upload_link が出した /upload?t=…）: そのリンクの鍵のシーンになり、AI は upload_status で受け取る。
        この PC の鍵（~/.janction-render.json）とリモートの鍵は別なので、この PC の scene_id はリモートでは使えない。"""
        from urllib.parse import parse_qs

        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"no such file: {p}")
        why = local_file_problem(p, scene=True)      # 11/10 監査: 隠しフォルダの中のファイルは、リンクでも送らない
        if why:
            raise ValueError(f"refused to send {p}: {why}")
        token = ""
        if upload_url:
            parts = urlsplit(upload_url)
            token = (parse_qs(parts.query).get("t") or [""])[0]
            if not token or not parts.path.rstrip("/").endswith("/upload"):
                raise ValueError("the upload link must be the /upload?t=... link that upload_link returned")
        auth = {"X-Upload-Token": token} if token else {}
        mode = ("link:" + hashlib.sha256(token.encode()).hexdigest()[:12]) if token else "drop"
        out = self.upload_resumable(p, progress=progress, auth=auth, mode=mode)
        if out is None:
            if token:
                raise ClientError(0, "uploads_unavailable", "this server does not accept upload links; send the file without --link")
            with p.open("rb") as fh:
                r = self.s.post(f"{self.server}/v1/drops", files={"file": (p.name, fh)}, timeout=1800,
                                headers={"Accept": "application/json"})
            self._raise(r)
            out = r.json()
        return out

    def upload_cap_bytes(self) -> int:
        """1 回の送信の上限（バイト）。0 は見ない（手元・自前の受付）。"""
        raw = (os.environ.get("JANCTION_RENDER_MAX_UPLOAD_MB") or "").strip()
        if raw:
            try:
                return max(0, int(raw)) * 1024 * 1024
            except ValueError:
                pass
        return EDGE_UPLOAD_MB * 1024 * 1024 if self.server.rstrip("/") == DEFAULT_SERVER else 0

    def _too_large(self, what: str, size: int, cap: int, link_field: str) -> ClientError:
        return ClientError(413, "too_large",
                           f"{what} is {size / 1048576:.0f} MB; one upload to {self.server} is limited to {cap // 1048576} MB. "
                           f"Put the file on a public https link that downloads it and pass the link as {link_field}, "
                           "or make it smaller (fewer or smaller textures)",
                           extra={"code": "INVALID_INPUT", "retryable": False, "recommended_action": "FIX_INPUT",
                                  "possible_fix": f"pass a public https link as {link_field} instead of uploading the file, or shrink it"})

    def upload_assets(self, scene_id: str, items: list[tuple[str, str | Path]]) -> dict[str, Any]:
        """素材をシーンに足す。items は [(送るときの名前, 場所)]。名前にフォルダを含めてよい（textures/a.png）。
        公開の受付には 1 回 100 MB までに分けて送る（1 つで超える素材は断ってリンクを案内する）。"""
        cap = self.upload_cap_bytes()
        if not cap:
            done: dict[str, Any] = {}
            for i in range(0, len(items), ASSET_BATCH_FILES):
                done = self._post_assets(scene_id, items[i:i + ASSET_BATCH_FILES])
            return done
        room = cap - 1024 * 1024           # multipart の見出しのぶんを空ける
        # 大きい素材（64 MiB を超える）は 1 つずつ分けて送る（UP-07、10/14。カード登録・前払いの鍵は 1 つ 5 GiB・合計 15 GiB まで）。
        # 受付が分けて送る道を開けていなければ、前のとおり 1 回で送る（100 MB を超えるものは断る）
        big = [(n, p) for n, p in items if Path(p).stat().st_size > min(room, RESUMABLE_ABOVE)]
        out: dict[str, Any] = {}
        sent_big: set[str] = set()
        for name, path in big:
            done = self.upload_resumable(path, scene_id=scene_id, asset=str(name).replace("\\", "/"))
            if done is None:
                break
            out = done.get("scene") or out
            sent_big.add(name)
        items = [(n, p) for n, p in items if n not in sent_big]
        if not items:
            return out
        batches: list[list[tuple[str, str | Path]]] = [[]]
        used = 0
        for name, path in items:
            n = Path(path).stat().st_size
            if n > room:
                if n > ASSET_LINK_MAX_BYTES:
                    # リンクで渡しても 1 つ 128 MB まで（受付の JR_MAX_ASSET_MB）。通らない送り方を勧めない（10/13 監査）
                    raise ClientError(413, "too_large",
                                      f"asset {name} is {n / 1048576:.0f} MB; an asset can be at most "
                                      f"{ASSET_LINK_MAX_BYTES // 1048576} MB, uploaded or by link. Make it smaller "
                                      "(lower texture resolution, or compress it) or pack it into the .blend",
                                      extra={"code": "INVALID_INPUT", "retryable": False, "recommended_action": "FIX_INPUT"})
                raise self._too_large(f"asset {name}", n, cap, "asset_urls")
            if batches[-1] and (used + n > room or len(batches[-1]) >= ASSET_BATCH_FILES):
                batches.append([])
                used = 0
            batches[-1].append((name, path))
            used += n
        out: dict[str, Any] = {}
        for b in batches:
            out = self._post_assets(scene_id, b)
        return out

    def _post_assets(self, scene_id: str, items: list[tuple[str, str | Path]]) -> dict[str, Any]:
        handles = []
        try:
            files = []
            for name, path in items:
                fh = Path(path).open("rb")
                handles.append(fh)
                files.append(("files", (name, fh, "application/octet-stream")))
            r = self.s.post(f"{self.server}/v1/files/{scene_id}/assets", headers=self._headers(), files=files, timeout=1800)
        finally:
            for fh in handles:
                fh.close()
        self._raise(r)
        return r.json()

    def share(self, job_id: str, title: str = "", note: str = "", include_script: bool = False, listed: bool = False,
              prompt: str = "") -> dict[str, Any]:
        """描けた結果を公開ページにする（/r/<id>）。prompt は「エージェントに頼んだこと」。"""
        r = self.s.post(f"{self.server}/v1/jobs/{job_id}/share", headers=self._headers(),
                        json={"title": title, "note": note, "include_script": include_script, "listed": listed, "prompt": prompt}, timeout=120)
        self._raise(r)
        return r.json()

    def unshare(self, job_id: str) -> dict[str, Any]:
        r = self.s.delete(f"{self.server}/v1/jobs/{job_id}/share", headers=self._headers(), timeout=60)
        self._raise(r)
        return r.json()

    def shares(self) -> dict[str, Any]:
        r = self.s.get(f"{self.server}/v1/shares", headers=self._headers(), timeout=30)
        self._raise(r)
        return r.json()

    def revoke_key(self) -> dict[str, Any]:
        """この鍵を失効させる（つながっているアプリも全部切れる）。手元の控えは、失効させた鍵がその控えと同じときだけ消す
        （10/11: 環境変数の別の鍵を失効させたら、保存済みの鍵の控えまで消えていた）。"""
        key = self.key()
        r = self.s.post(f"{self.server}/v1/keys/revoke", headers=self._headers(), timeout=30)
        self._raise(r)
        if self._read_cache().get(self.server) == key:
            self.forget_key()
        self._key = None
        return r.json()

    def connections(self) -> dict[str, Any]:
        r = self.s.get(f"{self.server}/v1/connections", headers=self._headers(), timeout=30)
        self._raise(r)
        return r.json()

    def connect_code(self) -> dict[str, Any]:
        """このアカウントの接続コード（8 字・10 分・1 回、11/12）。別の AI アプリの JANCTION の接続のページ（I have a connect code）か、
        別のブラウザの /connect/code に入れると、同じアカウント（残高・無料の残り・作品）につながる。鍵そのもので呼ぶ。"""
        r = self.s.post(f"{self.server}/v1/me/connect-code", headers=self._headers(), timeout=30)
        self._raise(r)
        return r.json()

    def disconnect(self, conn_id: str) -> dict[str, Any]:
        r = self.s.delete(f"{self.server}/v1/connections/{conn_id}", headers=self._headers(), timeout=30)
        self._raise(r)
        return r.json()

    def fetch_asset_urls(self, scene_id: str, urls: list[str]) -> dict[str, Any]:
        """URL か polyhaven:<id> の素材を受付に取らせてシーンに足す（受付が取るので手元には要らない）。"""
        r = self.s.post(f"{self.server}/v1/files/{scene_id}/assets/urls", headers=self._headers(),
                        json={"urls": [str(u) for u in urls]}, timeout=900)
        self._raise(r)
        return r.json()

    def asset_search(self, query: str, kind: str = "models") -> dict[str, Any]:
        """Poly Haven（CC0）の素材を名前・タグで引く。"""
        r = self.s.get(f"{self.server}/v1/assets/search", headers=self._headers(),
                       params={"q": query, "kind": kind}, timeout=30)
        self._raise(r)
        return r.json()

    def upload_text(self, name: str, text: str) -> dict[str, Any]:
        """文字列で受け取った bpy スクリプトを、そのままシーンとして送る（ファイルを作らなくてよい）。"""
        import tempfile

        if not name.lower().endswith(".py"):
            name = "scene.py"
        if not text.strip():
            raise ValueError("the script is empty")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / Path(name).name
            p.write_text(text, encoding="utf-8")
            return self.upload(p, _own_file=True)

    def upload_url(self, url: str) -> dict[str, Any]:
        """https の URL からシーンを取り込ませる（受付が取りに行く。手元に落とさない）。/samples/… の見本や /upload のリンクに。"""
        if not str(url or "").strip().lower().startswith("https://"):
            raise ValueError("scene_url must be an https URL")
        return self._req("POST", "/v1/files/url", json={"url": str(url).strip()}, timeout=120)

    def submit(self, scene_id: str, **params: Any) -> dict[str, Any]:
        body = {"scene_id": scene_id}
        body.update({k: v for k, v in params.items() if v is not None})
        return self._req("POST", "/v1/jobs", json=body)

    def estimate(self, scene_id: Optional[str] = None, **params: Any) -> dict[str, Any]:
        """入れずに見積もりだけ（GPU 秒・列の待ち・壁時計の目安・無料枠に収まるか）。"""
        body: dict[str, Any] = {k: v for k, v in params.items() if v is not None}
        if scene_id:
            body["scene_id"] = scene_id
        return self._req("POST", "/v1/estimate", json=body)

    def job(self, job_id: str) -> dict[str, Any]:
        return self._req("GET", f"/v1/jobs/{job_id}")

    def next_actions(self, job_id: str) -> Optional[dict[str, Any]]:
        """終わった仕事の次の一手（受付の旗 JR_RET_NEXT_ACTIONS が OFF なら None）。見るだけで描かない。"""
        try:
            r = self.s.get(f"{self.server}/v1/jobs/{job_id}/next-actions", headers=self._headers(), timeout=15)
        except Exception:  # noqa: BLE001
            return None
        return r.json() if r.status_code == 200 else None

    def feature_offers(self, job_id: str, accepts: list[str], actions: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        """試し描きの next_actions に、受付がこの鍵に勧める新しい機能の候補を足したもの（11/5）。古い受付・失敗なら None。見るだけ。"""
        try:
            r = self.s.post(f"{self.server}/v1/jobs/{job_id}/feature-offers", json={"accepts": list(accepts), "next_actions": actions},
                            headers=self._headers(), timeout=20)
        except Exception:  # noqa: BLE001
            return None
        return r.json() if r.status_code == 200 else None

    def recipe(self, job_id: str) -> dict[str, Any]:
        """次回用の設定（受付の旗 JR_RET_RECIPE）。鍵やリンクは入っていない。"""
        return self._req("GET", f"/v1/jobs/{job_id}/recipe")

    def jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._req("GET", f"/v1/jobs?limit={int(limit)}")["jobs"]

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self._req("DELETE", f"/v1/jobs/{job_id}")

    def retry(self, job_id: str, confirm: bool = False, max_yen: Optional[int] = None,
              idempotency_key: Optional[str] = None) -> dict[str, Any]:
        """失敗・取り消しの仕上げの足りないコマだけを描き直す（11/9、受付の旗 JR_FRAME_RETRY。OFF の受付は 404）。
        confirm=False は足りないコマと値段だけ（描かない）。confirm=True で新しい仕事を入れる。"""
        body: dict[str, Any] = {"confirm": bool(confirm)}
        if max_yen is not None:
            body["max_yen"] = int(max_yen)
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        return self._req("POST", f"/v1/jobs/{job_id}/retry", json=body, timeout=120)

    # ---- 決済 --------------------------------------------------------------

    def checkout(self, amount_yen: Optional[int] = None) -> dict[str, Any]:
        """クレジットをチャージする決済ページのリンクを作る。"""
        body = {"amount_yen": int(amount_yen)} if amount_yen else {}
        return self._req("POST", "/v1/billing/checkout", json=body)

    def billing_sync(self) -> dict[str, Any]:
        """払い終わった決済を確かめて残高に足す（戻り先のページを開かなかったときの保険）。"""
        return self._req("POST", "/v1/billing/sync", timeout=60)

    def limits(self, job_yen: Optional[int] = None, day_yen: Optional[int] = None) -> dict[str, Any]:
        """支出の上限（1 仕事・1 日、円）を読む（引数なし）か変える。上げる前に人に聞くこと。"""
        body = {k: int(v) for k, v in (("job_yen", job_yen), ("day_yen", day_yen)) if v is not None}
        if not body:
            return {"limits": self.me().get("limits")}
        return self._req("POST", "/v1/me/limits", json=body)

    def outcomes(self) -> dict[str, Any]:
        """定額の成果の一覧（選択肢と、先に言う値段）。"""
        return self._req("GET", "/v1/outcomes")

    def outcome(self, name: str, scene_id: str, idempotency_key: Optional[str] = None, **options: Any) -> dict[str, Any]:
        """成果を注文する（turntable / product-shot）。値段は応答の outcome.price_yen が天井。"""
        body: dict[str, Any] = {"scene_id": scene_id, **{k: v for k, v in options.items() if v is not None}}
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        return self._req("POST", f"/v1/outcomes/{name}", json=body)

    def ledger(self, limit: int = 50) -> dict[str, Any]:
        return self._req("GET", f"/v1/ledger?limit={int(limit)}")

    def wait(self, job_id: str, timeout: float, interval: float = 2.0,
             on_progress: Optional[Callable[[dict[str, Any]], None]] = None) -> dict[str, Any]:
        """done / failed / canceled になるまで待つ。上限を過ぎたらそのときの状態を返す。"""
        deadline = time.monotonic() + timeout
        last_key = None
        while True:
            j = self.job(job_id)
            key = (j["status"], j["progress"]["frames_done"])
            if on_progress and key != last_key:
                on_progress(j)
                last_key = key
            if j["status"] in ("done", "failed", "canceled") or time.monotonic() > deadline:
                return j
            time.sleep(interval)

    def download(self, job_id: str, out_dir: str | Path, only: Optional[list[str] | str] = None,
                 on_progress: Optional[Callable[[str], None]] = None) -> list[Path]:
        """成果物を out_dir に落とす。only は名前の一覧か、'mp4' / 'frames' / 'sheet' / 'output' / 'all'。
        on_progress は進み具合の 1 行（CLI は標準エラーに出す。10/14: 5 GB の受け取りが 4 分黙っていた）。"""
        self._say = on_progress or (lambda _msg: None)
        j = self.job(job_id)
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        from urllib.parse import urlsplit

        wanted = select_artifacts(j["artifacts"], only) if isinstance(only, str) or only is None else \
            [a for a in j["artifacts"] if a["name"] in only]
        for a in wanted:
            safe_name(a["name"])          # 11/10 監査: 受付が返した名前が out_dir の外を指すなら、何も書く前に止める
        if len(wanted) >= ARCHIVE_MIN_FILES:
            got = self._download_archive(job_id, out, wanted)
            if got is not None:
                return got
            self._say("the zip did not come through; fetching the files one by one")
        last = time.monotonic()
        for i, a in enumerate(wanted, 1):
            dest = out / safe_name(a["name"])
            if _have(dest, a):            # 前の回（切れた zip・打ち直し）で届いている
                paths.append(dest)
                continue
            if len(wanted) > 1 and time.monotonic() - last > 10:
                last = time.monotonic()
                self._say(f"downloading {i}/{len(wanted)} files")
            # 受付が返す URL は公開 URL の土台で組まれている。自分がつないだ先（SSH トンネルなど）でも
            # 落とせるように、パスだけを取り出して自分の server に付け直す
            parts = urlsplit(a["url"])
            path = parts.path + (f"?{parts.query}" if parts.query else "")
            url = f"{self.server}{path}" if parts.path.startswith("/v1/") or (not parts.scheme and path.startswith("/")) else a["url"]
            if urlsplit(url).scheme.lower() not in ("http", "https"):
                raise ClientError(0, "bad_artifact_url", f"the server sent an artifact link that is not http(s): {url[:200]!r}")
            self._download_file(url, dest)
            paths.append(dest)
        return paths

    def _download_file(self, url: str, dest: Path) -> None:
        """1 つのファイルを dest.part に受け取り、切れたら Range で続きから（10/14。受付の FileResponse は Range に答える）。"""
        part = dest.with_name(dest.name + ".part")
        for attempt in range(DOWNLOAD_TRIES):
            have = part.stat().st_size if part.exists() else 0
            # 11/10 監査: 受付の外のリンク（署名つきの /dl/ など）には鍵を付けない
            headers = {**self._headers_for(url), **({"Range": f"bytes={have}-"} if have else {})}
            try:
                with self.s.get(url, headers=headers, stream=True, timeout=600) as r:
                    if r.status_code == 416:          # もう全部ある
                        break
                    self._raise(r)
                    with part.open("ab" if r.status_code == 206 else "wb") as fh:
                        for chunk in r.iter_content(1024 * 1024):
                            fh.write(chunk)
                break
            except requests.RequestException:
                if attempt == DOWNLOAD_TRIES - 1:
                    raise
                time.sleep(2.0 * (attempt + 1))
        part.replace(dest)

    def _download_archive(self, job_id: str, out: Path, wanted: list[dict[str, Any]]) -> Optional[list[Path]]:
        """まとめて zip（GET /v1/jobs/{id}/archive）で取り、欲しい名前だけを out に出す。大きいときは名前の順に約 1 GiB ずつの
        区切り（first・last）で取り、届いた区切りは残して、切れた区切りだけを取り直す（10/14）。受付が古くて口が無い・取り直しても
        届かない・中身が足りないときは None（呼び手が 1 枚ずつに戻り、届いているファイルは飛ばす）。"""
        ordered = sorted(wanted, key=lambda a: a["name"])
        groups: list[list[dict[str, Any]]] = []
        size = 0
        for a in ordered:
            n = int(a.get("size") or 0)
            if not groups or (size + n > ARCHIVE_PART_BYTES and groups[-1]):
                groups.append([])
                size = 0
            groups[-1].append(a)
            size += n
        total_mb = sum(int(a.get("size") or 0) for a in wanted) / 1048576
        if len(groups) == 1:
            self._say(f"downloading {len(wanted)} files in one zip ({total_mb:.0f} MB)")
            return self._fetch_archive(job_id, out, wanted)
        self._say(f"downloading {len(wanted)} files ({total_mb / 1024:.1f} GB) in {len(groups)} zips of about 1 GB")
        paths: list[Path] = []
        for gi, g in enumerate(groups, 1):
            if all(_have(out / safe_name(a["name"]), a) for a in g):
                paths += [out / safe_name(a["name"]) for a in g]
                continue
            got: Any = None
            for attempt in range(DOWNLOAD_TRIES):
                self._say(f"zip {gi}/{len(groups)} ({len(g)} files, {sum(int(a.get('size') or 0) for a in g) / 1048576:.0f} MB)"
                          + (f", again (try {attempt + 1})" if attempt else ""))
                got = self._fetch_archive(job_id, out, g, (g[0]["name"], g[-1]["name"]))
                if got is not None:
                    break
                time.sleep(2.0 * (attempt + 1))
            if got == "unsliced":         # 区切りを知らない受付: 前のとおり 1 本で
                return self._fetch_archive(job_id, out, wanted)
            if got is None:
                return None
            paths += got
        return paths

    def _fetch_archive(self, job_id: str, out: Path, wanted: list[dict[str, Any]],
                       span: Optional[tuple[str, str]] = None) -> Any:
        """zip を 1 本取って欲しい名前を out に出す。span（最初と最後の名前）を渡すと、その一続きだけを頼む。
        区切りを頼んだのに受付が X-Archive-Range を返さなければ "unsliced"。"""
        import shutil
        import tempfile
        import zipfile
        from urllib.parse import urlencode

        names = {a["name"] for a in wanted}
        exts = sorted({Path(n).suffix.lstrip(".").lower() for n in names if Path(n).suffix})
        q = {**({"only": ",".join(exts)} if exts else {}), **({"first": span[0], "last": span[1]} if span else {})}
        url = f"{self.server}/v1/jobs/{job_id}/archive" + (f"?{urlencode(q)}" if q else "")
        tmp: Optional[str] = None
        try:
            with self.s.get(url, headers=self._headers(), stream=True, timeout=1800) as r:
                if r.status_code != 200:
                    return None
                if span and not r.headers.get("X-Archive-Range"):
                    return "unsliced"
                fd, tmp = tempfile.mkstemp(suffix=".zip", dir=out)
                got_b, last = 0, time.monotonic()
                with os.fdopen(fd, "wb") as fh:
                    for chunk in r.iter_content(1024 * 1024):
                        fh.write(chunk)
                        got_b += len(chunk)
                        if time.monotonic() - last > 15:
                            last = time.monotonic()
                            getattr(self, "_say", lambda _m: None)(f"  {got_b // 1048576} MB")
            paths: list[Path] = []
            with zipfile.ZipFile(tmp) as zf:
                if not names <= set(zf.namelist()):
                    return None
                for a in wanted:
                    dest = out / safe_name(a["name"])
                    with zf.open(a["name"]) as src, dest.open("wb") as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                    paths.append(dest)
            return paths
        except (requests.RequestException, zipfile.BadZipFile, OSError):
            return None
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass


# ------------------------------------------------------------------ 11/10 監査: 手元に書く名前・鍵を送る先・送る手元のファイル

def safe_name(name: Any) -> str:
    """受付が返した成果物の名前を、出力フォルダの中のファイル名にする（npm の safeName と同じ決まり）。フォルダの外を指す名前
    （/ \\ .. 絶対パス・ドライブ名・制御文字）は ClientError で、何も書かない。"""
    n = str(name or "")
    if (not n or "/" in n or "\\" in n or n in (".", "..") or any(ord(c) < 32 for c in n) or re.match(r"^[A-Za-z]:", n)):
        raise ClientError(0, "bad_artifact_name", f"the server sent an artifact name that is not a plain file name: {json.dumps(n)}")
    return n


def _origin(url: str) -> Optional[tuple[str, str, Optional[int]]]:
    try:
        p = urlsplit(str(url or ""))
        scheme = p.scheme.lower()
        return scheme, (p.hostname or "").lower(), p.port or {"http": 80, "https": 443}.get(scheme)
    except ValueError:
        return None


def same_origin(url: str, server: str) -> bool:
    """url が受付（server）と同じ scheme・ホスト・ポートか。鍵（X-API-Key）はここが真のときだけ送る。"""
    a, b = _origin(url), _origin(server)
    return a is not None and a == b and bool(a[1])


def write_private(path: Path, text: str) -> None:
    """持ち主だけが読める（0600）ファイルとして書く。一時ファイルを 0600 で作ってから置き換えるので、書いている間も
    ほかの利用者に読まれない（11/10 監査: 書いた後の chmod では一瞬読める）。"""
    import secrets

    path = Path(path)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# 素材として送る拡張子（画像・3D ファイルとその .bin/.mtl・.blend・フォント・音・動画）。文字のファイルはシーンのフォルダからだけ
ASSET_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".exr", ".hdr", ".tif", ".tiff", ".webp", ".bmp", ".tga", ".gif", ".dds", ".psd",
    ".bin", ".mtl", ".fbx", ".glb", ".gltf", ".obj", ".usd", ".usda", ".usdc", ".usdz", ".abc", ".stl", ".ply", ".dae", ".vdb",
    ".blend", ".ttf", ".otf", ".woff", ".woff2",
    ".bphys", ".blob", ".uni",        # 焼いたキャッシュ（11/9 JR_PRO_ASSETS。受けるかは受付が決める）
    ".wav", ".mp3", ".ogg", ".flac", ".m4a", ".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v",
})
TEXT_ASSET_SUFFIXES = frozenset({".json", ".txt", ".csv", ".py"})


def _hidden_part(p: Path) -> Optional[str]:
    """パスの中の隠しの名前（. で始まる）。作業フォルダの中なら作業フォルダより下、ホームの中ならホームより下を見る
    （エージェントの作業フォルダが隠しフォルダの中にあっても、その中のシーンは送れる）。"""
    parts: Optional[tuple[str, ...]] = None
    for base in (Path.cwd, Path.home):
        try:
            parts = p.relative_to(base().resolve()).parts
            break
        except (ValueError, OSError, RuntimeError):
            continue
    if parts is None:
        parts = p.parts[1:]
    return next((x for x in parts if x.startswith(".")), None)


def local_file_problem(path: str | Path, scene_dir: Optional[str | Path] = None, *, scene: bool = False) -> Optional[str]:
    """手元のファイルを送ってよいか（stdio の MCP・CLI・Python から）。良ければ None、悪ければ理由の 1 文（11/10 監査:
    プロンプトに仕込まれた指示で、鍵や設定のファイルを素材として送らせない）。scene=True はシーン本体（拡張子は呼び手が見る）。"""
    p = Path(path).expanduser()
    try:
        rp = p.resolve()
    except (OSError, RuntimeError):
        return "the path cannot be resolved"
    hidden = _hidden_part(rp)
    if hidden:
        return (f"it is in a hidden file or folder ({hidden}); files and folders whose names start with '.' are not sent. "
                "Copy the file into the scene's folder under a normal name if it belongs to the scene")
    if scene:
        return None
    ext = rp.suffix.lower()
    if ext in TEXT_ASSET_SUFFIXES:
        if scene_dir is None:
            return (f"{ext} files are sent only from the scene file's own folder; pass the scene as scene_path with this file "
                    "next to it (or in a folder below it)")
        try:
            rp.relative_to(Path(scene_dir).expanduser().resolve())
        except (ValueError, OSError, RuntimeError):
            return f"{ext} files are sent only from the scene file's own folder (or a folder below it)"
        return None
    if ext == ".gz" and rp.name.lower().endswith(".bobj.gz"):
        return None                   # 液体の面のキャッシュ（ほかの .gz は送らない）
    if ext not in ASSET_SUFFIXES:
        return (f"{ext or 'a file without an extension'} is not an asset type that is sent (images, 3D files with their .bin "
                "and .mtl, .blend, fonts, audio and video)")
    return None


def check_local_files(paths: Any, scene_dir: Optional[str | Path] = None) -> None:
    """素材の一覧を local_file_problem で見て、1 つでも外れれば ValueError（どのパスか・なぜかを言う）。何も送る前に呼ぶ。"""
    for a in paths or []:
        why = local_file_problem(a, scene_dir)
        if why:
            raise ValueError(f"refused to send {a}: {why}")
