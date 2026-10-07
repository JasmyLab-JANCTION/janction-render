"""JANCTION Render example 18: a low-poly forest around a lake at sunset (one still).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex18_lowpoly_forest.py",
                        width=1920, height=1080, samples=128, environment="sunset")
Trees are three stacked cones on a cylinder, rocks are flat-shaded icospheres; positions come from a fixed seed.
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
random.seed(18)


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

ground = material("Ground", (0.3, 0.45, 0.2), roughness=0.95)
water = material("Water", (0.1, 0.3, 0.45), roughness=0.05, metallic=0.1)
bark = material("Bark", (0.32, 0.2, 0.12), roughness=0.9)
leaves = [material(f"Leaf{i}", c, roughness=0.85) for i, c in enumerate(((0.16, 0.42, 0.18), (0.25, 0.5, 0.2), (0.45, 0.5, 0.15)))]
rock = material("Rock", (0.45, 0.45, 0.42), roughness=0.9)
add("primitive_plane_add", "Ground", ground, size=120)
add("primitive_circle_add", "Lake", water, radius=9.0, vertices=48, location=(3.0, 6.0, 0.01), fill_type="NGON")


def tree(x, y):
    h = 2.0 + random.random() * 2.5
    add("primitive_cylinder_add", "Trunk", bark, radius=0.12, depth=h * 0.4, location=(x, y, h * 0.2), vertices=8)
    m = random.choice(leaves)
    for dz, rr in ((0.45, 1.0), (0.68, 0.72), (0.9, 0.45)):
        add("primitive_cone_add", "Canopy", m, radius1=h * 0.3 * rr, depth=h * 0.45, location=(x, y, h * dz), vertices=7)


n = 0
while n < 70:
    x, y = random.uniform(-22, 22), random.uniform(-6, 30)
    if (Vector((x, y)) - Vector((3.0, 6.0))).length < 10.5:
        continue
    tree(x, y)
    n += 1
for i in range(14):
    x, y = random.uniform(-20, 20), random.uniform(-4, 26)
    if (Vector((x, y)) - Vector((3.0, 6.0))).length < 9.5:
        continue
    r = add("primitive_ico_sphere_add", f"Rock{i}", rock, radius=0.3 + random.random() * 0.6, subdivisions=1, location=(x, y, 0.15))
    r.scale = (1.0, 1.3, 0.6)
camera((-8.0, -14.0, 5.0), (3.0, 8.0, 1.0), lens=35)
