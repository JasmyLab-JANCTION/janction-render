"""JANCTION Render example 15: a ceramic mug from three named cameras in one job (product shots, cameras=[...]).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex15_product_cameras.py",
                        cameras=["Front", "Top", "Iso"], width=1200, height=1200, samples=128, environment="studio")
The scene defines three camera objects; the service renders the same frame from each and returns one PNG
per camera (camera_files maps the names). render_preview with the same cameras tiles them in one sheet.
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
random.seed(15)


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

ceramic = material("Ceramic", (0.93, 0.93, 0.9), roughness=0.18)
accent = material("Accent", (0.85, 0.25, 0.2), roughness=0.3)
floor = material("Floor", (0.84, 0.84, 0.82), roughness=0.35)
wall = material("Wall", (0.9, 0.9, 0.88), roughness=0.8)
add("primitive_plane_add", "Floor", floor, size=20)
back = add("primitive_plane_add", "Backdrop", wall, size=20, location=(0, 4, 5))
back.rotation_euler = (math.pi / 2, 0, 0)
body = add("primitive_cylinder_add", "Mug", ceramic, radius=0.42, depth=1.0, location=(0, 0, 0.5), vertices=96)
bev = body.modifiers.new("Bevel", "BEVEL")
bev.width = 0.03
bev.segments = 6
smooth(body)
inner = add("primitive_cylinder_add", "Inside", accent, radius=0.36, depth=0.9, location=(0, 0, 0.62), vertices=96)
smooth(inner)
handle = add("primitive_torus_add", "Handle", ceramic, major_radius=0.26, minor_radius=0.06, location=(0.5, 0, 0.5),
             major_segments=64, minor_segments=24)
handle.rotation_euler = (math.pi / 2, 0, 0)
smooth(handle)
band = add("primitive_cylinder_add", "Band", accent, radius=0.425, depth=0.12, location=(0, 0, 0.18), vertices=96, end_fill_type="NOTHING")
smooth(band)
light("Key", "AREA", (2.5, -2.5, 3.5), 350, target=(0, 0, 0.5), size=2.0)
light("Fill", "AREA", (-3.0, -1.5, 2.0), 120, target=(0, 0, 0.5), size=2.5)
camera((0.0, -4.2, 0.9), (0.0, 0.0, 0.5), lens=70, name="Front", active=True)
camera((0.0, -0.01, 4.5), (0.0, 0.0, 0.5), lens=50, name="Top", active=False)
camera((3.2, -3.2, 2.4), (0.0, 0.0, 0.5), lens=60, name="Iso", active=False)
