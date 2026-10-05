"""JANCTION Render example 02: turntable of a stylized pair of headphones (orbit=true, MP4).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex02_turntable_headphones.py",
                        orbit=True, orbit_frames=24, width=1280, height=720, samples=64,
                        environment="studio", output="mp4")
The orbit camera circles the non-flat objects; the thin pedestal is flat and is ignored for framing.
"""
import math

import bpy
from mathutils import Vector

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 1


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


def smooth(ob):
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


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


plastic = material("Plastic", (0.07, 0.07, 0.08), roughness=0.45)
accent = material("Accent", (0.85, 0.62, 0.3), roughness=0.25, metallic=1.0)
cushion = material("Cushion", (0.11, 0.11, 0.12), roughness=0.95)
base = material("Pedestal", (0.75, 0.75, 0.73), roughness=0.5)

band = add("primitive_torus_add", "Headband", plastic, major_radius=1.0, minor_radius=0.075, major_segments=96,
           minor_segments=24, location=(0, 0, 0.9), rotation=(math.pi / 2, 0, 0))
smooth(band)
for sign, side in ((-1, "L"), (1, "R")):
    cup = add("primitive_cylinder_add", "Cup" + side, accent, radius=0.42, depth=0.26, vertices=96,
              location=(sign * 1.05, 0, 0.9), rotation=(0, math.pi / 2, 0))
    smooth(cup)
    pad = add("primitive_torus_add", "Pad" + side, cushion, major_radius=0.34, minor_radius=0.1, major_segments=96,
              minor_segments=24, location=(sign * 0.9, 0, 0.9), rotation=(0, math.pi / 2, 0))
    smooth(pad)
    arm = add("primitive_cylinder_add", "Arm" + side, plastic, radius=0.05, depth=0.5, vertices=32,
              location=(sign * 1.0, 0, 1.25), rotation=(0, sign * 0.35, 0))
    smooth(arm)
pedestal = add("primitive_cylinder_add", "Pedestal", base, radius=1.7, depth=0.04, vertices=128, location=(0, 0, 0.02))
smooth(pedestal)

light("Key", "AREA", (2.5, -3.0, 3.5), 300, target=(0, 0, 0.9), size=2.0)
camera((0.0, -6.0, 1.7), (0.0, 0.0, 0.9), lens=50)
