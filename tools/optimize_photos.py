"""
Tworzy zoptymalizowane kopie zdjęć 360 do wgrania do IPFS. NIE rusza oryginałów:
czyta tools/photos_360/, zapisuje do tools/photos_360_ipfs/ (te same nazwy).

Dla każdego zdjęcia znajduje NAJNIŻSZĄ jakość JPEG, przy której średnie SSIM
(jasność) względem oryginału wynosi >= --target-ssim (domyślnie 0.975, czyli
ok. 2,5% straty). Rozdzielczość zostaje pełna - zdjęcia ogląda się z zoomem.
Zapisuje progresywny, zoptymalizowany JPEG i manifest.json (rozmiary, jakość, SSIM).

SSIM to tylko przybliżona miara - ostatecznym sędzią jest porównanie w
compare_360.html (dwa zsynchronizowane widoki 360).

Użycie:
    python optimize_photos.py                    # wszystkie
    python optimize_photos.py --limit 3          # test na kilku
    python optimize_photos.py --only "Maksimus 1" --target-ssim 0.98
    python optimize_photos.py --fixed-quality 50   # ZESTAW KOŃCOWY do IPFS -> photos_360_upload/
    python optimize_photos.py --only "Poziom  4 Korytarz 2" --qualities 3,10,20,35,50,62,82,90
        # dodatkowe, coraz wierniejsze (większe) kopie jednego zdjęcia do
        # photos_360_ipfs/variants/ + variants.json - do porównania w compare_360.html
"""
import argparse
import hashlib
import io
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter

FOLDER = Path(__file__).parent
SRC = FOLDER / "photos_360"
DST = FOLDER / "photos_360_ipfs"
Q_MIN, Q_MAX = 40, 95


def luminance(arr):
    return (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]).astype(np.float32)


def ssim(a, b, win=7):
    """Średnie SSIM dwóch obrazów jasności (0-255), okno jednorodne jak w scikit-image."""
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mu_a, mu_b = uniform_filter(a, win), uniform_filter(b, win)
    aa = uniform_filter(a * a, win) - mu_a ** 2
    bb = uniform_filter(b * b, win) - mu_b ** 2
    ab = uniform_filter(a * b, win) - mu_a * mu_b
    n = win * win
    cov_norm = n / (n - 1)
    num = (2 * mu_a * mu_b + c1) * (2 * cov_norm * ab + c2)
    den = (mu_a ** 2 + mu_b ** 2 + c1) * (cov_norm * (aa + bb) + c2)
    return float((num / den).mean())


def encode(img, quality):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True, subsampling="4:2:0")
    return buf.getvalue()


def optimize(path, target):
    img = Image.open(path).convert("RGB")
    ref = luminance(np.asarray(img))
    lo, hi = Q_MIN, Q_MAX
    best = None  # (quality, bytes, ssim)
    while lo <= hi:
        q = (lo + hi) // 2
        data = encode(img, q)
        s = ssim(ref, luminance(np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))))
        if s >= target:
            best = (q, data, s)
            hi = q - 1
        else:
            lo = q + 1
    if best is None:  # nawet Q_MAX nie spełnia celu - zapisz Q_MAX
        data = encode(img, Q_MAX)
        s = ssim(ref, luminance(np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))))
        best = (Q_MAX, data, s)
    return best


def make_variants(files, targets=None, qualities=None):
    """Osobny plik variants.json (nie manifest.json), żeby nie kolidować z główną konwersją.
    targets: cele SSIM (dobiera jakość); qualities: stałe jakości JPEG (do drabinki aż po "scuffed")."""
    vdir = DST / "variants"
    vdir.mkdir(parents=True, exist_ok=True)
    vpath = DST / "variants.json"
    variants = json.loads(vpath.read_text(encoding="utf-8")) if vpath.exists() else {}
    for f in files:
        entries = {e["file"]: e for e in variants.get(f.stem, [])}
        jobs = []
        if targets:
            jobs += [("ssim", t) for t in targets]
        if qualities:
            jobs += [("q", q) for q in qualities]
        img = ref = None
        for kind, value in jobs:
            if kind == "ssim":
                q, data, s = optimize(f, value)
                fname = f"{f.stem}__ssim{value:.3f}.jpg"
                target = value
            else:
                if img is None:
                    img = Image.open(f).convert("RGB")
                    ref = luminance(np.asarray(img))
                q = int(value)
                data = encode(img, q)
                s = ssim(ref, luminance(np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))))
                fname = f"{f.stem}__q{q:02d}.jpg"
                target = None
            (vdir / fname).write_bytes(data)
            entries[fname] = {"target_ssim": target, "file": fname, "quality": q,
                              "ssim": round(s, 4), "bytes": len(data)}
            print(f"{f.stem}: {kind}={value} -> q={q} ssim={s:.4f} {len(data) / 1e6:.2f} MB ({len(data) / f.stat().st_size * 100:.0f}% oryginału)", flush=True)
        variants[f.stem] = sorted(entries.values(), key=lambda e: e["bytes"])
        vpath.write_text(json.dumps(variants, ensure_ascii=False, indent=1), encoding="utf-8")


