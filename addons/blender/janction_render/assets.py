""".blend が要る外部ファイルを (相対の名前, 手元の絶対パス) の組で集め、依存の一覧（全部）も作る。

受付は素材をシーンの隣に相対の名前で置くので、``//textures/wood.png`` は ``textures/wood.png`` で送る。パック済みは送らない。

画像・フォント・Alembic/USD のキャッシュに加えて、次も集める（11/9、アドオン 0.1.11）:
  - 画像の連番（シーンのコマの範囲で実際に使うコマだけ）と動画のテクスチャ
  - OpenVDB（1 つのファイルと連番）
  - 焼いたシミュレーション: 点のキャッシュ（布・ソフトボディ・パーティクル・ダイナミックペイント）、ジオメトリノードのベイク、流体

.blend のフォルダの外のファイルは、アドオンの設定の「Asset folders」に本人が書いたフォルダからだけ送る（空なら .blend の
フォルダだけ。ネットワークの共有は書かれていなければ読まない）。そうしたファイルと、受付が受けない名前のファイルは
詰め替えのフォルダ（``jr_pack/<hash>/``）に入れ、送る写しの中の道だけを書き換える（``remaps``。ops.py が写しを保存した直後に
開いているファイルの道を元に戻す）。点のキャッシュと流体のキャッシュは道を変えると Blender がキャッシュを捨てる・名前を
付け替えるので書き換えず、.blend のフォルダの中にあるときだけ送る。

11/9 夜（0.1.12、受付の旗 JR_LINKED_BLEND）: リンクした .blend（bpy.data.libraries、入れ子も）と、その中の画像などを送る。
置き場は libplan（CLI と同じファイル）: .blend のフォルダの中は相対の名前のまま、外（Asset folders の中だけ）は ``lib/<hash>/``。
シーンが直接読むライブラリの道は送る写しの中だけ書き換え、入れ子の付け替えは jr_libraries.json（``library_map``）で渡す。
旗の無い受付は .blend を 400 unsupported で断るので、送り手はそれと jr_libraries.json だけを外して理由を言う（描画は止めない）。

``collect()`` は素のオブジェクトで動くので Blender なしで試せる。``collect_from_bpy()`` が bpy.data を渡す。
"""
import glob
import hashlib
import os
import posixpath
import re
from typing import Any, Callable, Iterable, Optional

try:
    from . import libplan
except ImportError:   # 試験はこのファイルだけを読む（パッケージの外）。同じフォルダの libplan.py を読む
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location("jr_addon_libplan", os.path.join(os.path.dirname(os.path.abspath(__file__)), "libplan.py"))
    libplan = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(libplan)

# 受付の ASSET_EXTENSIONS と素材の名前の決まりの写し。知らない型は受付が断る
ACCEPTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".exr", ".hdr", ".tif", ".tiff", ".webp", ".bmp", ".tga",
    ".bin", ".mtl", ".fbx", ".glb", ".gltf", ".obj", ".usd", ".usda", ".usdc", ".usdz", ".abc",
    ".mp4", ".mov", ".json", ".txt", ".csv", ".ttf", ".otf",
}
# 受付の旗 JR_PRO_ASSETS が ON のときだけ受ける型（server/pro_assets.py の EXTRA_EXTENSIONS）。旗の無い受付は
# 400 unsupported を返すので、送り手はこれだけを外して理由を言う（描画は止めない）
PRO_EXTENSIONS = {".vdb", ".bphys", ".blob", ".uni", ".gz", ".avi", ".mkv", ".webm"}
# 受付の旗 JR_LINKED_BLEND が ON のときだけ受ける型（リンクした .blend、server/linked_blend.py）。扱いは上と同じ
LIBRARY_EXTENSIONS = {".blend"}
NAME_RE =re.compile(r"^[A-Za-z0-9_.\-]{1,120}(/[A-Za-z0-9_.\-]{1,120}){0,4}$")
MAX_ASSETS = 40              # 旗の前の受付の数の上限。manifest の返事（limits.max_assets）があればそちら
COLLECT_MAX = 5000           # これより多いファイルは数えない（暴れた連番・キャッシュのフォルダ）
FRAMES_MAX = 100000          # 連番のために見るシーンのコマ数の上限
PACK_DIR = "jr_pack"
# ワーカーは送った写しを scene.blend として開く。既定の点のキャッシュは //blendcache_scene/ から読まれる
WORKER_SCENE_STEM = "scene"
FLUID_SUBDIRS = ("config", "data", "noise", "mesh", "particles", "guiding")

SEND, PACKED, SKIP = "send", "packed", "skip"


class Remap:
    """送る写しの中だけで書き換える道 1 つ。保存の間だけ ``setattr(block, attr, new)``、保存の後に元へ戻す。"""

    def __init__(self, block: Any, attr: str, new: str) -> None:
        self.block = block
        self.attr = attr
        self.new = new


