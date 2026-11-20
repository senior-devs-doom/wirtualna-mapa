import json
import math
from pathlib import Path

FOLDER = Path(__file__).parent
CSV_PATH = FOLDER / "location.csv"
CIDS_PATH = FOLDER / "photo_cids.json"  # zapisywane przez upload_to_ipfs.py
EDGES_PATH = FOLDER / "edges.json"
PRESETS_PATH = FOLDER / "risk_presets.json"
OUT_PATH = FOLDER / "graph_export.json"

METERS_PER_LEVEL = 3.5  # must match edge_editor.html - only used here to recompute node x/y/z for reference


def decode_description(s):
    r"""map_editor.html stores a newline in description as \n and a literal backslash as \\ (the CSV is line-based)."""
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] in ("n", "\\"):
            out.append("\n" if s[i + 1] == "n" else "\\")
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def load_nodes():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        lines = [l for l in f.read().splitlines() if l]
    rows = []
    for line in lines[1:]:
        parts = line.split(";")
        name, latlon, timestamp, height = parts[:4]
        # description is free text, may itself contain ";" - always the last field
        description = decode_description(";".join(parts[4:]).strip())
        lat, lon = (float(v) for v in latlon.split(","))
        if lat == 0 and lon == 0:
            continue
        rows.append({"name": name, "lat": lat, "lon": lon, "height": float(height), "description": description})

    center_lat = sum(r["lat"] for r in rows) / len(rows)
    center_lon = sum(r["lon"] for r in rows) / len(rows)
    m_per_deg_lat = 111320
    m_per_deg_lon = 111320 * math.cos(math.radians(center_lat))

    # CID zdjęcia w IPFS (jeśli już wgrane); puste = aplikacja użyje lokalnego /photos
    cids = json.loads(CIDS_PATH.read_text(encoding="utf-8")) if CIDS_PATH.exists() else {}

    nodes = []
    for i, r in enumerate(rows, start=1):
        nodes.append({
            "id": i,
            "name": r["name"],
            "x": (r["lon"] - center_lon) * m_per_deg_lon,
            "y": -(r["lat"] - center_lat) * m_per_deg_lat,
            "z": r["height"] * METERS_PER_LEVEL,
            "description": r["description"],
            "imageCid": cids.get(r["name"], {}).get("cid", ""),
        })
    return nodes


CLASSES = "ABCDEFGHI"


def classify_and_expand(stored_edges, nodes, presets):
    """Z krawędzi narysowanych w edge_editor (from, to, preset, L) robi krawędzie modelu v6b:
    - dojścia do windy (krawędź z węzłem Winda*, bez zmiany poziomu) dostają preset elevator_access;
    - L = dystans poziomy z współrzędnych węzłów (wysokość niesie składowa q, nie długość 3D);
    - q dla schodów i jazdy windą = |dz| / METERS_PER_LEVEL (liczba kondygnacji, może być ułamkowa,
      niezależna od podziału grafu); dla elevator_access ustawiane osobno dla każdego kierunku
      (oczekiwanie i obsługa kabiny tylko na krawędzi wejścia do kabiny, patrz direct_edges);
    - d, h*, b* kopiowane z presetu."""
    by_name = {n["name"]: n for n in nodes}
    pre = {p["name"]: p for p in presets}
    out, changed = [], []
    for e in stored_edges:
        a, b = by_name.get(e["from"]), by_name.get(e["to"])
        if a is None or b is None:
            out.append(e)
            continue
        dz = abs(b["z"] - a["z"])
        preset = e["preset"]
        touches_lift = e["from"].startswith("Winda") or e["to"].startswith("Winda")
        if touches_lift and dz < 0.5 and preset in ("normal", "elevator"):
            if preset != "elevator_access":
                changed.append((e["from"], e["to"], preset))
            preset = "elevator_access"
        p = pre[preset]
        q = round(dz / METERS_PER_LEVEL, 4) if preset in ("stairs", "elevator") else 0
        L = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
        edge = {"from": e["from"], "to": e["to"], "preset": preset, "L": L, "q": q, "d": p["d"]}
        for c in CLASSES:
            edge["h" + c] = p["h" + c]
        for c in CLASSES:
            edge["b" + c] = p["b" + c]
        out.append(edge)
    return out, changed


def direct_edges(stored_edges):
    """Każda narysowana krawędź to dwie skierowane. Oczekiwanie na windę (q = 1, d i b z presetu
    elevator_access) niesie tylko krawędź prowadząca do węzła windy z węzła spoza windy; pozostałe
    kierunki dojścia mają q = 0 (sam dystans). Węzły windy: końce krawędzi jazdy (preset elevator)."""
    lift = {x for e in stored_edges if e["preset"] == "elevator" for x in (e["from"], e["to"])}
    out = []
    for e in stored_edges:
        for f, t in ((e["from"], e["to"]), (e["to"], e["from"])):
            d = {**e, "from": f, "to": t}
            if e["preset"] == "elevator_access":
                d["q"] = 1 if (t in lift and f not in lift) else 0
            out.append(d)
    return out


def main():
    nodes = load_nodes()
    with open(EDGES_PATH, encoding="utf-8") as f:
        stored_edges = json.load(f)
    with open(PRESETS_PATH, encoding="utf-8") as f:
        presets = json.load(f)

    stored_edges, changed = classify_and_expand(stored_edges, nodes, presets)
    node_names = {n["name"] for n in nodes}
    kept = []
    skipped = []
    for e in stored_edges:
        if e["from"] not in node_names or e["to"] not in node_names:
            skipped.append(e)
            continue
        kept.append(e)
    # each stored (undirected) edge becomes two directed PATH relationships
    edges = direct_edges(kept)

    export = {"nodes": nodes, "riskPresets": presets, "edges": edges}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH.name}: {len(nodes)} nodes, {len(presets)} presets, "
          f"{len(edges)} directed edges ({len(stored_edges)} drawn connections).")
    print(f"Przeklasyfikowano na elevator_access: {len(changed)} krawędzi")
    for f, t, old in changed:
        print(f"  - {f} -> {t} (było: {old})")
    if skipped:
        print("Skipped edges referencing missing nodes:")
        for e in skipped:
            print(f"  - {e['from']} -> {e['to']}")


if __name__ == "__main__":
    main()
