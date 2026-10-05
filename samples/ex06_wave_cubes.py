"""JANCTION Render example 06: a 12x12 field of cubes rippling in a wave, 48 frames on EEVEE (MP4).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex06_wave_cubes.py",
                        frame_start=1, frame_end=48, width=1280, height=720, engine="eevee", output="mp4")
The script keys every cube's height on every second frame; the scene has its own world and lights,
so no environment preset is needed.
"""
import colorsys
import math

import bpy
from mathutils import Vector

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 48
scene.render.fps = 24
FRAMES = 48


def material(name, color, roughness=0.5, metallic=0.0, **inputs):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    for key, value in inputs.items():
        bsdf.inputs[key].default_value = value
    return mat


def add(op, name, mat=None, **kw):
    getattr(bpy.ops.mesh, op)(**kw)
    ob = bpy.context.object
    ob.name = name
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def look_at(ob, target):
    ob.rotation_euler = (Vector(target) - ob.location).to_track_quat("-Z", "Y").to_euler()


def camera(location, target, lens=50.0):
    data = bpy.data.cameras.new("Camera")
    data.lens = lens
    cam = bpy.data.objects.new("Camera", data)
    scene.collection.objects.link(cam)
    cam.location = location
    look_at(cam, target)
    scene.camera = cam
    return cam


def light(name, kind, location, energy, target=None, size=1.0, color=(1.0, 1.0, 1.0)):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    if kind == "AREA":
        data.size = size
    ob = bpy.data.objects.new(name, data)
    scene.collection.objects.link(ob)
    ob.location = location
    if target is not None:
        look_at(ob, target)
    return ob


def own_world(color=(0.05, 0.05, 0.06), strength=1.0):
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1.0)
    bg.inputs["Strength"].default_value = strength
    scene.world = world
    return world


own_world((0.02, 0.03, 0.06), 0.6)
floor = material("Floor", (0.06, 0.06, 0.08), roughness=0.4)
add("primitive_plane_add", "Floor", floor, size=40, location=(0, 0, -0.2))

N = 12
GAP = 1.0
mats = {}
for ix in range(N):
    for iy in range(N):
        x = (ix - (N - 1) / 2) * GAP
        y = (iy - (N - 1) / 2) * GAP
        dist = math.hypot(x, y)
        hue = (0.55 + 0.06 * dist) % 1.0
        key = round(hue, 2)
        if key not in mats:
            r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 0.9)
            mats[key] = material("Cube%02d" % len(mats), (r, g, b), roughness=0.35)
        cube = add("primitive_cube_add", "Cube_%d_%d" % (ix, iy), mats[key], size=0.8, location=(x, y, 0.6))
        # 2 コマおきに高さを打つ。位相は 48 コマで 1 周するので、MP4 はそのままループする
        for f in list(range(1, FRAMES + 1, 2)) + [FRAMES + 1]:
            phase = 2 * math.pi * (f - 1) / FRAMES
            cube.location = (x, y, 0.6 + 0.55 * math.sin(phase * 2 - 0.9 * dist))
            cube.keyframe_insert("location", frame=f)

light("Sun", "SUN", (6.0, -8.0, 10.0), 3.0, target=(0, 0, 0), color=(1.0, 0.95, 0.9))
light("Fill", "AREA", (-8.0, 6.0, 7.0), 1500, target=(0, 0, 0.5), size=6.0, color=(0.7, 0.8, 1.0))
camera((9.5, -12.5, 8.5), (0.0, 0.0, 0.3), lens=45)
