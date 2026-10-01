"""Thin client for JANCTION Render (https://render.janction.jp), standard library only.

Shared by the Maya, Houdini and Cinema 4D helpers in this folder. Works on the Python
that DCC applications bundle (3.7 and newer): no third-party packages, urllib only.

    import jr_submit as jr
    result = jr.render("model.usda", "preview", assets=[("wood.png", "/abs/wood.png")],
                       out_dir="renders", frames=[1, 8, 16, 24], environment="studio")
    jr.open_path(result["files"][0])

The API key lives in ~/.janction_render.json ({"server": ..., "api_key": ...}) and is
created on first use (free beta, no sign-up). JANCTION_RENDER_SERVER and
JANCTION_RENDER_API_KEY override the file. Every function takes an optional
Connection whose urlopen can be replaced for tests.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__version__ = "0.1.0"

DEFAULT_SERVER = "https://render.janction.jp"
CONFIG_NAME = ".janction_render.json"
SCENE_SUFFIXES = (".blend", ".py", ".glb", ".gltf", ".fbx", ".usd", ".usda", ".usdc", ".usdz",
                  ".obj", ".stl", ".ply", ".abc")
ASSET_SUFFIXES = (".png", ".jpg", ".jpeg", ".exr", ".hdr", ".tif", ".tiff", ".webp", ".bmp", ".tga",
                  ".bin", ".mtl", ".fbx", ".glb", ".gltf", ".obj", ".usd", ".usda", ".usdc", ".usdz", ".abc",
                  ".mp4", ".mov", ".json", ".txt", ".csv", ".ttf", ".otf")
PRESETS = ("studio", "sunset", "overcast", "night")
TERMINAL = ("done", "failed", "canceled")
PREVIEW_MAX_FRAMES = 4
FREE_MAX_FRAMES = 240
FREE_MAX_PIXELS = 1920 * 1080

_SCENE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")
_ASSET_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}(/[A-Za-z0-9_.\-]{1,120}){0,4}$")
_SEQUENCE_RE = re.compile(r"<udim>|<f\d*>|<frame\d*>|<tile>|%\d*d|\$F\d*", re.IGNORECASE)


class JRError(Exception):
    """A failure from the service or the network.

    code: short machine name (quota_exceeded, not_found, network, timeout, failed, ...)
    message: human sentence; status: HTTP status (0 when no response); extra: the rest of the
    error body (for 429 quota_exceeded it holds resets_at_iso).
    """

    def __init__(self, code: str, message: str = "", status: int = 0,
                 extra: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status = status
        self.extra = extra or {}

    def __str__(self) -> str:
        if self.message and self.code and self.code not in self.message:
            return "%s: %s" % (self.code, self.message)
        return self.message or self.code


class Connection:
    """Server URL, API key and the urlopen used for requests (replaceable for tests)."""

    def __init__(self, server: str = DEFAULT_SERVER, api_key: str = "", urlopen: Optional[Callable[..., Any]] = None,
                 client: str = "jr_submit", timeout: float = 60.0, config_path: Optional[str] = None) -> None:
        self.server = (server or DEFAULT_SERVER).rstrip("/")
        self.api_key = api_key or ""
        self.urlopen = urlopen or urllib.request.urlopen
        self.client = client
        self.timeout = timeout
        # set when the key came from a config file; a 401 then renews the key once
        self.config_path = config_path
        self._renewed = False

    def __repr__(self) -> str:
        return "Connection(%s, key=%s)" % (self.server, (self.api_key[:6] + "...") if self.api_key else "none")


# ---------------------------------------------------------------- HTTP

def _multipart(fields: Sequence[Tuple[str, str, bytes]]) -> Tuple[bytes, str]:
    """Encode [(field, filename, data)] as multipart/form-data. Returns (body, content_type)."""
    boundary = "----jr-submit-" + uuid.uuid4().hex
    parts = []  # type: List[bytes]
    for field, filename, data in fields:
        safe_name = filename.replace("\\", "/").replace('"', "_")
        head = ('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n" % (boundary, field, safe_name))
        parts.append(head.encode("utf-8"))
        parts.append(data)
        parts.append(b"\r\n")
    parts.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def _error_from(status: int, body: bytes) -> JRError:
    """Map an HTTP error body to JRError. Accepts the flat shape the service sends
    ({"error": code, "detail": message, ...}) and the nested {"error": {"code", "message"}} shape."""
    text = body.decode("utf-8", "replace") if body else ""
    try:
        doc = json.loads(text) if text else {}
    except ValueError:
        doc = {}
    code = "http_%d" % status
    message = text[:300]
    extra = {}  # type: Dict[str, Any]
    if isinstance(doc, dict):
        err = doc.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or code)
            message = str(err.get("message") or err.get("detail") or message)
            extra = {k: v for k, v in doc.items() if k != "error"}
            extra.update({k: v for k, v in err.items() if k not in ("code", "message")})
        elif isinstance(err, str) and err:
            code = err
            message = str(doc.get("detail") or doc.get("message") or "")
            extra = {k: v for k, v in doc.items() if k not in ("error", "detail", "message")}
        elif doc.get("detail") is not None:
            detail = doc.get("detail")
            message = detail if isinstance(detail, str) else json.dumps(detail)[:300]
    if status == 429 and extra.get("resets_at_iso") and "reset" not in message:
        message = (message + " " if message else "") + "(resets at %s)" % extra["resets_at_iso"]
    if status == 401 and code == "http_401":
        code = "invalid_api_key"
    return JRError(code, message, status, extra)


def _http(conn: Connection, method: str, path: str, data: Optional[bytes] = None,
          content_type: Optional[str] = None, auth: bool = True, timeout: Optional[float] = None,
          dest: Optional[str] = None) -> Tuple[int, bytes]:
    """One request. Returns (status, body); with dest the body is streamed into that file.
    Raises JRError for HTTP errors and network failures. A 401 on a key that came from the
    config file renews the key once and retries."""
    headers = {"Accept": "application/json", "User-Agent": "jr_submit/" + __version__,
               "X-Client": "%s %s" % (conn.client, __version__)}
    if auth:
        if not conn.api_key:
            raise JRError("missing_api_key", "no API key; call ensure_key() first")
        headers["X-API-Key"] = conn.api_key
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(conn.server + path, data=data, headers=headers, method=method)
    try:
        resp = conn.urlopen(req, timeout=timeout or conn.timeout)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001 - the body is only for the message
            body = b""
        err = _error_from(exc.code, body)
        if exc.code == 401 and auth and conn.config_path and not conn._renewed and err.code != "missing_api_key":
            conn._renewed = True
            renew_key(conn)
            return _http(conn, method, path, data, content_type, auth, timeout, dest)
        raise err
    except urllib.error.URLError as exc:
        raise JRError("network", "cannot reach %s: %s" % (conn.server, exc.reason))
    except OSError as exc:  # socket timeouts, resets
        raise JRError("network", "%s: %s" % (conn.server, exc))
    try:
        status = int(getattr(resp, "status", None) or resp.getcode())
        if dest is not None:
            with open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
            return status, b""
        body = resp.read()
    except OSError as exc:
        raise JRError("network", "reading from %s failed: %s" % (conn.server, exc))
    finally:
        close = getattr(resp, "close", None)
        if close:
            close()
    return status, body


def _json(conn: Connection, method: str, path: str, body: Optional[Dict[str, Any]] = None,
          raw: Optional[bytes] = None, content_type: Optional[str] = None, auth: bool = True,
          timeout: Optional[float] = None) -> Dict[str, Any]:
    data = raw
    ctype = content_type
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        ctype = "application/json"
    status, text = _http(conn, method, path, data, ctype, auth, timeout)
    try:
        doc = json.loads(text.decode("utf-8")) if text else {}
    except ValueError:
        raise JRError("bad_response", "%s %s returned non-JSON (HTTP %d)" % (method, path, status), status)
    if not isinstance(doc, dict):
        raise JRError("bad_response", "%s %s returned %s" % (method, path, type(doc).__name__), status)
    return doc


# ---------------------------------------------------------------- key and config

def default_config_path() -> str:
    return os.path.join(os.path.expanduser("~"), CONFIG_NAME)


def read_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(path: str, data: Dict[str, Any]) -> None:
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def create_key(server: str = DEFAULT_SERVER, label: str = "jr_submit",
               urlopen: Optional[Callable[..., Any]] = None, client: str = "jr_submit") -> str:
    """POST /v1/keys: a free-beta key (10 GPU-minutes per day). No sign-up."""
    conn = Connection(server, "", urlopen, client)
    doc = _json(conn, "POST", "/v1/keys", {"label": label[:80]}, auth=False)
    key = doc.get("api_key")
    if not isinstance(key, str) or not key:
        raise JRError("bad_response", "POST /v1/keys returned no api_key")
    return key


def renew_key(conn: Connection, label: Optional[str] = None) -> str:
    """Create a key for conn.server, store it in conn (and its config file when it has one)."""
    key = create_key(conn.server, label or conn.client, conn.urlopen, conn.client)
    conn.api_key = key
    if conn.config_path:
        cfg = read_config(conn.config_path)
        cfg["server"] = conn.server
        cfg["api_key"] = key
        write_config(conn.config_path, cfg)
    return key


def ensure_key(config_path: Optional[str] = None, server: Optional[str] = None,
               urlopen: Optional[Callable[..., Any]] = None, label: Optional[str] = None,
               client: str = "jr_submit", timeout: float = 60.0) -> Connection:
    """Return a Connection with a working key.

    Order: JANCTION_RENDER_API_KEY (never written to disk) > the key in the config file for the
    same server > a new key from POST /v1/keys, saved to the config file. The server comes from the
    argument, JANCTION_RENDER_SERVER, the config file, then the public service.
    """
    path = config_path or default_config_path()
    cfg = read_config(path)
    env_server = (os.environ.get("JANCTION_RENDER_SERVER") or "").strip()
    srv = (server or env_server or str(cfg.get("server") or "") or DEFAULT_SERVER).rstrip("/")
    env_key = (os.environ.get("JANCTION_RENDER_API_KEY") or "").strip()
    if env_key:
        return Connection(srv, env_key, urlopen, client, timeout)
    stored = str(cfg.get("api_key") or "")
    if stored and str(cfg.get("server") or DEFAULT_SERVER).rstrip("/") == srv:
        return Connection(srv, stored, urlopen, client, timeout, config_path=path)
    conn = Connection(srv, "", urlopen, client, timeout, config_path=path)
    renew_key(conn, label)
    return conn


connect = ensure_key


# ---------------------------------------------------------------- small helpers

def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_asset_name(filename: str) -> str:
    """The name under which a texture is sent: its basename with characters the service does
    not accept replaced by '_'. Empty string when the file type is not accepted."""
    base = os.path.basename(str(filename).replace("\\", "/"))
    stem, ext = os.path.splitext(base)
    if ext.lower() not in ASSET_SUFFIXES:
        return ""
    stem = re.sub(r"[^A-Za-z0-9_.\-]", "_", stem).strip(".") or "asset"
    return stem[:100] + ext


def is_sequence_path(path: str) -> bool:
    """True for UDIM / frame-sequence texture tokens, which cannot be sent as one file."""
    return bool(_SEQUENCE_RE.search(path or ""))


def preview_frames(start: int, end: int, count: int = PREVIEW_MAX_FRAMES) -> List[int]:
    """count frames spread evenly across start..end (both included), unique, in order."""
    start, end = int(start), int(end)
    if end < start:
        start, end = end, start
    n = max(1, min(count, end - start + 1))
    if n == 1:
        return [start]
    out = []  # type: List[int]
    for i in range(n):
        v = start + int(round(i * (end - start) / float(n - 1)))
        if v not in out:
            out.append(v)
    return out


def fit_free_size(width: int, height: int, max_pixels: int = FREE_MAX_PIXELS) -> Tuple[int, int]:
    """Scale a final resolution down to the free-beta cap (1080p worth of pixels), even numbers."""
    width, height = max(16, int(width)), max(16, int(height))
    if width * height <= max_pixels:
        return width, height
    scale = (max_pixels / float(width * height)) ** 0.5
    return max(16, int(width * scale) // 2 * 2), max(16, int(height * scale) // 2 * 2)


def main_artifact(job: Dict[str, Any]) -> Optional[str]:
    """The artifact worth opening: output.mp4, else sheet.png, else the first frame PNG."""
    names = [a.get("name") for a in job.get("artifacts") or [] if isinstance(a, dict)]
    for want in ("output.mp4", "sheet.png"):
        if want in names:
            return want
    frames = sorted(n for n in names if isinstance(n, str) and n.startswith("frame_") and n.endswith(".png"))
    return frames[0] if frames else None


def status_line(job: Dict[str, Any]) -> str:
    """One line for a status label: 'Queued (2 jobs ahead), about 3 minutes' and the like."""
    st = str(job.get("status") or "unknown")
    prog = job.get("progress") or {}
    eta = job.get("eta") or {}
    human = eta.get("human") if isinstance(eta, dict) else None
    if st == "done":
        return "Done: %s GPU seconds" % job.get("gpu_seconds", "?")
    if st == "failed":
        return "Failed: %s" % (job.get("error") or "unknown error")
    if st == "canceled":
        return "Canceled"
    if st == "queued":
        ahead = int(prog.get("queue_ahead") or 0)
        text = "Queued" + (" (%d job%s ahead)" % (ahead, "" if ahead == 1 else "s") if ahead else "")
    elif st == "running":
        text = "Rendering %s/%s frames" % (prog.get("frames_done", 0), prog.get("frames_total", "?"))
    else:
        text = st
    if human:
        text += ", " + str(human)
    return text


def open_path(path: str) -> bool:
    """Open a file or folder with the OS viewer. Returns False when nothing could be started."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:  # noqa: BLE001 - a viewer that cannot start is not an error for the render
        return False


