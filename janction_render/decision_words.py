"""見積もりの decision（server/decision.py が作る）を文にする側（10/28）。stdio の MCP（公開パッケージ）にも入るので受付の中身は読まない。

brief.pay_words・mcp_common.estimate_next・pricing.view が、受付の decision を受け取ってここで文にする。受付側の decision.py も
同じ関数を使う（言葉を 2 か所に持たない）。
"""
from __future__ import annotations

from typing import Any, Optional

PAYMENT_CODES = ("PAYMENT_NEEDED", "RESOLUTION_NEEDS_PAID_KEY")   # 払えば（カード登録で・払った鍵になれば）通る種類
CAP_CODES = ("SPEND_CAP_JOB", "SPEND_CAP_DAY", "REQUEST_MAX_YEN")


def hard_blockers(decision: Optional[dict[str, Any]]) -> list[dict[str, str]]:
    """払っても消えない理由。"""
    if not decision:
        return []
    return [r for r in decision.get("blocking_reasons") or [] if r.get("code") not in PAYMENT_CODES]


def within_caps(decision: Optional[dict[str, Any]]) -> bool:
    """cost.within_caps の値（支出の上限の理由が無い）。decision から導くので別の計算を持たない。"""
    if not decision:
        return True
    return not any(r.get("code") in CAP_CODES for r in decision.get("blocking_reasons") or [])


def blocked_text(decision: Optional[dict[str, Any]], lang: str = "en") -> str:
    """払っても通らないときの 1 文（MCP の next・/start・pay_words が同じ文を使う）。空なら止まっていない。"""
    hard = hard_blockers(decision)
    if not hard:
        return ""
    needs_pay = any(r.get("code") == "PAYMENT_NEEDED" for r in (decision or {}).get("blocking_reasons") or [])
    if lang == "ja":
        why = "；".join(f"{r.get('message')}（{r.get('fix')}）" for r in hard)
        tail = "。チャージしても通りません" if needs_pay else ""
        return f"このままでは受け付けられません: {why}{tail}。どれを変えるか利用者に聞いてください（何も予約も請求もしていません）"
    why = "; ".join(f"{r.get('message')} ({r.get('fix')})" for r in hard)
    tail = "; paying alone would not change that" if needs_pay else ""
    return f"this cannot run as asked: {why}{tail}. Ask the user which to change; nothing was queued or charged"
