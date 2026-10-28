const test = require('node:test');
const assert = require('node:assert');
const Fuse = require('fuse.js');

let mod;
test.before(async () => { mod = await import('../public/js/poiSearch.mjs'); });

test('normalizeText usuwa polskie znaki i wielkość liter', () => {
  assert.strictEqual(mod.normalizeText('Łazienka Damska'), 'lazienka damska');
  assert.strictEqual(mod.normalizeText('  Piętro   4 Żółć '), 'pietro 4 zolc');
});

test('expandRange rozwija zakres na osobne pozycje', () => {
  assert.deepStrictEqual(mod.expandRange('Sala 420-426'),
    ['Sala 420', 'Sala 421', 'Sala 422', 'Sala 423', 'Sala 424', 'Sala 425', 'Sala 426']);
  assert.deepStrictEqual(mod.expandRange('Sala 420 - 422'), ['Sala 420', 'Sala 421', 'Sala 422']);
  assert.deepStrictEqual(mod.expandRange('Sale 410-411 (zachód)'), ['Sale 410 (zachód)', 'Sale 411 (zachód)']);
});

test('expandRange: bez zakresu, malejący i zbyt długi zakres zostają bez zmian', () => {
  assert.deepStrictEqual(mod.expandRange('Biblioteka'), ['Biblioteka']);
  assert.deepStrictEqual(mod.expandRange('Sala 426-420'), ['Sala 426-420']);
  assert.deepStrictEqual(mod.expandRange('Rok 1000-2000'), ['Rok 1000-2000']);
  assert.deepStrictEqual(mod.expandRange('Wejście B-2'), ['Wejście B-2']);
});

test('expandRange zachowuje zera wiodące i rozwija wiele zakresów', () => {
  assert.deepStrictEqual(mod.expandRange('Szafa 001-003'), ['Szafa 001', 'Szafa 002', 'Szafa 003']);
  assert.deepStrictEqual(mod.expandRange('Sala 1-2 / 5-6').length, 4);
});

test('parsePoiDescription: przykładowy opis z zakresem i synonimami', () => {
  const d = [
    'Biblioteka',
    'Siłownia',
    'Łazienka Damska | toaleta damska | WC damskie',
    'Sala 412',
    'Sala 410',
    'Łazienka dla osób ze specjalnymi potrzebami | toaleta dla niepełnosprawnych',
    '',
    'Sala 420-426',
  ].join('\n');
  const poi = mod.parsePoiDescription(d);
  assert.strictEqual(poi.length, 6 + 7);
  assert.deepStrictEqual(poi[2], { label: 'Łazienka Damska', aliases: ['toaleta damska', 'WC damskie'] });
  assert.deepStrictEqual(poi.slice(-7).map(p => p.label),
    ['Sala 420', 'Sala 421', 'Sala 422', 'Sala 423', 'Sala 424', 'Sala 425', 'Sala 426']);
  assert.deepStrictEqual(mod.parsePoiDescription(''), []);
  assert.deepStrictEqual(mod.parsePoiDescription(undefined), []);
});

test('alias z zakresem tej samej długości jest parowany po indeksie', () => {
  const poi = mod.parsePoiDescription('Sala 420-422 | pokój 420-422');
  assert.deepStrictEqual(poi.map(p => p.aliases), [['pokój 420'], ['pokój 421'], ['pokój 422']]);
});

function nodes() {
  const n = (id, name, description = '') => ({ id, properties: { name, description } });
  return [
    n(1, 'Parter Korytarz', 'Biblioteka\nŁazienka Damska | toaleta damska\nŁazienka Męska'),
    n(2, 'Poziom 2 Korytarz', 'Łazienka Damska | toaleta damska\nSiłownia'),
    n(3, 'Poziom 4 Korytarz 2', 'Łazienka Damska\nSala 410\nSala 412\nSala 420-426\nŁazienka dla osób ze specjalnymi potrzebami'),
    n(4, 'Winda11'),
  ];
}

test('wyszukiwanie: ta sama łazienka na trzech piętrach to jedna grupa z trzema węzłami', () => {
  const search = mod.createSearcher(nodes(), Fuse);
  const r = search('lazienka damska');
  assert.strictEqual(r[0].label, 'Łazienka Damska');
  assert.deepStrictEqual(r[0].nodes.map(x => x.id).sort(), [1, 2, 3]);
});

test('wyszukiwanie: pojedyncza sala z rozwiniętego zakresu', () => {
  const search = mod.createSearcher(nodes(), Fuse);
  const r = search('sala 423');
  assert.strictEqual(r[0].label, 'Sala 423');
  assert.deepStrictEqual(r[0].nodes, [{ id: 3, name: 'Poziom 4 Korytarz 2' }]);
});

test('wyszukiwanie: dokładne trafienie nie podsuwa podobnych numerów', () => {
  const search = mod.createSearcher(nodes(), Fuse);
  const r = search('sala 412');
  assert.deepStrictEqual(r.map(x => x.label), ['Sala 412']);
});

test('wyszukiwanie: literówka i synonim', () => {
  const search = mod.createSearcher(nodes(), Fuse);
  assert.strictEqual(search('bibloteka')[0].label, 'Biblioteka');
  const alias = search('toaleta damska');
  assert.strictEqual(alias[0].label, 'Łazienka Damska');
  assert.strictEqual(alias[0].nodes.length, 3);
});

test('wyszukiwanie: nazwa węzła też jest przeszukiwana, puste zapytanie nic nie zwraca', () => {
  const search = mod.createSearcher(nodes(), Fuse);
  assert.strictEqual(search('winda11')[0].label, 'Winda11');
  assert.deepStrictEqual(search(''), []);
  assert.deepStrictEqual(search('   '), []);
});