class Collected:
    def __init__(self) -> None:
        self.assets: list[tuple[str, str]] = []
        self.warnings: list[str] = []
        self.deps: list[dict[str, Any]] = []
        self.remaps: list[Remap] = []
        # 11/9 夜（0.1.12）: リンクした .blend の付け替えの組（jr_libraries.json の中身。無ければ None）
        self.library_map: Optional[dict[str, Any]] = None
        self._names: dict[str, str] = {}
        self._remapped: set[tuple[int, str]] = set()

    def add(self, name: str, abs_path: str) -> bool:
        """送る物に足す。同じ名前が別のファイルに使われている・数が多すぎるときは False（二重には送らない）。"""
        have = self._names.get(name)
        if have is not None:
            if os.path.normcase(have) != os.path.normcase(abs_path):
                self.warn(f"{name} is already used by another file; the second one is not sent")
                return False
            return True
        if len(self.assets) >= COLLECT_MAX:
            self.warn(f"more than {COLLECT_MAX} files; the rest are not sent")
            return False
        self._names[name] = abs_path
        self.assets.append((name, abs_path))
        return True

    def warn(self, text: str) -> None:
        if text not in self.warnings:
            self.warnings.append(text)

    def remap(self, block: Any, attr: str, new: str) -> None:
        key = (id(block), attr)
        if block is not None and key not in self._remapped:
            self._remapped.add(key)
            self.remaps.append(Remap(block, attr, new))

    def dep(self, kind: str, label: str, path: str, status: str, note: str = "", files: int = 0, size: int = 0,
            remapped: bool = False, warn: bool = True) -> None:
        self.deps.append({"kind": kind, "label": label, "path": path, "status": status, "note": note,
                          "files": files, "bytes": size, "remapped": remapped})
        if status == SKIP and warn:
            self.warn(f"{kind} {label}: {note}" + (f" ({path})" if path and path not in note else ""))

    def summary(self) -> str:
        send = [d for d in self.deps if d["status"] == SEND]
        files = sum(d["files"] for d in send)
        mb = sum(d["bytes"] for d in send) / 1048576.0
        packed = sum(1 for d in self.deps if d["status"] == PACKED)
        skipped = sum(1 for d in self.deps if d["status"] == SKIP)
        return f"{files} files to send ({mb:.1f} MB), {packed} inside the .blend, {skipped} not sent"


# ---- 名前と置き場 ------------------------------------------------------------

def relative_name(filepath: str) -> Optional[str]:
    """'//textures/wood.png' -> 'textures/wood.png'。.blend からの相対でなければ None。"""
    if not filepath or not filepath.startswith("//"):
        return None
    name = filepath[2:].replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    return name


def safe_segment(seg: str) -> str:
    """受付が受ける名前（英数字と . _ -）にする。数字は同じ場所に残すのでコマ番号はそのまま効く。<UDIM> も残す。"""
    parts = seg.split("<UDIM>")
    out = "<UDIM>".join(re.sub(r"[^A-Za-z0-9_.\-]", "_", p) for p in parts)[:120]
    return out if out.strip(".") else "_" + out


def accepted(name: str) -> bool:
    ext = os.path.splitext(name)[1].lower()
    if ext == ".gz":
        return name.lower().endswith(".bobj.gz")
    return ext in ACCEPTED_EXTENSIONS or ext in PRO_EXTENSIONS


def is_pro(name: str) -> bool:
    """旗 JR_PRO_ASSETS の受付だけが受ける型か。"""
    ext = os.path.splitext(name)[1].lower()
    return ext in PRO_EXTENSIONS and ext not in ACCEPTED_EXTENSIONS


def is_library(name: str) -> bool:
    """旗 JR_LINKED_BLEND の受付だけが受ける型（リンクした .blend）か。"""
    return os.path.splitext(name)[1].lower() in LIBRARY_EXTENSIONS


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _inside(path: str, folder: str) -> bool:
    p, f = _norm(path), _norm(folder)
    return p == f or p.startswith(f.rstrip("\\/") + os.sep)


def is_network_path(path: str) -> bool:
    p = path.replace("/", "\\")
    return p.startswith("\\\\") and not p.startswith("\\\\?\\")


def parse_roots(text: str) -> list[str]:
    """設定の Asset folders（; か改行で区切る）。"""
    return [r.strip().strip('"') for r in re.split(r"[;\n]", text or "") if r.strip().strip('"')]


class Places:
    """ファイルを取ってよい場所: .blend のフォルダと、本人が許したフォルダ。"""

    def __init__(self, blend_dir: str, roots: Iterable[str] = (), blend_stem: str = "") -> None:
        self.blend_dir = os.path.normpath(blend_dir) if blend_dir else ""
        self.blend_stem = blend_stem
        self.roots: list[str] = []
        self.root_problems: list[str] = []
        for r in roots:
            p = os.path.normpath(os.path.expanduser(r))
            if not os.path.isabs(p):
                self.root_problems.append(f"Asset folder {r}: use a full path")
            elif os.path.dirname(p.rstrip("\\/")) in ("", p.rstrip("\\/")) or _norm(p) == _norm(os.path.dirname(p)):
                self.root_problems.append(f"Asset folder {r}: a whole drive is too wide; list the project folders")
            elif not os.path.isdir(p):
                self.root_problems.append(f"Asset folder {r}: not found")
            else:
                self.roots.append(p)

    def abspath(self, filepath: str) -> Optional[str]:
        fp = (filepath or "").strip()
        if fp.startswith("//"):
            if not self.blend_dir:
                return None
            return os.path.normpath(os.path.join(self.blend_dir, fp[2:].replace("\\", "/")))
        if os.path.isabs(fp) or is_network_path(fp):
            return os.path.normpath(fp)
        return None

    def area(self, abs_path: str) -> tuple[str, str]:
        """('blend', 相対の場所) / ('root', 許したフォルダ) / ('', 送れない理由)。"""
        if self.blend_dir and _inside(abs_path, self.blend_dir):
            rel = os.path.relpath(abs_path, self.blend_dir).replace("\\", "/")
            return "blend", "" if rel == "." else rel
        for root in self.roots:
            if _inside(abs_path, root):
                return "root", root
        if is_network_path(abs_path):
            return "", "on a network share; add the share under Asset folders in the add-on preferences to send it"
        return "", ("outside the .blend folder; add its folder under Asset folders in the add-on preferences, "
                    "or move it next to the .blend")


def pack_folder(abs_dir: str) -> str:
    return f"{PACK_DIR}/{hashlib.sha1(_norm(abs_dir).encode('utf-8')).hexdigest()[:10]}"


def _same_path(a: str, b: str) -> bool:
    def n(x: str) -> str:
        x = x.replace("\\", "/")
        rel = x.startswith("//")
        x = os.path.normpath(x[2:] if rel else x).replace("\\", "/")
        return ("//" if rel else "") + ("" if x == "." else x)
    return n(a) == n(b)


def _stored_dir(filepath: str) -> str:
    """.blend の中の道のフォルダの部分（'//textures/a.png' -> '//textures'、'//a.png' -> '//'）。"""
    s = filepath.replace("\\", "/")
    if s.startswith("//"):
        return "//" + posixpath.dirname(s[2:])
    return posixpath.dirname(s)


