"""Per-scene user settings (Scene.jr_settings)."""
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty

# 'DEFAULT' falls back to the add-on preferences; 'SCENE' keeps the file's own world.
ENV_ITEMS = [
    ('DEFAULT', "Default", "Use the preset from the add-on preferences"),
    ('SCENE', "Scene world", "Keep the world of this file"),
    ('studio', "Studio", "Studio HDRI"),
    ('sunset', "Sunset", "Sunset HDRI"),
    ('overcast', "Overcast", "Overcast HDRI"),
    ('night', "Night", "Night HDRI"),
]
VERSION_ITEMS = [
    ('DEFAULT', "Default", "Use the version from the add-on preferences"),
    ('5.0', "Blender 5.0", ""),
    ('5.2', "Blender 5.2", ""),
    ('5.3', "Blender 5.3", ""),
]
OUTPUT_ITEMS = [
    ('mp4', "MP4", "One video file"),
    ('png', "PNG frames", "One PNG per frame"),
    # 11/9: 1 層の OpenEXR（受付の output="exr"、前から受ける）。合成用の多層・パスは受付の旗 JR_RENDER_PASSES の別の道
    ('exr', "EXR frames", "One OpenEXR file per frame (single layer, float)"),
]


class JRSettings(bpy.types.PropertyGroup):
    output: EnumProperty(name="Output", items=OUTPUT_ITEMS, default='mp4')
    environment: EnumProperty(name="Environment", items=ENV_ITEMS, default='DEFAULT')
    blender_version: EnumProperty(name="Blender", items=VERSION_ITEMS, default='DEFAULT')
    use_scene_samples: BoolProperty(name="Scene samples", description="Use the Cycles sample count of this scene",
                                    default=True)
    samples: IntProperty(name="Samples", default=64, min=1, max=4096)
    # 1 回の仕上げの支出の上限（円、0 = なし）。設定の Show costs（既定 OFF）のときだけ出して送る（料金の文は本人の承認待ち、11/9）
    max_yen: IntProperty(name="Spending cap (JPY)", default=0, min=0, max=10000000,
                         description="The service does not start a final render estimated above this; 0 = no cap")


def register() -> None:
    bpy.utils.register_class(JRSettings)
    bpy.types.Scene.jr_settings = PointerProperty(type=JRSettings)


def unregister() -> None:
    if hasattr(bpy.types.Scene, "jr_settings"):
        del bpy.types.Scene.jr_settings
    bpy.utils.unregister_class(JRSettings)
