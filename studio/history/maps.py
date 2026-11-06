# ruff: noqa: E501  (coordinate tables)
"""Rough, hand-drawn map regions for history map scenes: land outlines, place names and region labels.

No sourced or paid data: the outlines are coarse polygons in (longitude, latitude), good enough to show *where* a
place is and clearly drawn as approximate (the scene says so on screen). `pick_region` chooses the map from the place
names in the scene; `resolve_points` turns labels into positions on that map and never invents a position for a place
the table does not know. The western-Mediterranean map used by the Punic-war scenes stays in render.py.
"""

from __future__ import annotations

import re

Poly = list[tuple[float, float]]

# name -> view box (lon0, lon1, lat0, lat1), land polygons, region labels, known places (lon, lat), trigger words
REGIONS: dict[str, dict] = {
    "south_asia": {
        "view": (55.0, 105.0, 3.0, 31.0),
        "land": [
            [(55, 26), (62, 25), (68, 24), (72, 21), (73, 16), (76, 9), (78, 8), (80, 13), (80, 16), (87, 21), (89, 22),
             (92, 22), (98, 16), (100, 8), (105, 10), (105, 31), (55, 31)],
            [(80, 9.5), (82, 7), (81, 6), (80, 6.5)],
        ],
        "labels": {"INDIA": (77, 22), "BENGAL": (88.3, 25.6), "ARABIAN SEA": (65, 14), "BAY OF BENGAL": (89, 13), "CEYLON": (80.8, 4.6)},
        "places": {"bengal": (88.3, 24.5), "plassey": (88.3, 23.8), "calcutta": (88.4, 22.6), "kolkata": (88.4, 22.6),
                   "bombay": (72.8, 19.0), "mumbai": (72.8, 19.0), "madras": (80.3, 13.1), "chennai": (80.3, 13.1),
                   "delhi": (77.2, 28.6), "india": (78.0, 21.0), "ceylon": (80.7, 7.6), "sri lanka": (80.7, 7.6)},
    },
    "east_asia": {
        "view": (98.0, 130.0, 18.0, 36.0),
        "land": [
            [(98, 36), (98, 24), (100, 21.5), (106, 21), (108, 21.5), (110, 20.5), (114, 22.2), (117, 23.5), (120, 26), (122, 30),
             (121, 32), (120, 34), (119, 35), (122, 36.5)],
            [(120.1, 25), (121.9, 25.2), (121, 22)],
            [(108.6, 19.2), (111, 20), (110.5, 18.2)],
            [(129, 33), (131, 34.5), (130, 36), (128, 35)],
        ],
        "labels": {"CHINA": (108, 30), "SOUTH CHINA SEA": (113, 19.2), "EAST CHINA SEA": (126, 29), "TAIWAN": (123.4, 23.5)},
        "places": {"china": (108.0, 30.0), "hong kong": (114.2, 22.3), "canton": (113.3, 23.1), "guangzhou": (113.3, 23.1),
                   "shanghai": (121.5, 31.2), "nanjing": (118.8, 32.0), "macau": (113.5, 22.2), "taiwan": (121.0, 23.7)},
    },
    "world": {
        "view": (-170.0, 180.0, -58.0, 78.0),
        "land": [
            [(-168, 66), (-140, 70), (-110, 72), (-82, 70), (-62, 58), (-55, 48), (-70, 42), (-76, 35), (-81, 25), (-90, 29), (-97, 26),
             (-105, 22), (-96, 16), (-88, 14), (-80, 8), (-86, 12), (-105, 20), (-115, 30), (-124, 40), (-125, 50), (-135, 58), (-150, 60), (-165, 60)],
            [(-80, 8), (-62, 10), (-50, 0), (-35, -6), (-40, -22), (-50, -30), (-58, -38), (-66, -46), (-70, -54), (-75, -50), (-72, -30), (-70, -18), (-80, -5)],
            [(-10, 36), (-9, 43), (-2, 48), (-5, 50), (5, 53), (10, 57), (5, 62), (15, 70), (30, 71), (40, 66), (30, 60), (30, 50), (40, 45), (28, 41),
             (20, 40), (15, 38), (10, 44), (3, 43), (-6, 36)],
            [(-17, 21), (-10, 35), (10, 37), (32, 31), (34, 28), (43, 12), (51, 12), (40, -5), (40, -16), (33, -27), (20, -35), (12, -18), (9, -1),
             (8, 4), (-8, 4), (-17, 14)],
            [(40, 66), (60, 70), (100, 77), (140, 72), (170, 68), (180, 65), (160, 55), (140, 50), (132, 43), (122, 38), (122, 30), (110, 20),
             (106, 10), (100, 13), (103, 1), (98, 8), (94, 17), (88, 22), (80, 15), (77, 8), (72, 20), (67, 25), (57, 25), (52, 16), (43, 12),
             (35, 28), (36, 36), (28, 41), (40, 45), (48, 42), (55, 48), (50, 52), (45, 56), (40, 60)],
            [(114, -22), (130, -12), (142, -11), (153, -26), (150, -37), (140, -38), (130, -32), (115, -34)],
            [(-5, 50), (1, 51), (2, 53), (-2, 56), (-3, 59), (-6, 57), (-5, 54), (-3, 53)],
        ],
        "labels": {"NORTH AMERICA": (-100, 45), "SOUTH AMERICA": (-60, -15), "EUROPE": (15, 53), "AFRICA": (18, 5), "ASIA": (95, 52),
                   "AUSTRALIA": (134, -26), "INDIAN OCEAN": (78, -20), "ATLANTIC OCEAN": (-35, 25), "PACIFIC OCEAN": (-140, 5)},
        "places": {"britain": (-2.0, 54.0), "england": (-1.5, 52.5), "london": (-0.1, 51.5), "uk": (-2.0, 54.0), "europe": (15.0, 50.0),
                   "india": (78.0, 21.0), "china": (105.0, 35.0), "africa": (18.0, 5.0), "america": (-98.0, 40.0),
                   "united states": (-98.0, 40.0), "canada": (-100.0, 58.0), "australia": (134.0, -26.0), "egypt": (30.0, 27.0),
                   "south africa": (24.0, -30.0), "russia": (90.0, 60.0), "japan": (138.0, 36.0), "caribbean": (-72.0, 18.0),
                   "hong kong": (114.2, 22.3), "middle east": (45.0, 29.0)},
    },
}
# Words that pick a map when no point label is known: first match wins, "world" is the fallback.
_HINTS = {"south_asia": r"\b(india\w*|bengal\w*|plassey|calcutta|kolkata|bombay|mumbai|madras|chennai|delhi|ceylon|sri lanka|raj|sepoy\w*)\b",
          "east_asia": r"\b(china|chinese|hong kong|canton|guangzhou|shanghai|nanjing|macau|opium|qing)\b"}


