"""受付を呼ぶ側の共通部分。MCP とコマンドの両方がこれを使う（要件 F-01）。

環境変数:
    JANCTION_RENDER_SERVER   受付の URL（既定 http://127.0.0.1:8340）
    JANCTION_RENDER_API_KEY  API キー。無ければ受付に一時キーをもらい ~/.janction-render.json に覚える
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests

DEFAULT_SERVER = "http://127.0.0.1:8340"
CACHE = Path.home() / ".janction-render.json"

# 送れるシーン: .blend、bpy スクリプト、こちらの Blender が読み込める 3D ファイル
SCENE_SUFFIXES = (".blend", ".py", ".fbx", ".glb", ".gltf", ".obj", ".stl", ".ply", ".usd", ".usda", ".usdc", ".usdz", ".abc")
ONLY_CHOICES = ("all", "mp4", "frames", "sheet", "output")


def select_artifacts(artifacts: list[dict[str, Any]], only: Optional[str] = None) -> list[dict[str, Any]]:
    """成果物の絞り込み: all / mp4（output.mp4 だけ）/ frames（PNG のコマだけ）/ sheet（4 コマ並べだけ）/ output（mp4 か sheet）。"""
    o = (only or "all").strip().lower()
    if o in ("", "all"):
        return list(artifacts)
    if o == "mp4":
        return [a for a in artifacts if a["name"].endswith(".mp4")]
    if o == "frames":
        return [a for a in artifacts if a["name"].startswith("frame_")]
    if o == "sheet":
        return [a for a in artifacts if a["name"] == "sheet.png"]
    if o == "output":
        picked = [a for a in artifacts if a["name"] in ("output.mp4", "sheet.png")]
        return picked or [a for a in artifacts if a["name"].startswith("frame_")][:1]
    raise ValueError("only must be one of: " + ", ".join(ONLY_CHOICES))


def sha256_of(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def trace_blend_assets(blend: Path) -> tuple[list[tuple[str, Path]], list[str]]:
    """.blend が参照する外部ファイル（画像・ライブラリなど）を手元で調べる（blender-asset-tracer があるとき）。

    返すのは ([(送るときの名前, 場所)], [見つからなかったパス])。名前は .blend からの相対パス（//textures/a.png → textures/a.png）。
    .blend の外（上の階層や絶対パス）にあるものは送れないので「見つからなかった」に入れる。
    """
    try:
        from blender_asset_tracer import trace  # type: ignore
    except Exception:  # noqa: BLE001 — 入っていなければ調べない（受付の scene_info が GPU 側で知らせる）
        return [], []
    found: list[tuple[str, Path]] = []
    missing: list[str] = []
    seen: set[str] = set()
    base = Path(blend).resolve().parent
    try:
        for usage in trace.deps(Path(blend).resolve()):
            try:
                p = Path(usage.abspath)
            except Exception:  # noqa: BLE001
                continue
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            if usage.is_sequence:
                continue
            if not p.exists():
                missing.append(str(usage.asset_path))
                continue
            try:
                rel = p.resolve().relative_to(base)
            except ValueError:
                missing.append(f"{usage.asset_path} (outside the .blend folder; cannot be sent)")
                continue
            found.append((rel.as_posix(), p))
    except Exception:  # noqa: BLE001
        return found, missing
    return found, missing


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

    def payment(self) -> Optional[dict[str, Any]]:
        """残高不足（402）なら、決済ページのリンクなどをまとめて返す。"""
        if self.status != 402:
            return None
        out = {"payment_required": True, "detail": self.detail,
               **{k: self.extra.get(k) for k in ("needed_yen", "balance_yen", "topup_yen", "checkout_url",
                                                 "session_id", "yen_per_gpu_second", "how")}}
        if self.extra.get("accepts"):
            # x402（USDC）でも払える受付。対応しているエージェントは accepts から X-PAYMENT を組む
            out["x402"] = {"x402Version": self.extra.get("x402Version"), "accepts": self.extra["accepts"],
                           "how": self.extra.get("how_x402")}
        return out


class Client:
    def __init__(self, server: Optional[str] = None, api_key: Optional[str] = None, client: str = "") -> None:
        from . import __version__

        self.server = (server or os.environ.get("JANCTION_RENDER_SERVER") or DEFAULT_SERVER).rstrip("/")
        self._key = (api_key or os.environ.get("JANCTION_RENDER_API_KEY") or "").strip() or None
        self.s = requests.Session()
        # 受付に名乗る（どの入口から来たかを数える。個人を特定するものは入れない）
        self.s.headers["X-Client"] = f"{client or 'api'} {__version__}"

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
            CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
            try:
                os.chmod(CACHE, 0o600)
            except OSError:
                pass
        except OSError:
            pass

    # ---- 共通 --------------------------------------------------------------

    @staticmethod
    def _raise(r: requests.Response) -> None:
        if r.status_code < 400:
            return
        try:
            body = r.json()
        except ValueError:
            raise ClientError(r.status_code, f"http_{r.status_code}", r.text[:300])
        raise ClientError(r.status_code, str(body.get("error", r.status_code)), str(body.get("detail", "")),
                          extra=body if isinstance(body, dict) else None)

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.key()}

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
               trace_assets: bool = True) -> dict[str, Any]:
        """シーンを送る。同じ中身を送ってあれば送り直さない（sha256 で照合）。

        assets: 一緒に送る素材（画像など）。.blend は blender-asset-tracer があれば参照する外部ファイルを自動で集める。
        返り値に assets（送った素材）と missing_assets（見つからなかった参照）が入る。
        """
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"{p} is not a file")
        if p.suffix.lower() not in SCENE_SUFFIXES:
            raise ValueError("scene must be a .blend file, a Blender Python script (.py), or a 3D file "
                             "(" + ", ".join(SCENE_SUFFIXES[2:]) + ")")
        digest = sha256_of(p)
        out: Optional[dict[str, Any]] = None
        try:
            out = self.lookup(digest)
        except ClientError:
            out = None
        if out is None:
            with p.open("rb") as fh:
                r = self.s.post(f"{self.server}/v1/files", headers=self._headers(),
                                files={"file": (p.name, fh, "application/octet-stream")}, timeout=1800)
            self._raise(r)
            out = r.json()
        items: list[tuple[str, Path]] = []
        missing: list[str] = []
        if p.suffix.lower() == ".blend" and trace_assets:
            items, missing = trace_blend_assets(p)
        for a in assets or []:
            ap = Path(a)
            if not ap.is_file():
                raise FileNotFoundError(f"asset {ap} is not a file")
            try:
                name = ap.resolve().relative_to(p.resolve().parent).as_posix()
            except ValueError:
                name = ap.name
            items.append((name, ap))
        already = {a["name"] for a in out.get("assets") or []}
        todo = [(n, ap) for n, ap in items if n not in already]
        if todo:
            out = self.upload_assets(out["scene_id"], todo)
        out["missing_assets"] = missing
        return out

    def upload_assets(self, scene_id: str, items: list[tuple[str, str | Path]]) -> dict[str, Any]:
        """素材をシーンに足す。items は [(送るときの名前, 場所)]。名前にフォルダを含めてよい（textures/a.png）。"""
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
            return self.upload(p)

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

    def jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._req("GET", f"/v1/jobs?limit={int(limit)}")["jobs"]

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self._req("DELETE", f"/v1/jobs/{job_id}")

    # ---- 決済 --------------------------------------------------------------

    def checkout(self, amount_yen: Optional[int] = None) -> dict[str, Any]:
        """クレジットをチャージする決済ページのリンクを作る。"""
        body = {"amount_yen": int(amount_yen)} if amount_yen else {}
        return self._req("POST", "/v1/billing/checkout", json=body)

    def billing_sync(self) -> dict[str, Any]:
        """払い終わった決済を確かめて残高に足す（戻り先のページを開かなかったときの保険）。"""
        return self._req("POST", "/v1/billing/sync", timeout=60)

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

    def download(self, job_id: str, out_dir: str | Path, only: Optional[list[str] | str] = None) -> list[Path]:
        """成果物を out_dir に落とす。only は名前の一覧か、'mp4' / 'frames' / 'sheet' / 'output' / 'all'。"""
        j = self.job(job_id)
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        from urllib.parse import urlsplit

        wanted = select_artifacts(j["artifacts"], only) if isinstance(only, str) or only is None else \
            [a for a in j["artifacts"] if a["name"] in only]
        for a in wanted:
            # 受付が返す URL は公開 URL の土台で組まれている。自分がつないだ先（SSH トンネルなど）でも
            # 落とせるように、パスだけを取り出して自分の server に付け直す
            parts = urlsplit(a["url"])
            path = parts.path + (f"?{parts.query}" if parts.query else "")
            url = f"{self.server}{path}" if parts.path.startswith("/v1/") else a["url"]
            with self.s.get(url, headers=self._headers(), stream=True, timeout=600) as r:
                self._raise(r)
                dest = out / a["name"]
                with dest.open("wb") as fh:
                    for chunk in r.iter_content(1024 * 1024):
                        fh.write(chunk)
            paths.append(dest)
        return paths
