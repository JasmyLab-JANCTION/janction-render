"""JANCTION Render example 10: the letters of a word rise out of a glossy floor one after another, 48 frames on EEVEE (MP4).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex10_text_reveal.py",
                        frame_start=1, frame_end=48, width=1280, height=720, engine="eevee", output="mp4")
Each letter is its own text object with two location keyframes; Blender eases between them.
"""
import math

import bpy
from mathutils import Vector

WORD = "JANCTION"

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 48
scene.render.fps = 24


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


own_world((0.03, 0.03, 0.035), 1.0)
white = material("Letters", (0.92, 0.92, 0.9), roughness=0.3, **{"Coat Weight": 0.6})
floor = material("Floor", (0.05, 0.05, 0.06), roughness=0.1)
add("primitive_plane_add", "Floor", floor, size=40)

n = len(WORD)
spacing = 1.05
for i, ch in enumerate(WORD):
    font = bpy.data.curves.new("Letter%d" % i, "FONT")
    font.body = ch
    font.size = 1.3
    font.extrude = 0.18
    font.bevel_depth = 0.02
    font.align_x = "CENTER"
    font.materials.append(white)
    letter = bpy.data.objects.new("Letter%d" % i, font)
    scene.collection.objects.link(letter)
    letter.rotation_euler = (math.pi / 2, 0, 0)
    x = (i - (n - 1) / 2) * spacing
    start = 1 + 3 * i
    # 最後は床から少し浮かせる（J の下に伸びる部分が床に隠れないように）
    letter.location = (x, 0, -1.9)
    letter.keyframe_insert("location", frame=start)
    letter.location = (x, 0, 0.3)
    letter.keyframe_insert("location", frame=start + 16)

light("Key", "AREA", (3.0, -5.0, 5.0), 800, target=(0, 0, 0.5), size=3.0)
light("Rim", "AREA", (-4.0, 4.0, 3.0), 400, target=(0, 0, 0.5), size=2.0, color=(0.75, 0.85, 1.0))
camera((0.0, -9.5, 2.6), (0.0, 0.0, 0.5), lens=32)
