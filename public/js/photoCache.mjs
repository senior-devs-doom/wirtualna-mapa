// photoCache.mjs - pobieranie, przechowywanie i prefetch zdjęć 360 po stronie klienta.
//
// - get(): pobranie zdjęcia, które użytkownik właśnie wybrał (priorytet absolutny):
//   wstrzymuje start nowych pobierań w tle, a trwające w tle (jeszcze mało
//   zaawansowane) przerywa i odkłada z powrotem do kolejki, żeby wybrane zdjęcie
//   dostało całe łącze.
// - prefetch(order): kolejka pobierań w tle w podanej kolejności (np. od
//   najbliższych węzłów), maksymalnie `maxBackground` równolegle; kolejne
//   wywołanie zastępuje kolejność (re-priorytetyzacja po każdej nawigacji).
// - Trwały cache w Cache Storage pod kluczem CID (CID jest niezmienny, więc nie
//   potrzeba unieważniania). Zdjęcia bez CID (lokalny zapas) trzymane tylko w pamięci.
// - Źródła po kolei: bramy IPFS, a na końcu adres lokalny (localUrl).
//
// fetch/caches są wstrzykiwane, żeby moduł dało się testować w Node.

const ABORT_BELOW_PROGRESS = 0.7; // trwające pobieranie w tle przerywamy, jeśli jest poniżej tej części
const MIN_VALID_BYTES = 1000;

export class PhotoCache {
  constructor({
    gateways = [],
    localUrl = () => null,
    cacheName = 'wm-photos-v1',
    maxBackground = 3,
    fetchImpl = (...a) => globalThis.fetch(...a),
    cachesImpl = globalThis.caches,
    onChange = () => {},
    now = () => performance.now(),
  } = {}) {
    this.gateways = gateways;
    this.localUrl = localUrl;
    this.cacheName = cacheName;
    this.maxBackground = maxBackground;
    this.fetchImpl = fetchImpl;
    this.cachesImpl = cachesImpl;
    this.onChange = onChange;
    this.now = now;

    this.items = new Map();       // id -> item
    this.queue = [];              // id-y czekające na pobranie w tle, w kolejności priorytetu
    this.foreground = 0;          // ile pobrań na żądanie użytkownika trwa
    this.stored = new Set();      // CID-y obecne w Cache Storage (bez wczytywania blobów)
    this.log = [];                // statystyki pobrań (do pomiarów i pracy)
  }

  setGateways(list) { this.gateways = list; }

  register(nodes) {
    for (const n of nodes) {
      const name = n.properties && n.properties.name;
      if (!name) continue;
      const cid = n.properties.imageCid || '';
      this.items.set(n.id, {
        id: n.id, name, cid, key: cid || `local:${name}`,
        status: 'idle',          // idle | loading | ready | error
        kind: null,              // 'foreground' | 'background'
        promise: null, controller: null, blobUrl: null,
        loaded: 0, total: 0, listeners: new Set(),
      });
    }
  }

  async init() {
    if (!this.cachesImpl) return;
    try {
      const cache = await this.cachesImpl.open(this.cacheName);
      const known = new Set([...this.items.values()].map(i => i.cid).filter(Boolean));
      for (const req of await cache.keys()) {
        const cid = req.url.split('/').pop();
        if (known.has(cid)) this.stored.add(cid);
        else await cache.delete(req); // zdjęcie nieistniejące już w grafie
      }
    } catch { /* brak/odmowa Cache Storage - działamy bez trwałego cache */ }
    this.onChange(this.stats());
  }

  isReady(id) { const i = this.items.get(id); return !!i && i.status === 'ready'; }

  // czy zdjęcie da się dostać bez sieci (w pamięci albo w Cache Storage)
  isAvailableOffline(id) {
    const i = this.items.get(id);
    return !!i && (i.status === 'ready' || (i.cid && this.stored.has(i.cid)));
  }

  stats() {
    let ready = 0;
    for (const i of this.items.values()) if (i.status === 'ready' || (i.cid && this.stored.has(i.cid))) ready++;
    return { total: this.items.size, available: ready, queued: this.queue.length, foreground: this.foreground };
  }

  // Pobranie na żądanie użytkownika. Zwraca {url, fromCache, source, ms, bytes}.
  async get(id, { onProgress } = {}) {
    const item = this.items.get(id);
    if (!item) throw new Error(`Nieznany węzeł: ${id}`);
    if (item.status === 'ready') return this._result(item, true, 'memory', 0);

    if (onProgress) {
      item.listeners.add(onProgress);
      if (item.total) onProgress(item.loaded, item.total);
    }
    this.foreground++;
    this._pauseBackground(item);
    try {
      for (let attempt = 0; ; attempt++) {
        if (!item.promise) this._start(item, 'foreground');
        else item.kind = 'foreground'; // już pobierane w tle - awansuje
        try {
          return await item.promise;
        } catch (err) {
          // zdjęcie, które właśnie przerwaliśmy w tle, a użytkownik zaraz je wybrał
          if (err && err.name === 'AbortError' && item.status === 'idle' && attempt < 3) {
            this.queue = this.queue.filter(q => q !== item.id);
            continue;
          }
          throw err;
        }
      }
    } finally {
      this.foreground--;
      if (onProgress) item.listeners.delete(onProgress);
      this._pump();
    }
  }

  // Kolejka pobierań w tle: orderedIds = id-y węzłów od najważniejszego.
  prefetch(orderedIds) {
    this.queue = orderedIds.filter(id => {
      const i = this.items.get(id);
      return i && i.status !== 'ready' && !i.promise;
    });
    this._pump();
  }

