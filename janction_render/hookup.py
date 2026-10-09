"""ほかの AI クライアントとプロジェクトに JANCTION Render をつなぐ（10/10、ほかの AI に呼んでもらうためのフック）。

    janction-render connect               # この PC にある AI クライアントと、つなぐ方法を出すだけ（何も変えない）
    janction-render connect claude-code   # その 1 つにつなぐ（そのアプリのコマンドを実行するか、設定ファイルに 1 項目足す）
    janction-render connect all --yes     # 見つかったもの全部
    janction-render init                  # 今のフォルダ（プロジェクト）に、エージェント向けの指示と MCP の設定を書く

設定ファイルは JSON に janction-render の 1 項目を足すだけで、ほかの項目は消さない。書き換える前に <名前>.bak に控える。
同じ内容が入っていれば書かない。AGENTS.md などの指示は印（<!-- janction-render:start --> … end）の間だけを入れ替える。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

NAME = "janction-render"
DEFAULT_BASE = "https://render.janction.jp"
GEMINI_EXTENSION = "https://github.com/JasmyLab-JANCTION/janction-render"
MARK_START = "<!-- janction-render:start -->"
MARK_END = "<!-- janction-render:end -->"


def base_url(server: Optional[str] = None) -> str:
    return (server or os.environ.get("JANCTION_RENDER_SERVER") or DEFAULT_BASE).rstrip("/")


def mcp_url(server: Optional[str] = None) -> str:
    return base_url(server) + "/mcp"


# ---- 設定ファイル（JSON）に 1 項目足す -------------------------------------------------------------------------

def merge_json(path: Path, top: str, entry: dict[str, Any], dry_run: bool = False) -> str:
    """path の JSON の data[top][NAME] = entry にする。戻り値 'added' / 'updated' / 'unchanged'。
    壊れた JSON や想定外の形なら ValueError（ファイルは触らない）。"""
    data: dict[str, Any] = {}
    if path.exists():
        txt = path.read_text(encoding="utf-8")
        if txt.strip():
            try:
                data = json.loads(txt)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} is not valid JSON ({exc.msg}); add the entry by hand") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path} does not hold a JSON object; add the entry by hand")
    servers = data.get(top)
    if servers is None:
        servers = data[top] = {}
    if not isinstance(servers, dict):
        raise ValueError(f"'{top}' in {path} is not an object; add the entry by hand")
    if servers.get(NAME) == entry:
        return "unchanged"
    action = "updated" if NAME in servers else "added"
    if dry_run:
        return action
    servers[NAME] = entry
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return action


def upsert_section(path: Path, section: str, dry_run: bool = False) -> str:
    """Markdown に印つきの節を入れる（あれば入れ替える）。'added' / 'updated' / 'unchanged'。"""
    block = f"{MARK_START}\n{section.strip()}\n{MARK_END}\n"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if MARK_START in old and MARK_END in old:
        head, rest = old.split(MARK_START, 1)
        tail = rest.split(MARK_END, 1)[1].lstrip("\n")
        new = head + block + (("\n" + tail) if tail else "")
        action = "updated"
    else:
        new = (old.rstrip("\n") + "\n\n" if old.strip() else "") + block
        action = "added"
    if new == old:
        return "unchanged"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
    return action


# ---- AI クライアント --------------------------------------------------------------------------------------------

def _app_config_dir(home: Path) -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return home / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config"))


def clients(server: Optional[str] = None, home: Optional[Path] = None,
            which: Callable[[str], Optional[str]] = shutil.which) -> list[dict[str, Any]]:
    """つなぎ先の一覧。kind: cmd（そのアプリのコマンドを実行）/ json（設定ファイルに足す）/ manual（画面で足す）。
    found: この PC で見つかったか（コマンドがある・設定のフォルダがある）。"""
    url = mcp_url(server)
    home = home or Path.home()
    out: list[dict[str, Any]] = []
    for key, label, exe, argv in (
        ("claude-code", "Claude Code", "claude", ["mcp", "add", "--scope", "user", "--transport", "http", NAME, url]),
        ("codex", "Codex CLI", "codex", ["mcp", "add", NAME, "--url", url]),
        ("gemini", "Gemini CLI", "gemini", ["extensions", "install", GEMINI_EXTENSION]),
    ):
        path = which(exe)
        out.append({"key": key, "label": label, "kind": "cmd", "found": bool(path),
                    "argv": [path or exe, *argv], "show": " ".join([exe, *argv])})
    for key, label, cfg, top, entry in (
        ("cursor", "Cursor", home / ".cursor" / "mcp.json", "mcpServers", {"url": url}),
        ("windsurf", "Windsurf", home / ".codeium" / "windsurf" / "mcp_config.json", "mcpServers", {"serverUrl": url}),
        ("vscode", "VS Code", _app_config_dir(home) / "Code" / "User" / "mcp.json", "servers", {"type": "http", "url": url}),
    ):
        out.append({"key": key, "label": label, "kind": "json", "found": cfg.parent.exists(), "path": cfg, "top": top,
                    "entry": entry, "show": f"{cfg}: \"{top}\": {{\"{NAME}\": {json.dumps(entry)}}}"})
    for key, label, how in (
        ("claude-app", "Claude.ai / Claude Desktop", f"Settings > Connectors > Add custom connector > {url}"),
        ("chatgpt", "ChatGPT", f"Settings > Connectors > Advanced > Developer mode > Create > {url}"),
        ("grok", "Grok", f"Connectors > New Connector > Custom > {url}"),
        ("notion", "Notion Agent", f"Settings > Connections > Discover > Add Custom MCP > {url}"),
    ):
        out.append({"key": key, "label": label, "kind": "manual", "found": False, "show": how})
    return out


def connect(target: str = "", yes: bool = False, server: Optional[str] = None, home: Optional[Path] = None,
            which: Callable[[str], Optional[str]] = shutil.which,
            run: Callable[..., Any] = subprocess.run, echo: Callable[[str], None] = print) -> int:
    """target なし: 一覧を出すだけ。target=キー: その 1 つ。target=all: 見つかった cmd / json 全部（--yes が要る）。"""
    cs = clients(server, home, which)
    keys = [c["key"] for c in cs]
    if not target:
        echo(f"JANCTION Render MCP: {mcp_url(server)}")
        for c in cs:
            mark = "found" if c["found"] else ("by hand" if c["kind"] == "manual" else "not found")
            echo(f"  {c['key']:12} {c['label']:26} [{mark}]  {c['show']}")
        echo("Connect one: janction-render connect <name>   all found: janction-render connect all --yes")
        return 0
    if target != "all" and target not in keys:
        echo(f"unknown client '{target}'; choose from: {', '.join(keys)}, all")
        return 2
    if target == "all" and not yes:
        echo("connect all changes the settings of every client found here; run again with --yes")
        return 2
    chosen = [c for c in cs if (c["key"] == target) or (target == "all" and c["found"] and c["kind"] != "manual")]
    if not chosen:
        echo("no AI client found on this computer; see 'janction-render connect' for the manual steps")
        return 1
    rc = 0
    for c in chosen:
        if c["kind"] == "manual":
            echo(f"{c['label']}: {c['show']}")
            continue
        if c["kind"] == "cmd":
            if not c["found"]:
                echo(f"{c['label']}: '{c['argv'][0]}' is not on PATH; install it first, or run: {c['show']}")
                rc = 1
                continue
            p = run(c["argv"], capture_output=True, text=True)
            msg = ((p.stdout or "") + (p.stderr or "")).strip()
            if p.returncode == 0:
                echo(f"{c['label']}: connected ({c['show']})")
            elif "already exists" in msg.lower():
                echo(f"{c['label']}: already connected")
            else:
                echo(f"{c['label']}: failed ({p.returncode}): {msg[-300:]}")
                rc = 1
            continue
        try:
            action = merge_json(c["path"], c["top"], c["entry"])
            echo(f"{c['label']}: {action} in {c['path']}" + ("" if action == "unchanged" else
                                                             f" (backup: {c['path'].name}.bak)" if action == "updated" else ""))
        except (OSError, ValueError) as exc:
            echo(f"{c['label']}: {exc}")
            rc = 1
    echo("Restart the app (or reload its MCP servers), then ask: \"Render a preview of "
         f"{base_url(server)}/samples/cube_scene.py\"")
    return rc


# ---- プロジェクト（AGENTS.md・CLAUDE.md・.mcp.json ほか） ---------------------------------------------------

def agents_section(server: Optional[str] = None) -> str:
    """プロジェクトのエージェント向けの指示（AGENTS.md / CLAUDE.md / GEMINI.md）。値段の数字は書かない（変わるので）。"""
    b, url = base_url(server), mcp_url(server)
    return (
        "## Rendering 3D scenes: JANCTION Render\n\n"
        "When this project needs an image or a video of a Blender or 3D scene (a .blend, a bpy script, or a GLB, FBX, OBJ "
        "or USD model) and this machine has no NVIDIA GPU, or rendering locally would take more than a few minutes, render "
        "it with JANCTION Render instead of running Blender here.\n\n"
        f"- MCP server: {url} (set up in .mcp.json). Tools: scene_info, render_preview, render_estimate, render_final, "
        "render_status, render_download.\n"
        "- Flow: render_preview first (an image in seconds and a critic verdict with fix code), apply the fixes, then "
        "render_estimate, ask the user, and only then render_final.\n"
        "- Without MCP, from a terminal: `uvx janction-render preview <scene>`, then "
        "`uvx janction-render render <scene> --frames 1-48 --output mp4 --wait` (`uvx janction-render try` renders a "
        "sample first).\n"
        f"- Free time for new keys and prices: call the billing tool or see {b}/pricing. Ask the user before a final "
        "render.\n"
        f"- Facts for agents: {b}/llms.txt\n")


def claude_skill(server: Optional[str] = None) -> str:
    """Claude Code のプロジェクト用スキル（.claude/skills/janction-render/SKILL.md）。描く場面で Claude が自分から読む。"""
    return ("---\nname: janction-render\ndescription: Render Blender or 3D scenes (a .blend, a bpy script, or a GLB, FBX, OBJ "
            "or USD model) on cloud GPUs with JANCTION Render when this machine has no NVIDIA GPU or local rendering would "
            "be slow. Preview first, ask the user before a final render.\n---\n\n" + agents_section(server))


def _write_text(path: Path, text: str, dry_run: bool) -> str:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    action = "unchanged" if old == text else ("updated" if old is not None else "added")
    if action != "unchanged" and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return action


def cursor_rule(server: Optional[str] = None) -> str:
    return ("---\ndescription: Render Blender or 3D scenes on cloud GPUs with JANCTION Render (preview first, ask before a "
            "final render)\nalwaysApply: false\n---\n\n" + agents_section(server))


def init(directory: Path, server: Optional[str] = None, cursor: Optional[bool] = None, vscode: Optional[bool] = None,
         claude: Optional[bool] = None, dry_run: bool = False) -> list[tuple[Path, str]]:
    """プロジェクトに書く。既定: AGENTS.md と .mcp.json。CLAUDE.md・GEMINI.md・.cursor・.vscode は、すでにあるときか
    フラグで明示したときだけ（人のプロジェクトにファイルを増やしすぎない）。戻り値 [(パス, 'added'/'updated'/'unchanged')]。"""
    d = Path(directory)
    url = mcp_url(server)
    section = agents_section(server)
    done: list[tuple[Path, str]] = []
    done.append((d / "AGENTS.md", upsert_section(d / "AGENTS.md", section, dry_run)))
    done.append((d / ".mcp.json", merge_json(d / ".mcp.json", "mcpServers", {"type": "http", "url": url}, dry_run)))
    if claude or (claude is None and (d / "CLAUDE.md").exists()):
        done.append((d / "CLAUDE.md", upsert_section(d / "CLAUDE.md", section, dry_run)))
    if claude or (claude is None and (d / ".claude").is_dir()):
        skill = d / ".claude" / "skills" / "janction-render" / "SKILL.md"
        done.append((skill, _write_text(skill, claude_skill(server), dry_run)))
    if (d / "GEMINI.md").exists():
        done.append((d / "GEMINI.md", upsert_section(d / "GEMINI.md", section, dry_run)))
    if cursor or (cursor is None and (d / ".cursor").is_dir()):
        done.append((d / ".cursor" / "mcp.json", merge_json(d / ".cursor" / "mcp.json", "mcpServers", {"url": url}, dry_run)))
        rule = d / ".cursor" / "rules" / "janction-render.mdc"
        done.append((rule, _write_text(rule, cursor_rule(server), dry_run)))
    if vscode or (vscode is None and (d / ".vscode").is_dir()):
        done.append((d / ".vscode" / "mcp.json",
                     merge_json(d / ".vscode" / "mcp.json", "servers", {"type": "http", "url": url}, dry_run)))
    return done
