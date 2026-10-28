const test = require('node:test');
const assert = require('node:assert');

let PhotoCache, prefetchOrder;
test.before(async () => {
  ({ PhotoCache, prefetchOrder } = await import('../public/js/photoCache.mjs'));
});

const sleep = ms => new Promise(r => setTimeout(r, ms));
const BYTES = 4000; // > MIN_VALID_BYTES

// sztuczny fetch: plan[url] = { ms, fail }, strumieniuje 4 kawałki, respektuje signal
function makeFetch(plan = {}, defaults = { ms: 20 }) {
  const calls = [];
  let inFlight = 0, maxInFlight = 0;
  const fn = async (url, { signal } = {}) => {
    calls.push(url);
    const spec = plan[url] || defaults;
    inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
    try {
      await sleep(5);
      if (spec.fail) return new Response('nope', { status: spec.fail });
      const chunk = new Uint8Array(BYTES / 4).fill(7);
      let sent = 0;
      const stream = new ReadableStream({
        async pull(controller) {
          await sleep(spec.ms / 4);
          if (signal && signal.aborted) { inFlight--; controller.error(Object.assign(new Error('aborted'), { name: 'AbortError' })); return; }
          controller.enqueue(chunk);
          if (++sent === 4) { inFlight--; controller.close(); }
        },
      });
      if (signal) signal.addEventListener('abort', () => {}, { once: true });
      return new Response(stream, { status: 200, headers: { 'Content-Length': String(BYTES), 'Content-Type': 'image/jpeg' } });
    } catch (e) { inFlight--; throw e; }
  };
  fn.calls = calls;
  fn.maxInFlight = () => maxInFlight;
  return fn;
}

function fakeCaches() {
  const stores = new Map();
  return {
    stores,
    async open(name) {
      if (!stores.has(name)) stores.set(name, new Map());
      const m = stores.get(name);
      return {
        async put(key, res) { m.set(key, await res.blob()); },
        async match(key) { return m.has(key) ? new Response(m.get(key)) : undefined; },
        async keys() { return [...m.keys()].map(url => ({ url })); },
        async delete(req) { return m.delete(req.url); },
      };
    },
  };
}

const node = (id, name, cid = `cid${id}`) => ({ id, properties: { name, imageCid: cid, x: id, y: 0, z: 0 } });
const GW = ['https://gw1.test/ipfs/', 'https://gw2.test/ipfs/'];

function setup(opts = {}, n = 6) {
  const fetchImpl = opts.fetchImpl || makeFetch();
  const cache = new PhotoCache({ gateways: GW, localUrl: i => `/photos/${i.name}.jpg`, fetchImpl, cachesImpl: opts.cachesImpl, maxBackground: 3 });
  cache.register(Array.from({ length: n }, (_, k) => node(k + 1, `P${k + 1}`)));
  return { cache, fetchImpl };
}

test('get pobiera raz, równoległe wywołania współdzielą jedno pobranie', async () => {
  const { cache, fetchImpl } = setup();
  const [a, b] = await Promise.all([cache.get(1), cache.get(1)]);
  assert.strictEqual(fetchImpl.calls.length, 1);
  assert.strictEqual(a.url, b.url);
  assert.ok(a.url.startsWith('blob:'));
  assert.strictEqual(a.bytes, BYTES);
  const again = await cache.get(1);
  assert.strictEqual(again.fromCache, true);
  assert.strictEqual(fetchImpl.calls.length, 1);
});

test('get raportuje postęp pobierania', async () => {
  const { cache } = setup();
  const seen = [];
  await cache.get(2, { onProgress: (l, t) => seen.push([l, t]) });
  assert.ok(seen.length >= 3);
  assert.deepStrictEqual(seen[seen.length - 1], [BYTES, BYTES]);
});

test('awaria pierwszej bramy -> druga brama; awaria obu -> lokalny zapas', async () => {
  const f1 = makeFetch({ 'https://gw1.test/ipfs/cid1': { fail: 500 } });
  const { cache } = setup({ fetchImpl: f1 });
  const r = await cache.get(1);
  assert.strictEqual(r.source, 'gw2.test');
  assert.deepStrictEqual(f1.calls, ['https://gw1.test/ipfs/cid1', 'https://gw2.test/ipfs/cid1']);

  const f2 = makeFetch({ 'https://gw1.test/ipfs/cid2': { fail: 429 }, 'https://gw2.test/ipfs/cid2': { fail: 503 } });
  const { cache: c2 } = setup({ fetchImpl: f2 });
  const r2 = await c2.get(2);
  assert.strictEqual(r2.source, 'local');
  assert.strictEqual(f2.calls[2], '/photos/P2.jpg');
});

test('całkowita awaria odrzuca get, a kolejna próba może się udać', async () => {
  const plan = { 'https://gw1.test/ipfs/cid1': { fail: 500 }, 'https://gw2.test/ipfs/cid1': { fail: 500 }, '/photos/P1.jpg': { fail: 404 } };
  const { cache } = setup({ fetchImpl: makeFetch(plan) });
  await assert.rejects(() => cache.get(1));
  assert.strictEqual(cache.isReady(1), false);
});

test('prefetch: kolejność z kolejki i limit równoległości', async () => {
  const f = makeFetch({}, { ms: 40 });
  const { cache } = setup({ fetchImpl: f }, 8);
  cache.prefetch([5, 3, 1, 8, 2, 4, 6, 7]);
  await sleep(300);
  assert.strictEqual(cache.stats().available, 8);
  assert.ok(f.maxInFlight() <= 3, `maxInFlight=${f.maxInFlight()}`);
  const order = f.calls.map(u => Number(u.split('cid')[1]));
  assert.deepStrictEqual(order.slice(0, 3), [5, 3, 1]); // pierwsze trzy w kolejności priorytetu
});

