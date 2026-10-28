const fs = require('fs');
const path = require('path');
const neo4j = require('neo4j-driver');
const { getFullGraph } = require('./graph.queries');

function normalize(value) {
  return neo4j.isInt(value) ? value.toNumber() : value;
}

function normalizeProps(props) {
  const out = {};
  for (const [k, v] of Object.entries(props)) {
    out[k] = normalize(v);
  }
  return out;
}

// Źródło plikowe (data/graph_export.json): te same węzły i krawędzie co w bazie,
// bez uruchamiania Neo4j - do powtarzalnych obliczeń i testów (GRAPH_JSON=ścieżka).
function loadGraphFromFile(file) {
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const idOf = new Map(data.nodes.map((n, i) => [n.name, i + 1]));
  return {
    nodes: data.nodes.map((n, i) => ({ id: i + 1, labels: ['Location'], properties: { ...n } })),
    edges: data.edges.map((e, i) => {
      const { from, to, ...properties } = e;
      return { id: String(i), type: 'PATH', from: idOf.get(from), to: idOf.get(to), properties };
    }),
  };
}

// Bez skonfigurowanej bazy (brak NEO4J_URI) aplikacja czyta dołączony plik grafu data/graph_export.json,
// więc po `npm install && npm start` działa bez Neo4j.
const DEFAULT_GRAPH_FILE = path.join(__dirname, '../../../data/graph_export.json');

async function fetchGraph() {
  const file = process.env.GRAPH_JSON || (!process.env.NEO4J_URI && fs.existsSync(DEFAULT_GRAPH_FILE) ? DEFAULT_GRAPH_FILE : null);
  if (file) return loadGraphFromFile(file);
  const { getSession } = require('../../config/neo4j'); // dopiero tu: tryb plikowy nie wymaga .env
  const session = getSession();
  try {
    const result = await session.run(getFullGraph);

    const nodes = new Map();
    const edges = [];

    result.records.forEach(record => {
      const n = record.get('n');
      const m = record.get('m');
      const r = record.get('r');

      if (!nodes.has(n.identity.toInt())) {
        nodes.set(n.identity.toInt(), {
          id: n.identity.toInt(),
          labels: n.labels,
          properties: normalizeProps(n.properties),
        });
      }

      if (!nodes.has(m.identity.toInt())) {
        nodes.set(m.identity.toInt(), {
          id: m.identity.toInt(),
          labels: m.labels,
          properties: normalizeProps(m.properties),
        });
      }

      edges.push({
        // r.identity (legacy numeric id) is not guaranteed unique across
        // relationships in Neo4j 5.x - elementId is the stable, unique one
        id: r.elementId,
        type: r.type,
        from: n.identity.toInt(),
        to: m.identity.toInt(),
        properties: normalizeProps(r.properties),
      });
    });

    return {
      nodes: Array.from(nodes.values()),
      edges,
    };
  } finally {
    await session.close();
  }
}

module.exports = { fetchGraph };
