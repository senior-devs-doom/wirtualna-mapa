// bench_precompute.js - czas liczenia kosztów krawędzi dla jednego profilu (U1):
// wersja bez prekomputacji (pełny rachunek przy każdej krawędzi) i z podziałem na części
// zależne od profilu i od krawędzi (5.4 pracy). Użycie: GRAPH_JSON=data/graph_export.json node scripts/bench_precompute.js
require('dotenv').config({ quiet: true });
const RiskModel = require('../src/libs/riskModel');
const { fetchGraph } = require('../src/api/graph/graph.service');
const REP = 2000;

(async () => {
  const g = await fetchGraph();
  const edges = g.edges.filter(e => e.type === 'PATH').map(e => e.properties);
  const m = new RiskModel();
  const u = Array.from({ length: 7 }, (_, j) => (j === 0 ? RiskModel.U_ON : RiskModel.U_OFF));
  let sink = 0;
  const once = fn => { const t = process.hrtime.bigint(); for (let i = 0; i < REP; i++) fn(); return Number(process.hrtime.bigint() - t) / 1e6 / REP; };
  // mediana z 15 serii po REP powtórzeń (po rozgrzewce), żeby wynik nie zależał od chwilowego obciążenia
  const bench = fn => { for (let i = 0; i < 2000; i++) fn(); const a = Array.from({ length: 15 }, () => once(fn)).sort((x, y) => x - y); return a[7]; };

  const full = bench(() => { for (const e of edges) sink += m.computeCost(e, { u_vec: u }); });
  const pre = edges.map(e => m.prepareEdge(e));
  const prepared = bench(() => { const sv = m.prepareUser(u); for (const e of pre) sink += m.costPrepared(e, sv); });

  const n = edges.length;
  // operacje: iloczyny (9x7 przy s, s*h i s*b) i wartości funkcji phi (tylko dla niezerowych h_i, b_i)
  const nnz = pre.reduce((a, e) => a + e.h.filter(x => x > 0).length + e.b.filter(x => x > 0).length, 0);
  const multFull = n * 9 * 7 + 2 * nnz, multPre = 9 * 7 + 2 * nnz;
  console.log(JSON.stringify({
    krawedzie: n,
    bezPrekomputacji_ms: +full.toFixed(4), zPrekomputacja_ms: +prepared.toFixed(4), przyspieszenie: +(full / prepared).toFixed(1),
    spadekCzasu_procent: +(100 * (1 - prepared / full)).toFixed(1),
    operacje_bez: multFull, operacje_z: multPre, spadekOperacji_procent: +(100 * (1 - multPre / multFull)).toFixed(1),
    sink: sink > 0,
  }, null, 2));
  process.exit(0);
})();
