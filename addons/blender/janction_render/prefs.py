"""Add-on preferences: server, API key, default preset and Blender version."""
from typing import Optional

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import state
from .client import DEFAULT_SERVER, Client, JRError

WEBSITE = "https://render.janction.jp"

PREF_ENV_ITEMS = [
    ('SCENE', "Scene world", "Keep the world of the file"),
    ('studio', "Studio", "Studio HDRI"),
    ('sunset', "Sunset", "Sunset HDRI"),
    ('overcast', "Overcast", "Overcast HDRI"),
    ('night', "Night", "Night HDRI"),
]
PREF_VERSION_ITEMS = [
    ('AUTO', "Match this Blender", "5.2 when this Blender is 5.1 or newer, otherwise 5.0, so the worker never opens the file with an older Blender"),
    ('5.0', "Blender 5.0", ""),
    ('5.2', "Blender 5.2", ""),
]


def get_prefs(context=None) -> Optional["JRPreferences"]:
    """The preferences of this add-on, or None when it is not enabled under this package name."""
    ctx = context or bpy.context
    try:
        return ctx.preferences.addons[__package__].preferences
    except (KeyError, AttributeError):
        return None


def make_client(prefs: Optional["JRPreferences"]) -> Client:
    if prefs is None:
        return Client()
    return Client(server=prefs.server_url or DEFAULT_SERVER, api_key=prefs.api_key)


def key_prefix(api_key: str) -> str:
    key = (api_key or "").strip()
    return key[:10] + "..." if len(key) > 10 else key


def save_prefs() -> None:
    """Mark preferences dirty and save them when Blender auto-saves preferences."""
    try:
        bpy.context.preferences.is_dirty = True
        if bpy.context.preferences.use_preferences_save:
            bpy.ops.wm.save_userpref()
    except Exception:  # noqa: BLE001 - saving later is fine too
        pass


class JR_OT_get_key(bpy.types.Operator):
    """Create a free API key on the server and store it in the preferences"""
    bl_idname = "jr.get_key"
    bl_label = "Get a free key"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        prefs = get_prefs(context)
        if prefs is None:
            self.report({'ERROR'}, "Add-on preferences not found")
            return {'CANCELLED'}
        client = Client(server=prefs.server_url or DEFAULT_SERVER)
        try:
            out = client.create_key(label="blender add-on")
            key = str(out.get("api_key") or "")
            if not key:
                raise JRError("bad_answer", "the server did not return a key")
            prefs.api_key = key
            save_prefs()
            me = client.me()
            state.set_quota(me)
        except JRError as exc:
            self.report({'ERROR'}, f"Could not get a key: {exc}")
            return {'CANCELLED'}
        quota = state.quota_text()
        self.report({'INFO'}, f"Key {key_prefix(key)} saved" + (f", {quota}" if quota else ""))
        return {'FINISHED'}


class JRPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    server_url: StringProperty(name="Server", default=DEFAULT_SERVER)
    api_key: StringProperty(name="API key", subtype='PASSWORD',
                            description="Free beta key from render.janction.jp (no sign-up)")
    environment: EnumProperty(name="Environment", items=PREF_ENV_ITEMS, default='SCENE')
    blender_version: EnumProperty(name="Blender", items=PREF_VERSION_ITEMS, default='AUTO')
    open_results: BoolProperty(name="Open results folder when done", default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "server_url")
        row = layout.row(align=True)
        row.prop(self, "api_key")
        row.operator(JR_OT_get_key.bl_idname, text="Get a free key", icon='KEY_HLT')
        quota = state.quota_text()
        if self.api_key:
            layout.label(text=f"Key {key_prefix(self.api_key)}" + (f": {quota}" if quota else ""), icon='CHECKMARK')
        col = layout.column(align=True)
        col.prop(self, "environment")
        col.prop(self, "blender_version")
        layout.prop(self, "open_results")
        layout.operator("wm.url_open", text="render.janction.jp", icon='URL').url = WEBSITE


CLASSES = (JR_OT_get_key, JRPreferences)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
