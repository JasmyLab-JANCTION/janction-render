"""JANCTION Render example 14: hundreds of matte spheres scattered in a box with shallow depth of field (one still).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex14_scatter_spheres.py",
                        width=1920, height=1080, samples=128, environment="studio")
A deterministic random scatter (fixed seed), five colours, sizes drawn from a range, camera at f/2.0.
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
random.seed(14)


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

palette = [(0.95, 0.3, 0.25), (0.98, 0.75, 0.2), (0.25, 0.6, 0.95), (0.3, 0.8, 0.5), (0.95, 0.95, 0.92)]
mats = [material(f"Col{i}", c, roughness=0.55) for i, c in enumerate(palette)]
floor = material("Floor", (0.85, 0.85, 0.83), roughness=0.4)
add("primitive_plane_add", "Floor", floor, size=40)
placed = []
tries = 0
while len(placed) < 320 and tries < 5000:
    tries += 1
    r = 0.12 + random.random() ** 2 * 0.5
    p = Vector((random.uniform(-6, 6), random.uniform(-3, 9), r + random.random() * 2.2))
    if all((p - q).length > r + rq + 0.02 for q, rq in placed):
        placed.append((p, r))
for i, (p, r) in enumerate(placed):
    s = add("primitive_ico_sphere_add", f"Sphere{i}", random.choice(mats), radius=r, subdivisions=3, location=p)
    smooth(s)
camera((0.0, -9.5, 2.6), (0.0, 0.5, 1.0), lens=50, fstop=2.0, focus=9.0)
