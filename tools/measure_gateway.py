"""
Pomiar pobierania zdjęć z bramy IPFS (do rozdziału o ocenie IPFS jako hostingu).
Mierzy czas do pierwszego bajtu (TTFB), czas całkowity, przepustowość i błędy
dla: pobrań sekwencyjnych i równoległych (2, 4, 6), oraz porównawczo dla zwykłego
serwera statycznego (--baseline URL, np. plik z CDN o podobnym rozmiarze).

Nic nie zapisuje poza wypisaniem wyniku (i --json do pliku). Nie wymaga klucza.

Użycie:
    python measure_gateway.py --gateway https://gateway.pinata.cloud/ipfs/ --count 12
    python measure_gateway.py --baseline https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js
"""
import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

FOLDER = Path(__file__).parent
UA = {"User-Agent": "wirtualnamapa-measure/1.0"}


def fetch(url, timeout=60):
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            first = r.read(1)
            ttfb = time.perf_counter() - t0
            rest = r.read()
            total = time.perf_counter() - t0
            return {"ok": True, "status": r.status, "ttfb": ttfb, "total": total, "bytes": len(first) + len(rest)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "ttfb": time.perf_counter() - t0, "total": time.perf_counter() - t0, "bytes": 0}
    except Exception as e:
        return {"ok": False, "status": type(e).__name__, "ttfb": None, "total": time.perf_counter() - t0, "bytes": 0}


def run_parallel(urls, workers):
    results, lock = [], threading.Lock()
    idx = {"i": 0}

    def worker():
        while True:
            with lock:
                i = idx["i"]
                idx["i"] += 1
            if i >= len(urls):
                return
            r = fetch(urls[i])
            with lock:
                results.append(r)

    t0 = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(workers)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results, time.perf_counter() - t0


def pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * p))] if vals else float("nan")


def summarize(label, results, wall):
    ok = [r for r in results if r["ok"]]
    fails = [r["status"] for r in results if not r["ok"]]
    mb = sum(r["bytes"] for r in ok) / 1048576
    ttfb = [r["ttfb"] * 1000 for r in ok]
    tot = [r["total"] * 1000 for r in ok]
    line = {
        "label": label, "requests": len(results), "ok": len(ok), "failures": fails,
        "wall_s": round(wall, 1), "throughput_MiB_s": round(mb / wall, 2) if wall else None,
        "ttfb_ms": {"median": round(statistics.median(ttfb)) if ttfb else None, "p90": round(pct(ttfb, .9)) if ttfb else None, "max": round(max(ttfb)) if ttfb else None},
        "total_ms": {"median": round(statistics.median(tot)) if tot else None, "p90": round(pct(tot, .9)) if tot else None, "max": round(max(tot)) if tot else None},
    }
    print(json.dumps(line, ensure_ascii=False))
    return line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", default="https://gateway.pinata.cloud/ipfs/")
    ap.add_argument("--count", type=int, default=12, help="ile różnych zdjęć na serię")
    ap.add_argument("--baseline", help="URL pliku ze zwykłego serwera/CDN do porównania")
    ap.add_argument("--baseline-repeats", type=int, default=12)
    ap.add_argument("--json", help="zapisz wyniki do pliku")
    args = ap.parse_args()

    out = []
    if args.baseline:
        urls = [args.baseline] * args.baseline_repeats
        for w in (1, 4):
            res, wall = run_parallel(urls, w)
            out.append(summarize(f"baseline {w}x", res, wall))
    else:
        cids = [v["cid"] for v in json.loads((FOLDER / "photo_cids.json").read_text(encoding="utf-8")).values()]
        # rozłączne zestawy CID na każdą serię, żeby nie mierzyć cache bramy powtórnie
        batches = [(1, cids[0:args.count]), (2, cids[args.count:2 * args.count]), (4, cids[2 * args.count:3 * args.count]), (6, cids[3 * args.count:4 * args.count])]
        for workers, chunk in batches:
            if not chunk:
                continue
            res, wall = run_parallel([args.gateway + c for c in chunk], workers)
            out.append(summarize(f"zimne, {workers} równolegle", res, wall))
        # drugi raz te same pliki (ciepła brama)
        res, wall = run_parallel([args.gateway + c for c in batches[0][1]], 1)
        out.append(summarize("ponowne (ciepłe), 1 równolegle", res, wall))
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
