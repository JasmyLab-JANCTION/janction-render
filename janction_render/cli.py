"""コマンド。MCP と同じ機能を同じ受付で（要件 F-01）。

    janction-render preview scene.py                      # 試し描き 1 コマ → PNG
    janction-render render scene.blend --frames 1-240     # 仕上げ → MP4（1 コマなら PNG）
    janction-render status JOB
    janction-render download JOB --out DIR [--wait 600]
    janction-render cancel JOB
    janction-render jobs
    janction-render info
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .client import Client, ClientError, parse_frames


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _size(s: str) -> tuple[int, int]:
    try:
        w, h = s.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError("size must look like 1920x1080")


def _frames(s: str) -> tuple[int, int]:
    try:
        if "-" in s:
            a, b = s.split("-", 1)
            return int(a), int(b)
        return int(s), int(s)
    except ValueError:
        raise argparse.ArgumentTypeError("frames must look like 1-240 or 12")


def _progress(j: dict[str, Any]) -> None:
    p = j["progress"]
    print(f"  {j['status']}: {p['frames_done']}/{p['frames_total']} frames"
          + (f", {p['queue_ahead']} chunks ahead" if p["queue_ahead"] else ""), file=sys.stderr)


def _scene(c: Client, args: argparse.Namespace) -> str:
    if args.scene_id:
        return args.scene_id
    if not args.scene:
        raise SystemExit("give a scene file (.blend or .py) or --scene-id")
    up = c.upload(args.scene)
    print(f"uploaded {up['name']} -> scene_id {up['scene_id']}", file=sys.stderr)
    return up["scene_id"]


def cmd_inspect(c: Client, args: argparse.Namespace) -> int:
    sid = _scene(c, args)
    j = c.submit(sid, kind="info")
    if j["status"] != "done":
        print(f"job {j['job_id']} queued (reads the scene, no render)", file=sys.stderr)
        j = c.wait(j["job_id"], timeout=args.timeout, on_progress=_progress)
    if j["status"] != "done":
        print(_j({k: j.get(k) for k in ("job_id", "status", "error", "log_tail")}))
        return 1
    info = dict(j.get("info") or {})
    info["scene_id"] = sid
    if j.get("warnings"):
        info["blender_warnings"] = j["warnings"]
    print(_j(info))
    return 0


def cmd_preview(c: Client, args: argparse.Namespace) -> int:
    sid = _scene(c, args)
    w, h = args.size
    frames = parse_frames(args.frames, default=args.frame)
    j = c.submit(sid, kind="preview", frames=frames, camera=args.camera, width=w, height=h,
                 samples=args.samples, engine=args.engine)
    print(f"job {j['job_id']} queued: frames {frames} (estimate ~{j['estimate']['seconds']}s)", file=sys.stderr)
    j = c.wait(j["job_id"], timeout=args.timeout, on_progress=_progress)
    if j["status"] != "done":
        print(_j({k: j.get(k) for k in ("job_id", "status", "error", "log_tail", "warnings")}))
        return 1
    out = Path(args.out) if args.out else Path("render_out") / j["job_id"]
    paths = c.download(j["job_id"], out)
    print(_j({"job_id": j["job_id"], "scene_id": sid, "frames": frames, "files": [str(p) for p in paths],
              "warnings": j.get("warnings") or [], "gpu_seconds": j["gpu_seconds"], "device": j["device"],
              "expires_at": j["expires_at"]}))
    return 0


def cmd_render(c: Client, args: argparse.Namespace) -> int:
    sid = _scene(c, args)
    w, h = args.size
    fs, fe = args.frames
    j = c.submit(sid, kind="final", frame_start=fs, frame_end=fe, width=w, height=h,
                 samples=args.samples, fps=args.fps, output=args.output, camera=args.camera, engine=args.engine,
                 transparent=args.transparent or None, notify_url=args.notify_url or None)
    print(f"job {j['job_id']} queued: {fe - fs + 1} frames in {j['progress']['chunks_total']} chunks, "
          f"estimate ~{j['estimate']['seconds']}s", file=sys.stderr)
    if not args.wait:
        print(_j({"job_id": j["job_id"], "scene_id": sid, "estimate": j["estimate"]}))
        return 0
    j = c.wait(j["job_id"], timeout=args.timeout, on_progress=_progress)
    if j["status"] != "done":
        print(_j({k: j.get(k) for k in ("job_id", "status", "error", "log_tail")}))
        return 1
    out = Path(args.out) if args.out else Path("render_out") / j["job_id"]
    paths = c.download(j["job_id"], out)
    print(_j({"job_id": j["job_id"], "scene_id": sid, "files": [str(p) for p in paths],
              "warnings": j.get("warnings") or [], "gpu_seconds": j["gpu_seconds"], "device": j["device"],
              "expires_at": j["expires_at"]}))
    return 0


def cmd_status(c: Client, args: argparse.Namespace) -> int:
    print(_j(c.job(args.job)))
    return 0


def cmd_download(c: Client, args: argparse.Namespace) -> int:
    j = c.wait(args.job, timeout=args.wait, on_progress=_progress) if args.wait else c.job(args.job)
    out = Path(args.out) if args.out else Path("render_out") / args.job
    paths = c.download(args.job, out)
    print(_j({"job_id": args.job, "status": j["status"], "files": [str(p) for p in paths]}))
    return 0 if j["status"] == "done" else 1


def cmd_cancel(c: Client, args: argparse.Namespace) -> int:
    j = c.cancel(args.job)
    print(_j({"job_id": j["job_id"], "status": j["status"]}))
    return 0


def cmd_revoke_key(c: Client, args: argparse.Namespace) -> int:
    if not args.yes:
        print("this revokes your key and disconnects every app that uses it; run again with --yes", file=sys.stderr)
        return 2
    print(_j(c.revoke_key()))
    return 0


def cmd_connections(c: Client, args: argparse.Namespace) -> int:
    print(_j(c.connections()))
    return 0


def cmd_disconnect(c: Client, args: argparse.Namespace) -> int:
    print(_j(c.disconnect(args.id)))
    return 0


def cmd_share(c: Client, args: argparse.Namespace) -> int:
    v = c.share(args.job, title=args.title or "", note=args.note or "", include_script=bool(args.script), listed=bool(args.gallery),
                prompt=args.prompt or "")
    print(v["url"])
    return 0


def cmd_unshare(c: Client, args: argparse.Namespace) -> int:
    print(_j(c.unshare(args.job)))
    return 0


def cmd_jobs(c: Client, args: argparse.Namespace) -> int:
    rows = c.jobs(args.limit)
    for j in rows:
        p = j["progress"]
        print(f"{j['job_id']}  {j['kind']:<7} {j['status']:<9} {j['frame_start']}-{j['frame_end']}  "
              f"{p['frames_done']}/{p['frames_total']}  gpu {j['gpu_seconds']}s")
    return 0


def cmd_info(c: Client, args: argparse.Namespace) -> int:
    print(_j({"server": c.server, "health": c.health(), "me": c.me()}))
    return 0


def cmd_balance(c: Client, args: argparse.Namespace) -> int:
    me = c.me()
    synced = c.billing_sync() if me["billing"]["enabled"] else {}
    me = c.me()
    print(_j({"balance_yen": me["balance_yen"], "free_previews_left": me["free_previews_left"],
              "billing": me["billing"], "just_credited": synced.get("credited", []),
              "ledger": c.ledger(args.limit)["entries"]}))
    return 0


def cmd_topup(c: Client, args: argparse.Namespace) -> int:
    co = c.checkout(args.yen)
    print(f"open this page in a browser and pay: {co['checkout_url']}", file=sys.stderr)
    print(_j(co))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="janction-render",
                                description="Render Blender scenes on JANCTION GPUs from the terminal.")
    p.add_argument("--server", default=None, help="server URL (default: JANCTION_RENDER_SERVER or http://127.0.0.1:8340)")
    p.add_argument("--key", default=None, help="API key (default: JANCTION_RENDER_API_KEY or an auto-issued temporary key)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("inspect", help="read the scene without rendering (cameras, frame range, missing files)")
    s.add_argument("scene", nargs="?", help=".blend file or bpy Python script")
    s.add_argument("--scene-id", default=None, help="reuse an uploaded scene")
    s.add_argument("--timeout", type=float, default=180)
    s.set_defaults(fn=cmd_inspect)

    s = sub.add_parser("preview", help="render 1-4 preview frames (fast, up to 720p; several frames are tiled)")
    s.add_argument("scene", nargs="?", help=".blend file or bpy Python script")
    s.add_argument("--scene-id", default=None, help="reuse an uploaded scene")
    s.add_argument("--frame", type=int, default=1)
    s.add_argument("--frames", default="", help="e.g. 1,8,16,24 or 1-24 (4 evenly spaced) -> one tiled image")
    s.add_argument("--camera", default=None)
    s.add_argument("--size", type=_size, default=(1280, 720))
    s.add_argument("--samples", type=int, default=16)
    s.add_argument("--engine", choices=["cycles", "eevee"], default=None, help="cycles (default) or eevee (cheaper drafts)")
    s.add_argument("--out", default=None)
    s.add_argument("--timeout", type=float, default=300)
    s.set_defaults(fn=cmd_preview)

    s = sub.add_parser("render", help="render final frames (MP4 or PNG)")
    s.add_argument("scene", nargs="?")
    s.add_argument("--scene-id", default=None)
    s.add_argument("--frames", type=_frames, required=True, help="e.g. 1-240 or 12")
    s.add_argument("--size", type=_size, default=(1920, 1080))
    s.add_argument("--samples", type=int, default=128)
    s.add_argument("--engine", choices=["cycles", "eevee"], default=None, help="cycles (default) or eevee (cheaper drafts)")
    s.add_argument("--fps", type=int, default=24)
    s.add_argument("--output", choices=["auto", "png", "exr", "mp4", "webm", "prores", "gif", "webp"], default="auto",
                   help="png/exr = frames, mp4/webm/prores/gif/webp = video (auto: mp4 for a range, png for one frame)")
    s.add_argument("--transparent", action="store_true", help="transparent background (png/exr/webm/gif/webp)")
    s.add_argument("--notify-url", default=None, help="https URL that receives one JSON POST when the job finishes")
    s.add_argument("--camera", default=None)
    s.add_argument("--out", default=None)
    s.add_argument("--wait", action="store_true", help="wait until done and download")
    s.add_argument("--timeout", type=float, default=7200)
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("status")
    s.add_argument("job")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("download")
    s.add_argument("job")
    s.add_argument("--out", default=None)
    s.add_argument("--wait", type=float, default=0, help="seconds to wait for the job first")
    s.set_defaults(fn=cmd_download)

    s = sub.add_parser("revoke-key", help="revoke your key (use when it leaked); every connected app stops working")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=cmd_revoke_key)
    s = sub.add_parser("connections", help="apps connected with your key (Claude, ChatGPT, Codex ...)")
    s.set_defaults(fn=cmd_connections)
    s = sub.add_parser("disconnect", help="disconnect one app (id from 'connections')")
    s.add_argument("id")
    s.set_defaults(fn=cmd_disconnect)
    s = sub.add_parser("share", help="publish a finished job as a public page (/r/<id>)")
    s.add_argument("job")
    s.add_argument("--title", default=None)
    s.add_argument("--note", default=None)
    s.add_argument("--prompt", default=None, help="what you asked the agent (shown on the page)")
    s.add_argument("--script", action="store_true", help="include the bpy script on the page")
    s.add_argument("--gallery", action="store_true", help="ask for the page to appear in the public gallery (after review)")
    s.set_defaults(fn=cmd_share)
    s = sub.add_parser("unshare", help="remove the public page of a job")
    s.add_argument("job")
    s.set_defaults(fn=cmd_unshare)
    s = sub.add_parser("cancel")
    s.add_argument("job")
    s.set_defaults(fn=cmd_cancel)

    s = sub.add_parser("jobs")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_jobs)

    s = sub.add_parser("info")
    s.set_defaults(fn=cmd_info)

    s = sub.add_parser("balance", help="credit balance, price, and recent ledger (also confirms payments)")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_balance)

    s = sub.add_parser("topup", help="get a Stripe checkout link to add credit")
    s.add_argument("--yen", type=int, default=None, help="amount (default: the minimum)")
    s.set_defaults(fn=cmd_topup)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    c = Client(server=args.server, api_key=args.key, client="cli")
    try:
        return int(args.fn(c, args))
    except ClientError as exc:
        if exc.status == 429 and exc.error == "quota_exceeded":
            print(f"quota: {exc.detail}", file=sys.stderr)
            print(_j({k: exc.extra.get(k) for k in ("scope", "gpu_seconds_used_today", "gpu_seconds_per_day", "resets_at")}))
            return 4
        pay = exc.payment()
        if pay:
            print(f"payment required: {exc.detail}", file=sys.stderr)
            print(f"open this page in a browser and pay, then run the command again: {pay['checkout_url']}",
                  file=sys.stderr)
            print(_j(pay))
            return 3
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