def _why_not_rewritten(area: str, names_ok: bool, where: str) -> str:
    """道を書き換えられない物（点のキャッシュ・流体）が今の場所のままでは送れない理由。"""
    if area == "blend" and names_ok:
        return "its path is absolute; make it relative to the .blend (File > External Data > Make Paths Relative)"
    if area == "blend":
        return ("its file or folder names have characters the service does not take (letters, digits, . _ - and up to "
                "4 folders); rename them")
    return "outside the .blend folder; this kind of cache can only be sent from inside the .blend folder"         if area == "root" else where


def _add_files(acc: Collected, pairs: list[tuple[str, str]]) -> tuple[int, int]:
    sent = size = 0
    for n, p in pairs:
        if acc.add(n, p):
            sent += 1
            try:
                size += os.path.getsize(p)
            except OSError:
                pass
    return sent, size


def _note(*parts: str) -> str:
    return "; ".join(p for p in parts if p)


def _place_flat(acc: Collected, places: Places, kind: str, label: str, filepath: str, abs_dir: str,
                basenames: list[str], block: Any, attr: str, missing: int = 0, extra_note: str = "",
                is_dir: bool = False) -> None:
    """1 つのフォルダのファイル（1 枚・連番・UDIM）。``filepath`` は .blend の中の道（is_dir ならフォルダの道）。
    フォルダを書き換えるときもファイルの部分（コマ番号・<UDIM>）は残す。"""
    if not basenames:
        acc.dep(kind, label, filepath, SKIP, "file not found" if not missing else "no frames found on disk")
        return
    area, where = places.area(os.path.join(abs_dir, basenames[0]))
    if not area:
        acc.dep(kind, label, filepath, SKIP, where)
        return
    bad = [b for b in basenames if not accepted(b)]
    if bad:
        ext = os.path.splitext(bad[0])[1].lower() or "no extension"
        acc.dep(kind, label, filepath, SKIP, f"{ext} files are not accepted; pack the file into the .blend")
        return
    stored_base = "" if is_dir else posixpath.basename(filepath.replace("\\", "/"))
    stored_dir = filepath.replace("\\", "/") if is_dir else _stored_dir(filepath)
    names_ok = False
    if area == "blend":
        rel_dir = posixpath.dirname(os.path.relpath(os.path.join(abs_dir, basenames[0]), places.blend_dir).replace("\\", "/"))
        names = [f"{rel_dir}/{b}" if rel_dir else b for b in basenames]
        names_ok = all(NAME_RE.match(n) for n in names)
    if names_ok:
        new_dir = "//" + rel_dir
        rewrite = not _same_path(stored_dir, new_dir)
    else:
        new_dir = "//" + pack_folder(abs_dir)
        names = [f"{new_dir[2:]}/{safe_segment(b)}" for b in basenames]
        stored_base = safe_segment(stored_base) if stored_base else ""
        rewrite = True
    if rewrite and block is None:
        acc.dep(kind, label, filepath, SKIP, _why_not_rewritten(area, names_ok, where))
        return
    sent, size = _add_files(acc, [(n, os.path.join(abs_dir, b)) for b, n in zip(basenames, names)])
    if rewrite:
        acc.remap(block, attr, new_dir if is_dir else new_dir.rstrip("/") + "/" + stored_base)
    note = _note(extra_note, f"{missing} frame(s) of the range are not on disk" if missing else "",
                 f"from {where}" if area == "root" else "")
    acc.dep(kind, label, filepath, SEND, note, files=sent, size=size, remapped=rewrite)


def _place_tree(acc: Collected, places: Places, kind: str, label: str, filepath: str, abs_root: str,
                relfiles: list[str], block: Any, attr: str, prefix_sub: str = "") -> None:
    """1 つのフォルダの下のファイル（ベイク・流体）。``filepath`` はそのフォルダの道。``relfiles`` は abs_root/prefix_sub からの相対。"""
    if not relfiles:
        acc.dep(kind, label, filepath, SKIP, "nothing baked on disk", warn=False)
        return
    area, where = places.area(abs_root)
    if not area:
        acc.dep(kind, label, filepath, SKIP, where)
        return
    sub = f"{prefix_sub}/" if prefix_sub else ""
    names_ok = False
    if area == "blend":
        rel_root = os.path.relpath(abs_root, places.blend_dir).replace("\\", "/")
        rel_root = "" if rel_root == "." else rel_root
        names = [f"{rel_root}/{sub}{r}" if rel_root else f"{sub}{r}" for r in relfiles]
        names_ok = all(NAME_RE.match(n) for n in names)
    if names_ok:
        new_value = "//" + rel_root
        rewrite = not _same_path(filepath, new_value)
    else:
        folder = pack_folder(abs_root)
        names = [f"{folder}/{sub}" + "/".join(safe_segment(s) for s in r.split("/")) for r in relfiles]
        if not all(NAME_RE.match(n) for n in names):
            acc.dep(kind, label, filepath, SKIP, "the folder is nested too deep for the service (4 folders at most)")
            return
        new_value, rewrite = f"//{folder}", True
    if rewrite and block is None:
        acc.dep(kind, label, filepath, SKIP, _why_not_rewritten(area, names_ok, where))
        return
    base = os.path.join(abs_root, prefix_sub) if prefix_sub else abs_root
    sent, size = _add_files(acc, [(n, os.path.join(base, *r.split("/"))) for r, n in zip(relfiles, names)])
    if rewrite:
        acc.remap(block, attr, new_value)
    acc.dep(kind, label, filepath, SEND, f"from {where}" if area == "root" else "", files=sent, size=size, remapped=rewrite)


# ---- コマ ------------------------------------------------------------------------

