"""Runs INSIDE Blender (bpy). Original recurring cast for a nursery-rhyme channel, built from simple primitives.

Flat-ish colours, no textures, no rig: cheap on any GPU in Eevee. Do not import studio here.
Each builder returns an empty parent object (about 1.6 units tall, facing -y) so it can be placed and animated.
"""

import math

import bpy

INK = (0.1, 0.08, 0.14)
WHITE = (1, 1, 1)
CHEEK = (1.0, 0.55, 0.6)
_mats = {}


def lin(h):
    """'#RRGGBB' to linear RGB (rough sRGB conversion)."""
    h = h.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4))


def mat(color, rough=0.55):
    """Shared flat material per colour."""
    key = (tuple(color), rough)
    if key not in _mats:
        m = bpy.data.materials.new(f"m{len(_mats)}")
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Roughness"].default_value = rough
        _mats[key] = m
    return _mats[key]


def part(kind, parent, color, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0)):
    """Primitive (sphere, cone, cylinder) parented to `parent`."""
    if kind == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=loc)
    elif kind == "cone":
        bpy.ops.mesh.primitive_cone_add(vertices=24, location=loc)
    else:
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, location=loc)
    o = bpy.context.object
    o.scale, o.rotation_euler = scale, rot
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat(color))
    o.parent = parent
    return o