def project(region: str, lon: float, lat: float) -> tuple[float, float]:
    """(lon, lat) -> (x, y) in 0..1 of the region's view box (y grows downward)."""
    lon0, lon1, lat0, lat1 = REGIONS[region]["view"]
    return (lon - lon0) / (lon1 - lon0), (lat1 - lat) / (lat1 - lat0)


def pick_region(data: dict, narration: str = "") -> str | None:
    """The map a scene uses: an explicit `region`, else the map that knows most of its point labels, else the one the
    title / narration point to, else the world map. Returns None for the western-Mediterranean map (render.py draws it)."""
    from studio.history.autoscene import PLACES  # Mediterranean place table

    want = str(data.get("region") or "").lower().replace(" ", "_")
    if want in REGIONS:
        return want
    if want in ("mediterranean", "med"):
        return None
    labels = [str(p.get("label", "")).strip().lower() for p in data.get("points") or []]
    score = {name: sum(k in reg["places"] for k in labels) for name, reg in REGIONS.items()}
    score["mediterranean"] = sum(k in PLACES for k in labels)
    best = max(score.values())
    if best:
        for name in ("mediterranean", "south_asia", "east_asia", "world"):  # ties: the more local map wins
            if score[name] == best:
                return None if name == "mediterranean" else name
    text = " ".join([str(data.get("title", "")), narration]).lower()
    for name, pat in _HINTS.items():
        if re.search(pat, text):
            return name
    return None if any(re.search(rf"\b{re.escape(p)}\b", text) for p in PLACES) else "world"


def resolve_points(region: str, points: list[dict]) -> list[dict]:
    """Points with x, y on this region's map. A label the table does not know is dropped, never given an invented spot."""
    table = REGIONS[region]["places"]
    out = []
    for p in points or []:
        key = str(p.get("label", "")).strip().lower()
        if key in table:
            x, y = project(region, *table[key])
            out.append({**p, "x": x, "y": y})
    return out
