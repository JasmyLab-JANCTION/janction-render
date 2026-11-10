"""リンクした .blend（ライブラリ）を送る置き場と、ワーカーでの付け替えの組を決める（11/9 夜、受付の旗 JR_LINKED_BLEND）。

アドオン（addons/blender/janction_render/libplan.py）と CLI（janction_render/libplan.py）は同じファイル（tests/test_linked_blend_1109.py
が 1 字も違わないかを見る）。bpy も受付も読まない（標準のライブラリだけ）。

置き場（受付は素材をシーンの隣に名前のまま置き、ワーカーはシーンを scene.blend として開く）:
  - シーンの .blend のフォルダの中の物: そのフォルダからの相対の名前のまま（//lib/x.blend は lib/x.blend）。相対の道はそのまま解ける
  - 外の物（絶対の道・//../ で外へ出る道）: 相対の道でつながる物（ライブラリとそれが読むライブラリ・画像）を 1 つの組にし、組の
    共通のフォルダを lib/<そのフォルダの道の hash 10 桁>/ に写す（同じ並び）。組の中の相対の道は付け替えなしで解ける。名前の決まり
    （英数字と . _ -、フォルダ 4 段まで）に合わない物は、ライブラリなら lib/<自分のフォルダの hash>/<名前> に置いて付け替える。
    画像などは付け替えられない（リンクしたデータは開いた後に変えられない）ので送らずに理由を返す
付け替え（remaps）: 置いた場所で解けないライブラリの参照（絶対の道・並びを保てなかった相対の道）だけ、ワーカーの Blender が見せる道の
形（lib_key）→ 置いた名前の組にする。送り手は jr_libraries.json（MAP_NAME）に書いて素材として送る。ワーカー（caps.linked_blend）は
.blend を --disable-autoexec で開いた後、見つからないライブラリの道をこの組で付け替えて読み直す。入れ子のライブラリは親を読み直した
後に現れるので、変わらなくなるまで繰り返す。入れ子の相対の道を Blender はシーンのフォルダからの相対に直して見せる（5.2 で実測:
lib/h1/lib1.blend の //../../shared/lib2.blend は //shared/lib2.blend）ので、鍵は親を置いた場所から計算する（worker_ref）。
"""
import hashlib
import os
import posixpath
import re
from typing import Any, Callable, Optional

LIB_DIR = "lib"
MAP_NAME = "jr_libraries.json"
MAP_VERSION = 1
MAX_REMAPS = 200
NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}(/[A-Za-z0-9_.\-]{1,120}){0,4}$")
_DRIVE = re.compile(r"^([A-Za-z]):/")
# ワーカーがシーン本体に使う名前。素材がこれを上書きしないように一番上の階層では使わない
RESERVED_TOP = ("scene.blend",)


def lib_key(path: Any) -> str:
    """ライブラリの道を比べる形（ワーカーの式・受付・送り手で同じ）。区切りは /、. と .. をたたむ。.blend からの相対（//）は大小を
    そのまま、絶対の道は小文字（C:\\a は /c/a、Linux の Blender が見せる形にもそろえる）。UNC（\\\\server\\share）は unc: を付ける。"""
    raw = str(path or "")
    s = raw.replace("\\", "/").strip()
    if raw.startswith("//"):
        rest = posixpath.normpath(s[2:]) if s[2:] else ""
        return "//" + ("" if rest == "." else rest)
    unc = raw.startswith("\\\\")
    m = _DRIVE.match(s)
    if m:
        s = "/" + m.group(1).lower() + "/" + s[3:]
    s = posixpath.normpath(s).lower() if s else ""
    return ("unc:" + s) if unc else s


def is_relative(ref: Any) -> bool:
    return str(ref or "").startswith("//")


def worker_ref(ref: str, parent_name: str) -> str:
    """親（parent_name はワーカーで置かれる名前、"" はシーン）が ref で読むライブラリを、ワーカーの Blender が見せる道の形（lib_key）に。"""
    if is_relative(ref):
        rel = ref[2:].replace("\\", "/")
        base = posixpath.dirname(parent_name)
        return lib_key("//" + (posixpath.join(base, rel) if base else rel))
    return lib_key(ref)


def safe_segment(seg: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_.\-]", "_", seg)[:120]
    return out if out.strip(".") else "_" + out


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _inside(path: str, folder: str) -> bool:
    p, f = _norm(path), _norm(folder)
    return p == f or p.startswith(f.rstrip("\\/") + os.sep)


def folder_hash(abs_dir: str) -> str:
    return hashlib.sha1(_norm(abs_dir).encode("utf-8")).hexdigest()[:10]


def name_ok(name: str) -> bool:
    return bool(NAME_RE.match(name)) and ".." not in name.split("/") and name.lower() not in RESERVED_TOP


