"""Properties > Render > JANCTION Render panel.

11/9（0.1.11）: 下に Files の小さなパネル（送るファイルの一覧を全部。前は警告の 3 行だけ）と、前の Blender で終わらなかった
仕事の Resume を足した。
"""
import threading
import time

import bpy

from . import state
from .prefs import WEBSITE, get_prefs, key_prefix, make_client

_ICONS = {"done": 'CHECKMARK', "failed": 'ERROR', "canceled": 'CANCEL', "idle": 'INFO'}
_DEP_ICONS = {"send": 'EXPORT', "packed": 'PACKAGE', "skip": 'ERROR'}
FILES_ROWS = 200        # Files に並べる行の上限（残りは数だけ。Copy list で全部を貼り付けられる）


def _quota_once(prefs) -> None:
    """Fetch /v1/me in the background the first time the panel is drawn with a key."""
    if state.get("quota_requested") or not prefs or not prefs.api_key:
        return
    state.update(quota_requested=True)
    client = make_client(prefs)

    def work() -> None:
        try:
            state.set_quota(client.me())
        except Exception:  # noqa: BLE001 - the panel then shows the key without minutes
            pass
        try:
            state.set_capabilities(client.capabilities())
        except Exception:  # noqa: BLE001 - 読めなければ旗つきの物は出さない（今までと同じ）
            pass

    threading.Thread(target=work, name="janction-quota", daemon=True).start()


def _short(path: str, limit: int = 38) -> str:
    return path if len(path) <= limit else "..." + path[-(limit - 3):]


class RENDER_PT_janction_render(bpy.types.Panel):
    bl_label = "JANCTION Render"
    bl_idname = "RENDER_PT_janction_render"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs(context)
        snap = state.snapshot()
        settings = getattr(context.scene, "jr_settings", None)

        row = layout.row(align=True)
        if prefs is None or not prefs.api_key:
            row.label(text="No key", icon='KEY_DEHLT')
            row.operator("jr.get_key", text="Get a free key", icon='KEY_HLT')
        else:
            _quota_once(prefs)
            quota = state.quota_text()
            row.label(text=f"{key_prefix(prefs.api_key)}  {quota}" if quota else key_prefix(prefs.api_key),
                      icon='KEY_HLT')
            row.operator("jr.refresh_quota", text="", icon='FILE_REFRESH')

        if settings is not None:
            col = layout.column(align=True)
            col.prop(settings, "environment")
            col.prop(settings, "blender_version")
            sub = col.row(align=True)
            sub.prop(settings, "use_scene_samples")
            right = sub.row(align=True)
            right.enabled = not settings.use_scene_samples
            right.prop(settings, "samples", text="")
            col.prop(settings, "output")
            if prefs is not None and getattr(prefs, "show_costs", False):
                col.prop(settings, "max_yen")

        row = layout.row(align=True)
        row.operator("jr.preview", icon='RENDER_STILL')
        row.operator("jr.estimate", icon='TIME')
        row.operator("jr.final", icon='RENDER_ANIMATION')
        # 11/13: 受付が下描き動画を全員に開けているときだけ（旗 JR_DRAFT_VIDEO）。ほかの旗つきの物は Blender の設定から拾う
        if state.open_arg("render_preview", "draft_video"):
            layout.operator("jr.draft", icon='SEQUENCE')
        # 11/13 v2 REN-05: 受付が案件の印を全員に開けていて、この .blend が案件の番号を持っているときだけ
        if state.open_feature("project_tag"):
            layout.operator("jr.project_history", icon='FILE_BLEND')
            for row in (state.get("project_history") or [])[:5]:
                when = time.strftime("%m/%d %H:%M", time.localtime(float(row.get("created_at") or 0)))
                gone = " (files expired)" if row.get("files_expired") else ""
                layout.label(text=f"{when} {row.get('kind')} {row.get('status')} {row.get('size')}{gone}")
        if snap["phase"] in state.BUSY:
            layout.operator("jr.cancel", icon='CANCEL')

        if snap["message"]:
            layout.label(text=snap["message"], icon=_ICONS.get(snap["phase"], 'TIME'))
        if snap.get("checkout_url") and snap["phase"] == "failed":
            # 402: pay on the Stripe Checkout page in the browser, then press the same button again
            layout.operator("wm.url_open", text="Open top-up page", icon='URL').url = snap["checkout_url"]
        for w in snap["warnings"][:3]:
            layout.label(text=w, icon='ERROR')
        if len(snap["warnings"]) > 3:
            layout.label(text=f"{len(snap['warnings']) - 3} more: see Files below", icon='INFO')
        if snap["result"]:
            row = layout.row(align=True)
            row.label(text=_short(snap["result"]), icon='FILE_FOLDER')
            row.operator("jr.open_results", text="", icon='FILE_FOLDER')

        if prefs is not None and prefs.api_key and snap["phase"] not in state.BUSY:
            from . import ops
            try:
                rows = ops.pending_jobs(prefs)
            except Exception:  # noqa: BLE001 - 一覧が読めなくてもパネルは出す
                rows = []
            for r in rows[-5:]:
                row = layout.row(align=True)
                row.label(text=f"Unfinished {r.get('kind') or 'render'} {r.get('job_id') or '(not started)'} "
                               f"{r.get('blend') or ''}".rstrip(), icon='TIME')
                row.operator("jr.resume_job", text="Resume", icon='PLAY').idem = str(r.get("idem") or "")
                row.operator("jr.forget_job", text="", icon='X').idem = str(r.get("idem") or "")

        layout.operator("wm.url_open", text="render.janction.jp", icon='URL').url = WEBSITE


class RENDER_PT_janction_render_files(bpy.types.Panel):
    """送るファイルの一覧（全部）。Check files で集め直す。"""
    bl_label = "Files"
    bl_idname = "RENDER_PT_janction_render_files"
    bl_parent_id = "RENDER_PT_janction_render"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        snap = state.snapshot()
        row = layout.row(align=True)
        row.operator("jr.scan_files", icon='VIEWZOOM')
        row.operator("jr.copy_file_list", text="", icon='COPYDOWN')
        found = snap.get("checks") or []
        if found:                                  # 11/13 手元の点検（送らずに分かること）
            layout.label(text=snap.get("checks_summary") or "", icon='CHECKMARK' if not any(c[0] != "info" for c in found)
                         else 'ERROR')
            for level, _code, text in found[:8]:
                layout.label(text=text, icon={"block": 'CANCEL', "warn": 'ERROR'}.get(level, 'INFO'))
        deps = snap.get("deps") or []
        if not deps:
            layout.label(text="Press Check files to list what will be sent", icon='INFO')
            return
        if snap.get("deps_summary"):
            layout.label(text=snap["deps_summary"])
        col = layout.column(align=True)
        for d in deps[:FILES_ROWS]:
            files = f", {d['files']} files" if d.get("files", 0) > 1 else ""
            moved = ", path rewritten" if d.get("remapped") else ""
            col.label(text=f"{d['kind']} {d['label']}{files}{moved}", icon=_DEP_ICONS.get(d.get("status"), 'DOT'))
            if d.get("note"):
                col.label(text="    " + str(d["note"]))
        if len(deps) > FILES_ROWS:
            col.label(text=f"{len(deps) - FILES_ROWS} more (Copy list has all of them)")


CLASSES = (RENDER_PT_janction_render, RENDER_PT_janction_render_files)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
