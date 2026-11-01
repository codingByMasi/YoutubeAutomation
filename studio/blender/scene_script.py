"""Runs INSIDE Blender (`blender -b -P scene_script.py -- scene.json out_dir`). Do not import studio here.

Builds a simple kid-style 3D scene from the scene JSON (flat colours, rounded shapes, no textures, so it is light
on a 4 GB GPU), animates it, and renders a PNG sequence. Only uses bpy, json, math, os and sys.
"""

import json
import math
import os
import sys

import bpy

COLORS = {"red": (0.9, 0.2, 0.2), "orange": (1.0, 0.55, 0.1), "yellow": (1.0, 0.82, 0.15), "green": (0.25, 0.7, 0.3),
          "blue": (0.2, 0.5, 0.95), "purple": (0.55, 0.3, 0.85), "pink": (0.96, 0.5, 0.7), "white": (1, 1, 1),
          "ink": (0.12, 0.12, 0.2), "brown": (0.55, 0.35, 0.2)}
SKY = {"sky": (0.45, 0.75, 1.0), "meadow": (0.55, 0.85, 1.0), "ocean": (0.35, 0.7, 0.95),
       "night": (0.06, 0.07, 0.22), "farm": (1.0, 0.85, 0.6)}
GROUND = {"sky": (0.6, 0.85, 0.5), "meadow": (0.3, 0.7, 0.3), "ocean": (0.15, 0.4, 0.8),
          "night": (0.1, 0.25, 0.2), "farm": (0.85, 0.7, 0.4)}
BODY = {"duck": "yellow", "cat": "orange", "dog": "brown", "fish": "blue", "bunny": "white", "bird": "pink",
        "star": "yellow", "sun": "yellow", "apple": "red", "ball": "purple", "balloon": "red", "flower": "pink"}
_mats = {}


def mat(color):
    """One shared flat material per colour (keeps the scene tiny)."""
    key = tuple(color)
    if key not in _mats:
        m = bpy.data.materials.new("m" + str(len(_mats)))
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1)
        m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.6
        _mats[key] = m
    return _mats[key]


def part(kind, parent, color, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0)):
    """Add a primitive (sphere, cone or cylinder) as a child of `parent`."""
    if kind == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=loc)
    elif kind == "cone":
        bpy.ops.mesh.primitive_cone_add(vertices=16, location=loc)
    else:
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, location=loc)
    o = bpy.context.object
    o.scale, o.rotation_euler = scale, rot
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat(COLORS[color] if isinstance(color, str) else color))
    o.parent = parent
    return o


def face(root, y, z, spread=0.28, r=0.09):
    """Two eyes with a highlight, looking at the camera (-y)."""
    for sx in (-1, 1):
        part("sphere", root, "white", (sx * spread, y, z), (r * 1.3, r * 0.6, r * 1.3))
        part("sphere", root, "ink", (sx * spread, y - 0.02, z), (r, r * 0.5, r))


def build_character(name, color_override=None):
    """Return an empty parent for one character built from primitives (about 1.6 units tall)."""
    root = bpy.data.objects.new("c_" + name, None)
    bpy.context.collection.objects.link(root)
    body = color_override or BODY.get(name, "yellow")
    if name in ("duck", "cat", "dog", "bunny", "bird", "fish"):
        part("sphere", root, body, (0, 0, 0.55), (0.7, 0.6, 0.55))
        part("sphere", root, body, (0, -0.05, 1.15), (0.5, 0.45, 0.45))
        face(root, -0.46, 1.2)
        beak = "orange" if name == "duck" else "ink"
        if name in ("duck", "bird"):
            part("cone", root, beak, (0, -0.55, 1.1), (0.14, 0.14, 0.2), (math.radians(90), 0, 0))
        if name in ("cat", "dog", "bunny"):
            for sx in (-1, 1):
                h = 0.5 if name == "bunny" else 0.28
                part("cone", root, body, (sx * 0.28, 0, 1.6 + (0.2 if name == "bunny" else 0)),
                     (0.14, 0.1, h), (0, sx * 0.2, 0))
        if name == "fish":
            part("cone", root, "orange", (0.75, 0, 0.55), (0.3, 0.1, 0.3), (0, math.radians(90), 0))
    elif name in ("star", "sun"):
        part("sphere", root, body, (0, 0, 0.9), (0.6, 0.3, 0.6))
        n = 5 if name == "star" else 8
        for i in range(n):
            a = i * 2 * math.pi / n
            part("cone", root, body, (math.sin(a) * 0.8, 0, 0.9 + math.cos(a) * 0.8), (0.2, 0.15, 0.35), (0, a, 0))
        face(root, -0.26, 0.95, 0.2, 0.07)
    elif name in ("apple", "ball", "balloon"):
        part("sphere", root, body, (0, 0, 0.85), (0.7, 0.7, 0.75))
        if name == "apple":
            part("cylinder", root, "brown", (0, 0, 1.65), (0.05, 0.05, 0.2))
            part("sphere", root, "green", (0.2, 0, 1.7), (0.2, 0.05, 0.1))
        if name == "balloon":
            part("cylinder", root, "ink", (0, 0, 0.1), (0.01, 0.01, 0.4))
        face(root, -0.62, 0.95, 0.22, 0.07)
    else:  # flower
        part("cylinder", root, "green", (0, 0, 0.5), (0.05, 0.05, 0.5))
        for i in range(6):
            a = i * math.pi / 3
            part("sphere", root, body, (math.sin(a) * 0.4, 0, 1.2 + math.cos(a) * 0.4), (0.25, 0.1, 0.25))
        part("sphere", root, "yellow", (0, -0.05, 1.2), (0.22, 0.12, 0.22))
    return root