class Plan:
    """ライブラリと、ライブラリが読むファイルを集めて（add_library・add_dependency）、solve() で置き場と付け替えを決める。

    結果: files（[(送る名前, 手元の道)]）、remaps（{ワーカーの道の形: 置いた名前}）、direct（シーンが直接読むライブラリのうち、
    置いた場所で解けない物の {手元の道: 写しに書く //名前}。アドオンは写しの中で書き換え、remaps には入れない）、
    problems（[(道, 理由)]）、sha256（{置いた名前: sha256}、ライブラリだけ）。"""

    def __init__(self, scene_path: str, sha_of: Optional[Callable[[str], str]] = None, rewrite_direct: bool = False) -> None:
        self.scene_path = os.path.normpath(scene_path) if scene_path else ""
        self.scene_dir = os.path.dirname(self.scene_path) if self.scene_path else ""
        self.sha_of = sha_of
        self.rewrite_direct = rewrite_direct
        self._libs: dict[str, str] = {}                        # _norm → 手元の道（ライブラリ）
        self._edges: list[tuple[Optional[str], str, str]] = []  # (親の _norm か None, ref, 子の _norm)
        self._deps: list[tuple[str, str, str]] = []            # (持ち主の _norm, ref, 手元の道)
        self.files: list[tuple[str, str]] = []
        self.names: dict[str, str] = {}                        # _norm → 置いた名前
        self.remaps: dict[str, str] = {}
        self.direct: dict[str, str] = {}
        self.problems: list[tuple[str, str]] = []
        self.sha256: dict[str, str] = {}
        self._by_name: dict[str, str] = {}

    # ---- 集める ---------------------------------------------------------------

    def add_library(self, abs_path: str, ref: str, parent_abs: Optional[str] = None) -> None:
        """parent_abs（None はシーン）が ref（親の .blend に書かれた形）で読むライブラリ abs_path。"""
        abs_path = os.path.normpath(abs_path)
        if self.scene_path and _norm(abs_path) == _norm(self.scene_path):
            return                                            # シーン自身へのリンク（ワーカーでも scene.blend で解ける）
        if not os.path.isfile(abs_path):
            self._problem(ref or abs_path, "linked .blend not found on this computer")
            return
        self._libs.setdefault(_norm(abs_path), abs_path)
        self._edges.append((_norm(parent_abs) if parent_abs else None, str(ref or ""), _norm(abs_path)))

    def add_dependency(self, abs_path: str, ref: str, owner_abs: str) -> None:
        """ライブラリ owner_abs が ref（そのライブラリに書かれた形）で読むファイル（画像・フォントなど）。"""
        self._deps.append((_norm(owner_abs), str(ref or ""), os.path.normpath(abs_path)))

    def _problem(self, path: str, why: str) -> None:
        item = (str(path), why)
        if item not in self.problems:
            self.problems.append(item)

    # ---- 決める ---------------------------------------------------------------

    def _scene_name(self, abs_path: str) -> Optional[str]:
        if not self.scene_dir or not _inside(abs_path, self.scene_dir):
            return None
        rel = os.path.relpath(abs_path, self.scene_dir).replace("\\", "/")
        return rel if name_ok(rel) else None

    def _groups(self) -> dict[str, list[str]]:
        """外の物を、相対の道でつながる組に分ける（union-find）。{組の代表: [手元の道]}。"""
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        outside = {n: p for n, p in self._libs.items() if self._scene_name(p) is None}
        for n in outside:
            find(n)
        for par, ref, child in self._edges:
            if par is not None and par in outside and child in outside and is_relative(ref):
                union(par, child)
        for owner, ref, dep in self._deps:
            if owner in outside and is_relative(ref) and self._scene_name(dep) is None and os.path.isfile(dep):
                outside.setdefault(_norm(dep), dep)
                union(owner, _norm(dep))
        groups: dict[str, list[str]] = {}
        for n, p in outside.items():
            groups.setdefault(find(n), []).append(p)
        return groups

    def _take(self, name: str, abs_path: str) -> bool:
        """name で送る物に足す。同じ名前が別のファイルに使われていれば False。"""
        have = self._by_name.get(name)
        if have is not None:
            return _norm(have) == _norm(abs_path)
        self._by_name[name] = abs_path
        self.files.append((name, abs_path))
        self.names[_norm(abs_path)] = name
        return True

    def _drop(self, n: str) -> None:
        name = self.names.pop(n, None)
        if name is not None and name in self._by_name:
            del self._by_name[name]
            self.files = [(a, b) for a, b in self.files if a != name]

    def solve(self) -> "Plan":
        self._by_name = {}
        # 1) シーンのフォルダの中のライブラリ（相対の名前のまま）
        for n, p in self._libs.items():
            name = self._scene_name(p)
            if name is not None:
                self._take(name, p)
        # 2) 外のライブラリ: 相対の道でつながる組ごとに、共通のフォルダを lib/<hash>/ に同じ並びで。合わない物は自分のフォルダへ
        dep_names: dict[str, str] = {}
        for members in self._groups().values():
            try:
                root = os.path.commonpath([os.path.dirname(m) for m in members])
            except ValueError:                                # 別のドライブ（相対の道ではつながらない）
                root = ""
            prefix = f"{LIB_DIR}/{folder_hash(root)}/" if root else ""
            for m in members:
                name = (prefix + os.path.relpath(m, root).replace("\\", "/")) if root else ""
                if _norm(m) not in self._libs:
                    if name and name_ok(name):
                        dep_names[_norm(m)] = name            # 画像など: 持ち主が送れると決まってから送る（4）
                    continue
                if name and name_ok(name) and self._take(name, m):
                    continue
                own = f"{LIB_DIR}/{folder_hash(os.path.dirname(m))}/{safe_segment(os.path.basename(m))}"
                if not self._take(own, m):
                    self._take(f"{LIB_DIR}/{folder_hash(m)}/{safe_segment(os.path.basename(m))}", m)
        # 3) ライブラリの参照（シーンから順に）: 置いた場所で解けなければ付け替え。送れない親の子は送らない
        sent: set[str] = set()
        remaining = list(self._edges)
        while remaining:
            later = [e for e in remaining if e[0] is not None and e[0] not in sent]
            now = [e for e in remaining if not (e[0] is not None and e[0] not in sent)]
            if not now:
                for _par, ref, _child in later:
                    self._problem(ref, "the linked .blend that links it could not be sent")
                break
            for par, ref, child in now:
                child_name = self.names.get(child)
                if child_name is None:
                    self._problem(ref, "could not be placed for sending")
                    continue
                sent.add(child)
                key = worker_ref(ref, "" if par is None else self.names.get(par, ""))
                if key == lib_key("//" + child_name):
                    continue                                  # 置いた場所でそのまま解ける
                if par is None and self.rewrite_direct:
                    self.direct[self._libs[child]] = "//" + child_name
                    continue
                have = self.remaps.get(key)
                if have is not None and have != child_name:
                    self._problem(ref, "another linked .blend resolves to the same path on the GPU; rename one of them")
                    continue
                self.remaps[key] = child_name
            remaining = later
        for n in list(self._libs):
            if n not in sent:
                self._drop(n)
        # 4) ライブラリが読むファイル: 持ち主の置き場から相対の道で同じ並びに置けたものだけ（付け替えはできない）
        for owner, ref, dep in self._deps:
            owner_name = self.names.get(owner)
            if owner not in sent or owner_name is None:
                continue
            if not os.path.isfile(dep):
                self._problem(ref or dep, "a file a linked .blend uses was not found on this computer")
                continue
            if not is_relative(ref):
                self._problem(ref, "absolute path inside a linked .blend: open that library, make its paths relative "
                                   "(File > External Data > Make Paths Relative) and save it")
                continue
            want = posixpath.normpath(posixpath.join(posixpath.dirname(owner_name), ref[2:].replace("\\", "/")))
            name = self._scene_name(dep) or dep_names.get(_norm(dep))
            if name is None or name != want or not self._take(name, dep):
                self._problem(ref, "used by a linked .blend but outside the folders sent with it; keep it next to that "
                                   "library (or in a folder below it) with a relative path")
        if len(self.remaps) > MAX_REMAPS:
            self._problem("", f"more than {MAX_REMAPS} linked .blend paths need remapping; only the first {MAX_REMAPS} are sent")
            self.remaps = dict(list(self.remaps.items())[:MAX_REMAPS])
        if self.sha_of is not None:
            for name, p in self.files:
                if _norm(p) in self._libs:
                    try:
                        self.sha256[name] = self.sha_of(p)
                    except OSError:
                        pass
        return self

    # ---- 送る形 ---------------------------------------------------------------

    def library_names(self) -> list[str]:
        return [n for n, p in self.files if _norm(p) in self._libs]

    def map_document(self) -> Optional[dict[str, Any]]:
        """jr_libraries.json の中身（付け替えが無ければ None＝送らない）。"""
        if not self.remaps:
            return None
        rows = []
        for key, name in self.remaps.items():
            row = {"path": key, "asset": name}
            if self.sha256.get(name):
                row["sha256"] = self.sha256[name]
            rows.append(row)
        return {"version": MAP_VERSION, "libraries": rows}


def as_written(shown: str, abs_path: str, parent_abs: Optional[str]) -> str:
    """アドオン用: Blender が見せる入れ子のライブラリの道（相対はシーンからの相対に直してある）を、親の .blend に書かれた形に戻す。"""
    if parent_abs and is_relative(shown):
        try:
            return "//" + os.path.relpath(abs_path, os.path.dirname(parent_abs)).replace("\\", "/")
        except ValueError:
            return shown
    return shown

