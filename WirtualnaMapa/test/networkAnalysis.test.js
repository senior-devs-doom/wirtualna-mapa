const test = require('node:test');
const assert = require('node:assert');
const na = require('../src/libs/networkAnalysis');

// Mały graf: A - B - C w linii (korytarz), C - D schodami, B - D windą (cykl B-C-D),
// oraz E podpięte tylko schodami do D.
const node = id => ({ id, properties: { name: String(id) } });
const edge = (a, b, L, preset) => [
  { type: 'PATH', from: a, to: b, properties: { L, preset } },
  { type: 'PATH', from: b, to: a, properties: { L, preset } },
];
const graph = {
  nodes: ['A', 'B', 'C', 'D', 'E'].map(node),
  edges: [
    ...edge('A', 'B', 10, 'normal'), ...edge('B', 'C', 10, 'normal'),
    ...edge('C', 'D', 4, 'stairs'), ...edge('B', 'D', 5, 'elevator'),
    ...edge('D', 'E', 3, 'stairs'),
  ],
};

test('buildUndirected łączy pary skierowane w jedno połączenie i wyklucza typy', () => {
  assert.strictEqual(na.buildUndirected(graph).edges.length, 5);
  assert.strictEqual(na.buildUndirected(graph, { excludePresets: ['stairs'] }).edges.length, 3);
});

test('składowe: bez schodów węzeł E jest odcięty', () => {
  const full = na.components(na.buildUndirected(graph));
  const flat = na.components(na.buildUndirected(graph, { excludePresets: ['stairs'] }));
  assert.strictEqual(full.count, 1);
  assert.strictEqual(flat.count, 2);
  assert.deepStrictEqual([...flat.sizes].sort(), [1, 4]);
});

test('mosty i punkty artykulacji', () => {
  const r = na.bridgesAndCutNodes(na.buildUndirected(graph));
  assert.deepStrictEqual(r.bridges.map(e => e.key).sort(), ['A|B', 'D|E']);
  assert.deepStrictEqual(r.cutNodes.sort(), ['B', 'D']);
});

test('statystyki odległości: średnica po długości i liczba krok', () => {
  const s = na.distanceStats(na.buildUndirected(graph));
  assert.strictEqual(s.diameterLength.d, 19);       // A -> C idzie przez B i D: 10 + 5 + 4 (a nie 10 + 10)
  assert.strictEqual(s.diameterHops.d, 3);
  assert.strictEqual(s.connectedPairs, 20);
});

test('centralność pośrednictwa: D leży na najwięcej najkrótszych dróg (C-B idzie przez D, bo 4 + 5 < 10)', () => {
  const b = na.betweenness(na.buildUndirected(graph));
  const top = [...b.node.entries()].sort((x, y) => y[1] - x[1])[0][0];
  assert.strictEqual(top, 'D');
  assert.strictEqual(b.node.get('A'), 0);
});

test('rozłączne drogi między zbiorami: dwa połączenia B-D (winda) i B-C-D (schody)', () => {
  const g = na.buildUndirected(graph);
  assert.strictEqual(na.edgeDisjointPaths(g, ['B'], ['D']), 2);
  assert.strictEqual(na.edgeDisjointPaths(na.buildUndirected(graph, { excludePresets: ['stairs'] }), ['B'], ['D']), 1);
  assert.strictEqual(na.edgeDisjointPaths(g, ['A'], ['E']), 1);
});

test('składnia przestrzenna: węzły centralne mają większą integrację niż końcówki', () => {
  const g = na.buildUndirected(graph);
  const ss = na.spaceSyntax(g);
  assert.ok(ss.get('B').integration > ss.get('A').integration);
  assert.ok(ss.get('B').MD < ss.get('E').MD);
});

test('klasteryzacja: trójkąt B-C-D daje dodatnią wartość', () => {
  assert.ok(na.clustering(na.buildUndirected(graph)) > 0);
});
