#!/usr/bin/env python3
"""Refresh official SDOT mainline geometry using the reviewed map-area configuration.

Run from any directory with Python 3 (standard library only). This downloads two
small GIS queries, preserves existing disconnected components, and writes only
burke-gilman/data/trail-corridor.geojson. Changing topology fails for review.
The source PDF affine fit is fixed in trail-corridor-config.json; it determines
only approximate area splits and representative map positions, never distances
from service-request coordinates to the trail.
"""

import json
import math
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "scripts/trail-corridor-config.json").read_text())
CFG = CONFIG["georeference"]
# EPSG:2926 uses US survey feet, not the international foot (0.3048 m).
METERS_PER_SURVEY_FOOT = 1200 / 3937


def fetch(crs, format):
    params = {
        "where": CONFIG["query"],
        "outFields": "OBJECTID,ORD_STNAME_CONCAT,CITYCODE,ACCESS_CODE,SEGMENT_TYPE,GIS_SEG_LENGTH,SND_ID,F_INTR_ID,T_INTR_ID",
        "outSR": crs,
        "f": format,
    }
    url = CONFIG["source"] + "/query?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as response:
        data = json.load(response)
    if "error" in data or data.get("exceededTransferLimit"):
        raise RuntimeError(
            "GIS query failed or was truncated: " + str(data.get("error", "limit"))
        )
    return data


STATE = fetch(2926, "json")
WORLD = fetch(4326, "geojson")
main = [
    f
    for f in STATE["features"]
    if f["attributes"]["ORD_STNAME_CONCAT"] == "BURKE GILMAN TRL"
]
byid = {f["properties"]["OBJECTID"]: f for f in WORLD["features"]}
assert (
    len(main) == CONFIG["expectedSourceFeatures"]
), "Source changed; review geometry and update configuration."
# Assemble the two existing connected components from topology. Never draw the Missing Link.
adj = {}
for f in main:
    for node in [f["attributes"]["F_INTR_ID"], f["attributes"]["T_INTR_ID"]]:
        adj.setdefault(node, []).append(f)
assert all(len(v) in [1, 2] for v in adj.values())
seen = set()


def chain(start):
    node = start
    points = []
    world = []
    ids = []
    while True:
        options = [f for f in adj[node] if f["attributes"]["OBJECTID"] not in seen]
        if not options:
            break
        assert len(options) == 1
        f = options[0]
        a = f["attributes"]
        oid = a["OBJECTID"]
        seen.add(oid)
        assert len(f["geometry"]["paths"]) == 1
        p = f["geometry"]["paths"][0]
        q = byid[oid]["geometry"]["coordinates"]
        assert len(p) == len(q)
        if node != a["F_INTR_ID"]:
            p = p[::-1]
            q = q[::-1]
        node = a["T_INTR_ID"] if node == a["F_INTR_ID"] else a["F_INTR_ID"]
        if points:
            assert math.dist(points[-1], p[0]) < 0.05
        points.extend(p if not points else p[1:])
        world.extend(q if not world else q[1:])
        ids.append(oid)
    return points, world, ids


west = chain(CONFIG["startNodes"]["west"])
east = chain(CONFIG["startNodes"]["east"])
assert len(seen) == len(main)


def accumulated(points):
    d = [0.0]
    for a, b in zip(points, points[1:]):
        d.append(d[-1] + math.dist(a, b) * METERS_PER_SURVEY_FOOT)
    return d


wds = accumulated(west[0])
eds = accumulated(east[0])


def nearest(points, ds, q):
    best = None
    for i, (a, b) in enumerate(zip(points, points[1:])):
        v = [b[k] - a[k] for k in [0, 1]]
        n = sum(t * t for t in v)
        t = max(0, min(1, sum((q[k] - a[k]) * v[k] for k in [0, 1]) / n)) if n else 0
        p = [a[k] + t * v[k] for k in [0, 1]]
        dist = math.dist(p, q)
        if best is None or dist < best[0]:
            best = (dist, ds[i] + t * (ds[i + 1] - ds[i]), p, i, t)
    return best


trans = CFG["pdfToEPSG2926"]


def state(p):
    return [p[0] * trans[0][k] + p[1] * trans[1][k] + trans[2][k] for k in [0, 1]]


