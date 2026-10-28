// route_stats.js - statystyki tras dla profili użytkownika (podrozdział 7.1 pracy).
//
// Użycie:  GRAPH_JSON=data/graph_export.json node scripts/route_stats.js [wynik.json]
// (bez GRAPH_JSON czyta graf z bazy jak aplikacja). Niczego nie zapisuje poza plikiem wynikowym.
require('dotenv').config({ quiet: true });
const fs = require('fs');
const { fetchGraph } = require('../src/api/graph/graph.service');
const { findPath } = require('../src/api/path/path.service');
const RiskModel = require('../src/libs/riskModel');
const edgeLength = RiskModel.edgeLength;

const ALL = Object.fromEntries(['U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7'].map(u => [u, true]));
const PROFILES = { bez: {}, U1: { U1: true }, U3: { U3: true }, U5: { U5: true }, U1_U7: { U1: true, U7: true }, zlozony: { U1: true, U3: true, U5: true }, wszystkie: ALL };
const SCENARIOS = [
  ['Zewnątrz Południe', 'Poziom 4 Biblioteka'],
  ['Poziom 1 Korytarz 7', 'Poziom 2 Korytarz 3'],
  ['Poziom 4 Korytarz 5', 'Poziom -1 Korytarz 5'],
  ['Poziom -1 Korytarz 3', 'Poziom 1 Korytarz 7'],
];
const OUT = process.argv[2] || 'route_stats.json';
const r = (x, d = 1) => +x.toFixed(d);
const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
// schody liczone tylko tam, gdzie jest pokonywana kondygnacja (q > 0); dojścia do klatki (q = 0) nie są przeszkodą
const hasStairs = x => x.edges.some(e => e.preset === 'stairs' && e.q > 0);
const hasLift = x => x.edges.some(e => (e.preset === 'elevator' || e.preset === 'elevator_access') && e.q > 0);

