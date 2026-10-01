"""仕事の状態を、エージェントが読みやすい短い形にする。stdio の MCP（mcp_server.py）とリモート MCP（server/mcp_remote.py）で共通。"""
from __future__ import annotations

import time
from typing import Any

JST = 9 * 3600


def iso(ts: float | int | None) -> str | None:
    """epoch 秒 → "2026-10-01T04:12:00Z (2026-10-01 13:12 JST)"。エージェントがそのまま伝えられる形。"""
    if ts is None:
        return None
    try:
        t = float(ts)
    except (TypeError, ValueError):
        return None
    utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
    jst = time.strftime("%Y-%m-%d %H:%M JST", time.gmtime(t + JST))
    return f"{utc} ({jst})"


def trim(items: list[Any] | None, keep: int = 8) -> dict[str, Any]:
    """長い一覧を「先頭 keep 件 ＋ 残りの件数」にする（エージェントの文脈を食わないように）。"""
    items = list(items or [])
    out: dict[str, Any] = {"count": len(items), "first": items[:keep]}
    if len(items) > keep:
        out["more"] = len(items) - keep
    return out


def eta_brief(e: dict[str, Any] | None) -> dict[str, Any] | None:
    """受付の eta（作業時間の見積もり）から、伝える価値のある項目だけ。"""
    if not e:
        return None
    keep = ("human", "remaining_seconds", "queue_wait_seconds", "remaining_gpu_seconds", "elapsed_seconds",
            "running_for_seconds", "took_seconds", "workers_online", "basis")
    return {k: e[k] for k in keep if e.get(k) is not None}


def estimate_brief(e: dict[str, Any] | None) -> dict[str, Any] | None:
    if not e:
        return None
    keep = ("human", "seconds", "wall_seconds", "queue_wait_seconds", "per_frame_seconds", "frames", "chunks",
            "workers_online", "basis", "basis_note", "note", "quota", "cost")
    return {k: e[k] for k in keep if e.get(k) is not None}


def brief(j: dict[str, Any]) -> dict[str, Any]:
    p = j["progress"]
    out: dict[str, Any] = {
        "job_id": j["job_id"],
        "kind": j["kind"],
        "status": j["status"],
        "scene_id": j["scene_id"],
        "frames": j["frames"] if j.get("frames") else f"{j['frame_start']}-{j['frame_end']}",
        "progress": f"{p['frames_done']}/{p['frames_total']} frames, {p['chunks_done']}/{p['chunks_total']} chunks",
        "queue_ahead": p["queue_ahead"],
        "gpu_seconds": j["gpu_seconds"],
        "device": j["device"],
        "expires_at": iso(j.get("expires_at")) or j.get("expires_at"),
    }
    if j.get("eta"):
        out["eta"] = eta_brief(j["eta"])
    if j.get("estimate"):
        out["estimate"] = estimate_brief(j["estimate"])
    if j.get("error"):
        out["error"] = j["error"]
    if j.get("log_tail"):
        out["log_tail"] = j["log_tail"][-1500:]
    if j.get("warnings"):
        out["warnings"] = j["warnings"]
    if j.get("output"):
        out["output"] = j["output"]["name"]
    if j.get("cost"):
        c = j["cost"]
        out["cost"] = ("free" if c["free"] else
                       (f"{c['charged_yen']} yen charged" if c["settled"] else f"up to {c['reserved_yen']} yen reserved"))
    out["artifacts"] = [a["name"] for a in j["artifacts"]][:50]
    return out
