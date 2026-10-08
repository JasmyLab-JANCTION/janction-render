"""Module-level job state shared between the background thread, the timer and the panel.

Only this module touches the dict; everything goes through the lock. No Blender imports.
"""
import threading
from typing import Any, Optional

BUSY = ("uploading", "submitting", "queued", "running", "downloading")
TERMINAL = ("idle", "done", "failed", "canceled")

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "phase": "idle",        # idle | uploading | submitting | queued | running | downloading | done | failed | canceled
    "kind": "",             # preview | final
    "job_id": "",
    "message": "",          # one line for the panel
    "result": "",           # path of the last downloaded result (file or folder)
    "warnings": [],
    "quota": None,          # {"used": s, "limit": s, "resets_at_iso": ...} from /v1/me
    "key_prefix": "",
    "pending_image": "",    # a preview sheet the timer should load into Blender (main thread only)
    "pending_open": "",     # a path the timer should open with the OS
    "quota_requested": False,
    "checkout_url": "",     # the top-up page (Stripe Checkout) after a 402 payment_required; cleared by the next job
}


def snapshot() -> dict[str, Any]:
    with _LOCK:
        out = dict(_STATE)
        out["warnings"] = list(_STATE["warnings"])
        return out


def get(key: str, default: Any = None) -> Any:
    with _LOCK:
        return _STATE.get(key, default)


def update(**kw: Any) -> None:
    with _LOCK:
        _STATE.update(kw)


def pop(key: str, default: Any = "") -> Any:
    """Read a one-shot value and clear it."""
    with _LOCK:
        value = _STATE.get(key, default)
        _STATE[key] = default
        return value


def busy() -> bool:
    with _LOCK:
        return _STATE["phase"] in BUSY


def start_job(kind: str, warnings: Optional[list[str]] = None) -> None:
    update(phase="uploading", kind=kind, job_id="", message="Saving a copy...", result="",
           warnings=list(warnings or []), pending_image="", pending_open="", checkout_url="")


def fail(message: str, warnings: Optional[list[str]] = None) -> None:
    with _LOCK:
        _STATE["phase"] = "failed"
        _STATE["message"] = message
        if warnings:
            _STATE["warnings"] = list(warnings)


def need_payment(message: str, checkout_url: str) -> None:
    """A 402: the job goes past today's free GPU time and the credit is short. The panel then offers the top-up page."""
    with _LOCK:
        _STATE["phase"] = "failed"
        _STATE["message"] = message
        _STATE["checkout_url"] = checkout_url


def set_quota(me: dict[str, Any]) -> None:
    """Keep what the panel shows from a /v1/me answer."""
    q = me.get("quota") if isinstance(me, dict) else None
    with _LOCK:
        _STATE["key_prefix"] = str(me.get("prefix") or "") if isinstance(me, dict) else ""
        if isinstance(q, dict):
            _STATE["quota"] = {
                "used": float(q.get("gpu_seconds_used_today") or 0.0),
                "limit": float(q.get("gpu_seconds_per_day") or 0.0),
                "resets_at_iso": str(q.get("resets_at_iso") or ""),
                # ようこそクレジット（受付が JR_FREE_MODEL=welcome のとき、docs/46）
                "welcome": q.get("welcome") if isinstance(q.get("welcome"), dict) else None,
            }
        else:
            _STATE["quota"] = None


def quota_text() -> str:
    """'7.5 min left today', 'welcome credit: 320 JPY left (11 days)' or '' when nothing is known."""
    with _LOCK:
        q = _STATE["quota"]
    w = (q or {}).get("welcome")
    if w:
        if w.get("in_welcome"):
            return f"welcome credit: {int(w.get('yen_left') or 0)} JPY left ({int(w.get('days_left') or 0)} days)"
        return f"{float(w.get('preview_free_seconds_left_today') or 0.0) / 60.0:.1f} free preview min left today"
    if not q or not q.get("limit"):
        return ""
    left = max(0.0, q["limit"] - q["used"]) / 60.0
    return f"{left:.1f} min left today"