def image_user_frame(cfra: int, duration: int, start: int, offset: int, cyclic: bool) -> int:
    """シーンのコマ ``cfra`` で画像の連番が見せるファイルの番号（Blender の BKE_image_user_frame_get と同じ）。"""
    length = int(duration)
    if length <= 0:
        return 0
    f = int(cfra) - int(start) + 1
    if cyclic:
        f %= length
        if f == 0:
            f = length
    if f < 0:
        f = 0
    elif f > length:
        f = length
    return f + int(offset)


def volume_frame(cfra: int, duration: int, start: int, offset: int, mode: str) -> Optional[int]:
    """シーンのコマ ``cfra`` での VDB の連番の番号（Blender の volume_sequence_frame）。CLIP で見えないコマは None。"""
    length = int(duration)
    if length <= 0:
        return None
    f = int(cfra) - int(start) + 1
    if mode == "CLIP":
        if f < 1 or f > length:
            return None
    elif mode == "EXTEND":
        f = min(max(f, 1), length)
    elif mode == "REPEAT":
        f %= length
        if f == 0:
            f = length
    elif mode == "PING_PONG":
        pp = length * 2 - 2
        if pp > 0:
            f %= pp
            if f == 0:
                f = pp
            if f > length:
                f = length * 2 - f
        else:
            f = 1
    return f + int(offset)


def split_sequence(basename: str) -> Optional[tuple[str, str, str]]:
    """'frame_0001.png' -> ('frame_', '0001', '.png'): 拡張子の前の最後の数字（Blender の BLI_path_sequence_decode）。
    数字が無ければ None。"""
    stem, ext = os.path.splitext(basename)
    m = re.match(r"^(.*?)(\d+)(\D*)$", stem)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3) + ext


def frame_name(basename: str, frame: int) -> Optional[str]:
    parts = split_sequence(basename)
    if parts is None:
        return None
    head, digits, tail = parts
    return f"{head}{frame:0{len(digits)}d}{tail}" if frame >= 0 else None


def sequence_on_disk(abs_dir: str, basename: str) -> list[str]:
    """abs_dir にある連番 ``basename`` の全部のファイル（番号の順）。"""
    parts = split_sequence(basename)
    if parts is None or not os.path.isdir(abs_dir):
        return []
    head, _digits, tail = parts
    rx = re.compile("^" + re.escape(head) + r"(\d+)" + re.escape(tail) + "$")
    found = []
    for f in os.listdir(abs_dir):
        m = rx.match(f)
        if m and os.path.isfile(os.path.join(abs_dir, f)):
            found.append((int(m.group(1)), f))
    return [f for _, f in sorted(found)][:COLLECT_MAX]


def _frames(frame_range: Optional[tuple[int, int]]) -> range:
    if not frame_range:
        return range(0)
    fs, fe = int(frame_range[0]), int(frame_range[1])
    if fe < fs:
        fe = fs
    return range(fs, min(fe, fs + FRAMES_MAX - 1) + 1)


def _frame_files(abs_dir: str, basename: str, numbers: Iterable[int]) -> tuple[list[str], int]:
    """(番号のうちディスクにあるファイル, 無かった数)。"""
    out, missing = [], 0
    for n in sorted(set(numbers)):
        f = frame_name(basename, n)
        if f and os.path.isfile(os.path.join(abs_dir, f)):
            out.append(f)
        else:
            missing += 1
    return out, missing


# ---- データブロック ------------------------------------------------------------------------

def _label(block: Any) -> str:
    return str(getattr(block, "name", "") or "?")


def _consider(block: Any, kind: str, places: Places, acc: Collected, attr: str = "filepath",
              frame_range: Optional[tuple[int, int]] = None, users: Optional[list] = None) -> None:
    filepath = str(getattr(block, "filepath", "") or "")
    label = _label(block)
    if not filepath or filepath.startswith("<"):            # "<builtin>" font
        return
    if getattr(block, "packed_file", None) is not None:      # パック済み: .blend の中に入って届く
        acc.dep(kind, label, filepath, PACKED)
        return
    if getattr(block, "library", None) is not None:
        return       # 11/9 夜（0.1.12）: リンクした .blend の中の物は _libraries が見る（ライブラリと一緒に送るか、理由を言う）
    source = str(getattr(block, "source", "FILE") or "FILE")
    if source in ("GENERATED", "VIEWER"):
        return
    abs_path = places.abspath(filepath)
    if abs_path is None:
        if filepath.startswith("//"):
            acc.dep(kind, label, filepath, SKIP, f"save the .blend first so {filepath} can be found")
        else:
            acc.dep(kind, label, filepath, SKIP, "relative path without // (Blender's working folder); make it relative to the .blend")
        return
    abs_dir, base = os.path.split(abs_path)
    area, where = places.area(abs_path)
    if not area:
        # 外の物は、あるかどうかより先に「外だから送らない」と言う（フォルダを許せば送れる）
        acc.dep(kind, label, filepath, SKIP, where)
        return
    if source == "TILED" or "<UDIM>" in base:
        tiles = sorted(glob.glob(os.path.join(glob.escape(abs_dir), glob.escape(base).replace("<UDIM>", "[0-9][0-9][0-9][0-9]"))))
        if not tiles:
            acc.dep("UDIM image", label, filepath, SKIP, f"no UDIM tiles found for {filepath}")
            return
        _place_flat(acc, places, "UDIM image", label, filepath, abs_dir, [os.path.basename(t) for t in tiles], block, attr)
        return
    sequence = source == "SEQUENCE" or bool(getattr(block, "is_sequence", False))
    if sequence:
        kind = f"{kind} sequence"
        if split_sequence(base) is None:
            acc.dep(kind, label, filepath, SKIP, "the file name has no frame number")
            return
        numbers: set[int] = set()
        if kind == "Volume sequence":
            for cfra in _frames(frame_range):
                n = volume_frame(cfra, getattr(block, "frame_duration", 0), getattr(block, "frame_start", 1),
                                 getattr(block, "frame_offset", 0), str(getattr(block, "sequence_mode", "CLIP")))
                if n is not None:
                    numbers.add(n)
        elif users:
            for cfra in _frames(frame_range):
                for duration, start, offset, cyclic in users:
                    numbers.add(image_user_frame(cfra, duration, start, offset, cyclic))
        if numbers:
            files, missing = _frame_files(abs_dir, base, numbers)
            note = f"frames {min(numbers)}-{max(numbers)} of the scene range"
            if not files:
                acc.dep(kind, label, filepath, SKIP, "none of the frames the scene uses are on disk")
                return
            # .blend に書いてあるコマ（多くは 1 コマ目）も送る。ワーカーは開いた後にこの道があるかで「足りないファイル」を
            # 数えるので、使わないコマでも無いと誤った警告になる（1 ファイルだけ）
            if base not in files and os.path.isfile(abs_path):
                files = sorted(files + [base], key=lambda f: int((split_sequence(f) or ("", "0", ""))[1]))
        else:
            files, missing = sequence_on_disk(abs_dir, base), 0
            note = "every frame in the folder (no user of this sequence found)" if files else ""
        _place_flat(acc, places, kind, label, filepath, abs_dir, files, block, attr, missing=missing, extra_note=note)
        return
    if not os.path.isfile(abs_path):
        acc.dep(kind, label, filepath, SKIP, f"file not found ({abs_path})")
        return
    _place_flat(acc, places, "Movie" if source == "MOVIE" else kind, label, filepath, abs_dir, [base], block, attr)


