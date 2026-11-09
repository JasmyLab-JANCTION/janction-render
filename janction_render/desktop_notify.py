"""描き終わりをデスクトップの通知で知らせる（stdio の MCP・CLI 用。11/9）。

AI が待ち方を間違えても、会話が止まっていても、利用者の画面に「仕上がりました」が出るようにする。
失敗しても何もしない（通知は付け足しで、描画と受け取りの結果を変えない）。
JANCTION_RENDER_NOTIFY=0 で止める。

文はコマンドの文字列に埋め込まない（引数か環境変数で渡す）。シーン名などに記号が入っていても実行されない。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

TITLE = "JANCTION Render"

# Windows: PowerShell 5.1 の WinRT トースト。文は環境変数から読み、XML としてエスケープする
_PS_TOAST = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$t = [Security.SecurityElement]::Escape($env:JR_NOTIFY_TITLE)
$b = [Security.SecurityElement]::Escape($env:JR_NOTIFY_BODY)
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>")
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))
"""


def enabled() -> bool:
    return (os.environ.get("JANCTION_RENDER_NOTIFY") or "1").strip().lower() not in ("0", "false", "off", "no")


def command(body: str, title: str = TITLE, platform: str | None = None) -> tuple[list[str], dict[str, str]] | None:
    """その OS で通知を出すコマンドと、足す環境変数。出せない OS なら None。"""
    plat = platform or sys.platform
    if plat.startswith("win"):
        exe = shutil.which("powershell.exe") or shutil.which("powershell")
        if not exe:
            return None
        return ([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS_TOAST],
                {"JR_NOTIFY_TITLE": title, "JR_NOTIFY_BODY": body})
    if plat == "darwin":
        return (["osascript", "-e", "on run argv", "-e",
                 "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run", title, body], {})
    exe = shutil.which("notify-send")
    return ([exe, title, body], {}) if exe else None


def notify(body: str, title: str = TITLE) -> bool:
    """通知を 1 つ出す。出せたら True。止めてある・出せない・失敗は False（例外は出さない）。"""
    if not enabled():
        return False
    try:
        cmd = command(body[:240], title)
        if cmd is None:
            return False
        argv, env = cmd
        r = subprocess.run(argv, env={**os.environ, **env}, capture_output=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0
    except Exception:  # noqa: BLE001 — 通知は付け足し。失敗しても受け取りは続ける
        return False