test('nowe prefetch zmienia priorytet oczekujących (re-priorytetyzacja)', async () => {
  const f = makeFetch({}, { ms: 60 });
  const { cache } = setup({ fetchImpl: f }, 8);
  cache.prefetch([1, 2, 3, 4, 5, 6, 7, 8]);
  await sleep(10);
  cache.prefetch([8, 7, 6, 5, 4, 3, 2, 1]); // użytkownik przeszedł w inne miejsce
  await sleep(400);
  const order = f.calls.map(u => Number(u.split('cid')[1]));
  assert.deepStrictEqual(order.slice(0, 3), [1, 2, 3]);      // już trwały
  assert.deepStrictEqual(order.slice(3, 6), [8, 7, 6]);       // potem nowa kolejność
});

test('get ma bezwzględny priorytet: wstrzymuje tło, przerywa świeże pobrania i wznawia po zakończeniu', async () => {
  const f = makeFetch({}, { ms: 80 });
  const { cache } = setup({ fetchImpl: f }, 8);
  cache.prefetch([1, 2, 3, 4, 5, 6]);
  await sleep(15); // 1,2,3 ruszyły w tle, ale mają mało pobrane
  const fg = await cache.get(7);
  assert.strictEqual(cache.isReady(7), true);
  // w trakcie get nie wystartowało nic nowego z tła (4,5,6 czekają)
  const startedDuringFg = f.calls.filter(u => /cid[456]$/.test(u));
  assert.strictEqual(startedDuringFg.length, 0);
  // po zakończeniu get tło wznawia się i kończy wszystko, także przerwane 1-3
  await sleep(500);
  assert.strictEqual(cache.stats().available, 7);
  for (const id of [1, 2, 3, 4, 5, 6, 7]) assert.strictEqual(cache.isReady(id), true, `P${id}`);
  assert.ok(fg.ms < 400);
});

test('wybór zdjęcia właśnie przerwanego w tle też się udaje', async () => {
  const f = makeFetch({}, { ms: 80 });
  const { cache } = setup({ fetchImpl: f }, 4);
  cache.prefetch([1, 2, 3]);
  await sleep(15);
  const p4 = cache.get(4);          // przerywa 1-3
  const p1 = cache.get(1);          // chce dokładnie to, co właśnie przerwano
  const [r4, r1] = await Promise.all([p4, p1]);
  assert.ok(r4.url && r1.url);
});

test('pobranie w tle awansuje na pierwszoplanowe bez drugiego żądania', async () => {
  const f = makeFetch({}, { ms: 60 });
  const { cache } = setup({ fetchImpl: f }, 3);
  cache.prefetch([1, 2]);
  await sleep(10);
  const before = f.calls.filter(u => u.endsWith('cid1')).length;
  await cache.get(1);
  assert.strictEqual(before, 1);
  assert.strictEqual(f.calls.filter(u => u.endsWith('cid1')).length, 1);
});

test('trwały cache: drugi start nie pobiera z sieci, a nieznane CID-y są sprzątane', async () => {
  const caches = fakeCaches();
  const first = setup({ cachesImpl: caches });
  await first.cache.get(1);
  await first.cache.get(2);
  assert.strictEqual(first.fetchImpl.calls.length, 2);
  // stary wpis, którego już nie ma w grafie
  const store = caches.stores.get('wm-photos-v1');
  store.set('https://photo-cache.invalid/cid-stare', new Blob([new Uint8Array(BYTES)]));

  const second = setup({ cachesImpl: caches });
  await second.cache.init();
  assert.strictEqual(second.cache.isAvailableOffline(1), true);
  assert.strictEqual(second.cache.isAvailableOffline(3), false);
  assert.strictEqual(store.has('https://photo-cache.invalid/cid-stare'), false);
  const r = await second.cache.get(1);
  assert.strictEqual(r.source, 'cache-storage');
  assert.strictEqual(r.fromCache, true);
  assert.strictEqual(second.fetchImpl.calls.length, 0);
});

test('zapas lokalny nie trafia do trwałego cache', async () => {
  const caches = fakeCaches();
  const plan = { 'https://gw1.test/ipfs/cid1': { fail: 500 }, 'https://gw2.test/ipfs/cid1': { fail: 500 } };
  const { cache } = setup({ fetchImpl: makeFetch(plan), cachesImpl: caches });
  const r = await cache.get(1);
  assert.strictEqual(r.source, 'local');
  const store = caches.stores.get('wm-photos-v1');
  assert.ok(!store || store.size === 0);
});

test('prefetchOrder: po liczbie kroków w grafie, remis -> bliżej', () => {
  const nodes = [1, 2, 3, 4, 5].map(i => ({ id: i, properties: { name: `N${i}`, x: i === 4 ? 1 : i, y: 0, z: 0 } }));
  // 1-2, 2-3, 3-4, 1-5   (węzeł 4 leży blisko 1 w przestrzeni, ale daleko w grafie)
  const edges = [{ from: 1, to: 2 }, { from: 2, to: 3 }, { from: 3, to: 4 }, { from: 1, to: 5 }];
  const order = prefetchOrder(nodes, edges, 1);
  assert.strictEqual(order[0], 1);
  assert.deepStrictEqual(order.slice(1, 3).sort(), [2, 5]);   // 1 krok
  assert.strictEqual(order[3], 3);                             // 2 kroki
  assert.strictEqual(order[4], 4);                             // 3 kroki
});
