"""
Wgrywa zestaw końcowy zdjęć (tools/photos_360_upload/, patrz optimize_photos.py
--fixed-quality) do Pinata (publiczna sieć IPFS) i zapisuje CID każdego zdjęcia
w tools/photo_cids.json.

- Klucz: PINATA_JWT z WirtualnaMapa/.env (nigdy nie wypisywany).
- Wznawialne: zdjęcie z zapisanym CID i tym samym SHA-256 jest pomijane.
- --verify: pobiera plik z publicznej bramy i porównuje SHA-256 z lokalnym.

UWAGA: treść w publicznym IPFS jest adresowana po hashu i praktycznie
nieodwracalna - wgrywać dopiero, gdy zdjęcia są ostateczne.

Użycie:
    python upload_to_ipfs.py --only "Maksimus 1"     # próba na jednym
    python upload_to_ipfs.py                          # wszystkie
    python upload_to_ipfs.py --verify-only            # tylko weryfikacja pobraniem
"""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

FOLDER = Path(__file__).parent
UPLOAD_DIR = FOLDER / "photos_360_upload"
UPLOAD_MANIFEST = UPLOAD_DIR / "upload_manifest.json"
CIDS_PATH = FOLDER / "photo_cids.json"
ENV_PATH = FOLDER.parent / "WirtualnaMapa" / ".env"
UPLOAD_URL = "https://uploads.pinata.cloud/v3/files"
GATEWAYS = ["https://gateway.pinata.cloud/ipfs/", "https://ipfs.io/ipfs/", "https://dweb.link/ipfs/"]


def load_env():
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def multipart(fields, file_field, filename, data):
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    parts.append(
        (f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
         f'Content-Type: image/jpeg\r\n\r\n').encode("utf-8") + data + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload_one(jwt, name, path):
    data = path.read_bytes()
    body, ctype = multipart({"network": "public", "name": f"{name}.jpg"}, "file", path.name, data)
    last = None
    for attempt in range(1, 4):
        req = urllib.request.Request(UPLOAD_URL, data=body, method="POST",
                                     headers={"Authorization": f"Bearer {jwt}", "Content-Type": ctype,
                                              "User-Agent": "wirtualnamapa-uploader/1.0", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))["data"]
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        except Exception as e:  # sieć
            last = repr(e)
        time.sleep(2 * attempt)
    raise RuntimeError(f"{name}: upload nie powiódł się: {last}")


def find_existing(jwt, name):
    """CID pliku o tej nazwie już obecnego w Pinata (None, jeśli brak) - żeby nie wgrywać dwa razy."""
    url = "https://api.pinata.cloud/v3/files/public?limit=5&name=" + urllib.parse.quote(f"{name}.jpg")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {jwt}", "User-Agent": "wirtualnamapa-uploader/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        files = json.loads(r.read().decode("utf-8"))["data"]["files"]
    exact = [f for f in files if f.get("name") == f"{name}.jpg"]
    return exact[0] if exact else None


def fetch_via_gateways(cid):
    last = None
    for gw in GATEWAYS:
        try:
            with urllib.request.urlopen(urllib.request.Request(gw + cid, headers={"User-Agent": "wirtualnamapa-verify"}), timeout=120) as r:
                return gw, r.read()
        except Exception as e:
            last = f"{gw}: {e!r}"
    raise RuntimeError(f"żadna brama nie zwróciła pliku ({last})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="nazwa zdjęcia bez .jpg")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--verify", action="store_true", help="po wgraniu pobierz z bramy i porównaj SHA-256")
    args = ap.parse_args()

    manifest = json.loads(UPLOAD_MANIFEST.read_text(encoding="utf-8"))
    cids = json.loads(CIDS_PATH.read_text(encoding="utf-8")) if CIDS_PATH.exists() else {}
    names = [n for n in sorted(manifest) if not args.only or n == args.only]
    if not names:
        raise SystemExit("brak pasujących zdjęć")

    if not args.verify_only:
        jwt = load_env()["PINATA_JWT"]
        for i, name in enumerate(names, 1):
            m = manifest[name]
            if name in cids and cids[name]["sha256"] == m["sha256"]:
                print(f"[{i}/{len(names)}] {name}: już wgrane ({cids[name]['cid']})", flush=True)
                continue
            path = UPLOAD_DIR / m["file"]
            res = find_existing(jwt, name) or upload_one(jwt, name, path)
            # "size" z Pinaty to rozmiar drzewa UnixFS (plik + nagłówki fragmentów), nie liczba bajtów
            # pliku - poprawność sprawdza --verify (pobranie z bramy i SHA-256)
            cids[name] = {"cid": res["cid"], "sha256": m["sha256"], "bytes": m["bytes"],
                          "pinata_id": res.get("id"), "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            CIDS_PATH.write_text(json.dumps(cids, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[{i}/{len(names)}] {name}: {res['cid']}", flush=True)

    if args.verify or args.verify_only:
        bad = 0
        for i, name in enumerate(names, 1):
            if name not in cids:
                print(f"{name}: brak CID"); bad += 1; continue
            gw, data = fetch_via_gateways(cids[name]["cid"])
            ok = hashlib.sha256(data).hexdigest() == manifest[name]["sha256"]
            bad += 0 if ok else 1
            print(f"[{i}/{len(names)}] weryfikacja {name}: {'OK' if ok else 'RÓŻNICA'} ({gw})", flush=True)
        print("weryfikacja:", "wszystko zgodne" if not bad else f"{bad} niezgodnych")


if __name__ == "__main__":
    main()
