"""HTTP client for JANCTION Render built on urllib only.

Blender's bundled Python has no ``requests``, so this module speaks the same
API as ``janction_render/client.py`` in the main repository with the standard
library alone. The ``urlopen`` callable is injectable so tests can fake the
network. Python 3.11 compatible; no Blender imports here.
"""
import hashlib
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

VERSION = "0.1.4"
USER_AGENT = f"janction-render-blender/{VERSION}"
CLIENT_NAME = f"blender {VERSION}"
DEFAULT_SERVER = "https://render.janction.jp"
CHUNK = 1024 * 1024

# One request to POST /v1/files/{id}/assets carries at most this many files / bytes.
ASSET_BATCH_FILES = 10
ASSET_BATCH_BYTES = 256 * 1024 * 1024

Asset = tuple[str, str]   # (relative name as the scene references it, absolute path on disk)


class JRError(Exception):
    """An error answer from the service, or no connection at all.

    ``code`` is the service's short code (``quota_exceeded``, ``not_found``...),
    ``network`` / ``timeout`` when the request never got an answer, and
    ``no_key`` when the add-on has no API key yet. ``status`` is the HTTP
    status (0 without an answer). ``extra`` keeps the other fields of the
    error body, for example ``resets_at_iso`` on a 429.
    """

    def __init__(self, code: str, message: str, status: int = 0, extra: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra or {}

    def __str__(self) -> str:
        return self.message or self.code

    @property
    def resets_at_iso(self) -> str:
        return str(self.extra.get("resets_at_iso") or "")


def error_from_body(status: int, body: bytes) -> JRError:
    """Map an error body to JRError.

    Accepts the service's flat shape ``{"error": "code", "detail": "text", ...}``,
    the nested shape ``{"error": {"code": ..., "message": ...}}`` and FastAPI's
    422 ``{"detail": [...]}``. Anything else becomes ``http_<status>``.
    """
    text = body.decode("utf-8", "replace")
    try:
        data = json.loads(text) if text.strip() else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return JRError(f"http_{status}", text.strip()[:300] or f"HTTP {status}", status)
    err = data.get("error")
    if isinstance(err, dict):
        code = str(err.get("code") or f"http_{status}")
        message = str(err.get("message") or err.get("detail") or "")
        extra = {k: v for k, v in data.items() if k != "error"}
        extra.update({k: v for k, v in err.items() if k not in ("code", "message")})
        return JRError(code, message, status, extra)
    detail = data.get("detail")
    if isinstance(detail, list):
        parts = [str(d.get("msg")) for d in detail if isinstance(d, dict) and d.get("msg")]
        return JRError("validation", "; ".join(parts) or "invalid request", status, {})
    code = str(err or f"http_{status}")
    message = str(detail or data.get("message") or "")
    extra = {k: v for k, v in data.items() if k not in ("error", "detail", "message")}
    return JRError(code, message or code, status, extra)


def sha256_of(path: "str | Path") -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _multipart_filename(name: str) -> str:
    return name.replace("\\", "/").replace('"', "%22").replace("\r", "").replace("\n", "")


class MultipartBody:
    """A multipart/form-data body that streams file parts instead of copying them into memory.

    It has ``__len__`` (for Content-Length) and ``read(n)`` so http.client sends it in blocks.
    """

    def __init__(self) -> None:
        self.boundary = "----janction-render-" + uuid.uuid4().hex
        self._segments: list = []     # bytes, or Path for a file to stream
        self._closed = False
        self._idx = 0
        self._pos = 0
        self._fh = None

    def add_file(self, field: str, filename: str, path: "str | Path",
                 content_type: str = "application/octet-stream") -> None:
        head = (f"--{self.boundary}\r\n"
                f'Content-Disposition: form-data; name="{field}"; filename="{_multipart_filename(filename)}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n").encode("utf-8")
        self._segments += [head, Path(path), b"\r\n"]

    def finish(self) -> "MultipartBody":
        if not self._closed:
            self._segments.append(f"--{self.boundary}--\r\n".encode("utf-8"))
            self._closed = True
        return self

    def content_type(self) -> str:
        return f"multipart/form-data; boundary={self.boundary}"

    def __len__(self) -> int:
        return sum(len(s) if isinstance(s, bytes) else s.stat().st_size for s in self._segments)

    def read(self, n: int = -1) -> bytes:
        out = bytearray()
        while n < 0 or len(out) < n:
            if self._idx >= len(self._segments):
                break
            seg = self._segments[self._idx]
            if isinstance(seg, bytes):
                end = len(seg) if n < 0 else self._pos + (n - len(out))
                take = seg[self._pos:end]
                out += take
                self._pos += len(take)
                if self._pos >= len(seg):
                    self._idx += 1
                    self._pos = 0
                continue
            if self._fh is None:
                self._fh = seg.open("rb")
            want = -1 if n < 0 else n - len(out)
            data = self._fh.read(want)
            if data:
                out += data
            else:
                self._fh.close()
                self._fh = None
                self._idx += 1
                self._pos = 0
        return bytes(out)

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            finally:
                self._fh = None


_OPENER = None


def _default_urlopen(req: urllib.request.Request, timeout: float):
    """urllib's urlopen, with certifi's CA bundle when Blender's Python ships it (macOS has no system certs)."""
    global _OPENER
    if _OPENER is None:
        handlers = []
        try:
            import ssl
            import certifi  # type: ignore

            handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
        except Exception:  # noqa: BLE001 - fall back to the default context
            pass
        _OPENER = urllib.request.build_opener(*handlers)
    return _OPENER.open(req, timeout=timeout)


class Client:
    """Talks to one JANCTION Render server with one API key."""

    def __init__(self, server: str = DEFAULT_SERVER, api_key: str = "",
                 urlopen: Optional[Callable[..., Any]] = None, timeout: float = 30.0) -> None:
        self.server = (server or DEFAULT_SERVER).strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self._urlopen = urlopen or _default_urlopen

    # ---- plumbing ------------------------------------------------------------

    def _host(self) -> str:
        return urllib.parse.urlsplit(self.server).netloc or self.server

    def _open(self, method: str, path: str, *, json_body: Optional[dict[str, Any]] = None,
              body: Optional[MultipartBody] = None, query: Optional[dict[str, str]] = None,
              auth: bool = True, timeout: Optional[float] = None):
        url = self.server + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"User-Agent": USER_AGENT, "X-Client": CLIENT_NAME, "Accept": "application/json"}
        if auth:
            if not self.api_key:
                raise JRError("no_key", "No API key. Open the add-on preferences and press 'Get a free key'.")
            headers["X-API-Key"] = self.api_key
        data: Any = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif body is not None:
            body.finish()
            data = body
            headers["Content-Type"] = body.content_type()
            headers["Content-Length"] = str(len(body))
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            return self._urlopen(req, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except Exception:  # noqa: BLE001
                raw = b""
            raise error_from_body(int(exc.code), raw) from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise JRError("timeout", f"{self._host()} did not answer in time") from None
            raise JRError("network", f"cannot reach {self._host()}: {reason}") from None
        except (socket.timeout, TimeoutError):
            raise JRError("timeout", f"{self._host()} did not answer in time") from None
        except OSError as exc:
            raise JRError("network", f"cannot reach {self._host()}: {exc}") from None
        finally:
            if body is not None:
                body.close()

    def _json(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        resp = self._open(method, path, **kw)
        try:
            raw = resp.read()
        finally:
            close = getattr(resp, "close", None)
            if close:
                close()
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise JRError("bad_answer", f"{self._host()} answered with something that is not JSON") from None
        return data if isinstance(data, dict) else {"data": data}

    # ---- keys and status -----------------------------------------------------

    def create_key(self, label: str = "blender") -> dict[str, Any]:
        """POST /v1/keys. No sign-up; the answer carries ``api_key``. Also stores it on this client."""
        out = self._json("POST", "/v1/keys", json_body={"label": label}, auth=False, timeout=15)
        if out.get("api_key"):
            self.api_key = str(out["api_key"])
        return out

    def me(self) -> dict[str, Any]:
        """GET /v1/me: usage, the free GPU time left and the credit for this key."""
        return self._json("GET", "/v1/me", timeout=15)

    def health(self) -> dict[str, Any]:
        """GET /v1/health (no key): workers, queue, features."""
        return self._json("GET", "/v1/health", auth=False, timeout=10)

    # ---- scenes --------------------------------------------------------------

    def lookup(self, sha256: str) -> Optional[dict[str, Any]]:
        """GET /v1/files/lookup: the earlier scene with the same bytes, or None."""
        try:
            return self._json("GET", "/v1/files/lookup", query={"sha256": sha256})
        except JRError as exc:
            if exc.status == 404:
                return None
            raise

    def upload_scene(self, path: "str | Path", assets: Sequence[Asset] = (),
                     on_progress: Optional[Callable[[str], None]] = None) -> dict[str, Any]:
        """Send a scene file and its companion files.

        The scene is skipped when the server already has the same bytes (sha256
        lookup). Assets are ``(relative_name, absolute_path)`` pairs; names the
        scene already has with the same size are skipped too. Returns the scene
        view with ``assets_sent`` (names uploaded by this call).
        """
        p = Path(path)
        if not p.is_file():
            raise JRError("no_file", f"{p} is not a file")
        tell = on_progress or (lambda _msg: None)
        scene: Optional[dict[str, Any]] = None
        try:
            scene = self.lookup(sha256_of(p))
        except JRError as exc:
            if exc.code in ("network", "timeout", "no_key"):
                raise
            scene = None
        if scene is None:
            tell(f"Uploading {p.name} ({p.stat().st_size // 1024} KB)")
            body = MultipartBody()
            body.add_file("file", p.name, p)
            scene = self._json("POST", "/v1/files", body=body, timeout=1800)
        else:
            tell(f"{p.name} is already on the server")
        have = {str(a.get("name")): int(a.get("size") or -1) for a in scene.get("assets") or []}
        todo = [(name, abs_path) for name, abs_path in assets
                if have.get(name) != Path(abs_path).stat().st_size]
        sent: list[str] = []
        if todo:
            scene_id = str(scene["scene_id"])
            for batch in _batches(todo):
                tell(f"Uploading {len(sent) + len(batch)}/{len(todo)} textures")
                scene = self.upload_assets(scene_id, batch)
                sent += [name for name, _ in batch]
        scene["assets_sent"] = sent
        return scene

    def upload_assets(self, scene_id: str, assets: Sequence[Asset]) -> dict[str, Any]:
        """POST /v1/files/{scene_id}/assets with one multipart field ``files`` per asset."""
        body = MultipartBody()
        for name, abs_path in assets:
            body.add_file("files", name, abs_path)
        return self._json("POST", f"/v1/files/{scene_id}/assets", body=body, timeout=1800)

    # ---- jobs ----------------------------------------------------------------

    def estimate(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/estimate: seconds, human sentence and quota, without rendering."""
        return self._json("POST", "/v1/estimate", json_body=body, timeout=20)

    def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/jobs: start a preview or final render."""
        return self._json("POST", "/v1/jobs", json_body=body, timeout=60)

    def job(self, job_id: str) -> dict[str, Any]:
        return self._json("GET", f"/v1/jobs/{job_id}", timeout=20)

    def cancel(self, job_id: str) -> dict[str, Any]:
        """DELETE /v1/jobs/{job_id} (what the service implements for cancel)."""
        return self._json("DELETE", f"/v1/jobs/{job_id}", timeout=20)

    def artifact(self, job_id: str, name: str, dest_path: "str | Path") -> Path:
        """Download one artifact to ``dest_path`` (written through a .part file)."""
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        resp = self._open("GET", f"/v1/jobs/{job_id}/artifacts/{name}", timeout=600)
        try:
            with part.open("wb") as fh:
                while True:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
        finally:
            close = getattr(resp, "close", None)
            if close:
                close()
        part.replace(dest)
        return dest


def _batches(items: Sequence[Asset]) -> Iterable[list[Asset]]:
    batch: list[Asset] = []
    size = 0
    for name, abs_path in items:
        n = Path(abs_path).stat().st_size
        if batch and (len(batch) >= ASSET_BATCH_FILES or size + n > ASSET_BATCH_BYTES):
            yield batch
            batch, size = [], 0
        batch.append((name, abs_path))
        size += n
    if batch:
        yield batch