def _hex_names(owner: str) -> list[str]:
    """既定の点のキャッシュの名前は持ち主の名前の 16 進（1 文字ずつ ``%02X``）。x86 では char が符号付きなので 0x80 以上の
    バイトは FFFFFFxx になる。どちらの書き方にも合わせる。"""
    raw = owner.encode("utf-8")
    unsigned = "".join(f"{b:02X}" for b in raw)
    signed = "".join(f"{b:02X}" if b < 0x80 else f"{(b - 256) & 0xFFFFFFFF:08X}" for b in raw)
    return sorted({unsigned, signed})


def _point_cache(ref: Any, places: Places, acc: Collected) -> None:
    label = str(getattr(ref, "label", "") or "?")
    name = str(getattr(ref, "name", "") or "")
    if getattr(ref, "use_external", False):
        fp = str(getattr(ref, "filepath", "") or "")
        abs_dir = places.abspath(fp) if fp else None
        if not abs_dir or not os.path.isdir(abs_dir):
            acc.dep("Point cache", label, fp, SKIP, "external cache folder not found")
            return
        rx = re.compile("^" + re.escape(name) + r"_\d{6}(_\d{2})?\.bphys$")
        files = sorted(f for f in os.listdir(abs_dir) if rx.match(f))[:COLLECT_MAX]
        if not files:
            acc.dep("Point cache", label, fp, SKIP, "nothing cached in the external folder", warn=False)
            return
        _place_flat(acc, places, "Point cache", label, fp, abs_dir, files, None, "", is_dir=True)
        return
    if not getattr(ref, "use_disk_cache", False):
        if getattr(ref, "is_baked", False):
            acc.dep("Point cache", label, "", PACKED, "baked into the .blend")
        else:
            acc.dep("Point cache", label, "", SKIP, "not baked: the GPU simulates it again (bake it to keep this result)",
                    warn=False)
        return
    if not places.blend_dir or not places.blend_stem:
        acc.dep("Point cache", label, "", SKIP, "save the .blend first so its disk cache can be found")
        return
    folder = f"blendcache_{places.blend_stem}"
    abs_dir = os.path.join(places.blend_dir, folder)
    prefixes = [name] if name else _hex_names(str(getattr(ref, "owner", "") or ""))
    rx = re.compile("^(" + "|".join(re.escape(p) for p in prefixes) + r")_\d{6}_\d{2}\.bphys$")
    files = sorted(f for f in os.listdir(abs_dir) if rx.match(f))[:COLLECT_MAX] if os.path.isdir(abs_dir) else []
    if not files:
        acc.dep("Point cache", label, f"//{folder}/", SKIP, "nothing cached on disk: the GPU simulates it again", warn=False)
        return
    # ワーカーの写しは scene.blend なので Blender は //blendcache_scene/ を見る: そのフォルダの名前で送る
    names = [f"blendcache_{WORKER_SCENE_STEM}/{f}" for f in files]
    if not all(NAME_RE.match(n) for n in names):
        acc.dep("Point cache", label, f"//{folder}/", SKIP,
                "the cache name has characters the service does not take; rename the cache (letters, digits, . _ -)")
        return
    size = sent = 0
    for f, n in zip(files, names):
        p = os.path.join(abs_dir, f)
        if acc.add(n, p):
            sent += 1
            size += os.path.getsize(p)
    acc.dep("Point cache", label, f"//{folder}/", SEND, "", files=sent, size=size)


def _walk(abs_dir: str, exts: tuple[str, ...], depth: int = 3) -> list[str]:
    """abs_dir の下の、exts のどれかで終わるファイル（/ 区切りの相対）。``depth`` 段まで。"""
    out: list[str] = []
    if not os.path.isdir(abs_dir):
        return out
    base_depth = abs_dir.rstrip("\\/").count(os.sep)
    for root, dirs, files in os.walk(abs_dir):
        if root.rstrip("\\/").count(os.sep) - base_depth >= depth:
            dirs[:] = []
        dirs.sort()
        for f in sorted(files):
            if f.lower().endswith(exts):
                out.append(os.path.relpath(os.path.join(root, f), abs_dir).replace("\\", "/"))
                if len(out) >= COLLECT_MAX:
                    return out
    return out


def _bake(ref: Any, places: Places, acc: Collected) -> None:
    label = str(getattr(ref, "label", "") or "?")
    directory = str(getattr(ref, "directory", "") or "")
    if getattr(ref, "packed", False):
        acc.dep("Bake", label, "", PACKED, "baked into the .blend")
        return
    if not directory:
        acc.dep("Bake", label, "", SKIP, "not baked to disk", warn=False)
        return
    abs_root = places.abspath(directory)
    if abs_root is None:
        acc.dep("Bake", label, directory, SKIP, "save the .blend first so the bake folder can be found")
        return
    sub = str(getattr(ref, "sub", "") or "")
    relfiles = _walk(os.path.join(abs_root, sub) if sub else abs_root, (".json", ".blob"))
    _place_tree(acc, places, "Bake", label, directory, abs_root, relfiles, getattr(ref, "block", None),
                str(getattr(ref, "attr", "") or ""), prefix_sub=sub)


