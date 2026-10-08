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
            "running_for_seconds", "took_seconds", "workers_online", "basis", "gate")
    return {k: e[k] for k in keep if e.get(k) is not None}


def estimate_brief(e: dict[str, Any] | None) -> dict[str, Any] | None:
    if not e:
        return None
    keep = ("human", "seconds", "wall_seconds", "queue_wait_seconds", "per_frame_seconds", "frames", "chunks",
            "workers_online", "basis", "basis_note", "note", "quota", "cost", "gate")
    return {k: e[k] for k in keep if e.get(k) is not None}


FINAL_W, FINAL_H, FINAL_SPP = 1920, 1080, 128


def final_body_after_preview(j: dict[str, Any]) -> dict[str, Any] | None:
    """試し描き（done）の次の一手の見積もりに使う final の本文（10/7）: 同じシーン・同じ設定で、試し描きしたコマ範囲を
    1920x1080・128 サンプルで仕上げたら、という仮定。compare は 1 コマ、cameras は同じカメラ群、orbit は 1 周。"""
    if not j or j.get("kind") != "preview" or not j.get("scene_id"):
        return None
    p = j.get("params") or {}
    frames = [int(x) for x in (j.get("frames") or []) if isinstance(x, (int, float))]
    body: dict[str, Any] = {"scene_id": j["scene_id"], "kind": "final", "width": FINAL_W, "height": FINAL_H, "samples": FINAL_SPP}
    if p.get("cameras"):
        body["cameras"] = list(p["cameras"])
        body["frame_start"] = int(p.get("cameras_frame") or 1)
    elif p.get("compare"):
        body["frame_start"] = body["frame_end"] = int(p.get("compare_frame") or 1)
    elif p.get("orbit"):
        body.update({"orbit": True, "orbit_frames": p.get("orbit_frames") or 24, "frame_start": 1})
        for k in ("orbit_elevation", "orbit_target", "orbit_distance"):
            if p.get(k) not in (None, ""):
                body[k] = p[k]
    elif frames:
        body["frame_start"], body["frame_end"] = min(frames), max(frames)
    else:
        body["frame_start"] = body["frame_end"] = int(j.get("frame_start") or 1)
    for k in ("engine", "blender", "camera", "transparent"):
        if p.get(k):
            body[k] = p[k]
    env = p.get("environment")
    if env and env != "compare":
        body["environment"] = env
        for k in ("environment_strength", "environment_visible"):
            if p.get(k) is not None:
                body[k] = p[k]
    return body


def followup_after_preview(est: dict[str, Any] | None, body: dict[str, Any] | None) -> dict[str, Any]:
    """試し描きの後に添える「仕上げならどれくらいか・今日の枠の残り」（10/7）。est は /v1/estimate の返事。
    エージェントが『final なら約 N 秒、今日の無料枠はあと M 秒』と次の一手を提案できるようにする。"""
    if not est or not body:
        return {}
    q = est.get("quota") or {}
    fe = body.get("frame_end") or body.get("frame_start") or 1
    fs = body.get("frame_start") or 1
    if body.get("cameras"):
        what = f"frame {fs} from {len(body['cameras'])} cameras"
    elif body.get("orbit"):
        what = f"one {body.get('orbit_frames') or 24}-frame turntable"
    elif fe != fs:
        what = f"frames {fs}-{fe}"
    else:
        what = f"frame {fs}"
    out: dict[str, Any] = {
        "final_estimate": {"what": what, "size": f"{body.get('width')}x{body.get('height')}", "samples": body.get("samples"),
                           "gpu_seconds": est.get("seconds"), "human": est.get("human"),
                           "fits_today": q.get("fits_today"), "gpu_seconds_left_today": q.get("gpu_seconds_left_today")},
    }
    if q.get("gpu_seconds_left_today") is not None:
        out["quota_left_today"] = {"gpu_seconds": q["gpu_seconds_left_today"], "resets_at": iso(q.get("resets_at")) or q.get("resets_at")}
    cost = est.get("cost") or {}
    if cost.get("list_price_yen") is not None:
        out["final_estimate"]["list_price_yen"] = cost["list_price_yen"]
    if cost.get("estimated_yen") is not None:      # 有料モード: 無料枠を超えた分の見込み額（収まれば 0）
        out["final_estimate"]["charge_yen"] = cost["estimated_yen"]
    return out


def critic_next(critic: dict[str, Any] | None) -> str:
    """試し描きの批評から、next の頭に置く一文（直すものがあるときだけ、10/8）。"""
    if not critic or critic.get("verdict") in (None, "ok"):
        return ""
    issues = critic.get("issues") or []
    fixes = [i for i in issues if i.get("severity") == "fix"]
    first = (fixes or [i for i in issues if i.get("severity") == "check"] or [None])[0]
    if not first:
        return ""
    head = "The critic found a problem a final render would keep" if fixes else "The critic flagged something to check"
    return f"{head}: {first.get('message')}. Fix: {first.get('fix')}. Apply it and preview again before any final render. "


