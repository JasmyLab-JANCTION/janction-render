"""JANCTION Render example 12: a brushed-metal ring logo with letters, turning once in 48 frames on EEVEE (MP4).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex12_logo_ring_spin.py",
                        frame_start=1, frame_end=48, width=1280, height=720, engine="eevee", output="mp4")
The scene has its own dark world and lights; the ring and the letters are keyed with linear interpolation
so the rotation is constant and loops.
"""
import math
import random

import bpy
from mathutils import Vector

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 48
scene.render.fps = 24
random.seed(12)


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

world((0.01, 0.01, 0.015))
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
metal = material("Brushed", (0.9, 0.78, 0.45), roughness=0.3, metallic=1.0)
floor = material("Floor", (0.05, 0.05, 0.06), roughness=0.25)

add("primitive_plane_add", "Floor", floor, size=30)
ring = add("primitive_torus_add", "Ring", metal, major_radius=1.6, minor_radius=0.18, major_segments=96, minor_segments=24,
           location=(0, 0, 1.9))
ring.rotation_euler = (math.pi / 2, 0, 0)
smooth(ring)
letters = text("JR", "Letters", metal, (0, 0.05, 1.3), size=1.5, extrude=0.12, rotation=(math.pi / 2, 0, 0))
pivot = bpy.data.objects.new("Pivot", None)
scene.collection.objects.link(pivot)
pivot.location = (0, 0, 1.9)
for ob in (ring, letters):
    ob.parent = pivot
    ob.matrix_parent_inverse = pivot.matrix_world.inverted()
pivot.rotation_euler = (0, 0, 0)
pivot.keyframe_insert("rotation_euler", frame=1)
pivot.rotation_euler = (0, 0, 2 * math.pi)
pivot.keyframe_insert("rotation_euler", frame=49)

light("Key", "AREA", (4.0, -4.0, 5.0), 900, target=(0, 0, 1.9), size=3.0)
light("Rim", "AREA", (-4.0, 4.0, 4.0), 500, target=(0, 0, 1.9), size=2.0, color=(0.7, 0.8, 1.0))
light("Fill", "AREA", (0.0, -6.0, 1.0), 150, target=(0, 0, 1.9), size=4.0)
camera((0.0, -7.5, 2.2), (0.0, 0.0, 1.8), lens=60)