def _fluid(ref: Any, places: Places, acc: Collected) -> None:
    label = str(getattr(ref, "label", "") or "?")
    directory = str(getattr(ref, "directory", "") or "")
    abs_root = places.abspath(directory) if directory else None
    if abs_root is None or not os.path.isdir(abs_root):
        acc.dep("Fluid cache", label, directory, SKIP, "cache folder not found (bake the domain, or make its path relative)",
                warn=bool(getattr(ref, "baked", True)))
        return
    relfiles: list[str] = []
    for sub in FLUID_SUBDIRS:
        relfiles += [f"{sub}/{r}" for r in _walk(os.path.join(abs_root, sub), (".uni", ".vdb", ".bobj.gz", ".obj"), depth=1)]
    if not relfiles:
        acc.dep("Fluid cache", label, directory, SKIP, "nothing baked in the cache folder", warn=False)
        return
    # キャッシュのフォルダは書き換えない（変えると Blender がドメインのキャッシュを捨てる）。.blend のフォルダの中で、
    # 受付が受ける名前のときだけ送る
    area, where = places.area(abs_root)
    if area != "blend":
        acc.dep("Fluid cache", label, directory, SKIP, where if not area else
                "outside the .blend folder; a fluid cache can only be sent from inside the .blend folder")
        return
    _place_tree(acc, places, "Fluid cache", label, directory, abs_root, relfiles, None, "")


# ---- リンクした .blend（11/9 夜、0.1.12。受付の旗 JR_LINKED_BLEND） -------------------------------------

def _lib_id(lib: Any) -> str:
    """ライブラリを見分ける名前（bpy は同じ ID でも取るたびに別の Python の物を返すので id() は使えない）。"""
    return str(getattr(lib, "name_full", "") or getattr(lib, "name", "") or id(lib))


def _owned_abs(filepath: str, lib_abs: str) -> Optional[str]:
    """リンクした .blend の中の道（相対はそのライブラリの .blend からの相対）を手元の絶対の道に。"""
    fp = (filepath or "").strip()
    if fp.startswith("//"):
        return os.path.normpath(os.path.join(os.path.dirname(lib_abs), fp[2:].replace("\\", "/")))
    if os.path.isabs(fp) or is_network_path(fp):
        return os.path.normpath(fp)
    return None


def _libraries(acc: Collected, places: Places, libraries: list[Any], owned: list[tuple[str, Any]], blend_path: str,
               sha_of: Optional[Callable[[str], str]] = None) -> None:
    """リンクした .blend（入れ子も。Blender は bpy.data.libraries に全部並べ、入れ子は parent が付く）と、その中の画像などを送る物に
    足す。置き場と付け替えは libplan（CLI と同じファイル）。.blend のフォルダの外のライブラリは、画像と同じく Asset folders に
    書いたフォルダからだけ送る。シーンが直接読むライブラリの道は送る写しの中だけ書き換え（remaps）、入れ子の付け替えは
    jr_libraries.json（acc.library_map）でワーカーに渡す。"""
    if not libraries and not owned:
        return
    plan = libplan.Plan(blend_path, sha_of=sha_of, rewrite_direct=True)
    where_of: dict[str, str] = {}      # _lib_id → 手元の絶対の道（送ってよい場所のもの）
    for lib in libraries:
        fp = str(getattr(lib, "filepath", "") or "")
        label = _label(lib)
        if getattr(lib, "packed_file", None) is not None:
            acc.dep("Library", label, fp, PACKED)
            continue
        ab = places.abspath(fp)
        if ab is None:
            acc.dep("Library", label, fp, SKIP, f"save the .blend first so {fp} can be found" if fp.startswith("//") else
                    "relative path without // (Blender's working folder); make it relative to the .blend")
            continue
        area, where = places.area(ab)
        if not area:
            acc.dep("Library", label, fp, SKIP, where)
            continue
        where_of[_lib_id(lib)] = ab
    blocks: dict[str, Any] = {}
    owned_rows: list[tuple[str, str, str, str, list[str]]] = []   # (種類, 名前, 道, ライブラリの名前, 手元のファイル)
    for lib in libraries:
        ab = where_of.get(_lib_id(lib))
        if ab is None:
            continue
        parent = getattr(lib, "parent", None)
        pab = where_of.get(_lib_id(parent)) if parent is not None else None
        if parent is not None and pab is None:
            acc.dep("Library", _label(lib), str(lib.filepath), SKIP, f"linked from {_label(parent)}, which is not sent")
            continue
        blocks[libplan._norm(ab)] = lib
        plan.add_library(ab, libplan.as_written(str(lib.filepath), ab, pab) if parent is not None else str(lib.filepath), pab)
    for kind, block in owned:
        lib = getattr(block, "library", None)
        lab = where_of.get(_lib_id(lib))
        fp = str(getattr(block, "filepath", "") or "")
        label = _label(block)
        if not fp or fp.startswith("<") or getattr(block, "packed_file", None) is not None:
            continue                                      # パック済み: ライブラリの .blend の中に入って届く
        if str(getattr(block, "source", "FILE") or "FILE") in ("GENERATED", "VIEWER"):
            continue
        if lab is None:
            acc.dep(kind, label, fp, SKIP, "linked from a library that is not sent")
            continue
        ab = _owned_abs(fp, lab)
        if ab is None:
            acc.dep(kind, label, fp, SKIP, "relative path without // inside a linked .blend")
            continue
        area, where = places.area(ab)
        if not area:
            acc.dep(kind, label, fp, SKIP, f"inside the linked .blend {_label(lib)}: {where}")
            continue
        source = str(getattr(block, "source", "FILE") or "FILE")
        if source == "SEQUENCE" or bool(getattr(block, "is_sequence", False)):
            acc.dep(kind, label, fp, SKIP, f"a sequence inside the linked .blend {_label(lib)} is not sent; pack it into that "
                                           "library or make the data local")
            continue
        if source == "TILED" or "<UDIM>" in fp:
            base = os.path.basename(ab)
            tiles = sorted(glob.glob(os.path.join(glob.escape(os.path.dirname(ab)),
                                                  glob.escape(base).replace("<UDIM>", "[0-9][0-9][0-9][0-9]"))))
            ref_dir = _stored_dir(fp)
            for t in tiles:
                plan.add_dependency(t, ref_dir.rstrip("/") + "/" + os.path.basename(t), lab)
            if not tiles:
                acc.dep("UDIM image", label, fp, SKIP, f"no UDIM tiles found for {fp}")
            else:
                owned_rows.append(("UDIM image", label, fp, _label(lib), tiles))
            continue
        plan.add_dependency(ab, fp, lab)
        owned_rows.append((kind, label, fp, _label(lib), [ab]))
    plan.solve()
    for name, ab in plan.files:
        acc.add(name, ab)
    sent = {libplan._norm(p): n for n, p in plan.files}
    for n, lib in blocks.items():
        name = sent.get(n)
        if name is None:
            continue
        new = plan.direct.get(plan._libs.get(n, ""))
        if new:
            acc.remap(lib, "filepath", new)
        try:
            size = os.path.getsize(plan._libs[n])
        except OSError:
            size = 0
        nested = getattr(lib, "parent", None) is not None
        acc.dep("Library", _label(lib), str(lib.filepath), SEND, ("linked from " + _label(lib.parent)) if nested else "",
                files=1, size=size, remapped=bool(new) or name in plan.remaps.values())
    for kind, label, fp, lib_label, files in owned_rows:
        got = [f for f in files if libplan._norm(f) in sent]
        if got and len(got) == len(files):
            size = sum(os.path.getsize(f) for f in got if os.path.isfile(f))
            acc.dep(kind, label, fp, SEND, f"inside the linked .blend {lib_label}", files=len(got), size=size)
    for path, why in plan.problems:
        acc.dep("Linked file", path or "linked .blend", path, SKIP, why)
    acc.library_map = plan.map_document()


