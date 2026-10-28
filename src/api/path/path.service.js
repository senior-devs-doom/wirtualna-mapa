const RiskModel = require('../../libs/riskModel');
const { fetchGraph } = require('../graph/graph.service');

const USER_CLASSES = ['U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7'];

const model = new RiskModel();

function flagsToBitmask(flags) {
  let mask = 0;
  USER_CLASSES.forEach((code, i) => {
    if (flags[code]) mask |= (1 << i);
  });
  return mask;
}

function flagsToUVec(flags) {
  return USER_CLASSES.map(code => (flags[code] ? RiskModel.U_ON : RiskModel.U_OFF));
}

// Wszystko, co nie zależy od profilu użytkownika, liczone raz: graf z Neo4j,
// lista sąsiedztwa oraz dla każdej krawędzi parametry kosztu (L, q, d, h, b).
// Graf jest w produkcji stabilny, więc cache żyje do restartu serwera
// (po ponownej migracji do Neo4j trzeba zrestartować serwer).
let graphPromise = null;

function buildPrepared(graph) {
  const idToNode = new Map(graph.nodes.map(n => [n.id, n]));
  const byName = new Map();
  graph.nodes.forEach(n => {
    if (n.properties.name) byName.set(n.properties.name, n);
  });

  const adjacency = new Map();
  graph.nodes.forEach(n => adjacency.set(n.id, []));
  const edges = [];
  graph.edges.forEach(e => {
    if (e.type !== 'PATH') return;
    const prepared = {
      idx: edges.length,
      raw: e,
      L: e.properties.L,
      length: RiskModel.edgeLength(e.properties),
      params: model.prepareEdge(e.properties),
    };
    edges.push(prepared);
    if (!adjacency.has(e.from)) adjacency.set(e.from, []);
    adjacency.get(e.from).push({ to: e.to, edge: prepared });
  });

  return { idToNode, byName, adjacency, edges, profileCache: new Map() };
}

function getPrepared() {
  if (!graphPromise) {
    graphPromise = fetchGraph().then(buildPrepared).catch(err => {
      graphPromise = null; // nie zapamiętuj błędu (np. Neo4j chwilowo niedostępne)
      throw err;
    });
  }
  return graphPromise;
}

// Koszty wszystkich krawędzi dla danego profilu (maski flag) liczone naraz
// i zapamiętane - maksymalnie 2^7 = 128 profili. Dijkstra tylko odczytuje
// costs[idx], bez żadnej matematyki w pętli.
function costsForProfile(prepared, flags) {
  const bitmask = flagsToBitmask(flags);
  let costs = prepared.profileCache.get(bitmask);
  if (!costs) {
    const s = model.prepareUser(flagsToUVec(flags));
    costs = new Float64Array(prepared.edges.length);
    for (const e of prepared.edges) {
      costs[e.idx] = model.costPrepared(e.params, s);
    }
    prepared.profileCache.set(bitmask, costs);
  }
  return costs;
}

// Dijkstra - full riskModel.computeCost() result is the edge weight (not raw
// distance), so this is exactly optimal regardless of the cost function's
// shape. O(V^2) is fine at this graph's size (dozens of nodes/edges).
function dijkstra(adjacency, startId, goalIds, costs) {
  const dist = new Map([[startId, 0]]);
  const prevEdge = new Map();
  const visited = new Set();

  while (true) {
    let currentId = null;
    let currentDist = Infinity;
    for (const [id, d] of dist) {
      if (!visited.has(id) && d < currentDist) {
        currentDist = d;
        currentId = id;
      }
    }
    if (currentId === null) return { dist, prevEdge, reachedId: null };
    if (goalIds.has(currentId)) return { dist, prevEdge, reachedId: currentId };
    visited.add(currentId);

    for (const { to, edge } of adjacency.get(currentId) || []) {
      if (visited.has(to)) continue;
      const alt = currentDist + costs[edge.idx];
      if (alt < (dist.has(to) ? dist.get(to) : Infinity)) {
        dist.set(to, alt);
        prevEdge.set(to, { from: currentId, edge });
      }
    }
  }

  return { dist, prevEdge, reachedId: null };
}

// toNames: nazwa celu albo tablica nazw. Dla tablicy zwracana jest trasa do
// NAJTAŃSZEGO (wg kosztu personalizowanego) z nich - Dijkstra zatrzymuje się
// na pierwszym wyciągniętym z kolejki węźle docelowym, więc jedno przejście
// grafu wystarcza niezależnie od liczby celów.
async function findPath(fromName, toNames, flags) {
  const prepared = await getPrepared();
  const { byName, idToNode, adjacency } = prepared;

  const startNode = byName.get(fromName);
  if (!startNode) throw new Error(`Unknown start node: ${fromName}`);

  const names = Array.isArray(toNames) ? toNames : [toNames];
  const goalIds = new Set();
  for (const name of names) {
    const node = byName.get(name);
    if (node) goalIds.add(node.id);
  }
  if (goalIds.size === 0) {
    throw new Error(`Unknown destination node: ${names.join(', ')}`);
  }

  const costs = costsForProfile(prepared, flags || {});
  const { dist, prevEdge, reachedId } = dijkstra(adjacency, startNode.id, goalIds, costs);
  if (reachedId === null) return null;

  const pathNodeIds = [reachedId];
  const pathEdges = [];
  let cur = reachedId;
  while (cur !== startNode.id) {
    const step = prevEdge.get(cur);
    pathEdges.unshift(step.edge);
    pathNodeIds.unshift(step.from);
    cur = step.from;
  }

  return {
    path: pathNodeIds.map(id => idToNode.get(id).properties.name),
    edges: pathEdges.map(e => ({
      from: idToNode.get(e.raw.from).properties.name,
      to: idToNode.get(e.raw.to).properties.name,
      preset: e.raw.properties.preset,
      q: e.params.q,
      L: e.L,
      length: e.length,
      cost: costs[e.idx],
    })),
    target: idToNode.get(reachedId).properties.name,
    candidates: goalIds.size,
    alreadyThere: reachedId === startNode.id,
    totalCost: dist.get(reachedId),
    totalDistance: pathEdges.reduce((sum, e) => sum + e.length, 0),
  };
}

module.exports = { findPath, USER_CLASSES };
