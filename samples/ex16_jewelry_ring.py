"""JANCTION Render example 16: a gold ring with a cut stone on dark velvet, macro depth of field (one still).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex16_jewelry_ring.py",
                        width=1920, height=1080, samples=128, environment="studio")
Gold is a metallic Principled material; the stone is a glass material with a high IOR; the camera is at f/2.8.
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
random.seed(16)


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

gold = material("Gold", (1.0, 0.78, 0.35), roughness=0.14, metallic=1.0)
stone = material("Stone", (0.75, 0.85, 1.0), roughness=0.02, **{"Transmission Weight": 1.0, "IOR": 2.4})
velvet = material("Velvet", (0.12, 0.05, 0.09), roughness=0.95)
add("primitive_plane_add", "Velvet", velvet, size=12)
band = add("primitive_torus_add", "Band", gold, major_radius=0.9, minor_radius=0.11, major_segments=128, minor_segments=32,
           location=(0, 0, 0.9))
band.rotation_euler = (math.pi / 2, 0, 0.35)
smooth(band)
head = add("primitive_cylinder_add", "Head", gold, radius=0.24, depth=0.18, location=(0, 0, 1.93), vertices=48)
smooth(head)
gem = add("primitive_ico_sphere_add", "Gem", stone, radius=0.2, subdivisions=1, location=(0, 0, 2.1))
gem.rotation_euler = (0.2, 0.1, 0.4)
for a in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
    prong = add("primitive_cylinder_add", "Prong", gold, radius=0.025, depth=0.26, location=(0.19 * math.cos(a), 0.19 * math.sin(a), 2.08), vertices=12)
    smooth(prong)
light("Key", "AREA", (1.5, -1.5, 2.8), 120, target=(0, 0, 1.9), size=1.2)
light("Spec", "AREA", (-1.2, 1.0, 2.6), 80, target=(0, 0, 2.0), size=0.4)
camera((0.0, -3.6, 2.2), (0.0, 0.0, 1.9), lens=100, fstop=2.8, focus=3.6)
