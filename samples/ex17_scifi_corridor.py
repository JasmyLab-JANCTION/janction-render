"""JANCTION Render example 17: a sci-fi corridor lit by emissive strips (one still).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex17_scifi_corridor.py",
                        width=1920, height=1080, samples=128, environment="night")
Panels are boxes; the light comes from emissive materials (Principled BSDF emission), so the night preset only
adds a faint ambient. No volumetrics, so it stays cheap.
"""
import math
import random

import bpy
from mathutils import Vector

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 1
scene.render.fps = 24
random.seed(17)


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


def text(body, name, mat, location, size=1.0, extrude=0.02, rotation=(math.pi / 2, 0, 0), align="CENTER"):
    cu = bpy.data.curves.new(name, type="FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    ob = bpy.data.objects.new(name, cu)
    scene.collection.objects.link(ob)
    ob.location = location
    ob.rotation_euler = rotation
    ob.data.materials.append(mat)
    return ob


def look_at(ob, target):
    ob.rotation_euler = (Vector(target) - ob.location).to_track_quat("-Z", "Y").to_euler()


def camera(location, target, lens=50.0, name="Camera", active=True, fstop=None, focus=None):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    if fstop is not None:
        data.dof.use_dof = True
        data.dof.aperture_fstop = fstop
        data.dof.focus_distance = focus if focus is not None else (Vector(target) - Vector(location)).length
    cam = bpy.data.objects.new(name, data)
    scene.collection.objects.link(cam)
    cam.location = location
    look_at(cam, target)
    if active:
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


def world(color=(0.02, 0.02, 0.03), strength=1.0):
    w = bpy.data.worlds.new("World")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*color, 1.0)
    bg.inputs[1].default_value = strength
    scene.world = w
    return w

panel = material("Panel", (0.35, 0.37, 0.4), roughness=0.45, metallic=0.7)
dark = material("Dark", (0.08, 0.08, 0.09), roughness=0.6, metallic=0.3)
floor = material("Floor", (0.18, 0.18, 0.2), roughness=0.3, metallic=0.4)
glow = material("Glow", (0.2, 0.9, 1.0), roughness=0.5, **{"Emission Color": (0.2, 0.9, 1.0, 1.0), "Emission Strength": 18.0})
warm = material("Warm", (1.0, 0.6, 0.2), roughness=0.5, **{"Emission Color": (1.0, 0.6, 0.2, 1.0), "Emission Strength": 12.0})
L = 30.0
f = add("primitive_cube_add", "Floor", floor, size=1, location=(0, L / 2, -0.05))
f.scale = (2.2, L / 2, 0.05)
c = add("primitive_cube_add", "Ceiling", dark, size=1, location=(0, L / 2, 3.05))
c.scale = (2.2, L / 2, 0.05)
for side in (-1, 1):
    for i in range(10):
        y = 1.5 + i * 3.0
        p = add("primitive_cube_add", "Panel", panel, size=1, location=(side * 2.2, y, 1.5))
        p.scale = (0.05, 1.4, 1.5)
        rib = add("primitive_cube_add", "Rib", dark, size=1, location=(side * 2.1, y + 1.5, 1.5))
        rib.scale = (0.15, 0.08, 1.5)
        s = add("primitive_cube_add", "Strip", glow, size=1, location=(side * 2.12, y, 2.6))
        s.scale = (0.02, 1.3, 0.05)
        s2 = add("primitive_cube_add", "FloorStrip", glow, size=1, location=(side * 2.0, y, 0.02))
        s2.scale = (0.06, 1.3, 0.02)
for i in range(5):
    lamp = add("primitive_cube_add", "Lamp", warm, size=1, location=(0, 3.0 + i * 6.0, 2.98))
    lamp.scale = (0.6, 0.12, 0.02)
end = add("primitive_cube_add", "Door", dark, size=1, location=(0, L, 1.5))
end.scale = (2.2, 0.05, 1.5)
sign = add("primitive_cube_add", "Sign", warm, size=1, location=(0, L - 0.08, 2.2))
sign.scale = (0.8, 0.02, 0.15)
camera((0.3, -1.5, 1.4), (0.0, L, 1.3), lens=28)