def collect(images: Iterable[Any] = (), fonts: Iterable[Any] = (), cache_files: Iterable[Any] = (),
            blend_dir: str = "", libraries: Iterable[Any] = (), others: Iterable[tuple[str, Any]] = (),
            volumes: Iterable[Any] = (), movieclips: Iterable[Any] = (), point_caches: Iterable[Any] = (),
            bakes: Iterable[Any] = (), fluids: Iterable[Any] = (), roots: Iterable[str] = (), blend_stem: str = "",
            frame_range: Optional[tuple[int, int]] = None,
            image_users: Optional[dict[str, list[tuple[int, int, int, bool]]]] = None,
            blend_path: str = "", sha_of: Optional[Callable[[str], str]] = None) -> Collected:
    """渡したデータブロックを見る。``others`` は知らせるだけの (種類, ブロック)。``image_users`` は画像の名前 →
    使っている所ごとの (frame_duration, frame_start, frame_offset, use_cyclic)。
    11/9 夜（0.1.12）: ``libraries``（bpy.data.libraries、入れ子も）と、その中の画像などは _libraries が送る物に足す。
    ``blend_path`` は開いている .blend の道、``sha_of`` は jr_libraries.json に書く sha256 を出す関数（無ければ書かない）。"""
    images, fonts, cache_files = list(images), list(fonts), list(cache_files)
    volumes, movieclips = list(volumes), list(movieclips)
    acc = Collected()
    places = Places(blend_dir, roots, blend_stem)
    for p in places.root_problems:
        acc.warn(p)
    users = image_users or {}
    for img in images:
        _consider(img, "Image", places, acc, attr="filepath_raw", frame_range=frame_range,
                  users=users.get(str(getattr(img, "name_full", "") or _label(img))) or users.get(_label(img)))
    for font in fonts:
        _consider(font, "Font", places, acc)
    for cf in cache_files:
        _consider(cf, "Cache file", places, acc)
    for vol in volumes:
        _consider(vol, "Volume", places, acc, frame_range=frame_range)
    for clip in movieclips:
        _consider(clip, "Movie clip", places, acc)
    seen_pc: set[tuple[str, str, str]] = set()
    for pc in point_caches:
        key = (str(getattr(pc, "owner", "")), str(getattr(pc, "name", "")), str(getattr(pc, "filepath", "")))
        if key not in seen_pc:
            seen_pc.add(key)
            _point_cache(pc, places, acc)
    for b in bakes:
        _bake(b, places, acc)
    for fl in fluids:
        _fluid(fl, places, acc)
    owned = [(k, b) for k, blocks in (("Image", images), ("Font", fonts), ("Cache file", cache_files), ("Volume", volumes),
                                      ("Movie clip", movieclips)) for b in blocks if getattr(b, "library", None) is not None]
    if not blend_path and blend_dir:
        blend_path = os.path.join(blend_dir, (blend_stem or "scene") + ".blend")
    _libraries(acc, places, list(libraries), owned, blend_path, sha_of)
    for label, block in others:
        fp = str(getattr(block, "filepath", "") or "")
        if fp and getattr(block, "packed_file", None) is None:
            acc.dep(label, _label(block), fp, SKIP, f"not sent ({fp})")
    return acc


# ---- bpy -----------------------------------------------------------------------------------

