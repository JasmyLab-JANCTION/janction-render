"""A room furnished from Poly Haven (CC0) by name: no files to upload.

Send this script with asset_urls (remote MCP) or assets (stdio / CLI) set to
    ["polyhaven:wooden_table_02", "polyhaven:wood_floor_deck", "polyhaven:studio_small_09"]
The service fetches the files into JR_ASSETS_DIR/<id>/ and the helpers below wire them up.
    janction-render preview samples/polyhaven_room.py --assets polyhaven:wooden_table_02 polyhaven:wood_floor_deck polyhaven:studio_small_09
"""
import math

import bpy
import jr_assets  # provided by the service in front of every scene script

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, 24

jr_assets.import_model("wooden_table_02")                      # 1.13 x 0.71 x 0.80 m, textures included
bpy.ops.mesh.primitive_plane_add(size=6)
floor = bpy.context.active_object
jr_assets.apply(floor, jr_assets.material("wood_floor_deck", scale=2.0))
jr_assets.world_hdri("studio_small_09", strength=1.0)

cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (2.9, -3.1, 2.0)
cam.rotation_euler = (math.radians(66), 0, math.radians(43))
