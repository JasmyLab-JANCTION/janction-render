"""Properties > Render > JANCTION Render panel."""
import threading

import bpy

from . import state
from .prefs import WEBSITE, get_prefs, key_prefix, make_client

_ICONS = {"done": 'CHECKMARK', "failed": 'ERROR', "canceled": 'CANCEL', "idle": 'INFO'}


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

        row = layout.row(align=True)
        row.operator("jr.preview", icon='RENDER_STILL')
        row.operator("jr.estimate", icon='TIME')
        row.operator("jr.final", icon='RENDER_ANIMATION')
        if snap["phase"] in state.BUSY:
            layout.operator("jr.cancel", icon='CANCEL')

        if snap["message"]:
            layout.label(text=snap["message"], icon=_ICONS.get(snap["phase"], 'TIME'))
        for w in snap["warnings"][:3]:
            layout.label(text=w, icon='ERROR')
        if snap["result"]:
            row = layout.row(align=True)
            row.label(text=_short(snap["result"]), icon='FILE_FOLDER')
            row.operator("jr.open_results", text="", icon='FILE_FOLDER')

        layout.operator("wm.url_open", text="render.janction.jp", icon='URL').url = WEBSITE


def register() -> None:
    bpy.utils.register_class(RENDER_PT_janction_render)


def unregister() -> None:
    bpy.utils.unregister_class(RENDER_PT_janction_render)