def motion(kind, t, i, base_x):
    """(dx, dz, rot_y, scale) for item i at time t. Items appear one after another."""
    t = t - i * 0.45
    if t < 0:
        return 0.0, 0.0, 0.0, 0.0
    if kind == "bounce":
        return 0.0, abs(math.sin(t * 3.2)) * 0.5, 0.0, 1.0
    if kind == "sway":
        return 0.0, 0.0, math.sin(t * 2.6) * 0.25, 1.0
    if kind == "slide":
        return max(0.0, 3.0 - t * 4.0) * (1 if i % 2 else -1), 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0, min(1.0, t * 3.0) * (1 + 0.08 * math.sin(t * 8) * max(0.0, 1 - t))  # pop


def pick_engine(sc, requested):
    """Eevee's id differs between Blender versions (BLENDER_EEVEE_NEXT in 4.2-4.5, BLENDER_EEVEE in 5.x)."""
    ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    if requested in ids or requested == "CYCLES":  # Cycles is an add-on and may not be listed in bpy builds
        return requested
    for cand in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        if cand in ids:
            return cand
    return ids[0]


def _hex(h):
    h = h.lstrip("#")
    lin = lambda v: (v / 255) ** 2.2  # noqa: E731 - rough sRGB to linear
    return tuple(lin(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def build_title(cfg):
    """A 3D extruded title floating over a plain backdrop, with a slow camera push. For narrated channels."""
    sc = bpy.context.scene
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (*_hex(cfg["bg"]), 1)
    curve = bpy.data.curves.new("title", "FONT")
    curve.body = cfg["text"]
    curve.align_x, curve.align_y = "CENTER", "CENTER"
    curve.extrude, curve.bevel_depth, curve.size = 0.12, 0.02, 1.0
    obj = bpy.data.objects.new("title", curve)
    sc.collection.objects.link(obj)
    obj.rotation_euler = (math.radians(90), 0, 0)
    obj.data.materials.append(mat(_hex(cfg["accent"])))
    bpy.ops.object.light_add(type="SUN", location=(3, -6, 6))
    bpy.context.object.data.energy = 3.0
    bpy.context.object.rotation_euler = (math.radians(55), 0, math.radians(25))
    bpy.ops.object.camera_add(location=(0, -13, 0), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.object
    sc.camera = cam
    n = sc.frame_end
    for f in range(1, n + 1):
        p = (f - 1) / max(n - 1, 1)
        cam.location = (0, -13.0 + 2.5 * p, 0)
        cam.keyframe_insert("location", frame=f)
        obj.rotation_euler = (math.radians(90), 0, math.radians(8 * (0.5 - p)))
        obj.keyframe_insert("rotation_euler", frame=f)


def main(cfg):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    fps, dur = cfg["fps"], cfg["duration"]
    n_frames = max(1, round(dur * fps))
    sc.render.fps, sc.frame_start, sc.frame_end = fps, 1, n_frames
    sc.render.resolution_x, sc.render.resolution_y = cfg["width"], cfg["height"]
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = os.path.join(cfg["out_dir"], "f_")
    wanted = os.environ.get("STUDIO_BLENDER_ENGINE") or cfg.get("engine", "BLENDER_EEVEE_NEXT")
    sc.render.engine = pick_engine(sc, wanted)
    if sc.render.engine == "CYCLES":  # only used for headless tests without a GPU
        sc.cycles.samples, sc.cycles.device = 8, "CPU"
    elif hasattr(sc, "eevee") and hasattr(sc.eevee, "taa_render_samples"):
        sc.eevee.taa_render_samples = 16
    sc.view_settings.view_transform = "Standard"  # flat bright colours, not the filmic look
    if cfg.get("kind") == "title":
        build_title(cfg)
        bpy.ops.render.render(animation=True)
        return
    bg = cfg["background"]
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (*SKY[bg], 1)
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 4, 0))
    bpy.context.object.data.materials.append(mat(GROUND[bg]))
    bpy.ops.object.light_add(type="SUN", location=(4, -6, 8))
    bpy.context.object.data.energy = 1.8 if bg == "night" else 2.6
    bpy.context.object.rotation_euler = (math.radians(50), 0, math.radians(30))
    names, count = cfg["characters"], cfg["count"]
    gap = min(2.4, 9.0 / max(count, 1))
    scale = min(1.0, 1.0 + (3 - count) * 0.05) if count < 3 else min(1.0, 2.4 / gap)
    items = []
    for i in range(count):
        o = build_character(names[i % len(names)])
        base = (i - (count - 1) / 2) * gap
        o.location = (base, 0, 0)
        items.append((o, base))
    bpy.ops.object.camera_add(location=(0, -9.5, 2.3), rotation=(math.radians(84), 0, 0))
    cam = bpy.context.object
    cam.data.lens = 32
    sc.camera = cam
    for f in range(1, n_frames + 1):
        t, p = (f - 1) / fps, (f - 1) / max(n_frames - 1, 1)
        for i, (o, base) in enumerate(items):
            dx, dz, ry, s = motion(cfg["motion"], t, i, base)
            o.location = (base + dx, 0, dz)
            o.rotation_euler = (0, ry, 0)
            o.scale = (s * scale,) * 3
            for path in ("location", "rotation_euler", "scale"):
                o.keyframe_insert(path, frame=f)
        c = cfg.get("camera") or ""
        x = {"pan_left": 1.5 - 3 * p, "pan_right": -1.5 + 3 * p}.get(c, 0.0)
        y = {"zoom_in": -10.5 + 2.0 * p, "zoom_out": -8.5 - 2.0 * p}.get(c, -9.5)
        cam.location = (x, y, 2.3)
        cam.keyframe_insert("location", frame=f)
    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    with open(argv[0], encoding="utf-8") as fh:
        main(json.load(fh))
