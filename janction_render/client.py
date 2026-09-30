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

    def upload(self, path: str | Path) -> dict[str, Any]:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"{p} is not a file")
        if p.suffix.lower() not in (".blend", ".py"):
            raise ValueError("scene must be a .blend file or a Blender Python script (.py)")
        with p.open("rb") as fh:
            r = self.s.post(f"{self.server}/v1/files", headers=self._headers(),
                            files={"file": (p.name, fh, "application/octet-stream")}, timeout=1800)
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

    def download(self, job_id: str, out_dir: str | Path, only: Optional[list[str]] = None) -> list[Path]:
        """成果物を out_dir に落とす。only を渡せばその名前だけ。"""
        j = self.job(job_id)
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for a in j["artifacts"]:
            if only and a["name"] not in only:
                continue
            url = a["url"] if a["url"].startswith("http") else f"{self.server}{a['url']}"
            with self.s.get(url, headers=self._headers(), stream=True, timeout=600) as r:
                self._raise(r)
                dest = out / a["name"]
                with dest.open("wb") as fh:
                    for chunk in r.iter_content(1024 * 1024):
                        fh.write(chunk)
            paths.append(dest)
        return paths