def next_after_preview(fu: dict[str, Any] | None, edit_hint: str, final_hint: str, critic: dict[str, Any] | None = None) -> str:
    """試し描きの next 文（10/7）。見積もりがあれば、仕上げの所要時間と枠の残りを 1 文足す。批評に直すものがあれば頭に置く（10/8）。"""
    text = critic_next(critic) + f"look at the image; if the scene needs changes, {edit_hint}; if it looks right, {final_hint}"
    fe = (fu or {}).get("final_estimate") or {}
    if fe.get("human") or fe.get("gpu_seconds") is not None:
        text += (f". A final render of {fe.get('what')} at {fe.get('size')}/{fe.get('samples')} spp would take "
                 f"{fe.get('human') or 'about ' + str(fe.get('gpu_seconds')) + ' s'} ({fe.get('gpu_seconds')} GPU s)")
        left = fe.get("gpu_seconds_left_today")
        if left is not None:
            text += f"; {left} GPU s of today's free quota remain"
            if fe.get("fits_today") is False:
                text += " (it does not fit today: propose fewer frames, a smaller size, or waiting for the reset)"
            else:
                text += " (it fits)"
        text += ". Tell the user this before asking"
    return text


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
    if j.get("camera_files"):
        out["camera_files"] = j["camera_files"]
    if j.get("critic"):
        # 試し描きの批評（10/8）: verdict（ok / check / fix）と、問題ごとの直し方。数字の明細は REST の仕事の状態にある
        c = j["critic"]
        out["critic"] = {"verdict": c.get("verdict"), "score": c.get("score"), "summary": c.get("summary"),
                         "issues": [{k: i.get(k) for k in ("code", "severity", "message", "fix")} for i in (c.get("issues") or [])][:6]}
    if j.get("cost"):
        c = j["cost"]
        out["cost"] = ("free" if c["free"] else
                       (f"{c['charged_yen']} yen charged" if c["settled"] else f"up to {c['reserved_yen']} yen reserved"))
    out["artifacts"] = [a["name"] for a in j["artifacts"]][:50]
    return out

def welcome_billing(w: dict[str, Any], me: dict[str, Any], synced: dict[str, Any] | None = None) -> dict[str, Any]:
    """billing() のようこそクレジットの形（stdio の mcp_server も同じ形を返す）。残りが 100 円を切ったときと、
    期限の 3 日前は、チャージの案内を next に入れる（docs/46 の見せ方）。"""
    b = me.get("billing") or {}
    yen = b.get("yen_per_gpu_second")
    if w.get("in_welcome"):
        summary = f"welcome credit: {w['yen_left']} JPY left, {w['days_left']} days"
    elif w.get("in_window"):
        summary = "the welcome credit is used up"
    else:
        summary = "the welcome period has ended"
    pv = round(float(w.get("preview_free_seconds_per_day") or 0) / 60)
    out: dict[str, Any] = {
        "mode": "welcome_credit",
        "summary": f"{summary}; balance {me.get('balance_yen')} JPY",
        "note": (f"a new key's welcome credit covers previews and finals until it runs out or expires ({w.get('expires_at_iso')}); "
                 f"after that, previews are free up to {pv} GPU-minutes a day and finals cost {yen} JPY per GPU-second from "
                 "prepaid credit"),
        "welcome": w,
        "balance_yen": me.get("balance_yen"), "yen_per_gpu_second": yen, "min_topup_yen": b.get("min_topup_yen"),
        "pending_checkout_url": b.get("pending_checkout_url"), "charged_yen_total": me.get("charged_yen_total"),
        "just_credited": (synced or {}).get("credited", []), "key_prefix": me.get("prefix"),
    }
    bonus = float(w.get("first_topup_bonus") or 0)
    topup = b.get("topup_options") or {}
    opts = topup.get("options") or []
    if opts:
        # チャージの選択肢（docs/47）: 額・入る額・上乗せ。おすすめは受付が決める（まだ払っていない鍵は最低額、払ったことがあれば 2,000 円）
        out["topup_options"] = [{k: o.get(k) for k in ("amount_yen", "credit_yen", "bonus_yen", "bonus_reason", "recommended")} for o in opts]
        rec = next((o for o in opts if o.get("recommended")), None)
        if rec:
            out["recommended_topup"] = (f"{rec['amount_yen']:,} JPY gives {rec['credit_yen']:,} JPY of credit"
                                        + (f" (a {rec['bonus_yen']:,} JPY bonus)" if rec.get("bonus_yen") else ""))
    if bonus:
        cap = int(w.get("first_topup_bonus_cap_yen") or topup.get("first_topup_bonus_cap_yen") or 0)
        mt = int(b.get("min_topup_yen") or 500)
        first = next((o for o in opts if o.get("amount_yen") == mt), None)
        credit = int(first["credit_yen"]) if first else mt + min(round(mt * bonus), cap or round(mt * bonus))
        out["first_topup_bonus"] = (f"the first top-up during the welcome period counts {1 + bonus:g}x"
                                    + (f", bonus up to {cap:,} JPY" if cap else "") + f" ({mt} JPY adds {credit:,} JPY of credit)")
    if w.get("in_window") and (int(w.get("yen_left") or 0) < 100 or int(w.get("days_left") or 0) <= 3):
        out["next"] = ("tell the user the welcome credit is running out (" + summary + ")"
                       + (" and that the first top-up now counts " + f"{1 + bonus:g}x" if bonus else "")
                       + "; a top-up link comes with the next job that needs credit (402 checkout_url)")
    return out