def curve(parent, color, points, thick=0.03):
    """A thin tube through `points` (smile, tail, banana, antennae)."""
    cu = bpy.data.curves.new("c", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = thick
    cu.bevel_resolution = 4
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for p, pt in zip(sp.bezier_points, points):
        p.co = pt
        p.handle_left_type = p.handle_right_type = "AUTO"
    o = bpy.data.objects.new("c", cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat(color))
    o.parent = parent
    return o


def face(root, y, z, spread=0.24, r=0.13, smile=0.16, cheeks=True, look=(0.0, 0.0)):
    """Big shiny eyes, rosy cheeks and a smile on a head whose front is at y (facing -y)."""
    for sx in (-1, 1):
        part("sphere", root, WHITE, (sx * spread, y, z), (r, r * 0.5, r * 1.1))
        part("sphere", root, INK, (sx * spread + look[0], y - r * 0.28, z + look[1]), (r * 0.62, r * 0.3, r * 0.72))
        part("sphere", root, WHITE, (sx * spread + r * 0.2, y - r * 0.5, z + r * 0.3), (r * 0.2, r * 0.1, r * 0.2))
        if cheeks:
            part("sphere", root, CHEEK, (sx * (spread + 0.16), y + 0.02, z - r * 1.5), (r * 0.5, r * 0.18, r * 0.35))
    my = y - 0.01
    curve(root, INK, [(-smile, my, z - r * 1.55), (0, my - 0.02, z - r * 1.95), (smile, my, z - r * 1.55)], 0.018)


def bear():
    """Benny Bear: round, cuddly, blue dungarees."""
    brown, tan = lin("#9A6234"), lin("#E8C99A")
    r = bpy.data.objects.new("benny", None)
    bpy.context.collection.objects.link(r)
    part("sphere", r, brown, (0, 0, 0.5), (0.62, 0.55, 0.55))
    part("sphere", r, tan, (0, -0.35, 0.5), (0.4, 0.25, 0.4))
    part("sphere", r, lin("#2F7FE0"), (0, -0.05, 0.3), (0.64, 0.57, 0.33))
    for sx in (-1, 1):
        part("cylinder", r, lin("#2F7FE0"), (sx * 0.2, -0.3, 0.78), (0.05, 0.03, 0.2), (0.1, sx * 0.25, 0))
        part("sphere", r, lin("#FFD23F"), (sx * 0.2, -0.36, 0.62), (0.06, 0.04, 0.06))
        part("sphere", r, brown, (sx * 0.62, -0.05, 0.62), (0.2, 0.2, 0.3), (0, sx * 0.5, 0))
        part("sphere", r, brown, (sx * 0.3, -0.12, 0.08), (0.24, 0.3, 0.14))
        part("sphere", r, brown, (sx * 0.42, 0, 1.55), (0.2, 0.15, 0.2))
        part("sphere", r, tan, (sx * 0.42, -0.1, 1.55), (0.11, 0.06, 0.11))
    part("sphere", r, brown, (0, -0.05, 1.18), (0.55, 0.5, 0.48))
    part("sphere", r, tan, (0, -0.4, 1.02), (0.24, 0.15, 0.17))
    part("sphere", r, INK, (0, -0.52, 1.12), (0.09, 0.05, 0.065))
    face(r, -0.47, 1.3, 0.22, 0.11, 0.1, True)
    return r


def duckling():
    """Pip the Duckling: tiny, bouncy, red scarf."""
    yel, org = lin("#FFD83A"), lin("#FF8A1F")
    r = bpy.data.objects.new("pip", None)
    bpy.context.collection.objects.link(r)
    part("sphere", r, yel, (0, 0.05, 0.45), (0.55, 0.55, 0.5))
    part("sphere", r, yel, (0, -0.05, 1.12), (0.6, 0.55, 0.55))
    for a in (-0.35, 0, 0.35):
        part("cone", r, yel, (a * 0.35, -0.05, 1.7), (0.05, 0.05, 0.18), (0, a, 0))
    part("sphere", r, org, (0, -0.6, 1.0), (0.2, 0.2, 0.08))
    part("sphere", r, org, (0, -0.58, 1.07), (0.18, 0.17, 0.06))
    for sx in (-1, 1):
        part("sphere", r, yel, (sx * 0.58, 0, 0.5), (0.12, 0.3, 0.26), (0, 0, sx * 0.3))
        part("sphere", r, org, (sx * 0.22, -0.28, 0.04), (0.2, 0.28, 0.06))
    scarf = part("sphere", r, lin("#E8343B"), (0, -0.1, 0.78), (0.5, 0.45, 0.12))
    scarf.name = "scarf"
    part("sphere", r, lin("#E8343B"), (0.25, -0.38, 0.55), (0.1, 0.07, 0.2), (0, 0, 0.2))
    face(r, -0.51, 1.22, 0.24, 0.13, 0.0, True)
    return r


def monkey():
    """Mango Monkey: cheeky, orange-brown, curly tail and a banana."""
    fur, face_c = lin("#C4742B"), lin("#F2C98A")
    r = bpy.data.objects.new("mango", None)
    bpy.context.collection.objects.link(r)
    part("sphere", r, fur, (0, 0, 0.5), (0.5, 0.45, 0.55))
    part("sphere", r, face_c, (0, -0.28, 0.45), (0.32, 0.2, 0.38))
    for sx in (-1, 1):
        part("sphere", r, fur, (sx * 0.52, -0.08, 0.6), (0.14, 0.14, 0.34), (0, sx * 0.4, 0))
        part("sphere", r, fur, (sx * 0.24, -0.1, 0.06), (0.17, 0.28, 0.12))
        part("sphere", r, fur, (sx * 0.64, -0.05, 1.2), (0.22, 0.14, 0.22))
        part("sphere", r, face_c, (sx * 0.64, -0.14, 1.2), (0.14, 0.07, 0.14))
    part("sphere", r, fur, (0, -0.05, 1.15), (0.5, 0.46, 0.45))
    part("sphere", r, face_c, (0, -0.33, 1.1), (0.38, 0.2, 0.3))
    part("sphere", r, face_c, (-0.16, -0.38, 1.28), (0.18, 0.08, 0.14))
    part("sphere", r, face_c, (0.16, -0.38, 1.28), (0.18, 0.08, 0.14))
    part("sphere", r, INK, (0, -0.5, 1.12), (0.05, 0.03, 0.035))
    face(r, -0.5, 1.28, 0.17, 0.1, 0.1, True)
    curve(r, fur, [(0.2, 0.3, 0.2), (0.75, 0.5, 0.2), (0.95, 0.4, 0.8), (0.7, 0.35, 1.0)], 0.06)
    curve(r, lin("#FFE066"), [(-0.55, -0.4, 0.8), (-0.8, -0.45, 0.95), (-0.85, -0.45, 1.3)], 0.07)
    part("sphere", r, lin("#8A6A1D"), (-0.85, -0.45, 1.36), (0.05, 0.05, 0.04))
    return r


def ladybug():
    """Dotty Ladybug: red shell with black dots, curious antennae."""
    red, blk = lin("#E8212E"), lin("#1B1B26")
    r = bpy.data.objects.new("dotty", None)
    bpy.context.collection.objects.link(r)
    part("sphere", r, red, (0, 0.1, 0.62), (0.85, 0.75, 0.7))
    part("cylinder", r, blk, (0, -0.2, 0.7), (0.012, 0.01, 0.66), (math.radians(8), 0, 0))
    for loc in ((-0.4, -0.05, 1.18), (0.4, -0.05, 1.18), (0, 0.3, 1.25), (-0.72, 0.15, 0.85), (0.72, 0.15, 0.85),
                (-0.45, 0.6, 0.95), (0.45, 0.6, 0.95)):
        part("sphere", r, blk, loc, (0.14, 0.14, 0.07), (0, 0, 0))
    part("sphere", r, blk, (0, -0.52, 0.55), (0.6, 0.38, 0.5))
    for sx in (-1, 1):
        curve(r, blk, [(sx * 0.2, -0.5, 1.0), (sx * 0.35, -0.5, 1.4), (sx * 0.55, -0.45, 1.5)], 0.02)
        part("sphere", r, lin("#FFD23F"), (sx * 0.55, -0.45, 1.52), (0.07, 0.07, 0.07))
        part("sphere", r, blk, (sx * 0.5, -0.5, 0.06), (0.1, 0.2, 0.06))
        part("sphere", r, blk, (sx * 0.8, -0.35, 0.18), (0.1, 0.18, 0.06))
    face(r, -0.86, 0.66, 0.24, 0.13, 0.14, True)
    return r


def turtle():
    """Tilly Turtle: gentle, sleepy-kind, patterned shell with a flower."""
    skin, shell, patch = lin("#6DC76B"), lin("#2F8F5B"), lin("#F2A93B")
    r = bpy.data.objects.new("tilly", None)
    bpy.context.collection.objects.link(r)
    part("sphere", r, shell, (0, 0.12, 0.62), (0.88, 0.78, 0.62))
    for loc, s in (((0, -0.12, 1.1), 0.22), ((-0.42, -0.05, 0.95), 0.18), ((0.42, -0.05, 0.95), 0.18),
                   ((-0.5, 0.35, 0.8), 0.16), ((0.5, 0.35, 0.8), 0.16), ((0, 0.45, 1.0), 0.18)):
        part("sphere", r, patch, loc, (s, s * 0.6, s * 0.6))
    part("sphere", r, lin("#FF6FA8"), (0.25, -0.1, 1.28), (0.12, 0.12, 0.12))
    part("sphere", r, lin("#FFE066"), (0.25, -0.2, 1.28), (0.05, 0.04, 0.05))
    part("sphere", r, skin, (0, -0.65, 0.58), (0.55, 0.5, 0.5))
    for sx in (-1, 1):
        part("sphere", r, skin, (sx * 0.55, -0.4, 0.12), (0.22, 0.28, 0.14))
        part("sphere", r, skin, (sx * 0.5, 0.45, 0.12), (0.2, 0.26, 0.13))
    part("cone", r, skin, (0, 0.85, 0.2), (0.12, 0.2, 0.15), (math.radians(-90), 0, 0))
    face(r, -1.12, 0.72, 0.22, 0.12, 0.12, True)
    return r


CAST = {
    "benny": bear,
    "pip": duckling,
    "mango": monkey,
    "dotty": ladybug,
    "tilly": turtle,
}


def generic(name, main, accent):
    """A round friendly character in the given colours, for roster entries that have no hand-made model."""
    r = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(r)
    m, a = lin(main), lin(accent)
    part("sphere", r, m, (0, 0, 0.5), (0.6, 0.52, 0.55))
    part("sphere", r, a, (0, -0.32, 0.48), (0.38, 0.22, 0.4))
    part("sphere", r, m, (0, -0.05, 1.18), (0.55, 0.5, 0.5))
    for sx in (-1, 1):
        part("sphere", r, m, (sx * 0.4, -0.02, 1.62), (0.17, 0.12, 0.2))
        part("sphere", r, m, (sx * 0.28, -0.12, 0.08), (0.22, 0.3, 0.13))
        part("sphere", r, m, (sx * 0.62, -0.05, 0.6), (0.17, 0.17, 0.28), (0, sx * 0.4, 0))
    face(r, -0.5, 1.22, 0.22, 0.12, 0.12, True)
    return r


def build(name, info=None):
    """Build roster character `name`. `info` = {main, accent, builder}; a known builder key gets its own model."""
    info = info or {}
    key = info.get("builder") or name
    if key in CAST:
        return CAST[key]()
    return generic(name, info.get("main", "#F5B700"), info.get("accent", "#FFFFFF"))
