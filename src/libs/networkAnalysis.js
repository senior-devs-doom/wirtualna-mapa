// networkAnalysis.js
//
// Miary spójności i dostępności grafu budynku. Funkcje są czyste (przyjmują graf
// w postaci {nodes, edges} jak z /api/graph, nic nie czytają z bazy), więc można je
// testować na małych grafach.
//
// Graf jest traktowany jako nieskierowany i prosty (krawędzie skierowane przeciwnych
// kierunków o tym samym typie tworzą jedno połączenie). Podgrafy powstają przez
// wykluczenie typów odcinków (np. bez schodów = graf dostępny dla osoby na wózku)
// lub węzłów (awaria windy).

const RiskModel = require('./riskModel');

function buildUndirected(graph, { excludePresets = [], excludeNodes = [] } = {}) {
  const banned = new Set(excludeNodes);
  const ids = graph.nodes.filter(n => !banned.has(n.id)).map(n => n.id);
  const adj = new Map(ids.map(id => [id, []]));
  const seen = new Set();
  const edges = [];
  for (const e of graph.edges) {
    if (e.type && e.type !== 'PATH') continue;
    if (banned.has(e.from) || banned.has(e.to)) continue;
    if (excludePresets.includes(e.properties.preset)) continue;
    const key = e.from < e.to ? `${e.from}|${e.to}` : `${e.to}|${e.from}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const edge = { key, a: e.from, b: e.to, L: RiskModel.edgeLength(e.properties), preset: e.properties.preset };
    edges.push(edge);
    adj.get(e.from).push({ to: e.to, edge });
    adj.get(e.to).push({ to: e.from, edge });
  }
  return { ids, adj, edges };
}

function components(g) {
  const comp = new Map();
  let c = 0;
  for (const id of g.ids) {
    if (comp.has(id)) continue;
    const stack = [id];
    comp.set(id, c);
    while (stack.length) {
      const u = stack.pop();
      for (const { to } of g.adj.get(u)) {
        if (!comp.has(to)) { comp.set(to, c); stack.push(to); }
      }
    }
    c++;
  }
  const sizes = Array(c).fill(0);
  for (const v of comp.values()) sizes[v]++;
  return { comp, count: c, sizes };
}

function bfsHops(g, src) {
  const d = new Map([[src, 0]]);
  const q = [src];
  for (let i = 0; i < q.length; i++) {
    const u = q[i];
    for (const { to } of g.adj.get(u)) {
      if (!d.has(to)) { d.set(to, d.get(u) + 1); q.push(to); }
    }
  }
  return d;
}

// Dijkstra po długości fizycznej L; zwraca odległości i listę poprzedników (do centralności)
function dijkstraLength(g, src) {
  const dist = new Map([[src, 0]]);
  const done = new Set();
  const sigma = new Map([[src, 1]]);
  const preds = new Map([[src, []]]);
  const order = [];
  const EPS = 1e-9;
  while (true) {
    let u = null, best = Infinity;
    for (const [id, d] of dist) if (!done.has(id) && d < best) { best = d; u = id; }
    if (u === null) break;
    done.add(u);
    order.push(u);
    for (const { to, edge } of g.adj.get(u)) {
      if (done.has(to)) continue;
      const alt = best + edge.L;
      const cur = dist.has(to) ? dist.get(to) : Infinity;
      if (alt < cur - EPS) {
        dist.set(to, alt); sigma.set(to, sigma.get(u)); preds.set(to, [{ from: u, edge }]);
      } else if (Math.abs(alt - cur) <= EPS) {
        sigma.set(to, sigma.get(to) + sigma.get(u)); preds.get(to).push({ from: u, edge });
      }
    }
  }
  return { dist, sigma, preds, order };
}

// Statystyki odległości dla wszystkich par uporządkowanych połączonych ścieżką
function distanceStats(g) {
  let sumL = 0, sumH = 0, pairs = 0, sumInvL = 0;
  let diamL = { d: -1 }, diamH = { d: -1 };
  for (const s of g.ids) {
    const { dist } = dijkstraLength(g, s);
    const hops = bfsHops(g, s);
    for (const [t, d] of dist) {
      if (t === s) continue;
      const h = hops.get(t);
      sumL += d; sumH += h; sumInvL += 1 / d; pairs++;
      if (d > diamL.d) diamL = { d, from: s, to: t };
      if (h > diamH.d) diamH = { d: h, from: s, to: t };
    }
  }
  const n = g.ids.length;
  return {
    connectedPairs: pairs,
    totalPairs: n * (n - 1),
    meanLength: pairs ? sumL / pairs : null,
    meanHops: pairs ? sumH / pairs : null,
    diameterLength: diamL,
    diameterHops: diamH,
    globalEfficiency: n > 1 ? sumInvL / (n * (n - 1)) : null, // średnia z 1/d po wszystkich parach (niepołączone = 0)
  };
}

// Centralność pośrednictwa (Brandes, ważona długością): węzłów i krawędzi.
// Wartości znormalizowane przez liczbę par uporządkowanych (n-1)(n-2) dla węzłów
// i n(n-1) dla krawędzi, czyli "udział najkrótszych dróg przechodzących przez element".
function betweenness(g) {
  const node = new Map(g.ids.map(i => [i, 0]));
  const edge = new Map(g.edges.map(e => [e.key, 0]));
  for (const s of g.ids) {
    const { sigma, preds, order } = dijkstraLength(g, s);
    const delta = new Map(order.map(v => [v, 0]));
    for (let i = order.length - 1; i >= 0; i--) {
      const w = order[i];
      for (const { from: v, edge: e } of preds.get(w)) {
        const c = (sigma.get(v) / sigma.get(w)) * (1 + delta.get(w));
        delta.set(v, delta.get(v) + c);
        edge.set(e.key, edge.get(e.key) + c);
      }
      if (w !== s) node.set(w, node.get(w) + delta.get(w));
    }
  }
  const n = g.ids.length;
  for (const [k, v] of node) node.set(k, n > 2 ? v / ((n - 1) * (n - 2)) : 0);
  for (const [k, v] of edge) edge.set(k, n > 1 ? v / (n * (n - 1)) : 0);
  return { node, edge };
}

function clustering(g) {
  let sum = 0, cnt = 0;
  for (const id of g.ids) {
    const nb = g.adj.get(id).map(x => x.to);
    const k = nb.length;
    if (k < 2) { cnt++; continue; }
    let links = 0;
    for (let i = 0; i < k; i++) for (let j = i + 1; j < k; j++) {
      if (g.adj.get(nb[i]).some(x => x.to === nb[j])) links++;
    }
    sum += (2 * links) / (k * (k - 1)); cnt++;
  }
  return cnt ? sum / cnt : 0;
}

function bridgesAndCutNodes(g) {
  let t = 0;
  const disc = new Map(), low = new Map();
  const bridges = [], cuts = new Set();
  function dfs(u, pe) {
    disc.set(u, ++t); low.set(u, t);
    let ch = 0;
    for (const { to, edge } of g.adj.get(u)) {
      if (edge === pe) continue;
      if (disc.has(to)) low.set(u, Math.min(low.get(u), disc.get(to)));
      else {
        ch++; dfs(to, edge);
        low.set(u, Math.min(low.get(u), low.get(to)));
        if (low.get(to) > disc.get(u)) bridges.push(edge);
        if (pe && low.get(to) >= disc.get(u)) cuts.add(u);
      }
    }
    if (!pe && ch > 1) cuts.add(u);
  }
  for (const id of g.ids) if (!disc.has(id)) dfs(id, null);
  return { bridges, cutNodes: [...cuts] };
}

// Maksymalna liczba rozłącznych krawędziowo dróg między dwoma zbiorami węzłów
// (przepływ o jednostkowych przepustowościach, Edmonds-Karp). Każda krawędź
// nieskierowana ma przepustowość 1 w obu kierunkach.
function edgeDisjointPaths(g, setA, setB) {
  const A = new Set(setA), B = new Set(setB);
  if (!A.size || !B.size) return 0;
  const cap = new Map();
  const key = (u, v) => `${u}>${v}`;
  const nb = new Map(g.ids.map(i => [i, []]));
  nb.set('S', []); nb.set('T', []);
  const add = (u, v, c) => {
    if (!cap.has(key(u, v))) { cap.set(key(u, v), 0); nb.get(u).push(v); }
    if (!cap.has(key(v, u))) { cap.set(key(v, u), 0); nb.get(v).push(u); }
    cap.set(key(u, v), cap.get(key(u, v)) + c);
  };
  for (const e of g.edges) { add(e.a, e.b, 1); add(e.b, e.a, 1); }
  for (const a of A) add('S', a, 1e9);
  for (const b of B) add(b, 'T', 1e9);
  let flow = 0;
  while (true) {
    const prev = new Map([['S', null]]);
    const q = ['S'];
    for (let i = 0; i < q.length && !prev.has('T'); i++) {
      const u = q[i];
      for (const v of nb.get(u)) {
        if (!prev.has(v) && cap.get(key(u, v)) > 0) { prev.set(v, u); q.push(v); }
      }
    }
    if (!prev.has('T')) break;
    let f = Infinity;
    for (let v = 'T'; prev.get(v) !== null; v = prev.get(v)) f = Math.min(f, cap.get(key(prev.get(v), v)));
    for (let v = 'T'; prev.get(v) !== null; v = prev.get(v)) {
      const u = prev.get(v);
      cap.set(key(u, v), cap.get(key(u, v)) - f);
      cap.set(key(v, u), cap.get(key(v, u)) + f);
    }
    flow += f;
  }
  return flow;
}

// Składnia przestrzenna (Hillier, Hanson): średnia głębokość MD węzła (średnia liczba
// kroków do pozostałych), względna asymetria RA = 2(MD-1)/(n-2), RRA = RA / D_n,
// integracja = 1/RRA. D_n normalizuje do grafu o tej samej liczbie węzłów w układzie "diamentowym".
function spaceSyntax(g) {
  const n = g.ids.length;
  const Dn = (2 * (n * (Math.log2((n + 2) / 3) - 1) + 1)) / ((n - 1) * (n - 2));
  const out = new Map();
  for (const id of g.ids) {
    const h = bfsHops(g, id);
    if (h.size < n) { out.set(id, null); continue; } // węzeł w niespójnej części
    let s = 0;
    for (const [t, d] of h) if (t !== id) s += d;
    const MD = s / (n - 1);
    const RA = (2 * (MD - 1)) / (n - 2);
    const RRA = RA / Dn;
    out.set(id, { MD, RA, RRA, integration: 1 / RRA });
  }
  return out;
}

function summary(g) {
  const c = components(g);
  const ds = distanceStats(g);
  const deg = g.ids.map(id => g.adj.get(id).length);
  const n = g.ids.length, m = g.edges.length;
  const largest = Math.max(...c.sizes);
  return {
    nodes: n, edges: m, components: c.count, largestComponent: largest,
    connectedPairsShare: ds.connectedPairs / ds.totalPairs,
    density: (2 * m) / (n * (n - 1)),
    meanDegree: deg.reduce((a, b) => a + b, 0) / n,
    cyclomatic: m - n + c.count,
    clustering: clustering(g),
    meanLength: ds.meanLength, meanHops: ds.meanHops,
    diameterLength: ds.diameterLength, diameterHops: ds.diameterHops,
    globalEfficiency: ds.globalEfficiency,
  };
}

module.exports = {
  buildUndirected, components, bfsHops, dijkstraLength, distanceStats, betweenness,
  clustering, bridgesAndCutNodes, edgeDisjointPaths, spaceSyntax, summary,
};
