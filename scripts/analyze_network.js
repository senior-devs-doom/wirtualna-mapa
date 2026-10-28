// analyze_network.js - test obciążeniowy dostępności i spójności grafu budynku.
//
// Użycie (baza musi działać, .env jak dla aplikacji):
//   node scripts/analyze_network.js [plik_wyjściowy.json]
//
// Zamiast bazy można użyć pliku: GRAPH_JSON=data/graph_export.json node scripts/analyze_network.js
// Nic nie zapisuje w bazie ani w plikach danych; wynik trafia tylko do wskazanego pliku JSON.
require('dotenv').config({ quiet: true });
const fs = require('fs');
const RiskModel = require('../src/libs/riskModel');
const { fetchGraph } = require('../src/api/graph/graph.service');
const { findPath } = require('../src/api/path/path.service');
const na = require('../src/libs/networkAnalysis');

const USERS = ['U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7'];
const PROFILES = {
  U1: { U1: true },
  U3: { U3: true },
  U5: { U5: true },
  wszystkie: Object.fromEntries(USERS.map(u => [u, true])),
};
const OUT = process.argv[2] || 'network_analysis.json';

const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
const sorted = a => [...a].sort((x, y) => x - y);
const pct = (a, p) => { const s = sorted(a); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
const r = (x, d = 2) => (x === null || x === undefined ? null : +x.toFixed(d));

(async () => {
  const graph = await fetchGraph();
  const byId = new Map(graph.nodes.map(n => [n.id, n]));
  const nameOf = id => byId.get(id).properties.name;
  const names = [...graph.nodes].sort((p, q) => p.properties.id - q.properties.id).map(n => n.properties.name); // kolejność wg id z pliku grafu, żeby orientacja par a<b nie zależała od kolejności zwracanej przez bazę
  const model = new RiskModel();
  const out = {};

  // ---------- A. trasy: różnice między profilami ----------
  const edgeProps = new Map();       // "od|do" -> parametry kosztu (L, q, d, h, b)
  for (const e of graph.edges) {
    if (e.type !== 'PATH') continue;
    edgeProps.set(`${nameOf(e.from)}|${nameOf(e.to)}`, model.prepareEdge(e.properties));
  }
  const uvec = flags => USERS.map(c => (flags[c] ? RiskModel.U_ON : RiskModel.U_OFF));
  const costOfRoute = (pathNames, flags) => {
    const u = uvec(flags);
    const sv = model.prepareUser(u);
    let c = 0;
    for (let i = 0; i + 1 < pathNames.length; i++) {
      const p = edgeProps.get(`${pathNames[i]}|${pathNames[i + 1]}`);
      c += model.costPrepared(p, sv);
    }
    return c;
  };
  const idByName = new Map(graph.nodes.map(n => [n.properties.name, n.id]));
  const pos = n => byId.get(idByName.get(n)).properties;
  const eucl = (a, b) => {
    const A = pos(a), B = pos(b);
    return Math.hypot(A.x - B.x, A.y - B.y, A.z - B.z);
  };

  const base = new Map();            // "a|b" -> wynik profilu bez ograniczeń
  for (const a of names) for (const b of names) {
    if (a === b) continue;
    base.set(`${a}|${b}`, await findPath(a, b, {}));
  }

  // zdrowa osoba: najdłuższe trasy i krętość
  const healthy = [];
  for (const a of names) for (const b of names) {
    if (a >= b) continue;                              // para nieuporządkowana (symetria)
    const x = base.get(`${a}|${b}`);
    healthy.push({ a, b, d: x.totalDistance, euclid: eucl(a, b), hops: x.path.length - 1 });
  }
  out.zdrowy = {
    pary: healthy.length,
    najdluzsze: healthy.sort((p, q) => q.d - p.d).slice(0, 10).map(p => ({ ...p, d: r(p.d, 1), euclid: r(p.euclid, 1) })),
    krecosc: healthy.filter(p => p.euclid >= 10).map(p => ({ ...p, c: p.d / p.euclid }))
      .sort((p, q) => q.c - p.c).slice(0, 10).map(p => ({ a: p.a, b: p.b, d: r(p.d, 1), euclid: r(p.euclid, 1), c: r(p.c, 2) })),
    krecoscSrednia: r(mean(healthy.filter(p => p.euclid >= 10).map(p => p.d / p.euclid)), 3),
    krecoscMediana: r(pct(healthy.filter(p => p.euclid >= 10).map(p => p.d / p.euclid), 0.5), 3),
  };

  out.profile = {};
  for (const [pname, flags] of Object.entries(PROFILES)) {
    const rows = [];
    for (const a of names) for (const b of names) {
      if (a === b) continue;
      const r0 = base.get(`${a}|${b}`);
      const rp = await findPath(a, b, flags);
      const cP_r0 = costOfRoute(r0.path, flags);
      rows.push({
        a, b, d0: r0.totalDistance, dP: rp.totalDistance,
        c0: r0.totalCost, cP: rp.totalCost, cP_r0,
        same: r0.path.join('>') === rp.path.join('>'), p0: r0.path, pP: rp.path,
        st0: r0.edges.filter(e => e.preset === 'stairs').length, stP: rp.edges.filter(e => e.preset === 'stairs').length,
        elP: rp.edges.filter(e => e.preset === 'elevator').length,
      });
    }
    const dd = x => x.dP - x.d0;
    const fmt = x => ({ a: x.a, b: x.b, d0: r(x.d0, 1), dP: r(x.dP, 1), dd: r(dd(x), 1), ratio: r(x.dP / x.d0, 2),
      c0: r(x.c0, 2), cP: r(x.cP, 2), costRatio: r(x.cP / x.c0, 2), regret: r(x.cP_r0 - x.cP, 2), regretRatio: r(x.cP_r0 / x.cP, 2), stP: x.stP });
    const isStairNode = n => /Schody|Klatka Schodowa/.test(n);
    const poza = x => !isStairNode(x.a) && !isStairNode(x.b);
    const unordered = arr => arr.filter(x => x.a < x.b);        // trasy są symetryczne: liczymy każdą parę raz
    const top = (arr, key, n = 10) => unordered(arr).sort((p, q) => key(q) - key(p)).slice(0, n).map(fmt);
    const withPaths = (arr, key, n = 3) => unordered(arr).sort((p, q) => key(q) - key(p)).slice(0, n)
      .map(x => ({ ...fmt(x), trasaBazowa: x.p0.join(' > '), trasaProfilu: x.pP.join(' > ') }));
    const changed = rows.filter(x => !x.same);
    const nodeOrigin = new Map(), nodeDest = new Map();
    for (const x of rows) {
      (nodeOrigin.get(x.a) || nodeOrigin.set(x.a, []).get(x.a)).push(dd(x));
      (nodeDest.get(x.b) || nodeDest.set(x.b, []).get(x.b)).push(dd(x));
    }
    const worstNodes = m => [...m.entries()].map(([n, v]) => ({ n, mean: mean(v), max: Math.max(...v) }))
      .sort((p, q) => q.mean - p.mean).slice(0, 8).map(o => ({ n: o.n, mean: r(o.mean, 1), max: r(o.max, 1) }));
    out.profile[pname] = {
      pary: rows.length,
      zmienione: changed.length, zmienionePct: r(changed.length / rows.length * 100, 1),
      sredniaDlugosc0: r(mean(rows.map(x => x.d0)), 1), sredniaDlugoscP: r(mean(rows.map(x => x.dP)), 1),
      wydluzenie: {
        srednia_wszystkie: r(mean(rows.map(dd)), 1), srednia_zmienione: r(mean(changed.map(dd)), 1),
        mediana_zmienione: r(pct(changed.map(dd), 0.5), 1), p90_zmienione: r(pct(changed.map(dd), 0.9), 1), max: r(Math.max(...rows.map(dd)), 1),
        powyzej50: rows.filter(x => dd(x) > 50).length, powyzej100: rows.filter(x => dd(x) > 100).length,
      },
      kosztRatioPoza: { mediana: r(pct(rows.filter(poza).map(x => x.cP / x.c0), 0.5), 2), p90: r(pct(rows.filter(poza).map(x => x.cP / x.c0), 0.9), 2), max: r(Math.max(...rows.filter(poza).map(x => x.cP / x.c0)), 2) },
      kosztRatio: { mediana: r(pct(rows.map(x => x.cP / x.c0), 0.5), 2), srednia: r(mean(rows.map(x => x.cP / x.c0)), 2), p90: r(pct(rows.map(x => x.cP / x.c0), 0.9), 2), max: r(Math.max(...rows.map(x => x.cP / x.c0)), 2) },
      zalSchodyIgnorujac: { // ile kosztuje użytkownika podążanie trasą "zdrowego"
        mediana_regret: r(pct(rows.map(x => x.cP_r0 - x.cP), 0.5), 2),
        trasy_ze_schodami_u_zdrowego: rows.filter(x => x.st0 > 0).length,
        z_ktorych_schody_unika: rows.filter(x => x.st0 > 0 && x.stP === 0).length,
      },
      najgorszeDystans: top(rows, dd),
      najgorszeDystansTrasy: withPaths(rows, dd),
      najgorszeKosztRatioPoza: top(rows.filter(poza), x => x.cP / x.c0),
      najgorszeRegretPoza: top(rows.filter(poza), x => x.cP_r0 - x.cP),
      najgorszeRegretRatioPoza: top(rows.filter(x => poza(x) && x.cP_r0 - x.cP > 0.01), x => x.cP_r0 / x.cP),
      najgorszeWzgledne: top(rows.filter(x => x.d0 >= 20), x => x.dP / x.d0),
      najgorszeKosztRatio: top(rows, x => x.cP / x.c0),
      najgorszeRegret: top(rows, x => x.cP_r0 - x.cP),
      najgorszeRegretRatio: top(rows.filter(x => x.cP_r0 - x.cP > 0.01), x => x.cP_r0 / x.cP),
      najgorszePoczatki: worstNodes(nodeOrigin), najgorszeCele: worstNodes(nodeDest),
    };
    if (pname === 'U1') {
      const hist = {};
      for (const x of changed) { const bin = Math.floor(dd(x) / 25) * 25; hist[bin] = (hist[bin] || 0) + 1; }
      out.profile[pname].histogram25m = hist;
    }
    process.stderr.write(`profil ${pname} gotowy\n`);
  }

  // ---------- B. metryki sieci ----------
  const variants = {
    pelny: {},
    bez_schodow: { excludePresets: ['stairs'] },
    bez_wind: { excludePresets: ['elevator'] },
  };
  out.siec = {};
  const full = na.buildUndirected(graph);
  const eff = (g, ideal) => {
    let sum = 0;
    for (const src of g.ids) for (const [t, d] of na.dijkstraLength(g, src).dist) if (t !== src) sum += 1 / d;
    return sum / ideal;
  };
  let idealSum = 0;
  for (const a of graph.nodes) for (const b of graph.nodes) if (a.id !== b.id) idealSum += 1 / Math.hypot(a.properties.x - b.properties.x, a.properties.y - b.properties.y, a.properties.z - b.properties.z);
  for (const [vn, opt] of Object.entries(variants)) {
    const gAll = na.buildUndirected(graph, opt);
    const cc = na.components(gAll);
    const mainIdx = cc.sizes.indexOf(Math.max(...cc.sizes));
    const outside = gAll.ids.filter(id => cc.comp.get(id) !== mainIdx);
    const g = na.buildUndirected(graph, { ...opt, excludeNodes: outside });   // największa składowa
    const s = na.summary(g);
    const sAll = na.summary(gAll);
    const bt = na.betweenness(g);
    const topN = [...bt.node.entries()].sort((p, q) => q[1] - p[1]).slice(0, 6).map(([id, v]) => ({ n: nameOf(id), v: r(v, 3) }));
    const topE = [...bt.edge.entries()].sort((p, q) => q[1] - p[1]).slice(0, 6).map(([k, v]) => {
      const e = g.edges.find(z => z.key === k);
      return { e: `${nameOf(e.a)} - ${nameOf(e.b)}`, preset: e.preset, v: r(v, 3) };
    });
    const bc = na.bridgesAndCutNodes(g);
    const ss = na.spaceSyntax(g);
    const ssv = [...ss.entries()].filter(([, v]) => v).map(([id, v]) => ({ n: nameOf(id), ...v }));
    const nm = x => (x ? { ...x, from: nameOf(x.from), to: nameOf(x.to), d: r(x.d, 1) } : x);
    out.siec[vn] = {
      wezlowWszystkich: gAll.ids.length, wezlowIzolowanych: outside.length, skladowe: cc.count,
      udzialParPolaczonych: r(sAll.connectedPairsShare, 4),
      nodes: s.nodes, edges: s.edges, density: r(s.density, 4), meanDegree: r(s.meanDegree, 2), cyclomatic: s.cyclomatic,
      clustering: r(s.clustering, 3), meanLength: r(s.meanLength, 1), meanHops: r(s.meanHops, 2),
      diameterLength: nm(s.diameterLength), diameterHops: nm(s.diameterHops),
      efektywnoscZnormalizowana: r(eff(gAll, idealSum), 4),
      betweennessNodes: topN, betweennessEdges: topE,
      bridges: bc.bridges.length, bridgesList: bc.bridges.map(e => `${nameOf(e.a)} - ${nameOf(e.b)} [${e.preset}]`),
      bridgesShare: r(bc.bridges.length / s.edges, 3), cutNodes: bc.cutNodes.length, cutNodesList: bc.cutNodes.map(nameOf),
      spaceSyntax: {
        n: ssv.length, meanDepth: r(mean(ssv.map(v => v.MD)), 2), meanIntegration: r(mean(ssv.map(v => v.integration)), 3),
        top: [...ssv].sort((p, q) => q.integration - p.integration).slice(0, 5).map(v => ({ n: v.n, i: r(v.integration, 3), md: r(v.MD, 2) })),
        bottom: [...ssv].sort((p, q) => p.integration - q.integration).slice(0, 5).map(v => ({ n: v.n, i: r(v.integration, 3), md: r(v.MD, 2) })),
      },
    };
  }

  // poziomy użytkowe (dokładne wysokości kondygnacji)
  const LEVELS = [['-1', -3.5], ['parter', 0], ['2', 7], ['3', 10.5], ['4', 14]];
  const idsAt = z => graph.nodes.filter(n => Math.abs(n.properties.z - z) < 0.01).map(n => n.id);
  out.pionowa = {};
  for (let i = 0; i + 1 < LEVELS.length; i++) {
    const key = `${LEVELS[i][0]}↔${LEVELS[i + 1][0]}`;
    out.pionowa[key] = {};
    for (const [vn, opt] of Object.entries(variants)) {
      out.pionowa[key][vn] = na.edgeDisjointPaths(na.buildUndirected(graph, opt), idsAt(LEVELS[i][1]), idsAt(LEVELS[i + 1][1]));
    }
  }

  // osiągalność poziomów z wejścia głównego
  const entrance = idByName.get('Zewnątrz Południe');
  const reachInfo = g => {
    const h = na.bfsHops(g, entrance);
    const per = {};
    for (const [lv, z] of LEVELS) {
      const ids = idsAt(z);
      per[lv] = { wezlow: ids.length, osiagalnych: ids.filter(id => h.has(id)).length };
    }
    return { osiagalne: h.size, z: g.ids.length, poziomy: per };
  };
  out.osiagalnosc = { pelny: reachInfo(full), bez_schodow: reachInfo(na.buildUndirected(graph, { excludePresets: ['stairs'] })) };

  // cena dostępności bezschodowej: geometryczna (najkrótsza po L), bez modelu kosztu
  const gFull = full, gFlat = na.buildUndirected(graph, { excludePresets: ['stairs'] });
  const ratios = [], extra = [];
  let disconnected = 0;
  for (const s of gFull.ids) {
    const dF = na.dijkstraLength(gFull, s).dist, dN = na.dijkstraLength(gFlat, s).dist;
    for (const [t, d] of dF) {
      if (t === s) continue;
      if (!dN.has(s) || !dN.has(t)) { disconnected++; continue; }
      ratios.push(dN.get(t) / d); extra.push(dN.get(t) - d);
    }
  }
  out.cenaDostepnosci = {
    pary: gFull.ids.length * (gFull.ids.length - 1), nieosiagalneBezSchodow: disconnected,
    wskaznikDostepnosciBezSchodowej: r(1 - disconnected / (gFull.ids.length * (gFull.ids.length - 1)), 4),
    sredniaKrotnosc: r(mean(ratios), 3), medianaKrotnosc: r(pct(ratios, 0.5), 3), p90Krotnosc: r(pct(ratios, 0.9), 3), maxKrotnosc: r(Math.max(...ratios), 2),
    sredniDodatek: r(mean(extra), 1), medianaDodatek: r(pct(extra, 0.5), 1), p90Dodatek: r(pct(extra, 0.9), 1), maxDodatek: r(Math.max(...extra), 1),
    dodatek_gt50: extra.filter(x => x > 50).length, dodatek_gt100: extra.filter(x => x > 100).length, par_polaczonych: extra.length,
  };

  // odporność: usunięcie pojedynczego węzła / awaria całej windy lub klatki
  const share = (g, n0) => na.distanceStats(g).connectedPairs / (n0 * (n0 - 1));
  const resilience = (opt0, label) => {
    const g0 = na.buildUndirected(graph, opt0);
    const n0 = g0.ids.length;
    const base = na.distanceStats(g0);
    const rows = [];
    for (const id of g0.ids) {
      const g = na.buildUndirected(graph, { ...opt0, excludeNodes: [id] });
      const s = na.distanceStats(g);
      const cs = na.components(g0);
      const sizeV = cs.sizes[cs.comp.get(id)];
      rows.push({ n: nameOf(id), lost: base.connectedPairs - s.connectedPairs - 2 * (sizeV - 1), meanLength: s.meanLength, comps: na.components(g).count - cs.count });
    }
    rows.sort((p, q) => q.lost - p.lost);
    return { label, pary0: base.connectedPairs, srednia0: r(base.meanLength, 1),
      najgorsze: rows.slice(0, 6).map(x => ({ n: x.n, utracone_pary: x.lost, nowe_skladowe: x.comps, srednia: r(x.meanLength, 1) })),
      wezlyKrytyczne: rows.filter(x => x.lost > 0).length };
  };
  out.odpornosc = { pelny: resilience({}, 'pełny'), bez_schodow: resilience({ excludePresets: ['stairs'] }, 'bez schodów') };

  const groupIds = prefix => graph.nodes.filter(n => n.properties.name.startsWith(prefix)).map(n => n.id);
  const outage = (label, prefixes, opt0) => {
    const ex = prefixes.flatMap(groupIds);
    const g = na.buildUndirected(graph, { ...opt0, excludeNodes: ex });
    const g0 = na.buildUndirected(graph, opt0);
    const h = na.bfsHops(g, entrance);
    const h0 = na.bfsHops(g0, entrance);
    const per = {};
    for (const [lv, z] of LEVELS) {
      const ids = idsAt(z).filter(id => !ex.includes(id));
      per[lv] = ids.filter(id => h.has(id)).length + '/' + idsAt(z).filter(id => h0.has(id)).length;
    }
    const s = na.distanceStats(g), s0 = na.distanceStats(g0);
    return { label, wezlowUsunietych: ex.length, osiagalneZWejscia: h.size, osiagalneBazowo: h0.size, poziomy: per,
      sredniaDlugosc: r(s.meanLength, 1), sredniaDlugosc0: r(s0.meanLength, 1), skladowe: na.components(g).count };
  };
  out.awarie = {
    bez_schodow: [
      outage('winda centralna', ['Winda Centralna'], { excludePresets: ['stairs'] }),
      outage('winda południowa', ['Winda Południowa'], { excludePresets: ['stairs'] }),
      outage('obie windy', ['Winda Centralna', 'Winda Południowa'], { excludePresets: ['stairs'] }),
    ],
    pelny: [
      outage('schody wschodnie', ['Schody Wschodnie'], {}),
      outage('schody centralne', ['Schody Centralne'], {}),
      outage('schody zachodnie', ['Schody Zachodnie'], {}),
      outage('winda centralna', ['Winda Centralna'], {}),
      outage('winda południowa', ['Winda Południowa'], {}),
    ],
  };

  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  process.stderr.write(`zapisano ${OUT}\n`);
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
