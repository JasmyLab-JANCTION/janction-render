"""JANCTION Render for Blender: render the open .blend on JANCTION cloud GPUs.

Blender loads this package as an extension (``bl_ext.<repository>.janction_render``),
so every import inside the package is relative. The manifest
(blender_manifest.toml) carries the metadata; there is no bl_info.
"""

__version__ = "0.1.3"

if "bpy" in locals():  # reload (F3 > Reload Scripts) picks up edited modules
    import importlib

    for _module in (client, state, assets, props, prefs, ops, panel):  # noqa: F821 - bound by the first import
        importlib.reload(_module)

import bpy  # noqa: E402,F401

from . import assets, client, ops, panel, prefs, props, state  # noqa: E402,F401

_MODULES = (props, prefs, ops, panel)


def register() -> None:
    for module in _MODULES:
        module.register()


def unregister() -> None:
    for module in reversed(_MODULES):
        try:
            module.unregister()
        except Exception:  # noqa: BLE001 - keep unregistering the rest
            pass