def pdf(p):
    a, b = trans[0]
    c, d = trans[1]
    u = p[0] - trans[2][0]
    v = p[1] - trans[2][1]
    det = a * d - b * c
    return [(d * u - c * v) / det, (-b * u + a * v) / det]


areas = CONFIG["areas"]
boundaries = []
for a, boundary in zip(areas[1:], CONFIG["areaBoundaries"]):
    assert a["id"] == boundary["startsAreaId"]
    p = boundary["pdfPoint"]
    err, station, snap, i, t = nearest(east[0], eds, state(p))
    geo = [east[1][i][k] + t * (east[1][i + 1][k] - east[1][i][k]) for k in [0, 1]]
    boundaries.append(
        {
            "startsAreaId": a["id"],
            "pdfPoint": p,
            "mainlineDistanceM": round(station, 6),
            "coordinates": geo,
            "offsetToOfficialCenterlineM": round(err * METERS_PER_SURVEY_FOOT, 3),
        }
    )
assert all(
    a["mainlineDistanceM"] < b["mainlineDistanceM"]
    for a, b in zip(boundaries, boundaries[1:])
)


def subline(points, ds, start, end):
    out = []
    for i, (a, b) in enumerate(zip(points, points[1:])):
        lo = max(start, ds[i])
        hi = min(end, ds[i + 1])
        if hi <= lo:
            continue
        l = ds[i + 1] - ds[i]
        p = [a[k] + (b[k] - a[k]) * (lo - ds[i]) / l for k in [0, 1]]
        q = [a[k] + (b[k] - a[k]) * (hi - ds[i]) / l for k in [0, 1]]
        if not out:
            out.append(p)
        out.append(q)
    return out


starts = [0] + [b["mainlineDistanceM"] for b in boundaries]
ends = starts[1:] + [eds[-1]]
features = []
for i, a in enumerate(areas):
    start, end = starts[i], ends[i]
    paths = [subline(east[1], eds, start, end)]
    if i == 0:
        paths.insert(0, west[1])
    length = end - start + (wds[-1] if i == 0 else 0)
    mid = (start + end) / 2
    if i == 0:
        # Representative point on the western reach; counts still include both components.
        target = wds[-1] / 2
        anchor_state = subline(west[0], wds, target, target + 0.01)[0]
    else:
        anchor_state = subline(east[0], eds, mid, mid + 0.01)[0]
    props = {
        "id": a["id"],
        "areaId": a["id"],
        "name": a["name"],
        "lengthM": round(length, 3),
        "pdfAnchor": [round(v, 4) for v in pdf(anchor_state)],
        "areaDefinition": "Approximate ownership-map grouping; not an official neighborhood boundary.",
    }
    geometry = (
        {"type": "LineString", "coordinates": paths[0]}
        if len(paths) == 1
        else {"type": "MultiLineString", "coordinates": paths}
    )
    features.append({"type": "Feature", "properties": props, "geometry": geometry})
assert abs(sum(f["properties"]["lengthM"] for f in features) - wds[-1] - eds[-1]) < 0.01
source = CONFIG["source"]
meta = {
    "title": "Seattle Burke-Gilman existing mainline, grouped into eight approximate map areas",
    "source": source,
    "sourceItem": CONFIG["sourceItem"],
    "query": CONFIG["query"],
    "downloaded": date.today().isoformat(),
    "crs": "WGS84 / EPSG:4326; GeoJSON coordinates are [longitude, latitude]",
    "sourceFeatureCount": len(main),
    "connectedComponents": 2,
    "totalLengthM": round(wds[-1] + eds[-1], 3),
    "excluded": "Ballard Missing Link gap; BURKE GILMAN ACCESS TRL and BURKE GILMAN SAND PT TRL branches; trail north of Seattle city limit. No lines were invented to close gaps.",
    "areas": "Eight approximate groups inherit the existing PDF map section ranges, not official neighborhood boundaries. Boundaries are projected onto the official centerline.",
    "georeference": CFG,
    "boundaries": boundaries,
}
(ROOT / "burke-gilman/data/trail-corridor.geojson").write_text(
    json.dumps(
        {"type": "FeatureCollection", "metadata": meta, "features": features},
        separators=(",", ":"),
    )
    + chr(10)
)

print(
    "Wrote trail-corridor.geojson:",
    len(features),
    "areas;",
    meta["totalLengthM"],
    "meters; Missing Link remains excluded.",
)
