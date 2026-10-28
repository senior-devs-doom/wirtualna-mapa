// poiSearch.js - czysta logika wyszukiwania miejsc (bez DOM), działa w przeglądarce
// i w Node (testy). Konstruktor Fuse jest wstrzykiwany, żeby moduł nie zależał
// od sposobu ładowania biblioteki.
//
// Format pola `description` węzła: jedno miejsce w linii, synonimy po " | ":
//   Łazienka Damska | toaleta damska | WC damskie
//   Sala 420-426
// Zakres liczb w nazwie ("Sala 420-426") jest rozwijany na osobne miejsca.

const MAX_RANGE_SPAN = 200; // zabezpieczenie przed np. "Rok 1990-2024" rozwijanym na 35 pozycji bez sensu / literówkami

// małe litery, bez znaków diakrytycznych ("Łazienka" == "lazienka"); ł/Ł nie rozkłada się w NFD, stąd osobny krok
export function normalizeText(s) {
  return String(s)
    .toLowerCase()
    .replace(/ł/g, 'l')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

const RANGE_RE = /^(.*?)(\d+)\s*[-–—]\s*(\d+)(.*)$/;

// "Sala 420-426" -> ["Sala 420", ..., "Sala 426"]; bez zakresu zwraca [s].
// Zakres malejący lub dłuższy niż MAX_RANGE_SPAN zostaje bez zmian.
// Wiele zakresów w jednej nazwie rozwijane jest rekurencyjnie (iloczyn).
export function expandRange(s) {
  const m = RANGE_RE.exec(s);
  if (!m) return [s];
  const [, prefix, aStr, bStr, suffix] = m;
  const a = Number(aStr), b = Number(bStr);
  if (b < a || b - a > MAX_RANGE_SPAN) return [s];
  const width = aStr.startsWith('0') ? aStr.length : 0; // zachowaj zera wiodące, np. 001-003
  const out = [];
  for (let n = a; n <= b; n++) {
    const num = width ? String(n).padStart(width, '0') : String(n);
    out.push(...expandRange(prefix + num + suffix));
  }
  return out;
}

// description -> [{label, aliases[]}], po rozwinięciu zakresów
export function parsePoiDescription(description) {
  if (!description) return [];
  const entries = [];
  for (const rawLine of String(description).split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    const [main, ...aliasParts] = line.split('|').map(p => p.trim()).filter(Boolean);
    if (!main) continue;
    const labels = expandRange(main);
    const aliasLists = aliasParts.map(expandRange);
    labels.forEach((label, i) => {
      // alias z zakresem tej samej długości co nazwa parujemy po indeksie
      // ("Sala 420-426 | pokój 420-426"), pozostałe przypisujemy w całości
      const aliases = [];
      aliasLists.forEach(list => {
        if (list.length === labels.length) aliases.push(list[i]);
        else aliases.push(...list);
      });
      entries.push({ label, aliases });
    });
  }
  return entries;
}

// węzły grafu -> płaska lista wpisów do przeszukania: nazwa każdego węzła
// oraz każde miejsce z jego opisu
export function buildEntries(nodes) {
  const entries = [];
  for (const node of nodes) {
    const name = node.properties && node.properties.name;
    if (!name) continue;
    entries.push({ label: name, aliases: [], nodeId: node.id, nodeName: name });
    for (const poi of parsePoiDescription(node.properties.description)) {
      entries.push({ label: poi.label, aliases: poi.aliases, nodeId: node.id, nodeName: name });
    }
  }
  // synonimy są wspólne dla wszystkich miejsc o tej samej nazwie: wystarczy
  // wpisać je raz (np. przy jednej łazience), a znajdą wszystkie takie miejsca
  const aliasesByLabel = new Map();
  for (const e of entries) {
    const key = normalizeText(e.label);
    if (!aliasesByLabel.has(key)) aliasesByLabel.set(key, new Map());
    for (const a of e.aliases) aliasesByLabel.get(key).set(normalizeText(a), a);
  }
  return entries.map(e => {
    const key = normalizeText(e.label);
    const shared = [...aliasesByLabel.get(key).entries()];
    return {
      ...e,
      norm: key,
      aliases: shared.map(([, original]) => original),
      aliasesNorm: shared.map(([norm]) => norm),
    };
  });
}

// Zwraca search(query, limit) -> [{label, nodes:[{id,name}], score}]
// Wyniki o tej samej (znormalizowanej) nazwie z różnych węzłów trafiają do
// jednej grupy - np. "Łazienka Damska" na trzech piętrach to jedna pozycja
// z trzema węzłami (podstawa przycisku "najbliższa").
export function createSearcher(nodes, FuseCtor, options = {}) {
  const entries = buildEntries(nodes);
  const fuse = new FuseCtor(entries, {
    keys: [{ name: 'norm', weight: 2 }, { name: 'aliasesNorm', weight: 1 }],
    includeScore: true,
    ignoreLocation: true,
    threshold: options.threshold ?? 0.3,
    minMatchCharLength: 2,
  });

  return function search(query, limit = 15) {
    const q = normalizeText(query || '');
    if (!q) return [];
    let hits = fuse.search(q);
    // 1) numery to nie literówki: "korytarz 3" nie ma znaczyć "korytarz 1", więc
    //    każda liczba z zapytania musi wystąpić w wyniku jako osobny token
    const nums = q.match(/\d+/g) || [];
    if (nums.length) {
      const hasAll = text => {
        const toks = new Set(text.match(/\d+/g) || []);
        return nums.every(n => toks.has(n));
      };
      hits = hits.filter(h => hasAll(h.item.norm) || h.item.aliasesNorm.some(hasAll));
    }
    // 2) jeśli coś zawiera zapytanie dosłownie, nie podsuwaj "podobnych"
    //    (wynik Fuse dla dokładnego trafienia nie jest dokładnie 0 - zależy od długości pola)
    const exactHit = h => h.item.norm.includes(q) || h.item.aliasesNorm.some(a => a.includes(q));
    if (hits.some(exactHit)) hits = hits.filter(exactHit);

    const groups = new Map();
    for (const { item, score } of hits) {
      const key = item.norm;
      let g = groups.get(key);
      if (!g) {
        g = { label: item.label, nodes: [], seen: new Set(), score };
        groups.set(key, g);
      }
      g.score = Math.min(g.score, score);
      if (!g.seen.has(item.nodeId)) {
        g.seen.add(item.nodeId);
        g.nodes.push({ id: item.nodeId, name: item.nodeName });
      }
    }
    return [...groups.values()]
      .sort((a, b) => a.score - b.score || a.label.length - b.label.length || a.label.localeCompare(b.label, 'pl'))
      .slice(0, limit)
      .map(({ label, nodes, score }) => ({ label, nodes, score }));
  };
}
