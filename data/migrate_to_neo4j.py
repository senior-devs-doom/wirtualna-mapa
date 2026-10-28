"""
Generates a Cypher migration for the finished graph (tools/graph_export.json)
and runs it against a Neo4j database via the HTTP transaction API.

Usage: python migrate_to_neo4j.py [--database main] [--no-run] [--no-clear]
Domyślnie przed wczytaniem czyści docelową bazę (węzły i relacje), więc baza zawsze odpowiada plikowi grafu.
"""
import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

FOLDER = Path(__file__).parent
EXPORT_PATH = FOLDER / "graph_export.json"
ENV_PATH = FOLDER.parent / ".env"
CYPHER_OUT_PATH = FOLDER / "migration.cypher"

NODE_FIELDS = ["id", "name", "x", "y", "z", "description", "imageCid"]
CLASSES = "ABCDEFGHI"
HB = ["h" + c for c in CLASSES] + ["b" + c for c in CLASSES]
PRESET_FIELDS = ["name", "description", "d"] + HB
EDGE_PROP_FIELDS = HB + ["preset", "L", "q", "d"]


def cypher_literal(value):
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    return repr(value) if not isinstance(value, float) else repr(value)


def cypher_map(d, fields):
    parts = [f"{k}: {cypher_literal(d[k])}" for k in fields]
    return "{" + ", ".join(parts) + "}"


def load_env(path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def build_cypher(export, database):
    nodes = export["nodes"]
    presets = export["riskPresets"]
    edges = export["edges"]

    lines = [
        f"// Migration generated from graph_export.json - run against database `{database}`",
        f"// {len(nodes)} Location nodes, {len(presets)} RiskPreset nodes, {len(edges)} directed PATH edges",
        "",
        "CREATE CONSTRAINT location_name_unique IF NOT EXISTS FOR (n:Location) REQUIRE n.name IS UNIQUE;",
        "CREATE CONSTRAINT riskpreset_name_unique IF NOT EXISTS FOR (n:RiskPreset) REQUIRE n.name IS UNIQUE;",
        "",
        "UNWIND " + json_list_to_cypher(nodes, NODE_FIELDS) + " AS row",
        "CREATE (:Location {id: row.id, name: row.name, x: row.x, y: row.y, z: row.z, description: row.description, imageCid: row.imageCid});",
        "",
        "UNWIND " + json_list_to_cypher(presets, PRESET_FIELDS) + " AS row",
        "CREATE (:RiskPreset {name: row.name, description: row.description, d: row.d, "
        + ", ".join(f"{k}: row.{k}" for k in HB) + "});",
        "",
    ]

    # edges in chunks to keep any single statement from getting unreasonably large
    chunk_size = 500
    for start in range(0, len(edges), chunk_size):
        chunk = edges[start:start + chunk_size]
        rows = []
        for e in chunk:
            props = cypher_map(e, EDGE_PROP_FIELDS)
            rows.append("{from: %s, to: %s, props: %s}" % (cypher_literal(e["from"]), cypher_literal(e["to"]), props))
        lines.append("UNWIND [" + ", ".join(rows) + "] AS row")
        lines.append(
            "MATCH (a:Location {name: row.from}), (b:Location {name: row.to}) "
            "CREATE (a)-[r:PATH]->(b) SET r = row.props;"
        )
        lines.append("")

    return "\n".join(lines)


def json_list_to_cypher(items, fields):
    return "[" + ", ".join(cypher_map(item, fields) for item in items) + "]"


def split_statements(cypher_text):
    statements = []
    for raw in cypher_text.split(";\n"):
        stmt_lines = [l for l in raw.splitlines() if not l.strip().startswith("//")]
        stmt = "\n".join(stmt_lines).strip()
        if stmt:
            statements.append(stmt)
    return statements


def http_post(url, user, password, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    import base64
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ensure_database(base_url, user, password, database):
    result = http_post(f"{base_url}/db/system/tx/commit", user, password,
                        {"statements": [{"statement": f"CREATE DATABASE {database} IF NOT EXISTS"}]})
    if result.get("errors"):
        raise RuntimeError(f"CREATE DATABASE failed: {result['errors']}")

    for _ in range(20):
        result = http_post(f"{base_url}/db/system/tx/commit", user, password,
                            {"statements": [{"statement": "SHOW DATABASES"}]})
        rows = result["results"][0]["data"]
        for row in rows:
            cols = result["results"][0]["columns"]
            record = dict(zip(cols, row["row"]))
            if record["name"] == database and record["currentStatus"] == "online":
                return
        time.sleep(1)
    raise RuntimeError(f"Database {database} did not come online in time")


def run_statements(base_url, user, password, database, statements):
    for i, stmt in enumerate(statements, 1):
        result = http_post(f"{base_url}/db/{database}/tx/commit", user, password,
                            {"statements": [{"statement": stmt}]})
        if result.get("errors"):
            raise RuntimeError(f"Statement {i}/{len(statements)} failed:\n{stmt[:200]}...\n{result['errors']}")
        print(f"  [{i}/{len(statements)}] ok")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="main")
    parser.add_argument("--no-run", action="store_true", help="only write migration.cypher, do not execute")
    parser.add_argument("--no-clear", action="store_true", help="do not delete existing nodes before loading")
    args = parser.parse_args()

    export = json.loads(EXPORT_PATH.read_text(encoding="utf-8"))
    cypher_text = build_cypher(export, args.database)
    CYPHER_OUT_PATH.write_text(cypher_text, encoding="utf-8")
    print(f"Wrote {CYPHER_OUT_PATH.name}")

    if args.no_run:
        return

    env = load_env(ENV_PATH)
    user = env.get("NEO4J_USER", "neo4j")
    password = env.get("NEO4J_PASSWORD")
    if not password:
        raise SystemExit("No NEO4J_PASSWORD found in WirtualnaMapa/.env")
    base_url = "http://localhost:7474"

    print(f"Ensuring database `{args.database}` exists and is online...")
    ensure_database(base_url, user, password, args.database)

    statements = split_statements(cypher_text)
    if not args.no_clear:
        statements.insert(0, "MATCH (n) DETACH DELETE n")
    print(f"Running {len(statements)} statements against `{args.database}`...")
    run_statements(base_url, user, password, args.database, statements)
    print("Migration complete.")


if __name__ == "__main__":
    main()
