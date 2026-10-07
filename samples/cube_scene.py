"""見本: bpy でシーンを組むスクリプト（手元に Blender が無くても描ける入力の形）。

床の上に立方体・球・トーラス・サルを置き、カメラが 24 コマで一周する。
受付側の設定（解像度・サンプル数・ノイズ除去・GPU）はこの後に上書きされるので、
ここではシーンの中身とコマ範囲だけを決める。
"""
import math

import bpy

# 起動時の既定のオブジェクト（Cube / Light / Camera）を消して空にする
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 24
scene.render.fps = 24


def material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


# 床
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
floor = bpy.context.object
floor.name = "Floor"
floor.data.materials.append(material("FloorMat", (0.85, 0.85, 0.82), roughness=0.9))

# 物
bpy.ops.mesh.primitive_cube_add(size=2, location=(-2.5, 0, 1))
cube = bpy.context.object
cube.name = "Cube"
cube.data.materials.append(material("CubeMat", (0.9, 0.35, 0.2), roughness=0.4))

bpy.ops.mesh.primitive_uv_sphere_add(radius=1.1, location=(0.5, -1.5, 1.1), segments=64, ring_count=32)
sphere = bpy.context.object
sphere.name = "Sphere"
bpy.ops.object.shade_smooth()
sphere.data.materials.append(material("SphereMat", (0.2, 0.5, 0.9), roughness=0.15, metallic=0.8))

bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.35, location=(2.8, 1.0, 0.4))
torus = bpy.context.object
torus.name = "Torus"
bpy.ops.object.shade_smooth()
torus.data.materials.append(material("TorusMat", (0.95, 0.8, 0.2), roughness=0.3, metallic=0.4))

bpy.ops.mesh.primitive_monkey_add(size=1.6, location=(0.2, 2.2, 1.0), rotation=(0, 0, math.radians(-30)))
monkey = bpy.context.object
monkey.name = "Suzanne"
bpy.ops.object.shade_smooth()
monkey.data.materials.append(material("MonkeyMat", (0.3, 0.7, 0.4), roughness=0.5))

# 光
sun_data = bpy.data.lights.new("Sun", "SUN")
sun_data.energy = 4.0
sun_data.angle = math.radians(3)
sun = bpy.data.objects.new("Sun", sun_data)
sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
scene.collection.objects.link(sun)

area_data = bpy.data.lights.new("Fill", "AREA")
area_data.energy = 400.0
area_data.size = 6.0
fill = bpy.data.objects.new("Fill", area_data)
fill.location = (-5, -5, 6)
fill.rotation_euler = (math.radians(45), 0, math.radians(-45))
scene.collection.objects.link(fill)

world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.55, 0.65, 0.8, 1.0)
bg.inputs[1].default_value = 0.6
scene.world = world

# カメラ: 中心を見ながら 24 コマで一周する。どのコマでも全部が写る（試し描きの批評が要確認を出さない）
target = bpy.data.objects.new("Target", None)
target.location = (0.3, 0.3, 0.9)
scene.collection.objects.link(target)

cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 35
cam = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
track = cam.constraints.new("TRACK_TO")
track.target = target
track.track_axis = "TRACK_NEGATIVE_Z"
track.up_axis = "UP_Y"

radius, height = 12.0, 4.5   # 10/8: 24 コマのどのコマでも 4 つの物が枠に収まる距離（9.0 / 4.0 / 40 mm ではトーラスが切れた）
for f in range(scene.frame_start, scene.frame_end + 1):
    t = (f - scene.frame_start) / (scene.frame_end - scene.frame_start + 1)
    a = 2 * math.pi * t
    cam.location = (radius * math.cos(a), radius * math.sin(a), height)
    cam.keyframe_insert(data_path="location", frame=f)