def scan_usda_asset_paths(path: str) -> List[Tuple[str, str, str]]:
    """Texture references (@...@) in an ASCII USD file that exist on disk.
    Returns [(asset_name, absolute_path, original_reference)]; sequences and unknown types are skipped."""
    try:
        with open(path, "r", encoding="utf-8", errors="surrogateescape") as fh:
            text = fh.read()
    except OSError:
        return []
    if not text.lstrip().startswith("#usda"):
        return []
    base_dir = os.path.dirname(os.path.abspath(path))
    out = []  # type: List[Tuple[str, str, str]]
    seen = set()  # type: set
    for ref in re.findall(r"@([^@\r\n]+)@", text):
        if ref in seen or is_sequence_path(ref):
            continue
        seen.add(ref)
        name = safe_asset_name(ref)
        if not name:
            continue
        candidate = ref if os.path.isabs(ref) else os.path.join(base_dir, ref)
        if os.path.isfile(candidate):
            out.append((name, os.path.abspath(candidate), ref))
    return out


def rewrite_usda_asset_paths(path: str, names: Dict[str, str]) -> int:
    """In an ASCII USD file, replace @/abs/dir/wood.png@ by @wood.png@ for every basename in names
    ({basename (lower-case): asset name}). Returns the number of references rewritten.
    Binary (.usdc) files are left untouched (returns 0)."""
    try:
        with open(path, "r", encoding="utf-8", errors="surrogateescape") as fh:
            text = fh.read()
    except OSError:
        return 0
    if not text.lstrip().startswith("#usda"):
        return 0
    count = [0]

    def repl(m: Any) -> str:
        ref = m.group(1)
        base = os.path.basename(ref.replace("\\", "/"))
        new = names.get(base.lower()) or names.get(base)
        if new and ref != new:
            count[0] += 1
            return "@%s@" % new
        return m.group(0)

    new_text = re.sub(r"@([^@\r\n]+)@", repl, text)
    if count[0]:
        with open(path, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(new_text)
    return count[0]


# ---------------------------------------------------------------- API calls

def health(conn: Optional[Connection] = None, server: Optional[str] = None) -> Dict[str, Any]:
    """GET /v1/health (no key): workers online/gated, queue, supported inputs and presets."""
    c = conn or Connection(server or DEFAULT_SERVER)
    return _json(c, "GET", "/v1/health", auth=False)


def me(conn: Optional[Connection] = None) -> Dict[str, Any]:
    """GET /v1/me: today's free quota for this key."""
    return _json(conn or connect(), "GET", "/v1/me")


def lookup(sha256: str, conn: Optional[Connection] = None) -> Optional[Dict[str, Any]]:
    """GET /v1/files/lookup: the earlier upload of the same bytes, or None."""
    conn = conn or connect()
    try:
        return _json(conn, "GET", "/v1/files/lookup?sha256=" + urllib.parse.quote(sha256))
    except JRError as exc:
        if exc.status == 404:
            return None
        raise


def _asset_items(assets: Optional[Sequence[Any]]) -> List[Tuple[str, str]]:
    items = []  # type: List[Tuple[str, str]]
    for entry in assets or []:
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            name, src = str(entry[0]), str(entry[1])
        else:
            src = str(entry)
            name = os.path.basename(src)
        name = name.replace("\\", "/")
        while name.startswith("./"):
            name = name[2:]
        name = name.lstrip("/")
        if not _ASSET_NAME_RE.match(name) or ".." in name.split("/"):
            raise JRError("bad_name", "asset name '%s': letters, digits, . _ - and up to 4 folders only" % name)
        if os.path.splitext(name)[1].lower() not in ASSET_SUFFIXES:
            raise JRError("unsupported", "asset '%s' has a type the service does not accept" % name)
        if not os.path.isfile(src):
            raise JRError("not_found", "asset file not found: %s" % src)
        items.append((name, src))
    return items


def upload_assets(scene_id: str, assets: Sequence[Any], conn: Optional[Connection] = None) -> Dict[str, Any]:
    """POST /v1/files/{scene_id}/assets with [(relative_name, local_path)] (or plain paths, sent by basename)."""
    conn = conn or connect()
    items = _asset_items(assets)
    if not items:
        raise JRError("bad_request", "no assets to send")
    fields = []  # type: List[Tuple[str, str, bytes]]
    for name, src in items:
        with open(src, "rb") as fh:
            fields.append(("files", name, fh.read()))
    body, ctype = _multipart(fields)
    return _json(conn, "POST", "/v1/files/%s/assets" % scene_id, raw=body, content_type=ctype,
                 timeout=max(conn.timeout, 1800))


def upload(path: str, assets: Optional[Sequence[Any]] = None, conn: Optional[Connection] = None,
           reuse: bool = True) -> Dict[str, Any]:
    """Send a scene file (lookup by sha256 first, so identical bytes are not sent twice) and its assets.

    assets: [(relative_name, local_path)]; relative_name is the name the scene references
    (textures/wood.png). Assets already present with the same name and size are skipped.
    Returns the scene view: scene_id, name, size, sha256, assets, references (when the file
    names companions), missing_references (named by the file but not sent).
    """
    conn = conn or connect()
    path = os.fspath(path)
    name = os.path.basename(path)
    if not os.path.isfile(path):
        raise JRError("not_found", "%s is not a file" % path)
    if os.path.splitext(name)[1].lower() not in SCENE_SUFFIXES:
        raise JRError("unsupported", "scene must be one of %s (got %s)" % (", ".join(SCENE_SUFFIXES), name))
    if not _SCENE_NAME_RE.match(name):
        raise JRError("bad_name", "scene file name '%s': letters, digits, . _ - only (rename it)" % name)
    items = _asset_items(assets)
    scene = None  # type: Optional[Dict[str, Any]]
    if reuse:
        scene = lookup(sha256_of(path), conn)
    reused = scene is not None
    if scene is None:
        with open(path, "rb") as fh:
            data = fh.read()
        if not data:
            raise JRError("empty", "%s is empty" % name)
        body, ctype = _multipart([("file", name, data)])
        scene = _json(conn, "POST", "/v1/files", raw=body, content_type=ctype, timeout=max(conn.timeout, 1800))
    have = set()  # type: set
    for a in scene.get("assets") or []:
        if isinstance(a, dict):
            have.add((a.get("name"), a.get("size")))
    todo = [(n, p) for n, p in items if (n, os.path.getsize(p)) not in have]
    if todo:
        first = scene
        scene = upload_assets(scene["scene_id"], todo, conn)
        for key in ("references", "note", "kind", "name", "size", "sha256"):
            if key in first and key not in scene:
                scene[key] = first[key]
    sent = set(n for n, _ in items)
    sent.update(a.get("name") for a in scene.get("assets") or [] if isinstance(a, dict))
    scene["missing_references"] = [r for r in scene.get("references") or [] if r not in sent]
    scene["reused"] = reused
    return scene


def estimate(body: Dict[str, Any], conn: Optional[Connection] = None) -> Dict[str, Any]:
    """POST /v1/estimate with the same body as a job: seconds, human, quota (no GPU time used)."""
    return _json(conn or connect(), "POST", "/v1/estimate", body)


def submit(body: Dict[str, Any], conn: Optional[Connection] = None) -> Dict[str, Any]:
    """POST /v1/jobs. body: scene_id, kind (preview|final), frames or frame_start/frame_end,
    width, height, samples, output, fps, environment, orbit, blender."""
    return _json(conn or connect(), "POST", "/v1/jobs", body)


def job(job_id: str, conn: Optional[Connection] = None) -> Dict[str, Any]:
    """GET /v1/jobs/{job_id}: status, progress, eta, artifacts, warnings, gpu_seconds, error."""
    return _json(conn or connect(), "GET", "/v1/jobs/%s" % job_id)


def share(job_id: str, title: str = "", note: str = "", include_script: bool = False, listed: bool = False,
          conn: Optional[Connection] = None) -> Dict[str, Any]:
    """POST /v1/jobs/{job_id}/share: a public page for a finished job. Returns {share_id, url, ...}."""
    return _json(conn or connect(), "POST", "/v1/jobs/%s/share" % job_id,
                 {"title": title, "note": note, "include_script": include_script, "listed": listed})


def unshare(job_id: str, conn: Optional[Connection] = None) -> Dict[str, Any]:
    return _json(conn or connect(), "DELETE", "/v1/jobs/%s/share" % job_id)


def cancel(job_id: str, conn: Optional[Connection] = None) -> Dict[str, Any]:
    """DELETE /v1/jobs/{job_id} (the service's cancel route). Returns the job view."""
    return _json(conn or connect(), "DELETE", "/v1/jobs/%s" % job_id)


def wait(job_id: str, poll_s: float = 2.0, timeout_s: float = 900.0,
         on_progress: Optional[Callable[[Dict[str, Any]], None]] = None, conn: Optional[Connection] = None,
         stop: Optional[Callable[[], bool]] = None, sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """Poll until the job is done / failed / canceled, the timeout passes, or stop() returns True.
    Returns the last job view (check its status). on_progress(job) is called whenever the status,
    the finished frame count or the queue position changes."""
    conn = conn or connect()
    deadline = time.monotonic() + float(timeout_s)
    last = None
    while True:
        view = job(job_id, conn)
        prog = view.get("progress") or {}
        key = (view.get("status"), prog.get("frames_done"), prog.get("queue_ahead"))
        if on_progress and key != last:
            on_progress(view)
            last = key
        if view.get("status") in TERMINAL:
            return view
        if stop and stop():
            return view
        if time.monotonic() >= deadline:
            return view
        sleep(float(poll_s))


def download(job_id: str, dest_dir: str, names: Optional[Sequence[str]] = None,
             conn: Optional[Connection] = None) -> List[str]:
    """Download the job's artifacts (all, or only names) into dest_dir. Returns the local paths."""
    conn = conn or connect()
    view = job(job_id, conn)
    os.makedirs(dest_dir, exist_ok=True)
    out = []  # type: List[str]
    for a in view.get("artifacts") or []:
        name = a.get("name") if isinstance(a, dict) else None
        if not isinstance(name, str) or not _SCENE_NAME_RE.match(name):
            continue
        if names is not None and name not in names:
            continue
        parts = urllib.parse.urlsplit(str(a.get("url") or ""))
        if parts.path.startswith("/v1/"):
            # keep the path, re-base it on our server (the service builds URLs with its public host)
            path = parts.path + ("?" + parts.query if parts.query else "")
        else:
            path = "/v1/jobs/%s/artifacts/%s" % (job_id, name)
        dest = os.path.join(dest_dir, name)
        _http(conn, "GET", path, dest=dest, timeout=600)
        out.append(dest)
    return out


def render(path: str, kind: str = "preview", assets: Optional[Sequence[Any]] = None,
           out_dir: Optional[str] = None, conn: Optional[Connection] = None,
           on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
           on_stage: Optional[Callable[[str], None]] = None, poll_s: float = 2.0, timeout_s: float = 900.0,
           names: Optional[Sequence[str]] = None, stop: Optional[Callable[[], bool]] = None,
           **params: Any) -> Dict[str, Any]:
    """Upload (or reuse) the scene, submit, wait, download. Returns
    {"files": [...], "job_id", "job", "scene_id", "scene", "gpu_seconds", "warnings"}.

    kind: "preview" (frames=[...], up to 4, tiled into sheet.png) or "final" (frame_start/frame_end,
    output png|mp4). Other keyword arguments go into the job body as they are
    (width, height, samples, fps, environment, orbit, blender, ...). Raises JRError when the job
    fails, is canceled, or is still running after timeout_s (extra["job_id"] then lets you come back).
    """
    conn = conn or connect()
    if on_stage:
        on_stage("Uploading %s (%.1f MB)" % (os.path.basename(path), os.path.getsize(path) / 1048576.0))
    scene = upload(path, assets, conn)
    body = {"scene_id": scene["scene_id"], "kind": kind}  # type: Dict[str, Any]
    body.update({k: v for k, v in params.items() if v is not None})
    if on_stage:
        on_stage("Submitting")
    view = submit(body, conn)
    job_id = str(view["job_id"])
    if on_progress:
        on_progress(view)
    view = wait(job_id, poll_s, timeout_s, on_progress, conn, stop)
    status = view.get("status")
    if status != "done":
        extra = {"job_id": job_id, "job": view}
        if status in ("failed", "canceled"):
            message = str(view.get("error") or status)
            tail = view.get("log_tail")
            if status == "failed" and isinstance(tail, str) and tail.strip():
                message += "\n" + tail.strip()[-600:]
            raise JRError(status, message, extra=extra)
        if stop and stop():
            raise JRError("canceled", "canceled before the job finished (job %s)" % job_id, extra=extra)
        raise JRError("timeout", "job %s is still %s after %d s; download it later with its job id"
                      % (job_id, status, int(timeout_s)), extra=extra)
    if on_stage:
        on_stage("Downloading")
    files = download(job_id, out_dir or os.getcwd(), names, conn)
    return {"files": files, "job_id": job_id, "job": view, "scene_id": scene["scene_id"], "scene": scene,
            "gpu_seconds": view.get("gpu_seconds"), "warnings": list(view.get("warnings") or [])}


# ---------------------------------------------------------------- background helper for UIs

class BackgroundRender(threading.Thread):
    """render() in a daemon thread. The UI reads .text / .done / .result / .error, or gets
    on_update(runner) calls from the worker thread (wrap them for your UI's main thread).
    cancel() stops waiting and cancels the job on the service."""

    def __init__(self, path: str, kind: str, assets: Optional[Sequence[Any]] = None,
                 out_dir: Optional[str] = None, conn: Optional[Connection] = None,
                 on_update: Optional[Callable[["BackgroundRender"], None]] = None,
                 poll_s: float = 2.0, timeout_s: float = 900.0, names: Optional[Sequence[str]] = None,
                 cleanup: Optional[Sequence[str]] = None, client: str = "jr_submit", **params: Any) -> None:
        super().__init__(name="jr_submit-render")
        self.daemon = True
        self.path = path
        self.kind = kind
        self.assets = list(assets or [])
        self.out_dir = out_dir
        self.conn = conn
        self.client = client
        self.on_update = on_update
        self.poll_s = poll_s
        self.timeout_s = timeout_s
        self.names = names
        self.cleanup = list(cleanup or [])
        self.params = params
        self.text = "Starting"
        self.job_id = None  # type: Optional[str]
        self.job = None  # type: Optional[Dict[str, Any]]
        self.result = None  # type: Optional[Dict[str, Any]]
        self.error = None  # type: Optional[BaseException]
        self.done = False
        self._stop_event = threading.Event()  # not _stop: threading.Thread uses that name

    def _notify(self) -> None:
        if self.on_update:
            try:
                self.on_update(self)
            except Exception:  # noqa: BLE001 - a UI callback must not kill the render thread
                pass

    def _stage(self, text: str) -> None:
        self.text = text
        self._notify()

    def _progress(self, view: Dict[str, Any]) -> None:
        self.job = view
        self.job_id = str(view.get("job_id") or self.job_id or "")
        self.text = status_line(view)
        self._notify()

    def run(self) -> None:
        try:
            if self.conn is None:
                self._stage("Connecting")
                self.conn = connect(client=self.client)
            self.result = render(self.path, self.kind, self.assets, self.out_dir, self.conn,
                                 on_progress=self._progress, on_stage=self._stage, poll_s=self.poll_s,
                                 timeout_s=self.timeout_s, names=self.names, stop=self._stop_event.is_set,
                                 **self.params)
            self.text = "Done: %s GPU seconds, %d file%s" % (self.result.get("gpu_seconds"), len(self.result["files"]),
                                                             "" if len(self.result["files"]) == 1 else "s")
        except JRError as exc:
            self.error = exc
            self.text = str(exc)
        except Exception as exc:  # noqa: BLE001 - shown to the user instead of crashing the host
            self.error = exc
            self.text = "%s: %s" % (type(exc).__name__, exc)
        finally:
            for p in self.cleanup:
                shutil.rmtree(p, ignore_errors=True)
            self.done = True
            self._notify()

    def cancel(self) -> None:
        """Stop waiting; cancel the job on the service when one was submitted."""
        self._stop_event.set()
        if self.job_id and self.conn is not None and not self.done:
            try:
                cancel(self.job_id, self.conn)
            except Exception:  # noqa: BLE001 - best effort from a UI button
                pass