def image_users_from_bpy(data: Any) -> dict[str, list[tuple[int, int, int, bool]]]:
    """画像ごとに、それを見せるノード・テクスチャ・画像のエンプティのコマの設定。"""
    out: dict[str, list[tuple[int, int, int, bool]]] = {}

    def add(img: Any, iu: Any) -> None:
        if img is None or iu is None:
            return
        try:
            item = (int(iu.frame_duration), int(iu.frame_start), int(iu.frame_offset), bool(iu.use_cyclic))
        except (AttributeError, TypeError, ValueError):
            return
        out.setdefault(str(getattr(img, "name_full", "") or img.name), []).append(item)

    trees = []
    for coll in ("materials", "worlds", "lights", "textures", "linestyles"):
        for idb in getattr(data, coll, ()) or ():
            nt = getattr(idb, "node_tree", None)
            if nt is not None:
                trees.append(nt)
    trees += list(getattr(data, "node_groups", ()) or ())
    for sc in getattr(data, "scenes", ()) or ():
        for attr in ("node_tree", "compositing_node_group"):
            nt = getattr(sc, attr, None)
            if nt is not None:
                trees.append(nt)
    for nt in trees:
        for node in getattr(nt, "nodes", ()) or ():
            add(getattr(node, "image", None), getattr(node, "image_user", None))
    for tex in getattr(data, "textures", ()) or ():
        if getattr(tex, "type", "") == "IMAGE":
            add(getattr(tex, "image", None), getattr(tex, "image_user", None))
    for ob in getattr(data, "objects", ()) or ():
        if getattr(ob, "type", "") == "EMPTY" and getattr(ob, "empty_display_type", "") == "IMAGE":
            add(getattr(ob, "data", None), getattr(ob, "image_user", None))
    return out


class _Ref:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


def _pc_ref(ob: Any, label: str, pc: Any) -> Optional[_Ref]:
    if pc is None:
        return None
    return _Ref(label=f"{ob.name} / {label}", owner=ob.name, use_disk_cache=bool(pc.use_disk_cache),
                use_external=bool(pc.use_external), filepath=str(pc.filepath or ""), name=str(pc.name or ""),
                is_baked=bool(pc.is_baked))


def simulations_from_bpy(data: Any) -> tuple[list[Any], list[Any], list[Any]]:
    """ローカルのオブジェクトの (点のキャッシュ, ジオメトリノードのベイク, 流体のドメイン)。"""
    caches: list[Any] = []
    bakes: list[Any] = []
    fluids: list[Any] = []
    for ob in getattr(data, "objects", ()) or ():
        if getattr(ob, "library", None) is not None:
            continue
        for mod in getattr(ob, "modifiers", ()) or ():
            t = getattr(mod, "type", "")
            try:
                if t in ("CLOTH", "SOFT_BODY"):
                    caches.append(_pc_ref(ob, mod.name, mod.point_cache))
                elif t == "PARTICLE_SYSTEM":
                    caches.append(_pc_ref(ob, mod.name, mod.particle_system.point_cache))
                elif t == "DYNAMIC_PAINT" and getattr(mod, "canvas_settings", None) is not None:
                    for s in mod.canvas_settings.canvas_surfaces:
                        caches.append(_pc_ref(ob, f"{mod.name} / {s.name}", s.point_cache))
                elif t == "NODES":
                    for b in getattr(mod, "bakes", ()) or ():
                        target = str(getattr(b, "bake_target", "INHERIT"))
                        if target == "INHERIT":
                            target = str(getattr(mod, "bake_target", "PACKED"))
                        label = f"{ob.name} / {mod.name}"
                        if getattr(b, "use_custom_path", False):
                            bakes.append(_Ref(label=label, packed=target == "PACKED", directory=str(b.directory or ""),
                                              sub="", block=b, attr="directory"))
                        else:
                            bakes.append(_Ref(label=label, packed=target == "PACKED",
                                              directory=str(mod.bake_directory or ""), sub=str(b.bake_id),
                                              block=mod, attr="bake_directory"))
                elif t == "FLUID" and getattr(mod, "fluid_type", "") == "DOMAIN":
                    ds = mod.domain_settings
                    fluids.append(_Ref(label=f"{ob.name} / {mod.name}", directory=str(ds.cache_directory or ""),
                                       baked=bool(getattr(ds, "has_cache_baked_any", True))))
            except (AttributeError, TypeError):
                continue
    return [c for c in caches if c is not None], bakes, fluids


def collect_from_bpy(scene: Any = None, roots: Iterable[str] = ()) -> Collected:
    import bpy

    data = bpy.data
    blend_dir = os.path.dirname(data.filepath) if data.filepath else ""
    stem = os.path.splitext(os.path.basename(data.filepath))[0] if data.filepath else ""
    scene = scene if scene is not None else getattr(bpy.context, "scene", None)
    frame_range = (int(scene.frame_start), int(scene.frame_end)) if scene is not None and hasattr(scene, "frame_start") else None
    caches, bakes, fluids = simulations_from_bpy(data)
    others = [("Sound", b) for b in getattr(data, "sounds", ()) or ()]
    from .client import cached_sha256      # jr_libraries.json の sha256（素材の照合と同じ控えを使う）
    return collect(images=data.images, fonts=data.fonts, cache_files=getattr(data, "cache_files", ()),
                   volumes=getattr(data, "volumes", ()), movieclips=getattr(data, "movieclips", ()),
                   blend_dir=blend_dir, blend_stem=stem, libraries=data.libraries, others=others,
                   point_caches=caches, bakes=bakes, fluids=fluids, roots=roots, frame_range=frame_range,
                   image_users=image_users_from_bpy(data), blend_path=data.filepath or "", sha_of=cached_sha256)


def apply_remaps(remaps: Iterable[Remap]) -> list[tuple[Any, str, Any]]:
    """写しのために道を書き換える。restore_remaps() に渡す物を返す。途中で失敗したら全部元に戻す。"""
    done: list[tuple[Any, str, Any]] = []
    try:
        for r in remaps:
            old = getattr(r.block, r.attr)
            setattr(r.block, r.attr, r.new)
            done.append((r.block, r.attr, old))
    except Exception:
        restore_remaps(done)
        raise
    return done


def restore_remaps(done: list[tuple[Any, str, Any]]) -> None:
    for block, attr, old in reversed(done):
        try:
            setattr(block, attr, old)
        except Exception:  # noqa: BLE001 - 残りも戻す
            pass