  _pump() {
    if (this.foreground > 0) return;
    let active = [...this.items.values()].filter(i => i.kind === 'background' && i.status === 'loading').length;
    while (active < this.maxBackground && this.queue.length) {
      const item = this.items.get(this.queue.shift());
      if (!item || item.promise || item.status === 'ready') continue;
      this._start(item, 'background');
      active++;
    }
  }

  _pauseBackground(except) {
    for (const i of this.items.values()) {
      if (i === except || i.kind !== 'background' || i.status !== 'loading') continue;
      const progress = i.total ? i.loaded / i.total : 0;
      if (progress < ABORT_BELOW_PROGRESS && i.controller) {
        i.aborted = true;
        i.controller.abort();
      }
    }
  }

  _start(item, kind) {
    item.kind = kind;
    item.status = 'loading';
    item.aborted = false;
    item.loaded = 0;
    item.total = 0;
    item.controller = new AbortController();
    const t0 = this.now();
    item.promise = this._load(item, t0).then(
      result => {
        item.status = 'ready';
        item.promise = null;
        item.controller = null;
        this.onChange(this.stats());
        this._pump();
        return result;
      },
      err => {
        item.promise = null;
        item.controller = null;
        if (item.aborted) { // przerwane na rzecz zdjęcia na żądanie - wraca na początek kolejki
          item.status = 'idle';
          item.aborted = false;
          this.queue.unshift(item.id);
        } else {
          item.status = 'error';
        }
        this.onChange(this.stats());
        throw err;
      },
    );
    // pobranie w tle nikogo nie czeka na wynik - nie zostawiaj nieobsłużonego odrzucenia
    if (kind === 'background') item.promise.catch(() => {});
    return item.promise;
  }

  async _load(item, t0) {
    // 1. trwały cache
    if (item.cid && this.cachesImpl) {
      try {
        const cache = await this.cachesImpl.open(this.cacheName);
        const hit = await cache.match(this._storageKey(item));
        if (hit) {
          const blob = await hit.blob();
          if (blob.size >= MIN_VALID_BYTES) return this._finish(item, blob, true, 'cache-storage', t0);
        }
      } catch { /* przejdź do sieci */ }
    }
    // 2. sieć: bramy po kolei, na końcu lokalnie
    const sources = [];
    if (item.cid) this.gateways.forEach(g => sources.push({ url: g + item.cid, label: new URL(g).host }));
    const local = this.localUrl(item);
    if (local) sources.push({ url: local, label: 'local' });
    let lastErr = new Error(`Brak źródeł dla ${item.name}`);
    for (const src of sources) {
      try {
        const blob = await this._download(item, src.url);
        if (item.cid && this.cachesImpl && src.label !== 'local') {
          try { await (await this.cachesImpl.open(this.cacheName)).put(this._storageKey(item), new Response(blob, { headers: { 'Content-Type': 'image/jpeg' } })); this.stored.add(item.cid); } catch { /* cache pełny / niedostępny */ }
        }
        return this._finish(item, blob, false, src.label, t0);
      } catch (err) {
        if (item.aborted) throw err;
        lastErr = err;
      }
    }
    throw lastErr;
  }

  _storageKey(item) { return `https://photo-cache.invalid/${item.cid}`; }

  async _download(item, url) {
    const res = await this.fetchImpl(url, { signal: item.controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status} z ${url}`);
    const total = Number(res.headers.get('Content-Length')) || 0;
    item.total = total;
    const chunks = [];
    let loaded = 0;
    if (res.body && res.body.getReader) {
      const reader = res.body.getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        loaded += value.length;
        item.loaded = loaded;
        item.listeners.forEach(fn => fn(loaded, total));
      }
    } else {
      chunks.push(new Uint8Array(await res.arrayBuffer()));
      loaded = chunks[0].length;
    }
    const blob = new Blob(chunks, { type: res.headers.get('Content-Type') || 'image/jpeg' });
    if (blob.size < MIN_VALID_BYTES || /text\/html/.test(blob.type)) throw new Error(`Nieprawidłowa odpowiedź z ${url}`);
    return blob;
  }

  _finish(item, blob, fromCache, source, t0) {
    item.blobUrl = URL.createObjectURL(blob);
    const ms = this.now() - t0;
    this.log.push({ id: item.id, name: item.name, kind: item.kind, source, fromCache, bytes: blob.size, ms: Math.round(ms) });
    return this._result(item, fromCache, source, ms, blob.size);
  }

  _result(item, fromCache, source, ms, bytes) {
    return { url: item.blobUrl, fromCache, source, ms: Math.round(ms), bytes };
  }
}

// Kolejność prefetchu: węzły rosnąco po liczbie kroków w grafie od `centerId`
// (BFS po krawędziach traktowanych jako nieskierowane), remis -> bliżej w 3D.
export function prefetchOrder(nodes, edges, centerId) {
  const adj = new Map(nodes.map(n => [n.id, []]));
  for (const e of edges) {
    if (adj.has(e.from) && adj.has(e.to)) { adj.get(e.from).push(e.to); adj.get(e.to).push(e.from); }
  }
  const hops = new Map([[centerId, 0]]);
  const queue = [centerId];
  while (queue.length) {
    const cur = queue.shift();
    for (const nb of adj.get(cur) || []) {
      if (!hops.has(nb)) { hops.set(nb, hops.get(cur) + 1); queue.push(nb); }
    }
  }
  const center = nodes.find(n => n.id === centerId);
  const dist = n => center
    ? Math.hypot(n.properties.x - center.properties.x, n.properties.y - center.properties.y, n.properties.z - center.properties.z)
    : 0;
  return nodes
    .filter(n => n.properties.name)
    .sort((a, b) => (hops.get(a.id) ?? 1e9) - (hops.get(b.id) ?? 1e9) || dist(a) - dist(b))
    .map(n => n.id);
}
