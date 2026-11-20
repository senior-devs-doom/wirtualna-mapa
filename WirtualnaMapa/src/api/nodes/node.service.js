const neo4j = require('neo4j-driver');
const { getSession } = require('../../config/neo4j');
const { getNodeWithConnections } = require('./node.queries');

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

async function fetchNode(id) {
  const session = getSession();
  try {
    const result = await session.run(getNodeWithConnections, {
      id: neo4j.int(id),
    });

    if (result.records.length === 0) return null;

    const baseNode = result.records[0].get('n');

    const connections = [];

    result.records.forEach(record => {
      const r = record.get('r');
      const m = record.get('m');
      if (!r || !m) return;

      connections.push({
        relationship: {
          id: r.identity.toInt(),
          type: r.type,
          properties: normalizeProps(r.properties),
        },
        node: {
          id: m.identity.toInt(),
          labels: m.labels,
          properties: normalizeProps(m.properties),
        },
      });
    });

    return {
      id: baseNode.identity.toInt(),
      labels: baseNode.labels,
      properties: normalizeProps(baseNode.properties),
      connections,
    };
  } finally {
    await session.close();
  }
}

module.exports = { fetchNode };
