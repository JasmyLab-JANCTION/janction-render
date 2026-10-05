"""JANCTION Render example 01: product shot of a glass bottle on a studio backdrop (one still).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex01_product_bottle.py",
                        width=1440, height=1440, samples=128, environment="studio")
The receptionist sets resolution, samples, denoising and the GPU; this script only builds the scene,
the camera and the frame range.
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


glass = material("Glass", (0.85, 0.95, 0.92), roughness=0.04, **{"Transmission Weight": 1.0, "IOR": 1.45})
liquid = material("Liquid", (0.95, 0.55, 0.12), roughness=0.08, **{"Transmission Weight": 1.0, "IOR": 1.36})
cap = material("Cap", (0.03, 0.03, 0.03), roughness=0.45)
paper = material("Label", (0.96, 0.94, 0.88), roughness=0.7)
floor = material("Floor", (0.82, 0.82, 0.8), roughness=0.3)
wall = material("Wall", (0.9, 0.9, 0.88), roughness=0.8)

add("primitive_plane_add", "Floor", floor, size=24)
back = add("primitive_plane_add", "Backdrop", wall, size=24, location=(0, 4, 6))
back.rotation_euler = (math.pi / 2, 0, 0)

body = add("primitive_cylinder_add", "Bottle", glass, radius=0.5, depth=2.0, location=(0, 0, 1.0), vertices=96)
bev = body.modifiers.new("Bevel", "BEVEL")
bev.width = 0.12
bev.segments = 10
smooth(body)
neck = add("primitive_cylinder_add", "Neck", glass, radius=0.17, depth=0.7, location=(0, 0, 2.3), vertices=64)
smooth(neck)
inner = add("primitive_cylinder_add", "Liquid", liquid, radius=0.45, depth=1.55, location=(0, 0, 0.85), vertices=96)
smooth(inner)
top = add("primitive_cylinder_add", "Cap", cap, radius=0.21, depth=0.28, location=(0, 0, 2.78), vertices=64)
smooth(top)
label = add("primitive_cylinder_add", "Label", paper, radius=0.505, depth=0.62, location=(0, 0, 0.95), vertices=96,
            end_fill_type="NOTHING")
smooth(label)

light("Key", "AREA", (3.0, -3.0, 4.0), 450, target=(0, 0, 1.2), size=2.5)
light("Rim", "AREA", (-3.0, 3.0, 3.0), 250, target=(0, 0, 1.4), size=1.5, color=(0.9, 0.95, 1.0))
camera((0.0, -7.8, 1.5), (0.0, 0.0, 1.4), lens=70)
