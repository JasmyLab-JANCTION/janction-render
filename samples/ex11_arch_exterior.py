"""JANCTION Render example 11: a small modern house seen from the street (architectural exterior, one still).

Reproduce: render_final(scene_url="https://render.janction.jp/samples/ex11_arch_exterior.py",
                        width=1920, height=1080, samples=128, environment="overcast")
Boxes for the volumes, glass panes for the windows, cone-and-cylinder trees. The overcast preset lights it.
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
random.seed(11)


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

concrete = material("Concrete", (0.72, 0.7, 0.66), roughness=0.85)
dark = material("DarkCladding", (0.12, 0.11, 0.1), roughness=0.6)
glass = material("Glass", (0.8, 0.9, 0.95), roughness=0.05, **{"Transmission Weight": 1.0, "IOR": 1.5})
frame = material("Frame", (0.05, 0.05, 0.05), roughness=0.4, metallic=0.6)
grass = material("Grass", (0.24, 0.42, 0.16), roughness=0.95)
path = material("Path", (0.6, 0.58, 0.55), roughness=0.9)
bark = material("Bark", (0.3, 0.2, 0.12), roughness=0.9)
leaf = material("Leaves", (0.2, 0.45, 0.18), roughness=0.8)

add("primitive_plane_add", "Ground", grass, size=80)
walk = add("primitive_plane_add", "Path", path, size=1, location=(2.5, -6, 0.005))
walk.scale = (1.4, 6, 1)

# two stacked volumes, a flat roof slab and a canopy over the door
lower = add("primitive_cube_add", "Lower", concrete, size=1, location=(0, 0, 1.5))
lower.scale = (5.0, 4.0, 1.5)
upper = add("primitive_cube_add", "Upper", dark, size=1, location=(-1.0, 0.5, 4.3))
upper.scale = (3.6, 3.2, 1.3)
roof = add("primitive_cube_add", "Roof", concrete, size=1, location=(-1.0, 0.5, 5.7))
roof.scale = (3.9, 3.5, 0.12)
canopy = add("primitive_cube_add", "Canopy", dark, size=1, location=(2.6, -2.6, 3.05))
canopy.scale = (1.6, 1.4, 0.08)


def window(x, y, z, w, h, along_y=False):
    pane = add("primitive_cube_add", "Pane", glass, size=1, location=(x, y, z))
    fr = add("primitive_cube_add", "Frame", frame, size=1, location=(x, y, z))
    if along_y:
        pane.scale = (0.02, w / 2, h / 2)
        fr.scale = (0.015, w / 2 + 0.06, h / 2 + 0.06)
    else:
        pane.scale = (w / 2, 0.02, h / 2)
        fr.scale = (w / 2 + 0.06, 0.015, h / 2 + 0.06)


window(-2.0, -4.02, 1.6, 3.2, 2.0)
window(1.8, -4.02, 1.4, 2.0, 1.6)
window(-1.0, -2.72, 4.3, 4.4, 1.6)
window(5.02, -1.0, 1.5, 2.2, 1.4, along_y=True)
door = add("primitive_cube_add", "Door", dark, size=1, location=(3.4, -4.02, 1.1))
door.scale = (0.5, 0.03, 1.1)


def tree(x, y, h=3.0, r=1.1):
    trunk = add("primitive_cylinder_add", "Trunk", bark, radius=0.12, depth=h * 0.5, location=(x, y, h * 0.25), vertices=12)
    for dz, rr in ((0.45, 1.0), (0.65, 0.75), (0.85, 0.5)):
        c = add("primitive_cone_add", "Canopy", leaf, radius1=r * rr, depth=h * 0.45, location=(x, y, h * dz), vertices=16)
        smooth(c)
    smooth(trunk)


for x, y in ((-7.5, -3.0), (-6.0, 3.5), (7.0, 2.0), (8.5, -4.5), (-9.0, 0.5)):
    tree(x, y, h=3.0 + random.random() * 1.5, r=1.0 + random.random() * 0.4)

camera((12.0, -14.0, 3.2), (0.0, -0.5, 2.2), lens=35)
