"""JANCTION Render example 09: marbles on a wooden table, shallow depth of field at f/1.8 (one still).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex09_macro_marbles.py",
                        width=1920, height=1080, samples=128, environment="studio")
Depth of field is cam.data.dof: focus_object picks the sharp marble, aperture_fstop sets the blur.
"""
import random

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


table = material("Table", (0.45, 0.28, 0.16), roughness=0.35)
add("primitive_plane_add", "Table", table, size=12)

colors = [(0.9, 0.2, 0.15), (0.2, 0.5, 0.9), (0.95, 0.75, 0.2), (0.3, 0.75, 0.35), (0.85, 0.85, 0.9),
          (0.6, 0.25, 0.7), (0.95, 0.5, 0.2), (0.2, 0.7, 0.7), (0.95, 0.95, 0.95)]
rng = random.Random(3)
focus = None
for i, color in enumerate(colors):
    gx, gy = i % 3, i // 3
    x = (gx - 1) * 0.72 + rng.uniform(-0.12, 0.12)
    y = (gy - 1) * 0.72 + rng.uniform(-0.12, 0.12)
    if i in (4, 8):
        mat = material("Marble%d" % i, color, roughness=0.15, metallic=1.0)
    else:
        mat = material("Marble%d" % i, color, roughness=0.05, **{"Coat Weight": 1.0, "Coat Roughness": 0.02})
    ball = add("primitive_uv_sphere_add", "Marble%d" % i, mat, radius=0.3, segments=96, ring_count=48, location=(x, y, 0.3))
    smooth(ball)
    if i == 4:
        focus = ball

light("Key", "AREA", (1.5, -1.5, 2.0), 150, target=(0, 0, 0.3), size=1.5)

data = bpy.data.cameras.new("Camera")
data.lens = 60
data.dof.use_dof = True
data.dof.focus_object = focus
data.dof.aperture_fstop = 1.8
cam = bpy.data.objects.new("Camera", data)
scene.collection.objects.link(cam)
cam.location = (0.5, -3.1, 1.35)
look_at(cam, (0.0, 0.0, 0.3))
scene.camera = cam