(async () => {
  const graph = await fetchGraph();
  const z = new Map(graph.nodes.map(n => [n.properties.name, n.properties.z]));
  const names = [...graph.nodes].sort((p, q) => p.properties.id - q.properties.id).map(n => n.properties.name); // kolejność wg id z pliku grafu, żeby orientacja par a<b nie zależała od kolejności zwracanej przez bazę
  const pairs = [];
  for (const a of names) for (const b of names) if (a !== b) pairs.push([a, b, Math.abs(z.get(a) - z.get(b)) > 1]);
  const between = pairs.filter(p => p[2]);

  const res = {};
  for (const [pname, flags] of Object.entries(PROFILES)) {
    res[pname] = pairs.map(([a, b]) => findPath(a, b, flags));
    res[pname] = await Promise.all(res[pname]);
  }
  const base = res.bez;

  // najkrótsze drogi (po długości) bez przeszkód schodowych (q > 0): czy schodów da się uniknąć i jakim kosztem długości
  const idx = new Map(names.map((n, i) => [n, i]));
  const byId = new Map(graph.nodes.map(n => [n.id, n.properties.name]));
  const N = names.length;
  const flat = Array.from({ length: N }, (_, i) => Array.from({ length: N }, (_, j) => (i === j ? 0 : Infinity)));
  const all = Array.from({ length: N }, (_, i) => Array.from({ length: N }, (_, j) => (i === j ? 0 : Infinity)));
  for (const e of graph.edges) {
    if (e.type !== 'PATH') continue;
    const i = idx.get(byId.get(e.from)), j = idx.get(byId.get(e.to));
    all[i][j] = Math.min(all[i][j], edgeLength(e.properties));
    if (!(e.properties.preset === 'stairs' && e.properties.q > 0)) flat[i][j] = Math.min(flat[i][j], edgeLength(e.properties));
  }
  for (const D of [flat, all]) for (let k = 0; k < N; k++) for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) if (D[i][k] + D[k][j] < D[i][j]) D[i][j] = D[i][k] + D[k][j];
  const out = { pary: pairs.length, miedzyPoziomami: between.length, profile: {}, scenariusze: [] };
  for (const pname of Object.keys(PROFILES)) {
    const R = res[pname];
    const idxBetween = pairs.map((p, i) => (p[2] ? i : -1)).filter(i => i >= 0);
    const d = R.map((x, i) => x.totalDistance - base[i].totalDistance);
    const changedIdx = R.map((x, i) => (x.path.join('>') !== base[i].path.join('>') ? i : -1)).filter(i => i >= 0);
    const dc = changedIdx.map(i => d[i]);
    out.profile[pname] = {
      sredniaDlugosc: r(mean(R.map(x => x.totalDistance))),
      medianaDlugosc: r(pct(R.map(x => x.totalDistance), 0.5)),
      wydluzenieProcent: r(100 * (mean(R.map(x => x.totalDistance)) / mean(base.map(x => x.totalDistance)) - 1)),
      schodyProcent: r(100 * R.filter(hasStairs).length / R.length),
      schodyProcentMiedzyPoziomami: r(100 * idxBetween.filter(i => hasStairs(R[i])).length / idxBetween.length),
      winda_procentMiedzyPoziomami: r(100 * idxBetween.filter(i => hasLift(R[i])).length / idxBetween.length),
      trasyZeSchodami: R.filter(hasStairs).length,
      pary: (() => {
        // pary nieuporządkowane (a < b) o trasie ze schodami; wśród nich te, gdzie płaskie obejście istnieje
        let withStairs = 0, avoidable = 0, tol = 0, shortestStairsPairs = 0;
        pairs.forEach(([a, b], i) => {
          if (idx.get(a) >= idx.get(b) || !hasStairs(R[i])) return;
          withStairs++;
          if (flat[idx.get(a)][idx.get(b)] < Infinity) { avoidable++; tol = Math.max(tol, flat[idx.get(a)][idx.get(b)] / all[idx.get(a)][idx.get(b)]); }
        });
        // pary, w których najkrótsza trasa ma schody, a wybrana ich nie ma (tolerowane obejście = długość wybranej / najkrótszej)
        let detour = 0;
        pairs.forEach(([a, b], i) => {
          if (idx.get(a) >= idx.get(b)) return;
          const sh = base[i];
          if (hasStairs(sh) && !hasStairs(R[i])) { shortestStairsPairs++; detour = Math.max(detour, R[i].totalDistance / sh.totalDistance); }
        });
        return { zeSchodami: withStairs, zeSchodamiMimoObejscia: avoidable, najwiekszeObejscie: r(tol, 2), unikniete: shortestStairsPairs, tolerowaneObejscie: r(detour, 2) };
      })(),
      zmienione: changedIdx.length,
      zmienioneProcent: r(100 * changedIdx.length / R.length),
      wydluzenieZmienionych: dc.length ? {
        mediana: r(pct(dc, 0.5)), p90: r(pct(dc, 0.9)), max: r(Math.max(...dc)),
        powyzej50: dc.filter(x => x > 50).length, powyzej100: dc.filter(x => x > 100).length,
      } : null,
    };
  }
  for (const [a, b] of SCENARIOS) {
    const row = { a, b };
    for (const [pname, flags] of Object.entries(PROFILES)) {
      const x = await findPath(a, b, flags);
      row[pname] = { dl: r(x.totalDistance), koszt: r(x.totalCost, 2), schody: x.edges.filter(e => e.preset === 'stairs' && e.q > 0).length, windy: x.edges.filter(e => e.preset === 'elevator' && e.q > 0).length, trasa: x.path.join(' > ') };
    }
    out.scenariusze.push(row);
  }
  // U1: pary, w których schody nie są konieczne, a mimo to wybrane (zakres tolerowanego obejścia)
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  console.log('zapisano', OUT);
  process.exit(0); // sterownik bazy trzyma połączenie
})();