def build_upload_set(files, quality, out_dir):
    """Zestaw końcowy do wgrania do IPFS: wszystkie zdjęcia przy STAŁEJ jakości JPEG
    (bez dopasowania SSIM), pełna rozdzielczość, progresywny JPEG. Zapisuje upload_manifest.json
    z rozmiarami, SSIM i SHA-256 każdego pliku (do późniejszego zestawienia z CID)."""
    out_dir.mkdir(exist_ok=True)
    manifest_path = out_dir / "upload_manifest.json"
    manifest = {}
    t0 = time.time()
    for i, f in enumerate(files, 1):
        img = Image.open(f).convert("RGB")
        ref = luminance(np.asarray(img))
        data = encode(img, quality)
        s = ssim(ref, luminance(np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))))
        (out_dir / f.name).write_bytes(data)
        manifest[f.stem] = {
            "file": f.name,
            "quality": quality,
            "width": img.width,
            "height": img.height,
            "original_bytes": f.stat().st_size,
            "bytes": len(data),
            "ssim": round(s, 4),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{i}/{len(files)}] {f.stem}: q={quality} ssim={s:.4f} {f.stat().st_size / 1e6:.2f} -> {len(data) / 1e6:.2f} MB ({len(data) / f.stat().st_size * 100:.0f}%) {time.time() - t0:.0f}s", flush=True)
    print("KONIEC", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-ssim", type=float, default=0.975)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", help="nazwa zdjęcia bez .jpg")
    ap.add_argument("--variants", help="lista celów SSIM po przecinku; tworzy kopie dodatkowe zamiast głównej")
    ap.add_argument("--qualities", help="lista stałych jakości JPEG po przecinku (np. 3,10,20,50,90); jak --variants, ale bez dopasowania SSIM")
    ap.add_argument("--fixed-quality", type=int, help="zestaw końcowy do IPFS: stała jakość JPEG dla wszystkich zdjęć (np. 50)")
    ap.add_argument("--out-dir", default="photos_360_upload", help="katalog zestawu końcowego (z --fixed-quality)")
    args = ap.parse_args()

    DST.mkdir(exist_ok=True)
    files = sorted(SRC.glob("*.jpg"))
    if args.only:
        files = [f for f in files if f.stem == args.only]
    if args.limit:
        files = files[:args.limit]

    if args.fixed_quality:
        build_upload_set(files, args.fixed_quality, FOLDER / args.out_dir)
        return

    if args.variants or args.qualities:
        make_variants(
            files,
            [float(v) for v in args.variants.split(",")] if args.variants else None,
            [int(v) for v in args.qualities.split(",")] if args.qualities else None,
        )
        return

    manifest_path = DST / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    t0 = time.time()
    for i, f in enumerate(files, 1):
        q, data, s = optimize(f, args.target_ssim)
        (DST / f.name).write_bytes(data)
        manifest[f.stem] = {
            "original_bytes": f.stat().st_size,
            "optimized_bytes": len(data),
            "quality": q,
            "ssim": round(s, 4),
            "target_ssim": args.target_ssim,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        ratio = len(data) / f.stat().st_size * 100
        print(f"[{i}/{len(files)}] {f.stem}: q={q} ssim={s:.4f} {f.stat().st_size / 1e6:.2f} -> {len(data) / 1e6:.2f} MB ({ratio:.0f}%) {time.time() - t0:.0f}s", flush=True)
    print("KONIEC", flush=True)


if __name__ == "__main__":
    main()
