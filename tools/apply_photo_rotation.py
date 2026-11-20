"""
Rotates 360 equirectangular photos horizontally so every photo shares the
same yaw=0 reference direction, using angles you collected by eye against
Google Earth (see WirtualnaMapa's on-page QA log: "name,yaw,...").

Input file format - "name,yaw_degrees" as the first two comma-separated
fields per line; anything after the second field (e.g. a trailing pitch or
height column, as the app's QA log includes) is ignored, so a raw log line
can be pasted in directly without editing it down to just two fields:
    Gł.korytarz1,42.3
    Zewnątrz1,301.0,5.2,0

yaw_degrees is the angle you rotated the viewer TO in order to face the
shared reference direction - after correction, that direction becomes the
new yaw=0 for that photo.

By default this NEVER touches tools/photos_360/ - it writes corrected
copies to tools/photos_360_corrected/ so you can inspect them first.
Pass --apply to replace the originals (after taking a full backup).

Usage:
    python apply_photo_rotation.py rotations.txt
    python apply_photo_rotation.py rotations.txt --apply
"""
import argparse
import shutil
import sys
import time
from pathlib import Path

import os

import numpy as np
from PIL import Image

# ROTATION_TEST_DIR lets the test suite redirect this script at a throwaway
# scratch directory via subprocess env, without ever touching the real
# photos_360/ folder. Unset in normal (production) use - the Node backend
# never sets it, so this is a no-op there.
FOLDER = Path(os.environ["ROTATION_TEST_DIR"]) if "ROTATION_TEST_DIR" in os.environ else Path(__file__).parent
PHOTOS_DIR = FOLDER / "photos_360"
OUT_DIR = FOLDER / "photos_360_corrected"
BACKUP_ROOT = FOLDER / ".backups"


def parse_rotations(path):
    rotations = []
    for lineno, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "," not in line:
            print(f"  skipping line {lineno} (no comma): {line!r}")
            continue
        # first two fields only - a raw QA-log line can have extra trailing
        # columns (pitch, height) that are irrelevant here and get ignored
        name, yaw = line.split(",", 2)[:2]
        name = name.strip()
        try:
            yaw = float(yaw.strip())
        except ValueError:
            print(f"  skipping line {lineno} (bad angle): {line!r}")
            continue
        rotations.append((name, yaw))
    return rotations


def rotate_equirectangular(img, yaw_degrees):
    arr = np.array(img)
    width = arr.shape[1]
    shift_px = round((yaw_degrees % 360) / 360 * width)
    return Image.fromarray(np.roll(arr, -shift_px, axis=1))


def apply_single(name, yaw_degrees):
    """Used by WirtualnaMapa's live calibration buttons - backs up and
    overwrites one real photo immediately, no review step. Prints a single
    JSON line to stdout so the caller (Node) can parse the result."""
    import json

    src = PHOTOS_DIR / f"{name}.jpg"
    if not src.exists():
        print(json.dumps({"ok": False, "error": f"no photo found for {name}"}))
        return

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = BACKUP_ROOT / f"photos_360_pre_rotation_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, backup_dir / f"{name}.jpg")

    img = Image.open(src)
    corrected = rotate_equirectangular(img, yaw_degrees)
    corrected.save(src, quality=95)

    print(json.dumps({"ok": True, "name": name, "yaw": yaw_degrees, "backup": str(backup_dir / f"{name}.jpg")}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rotations_file", nargs="?")
    parser.add_argument("--apply", action="store_true",
                         help="after writing corrected copies, back up and replace the real photos_360/ files")
    parser.add_argument("--single", nargs=2, metavar=("NAME", "YAW_DEGREES"),
                         help="immediately back up and correct one real photo (used by the app's live calibration buttons)")
    args = parser.parse_args()

    if args.single:
        name, yaw = args.single
        apply_single(name, float(yaw))
        return

    if not args.rotations_file:
        sys.exit("rotations_file is required unless --single is used")

    rotations = parse_rotations(args.rotations_file)
    if not rotations:
        sys.exit("No valid rotation entries found.")

    OUT_DIR.mkdir(exist_ok=True)
    written, missing = [], []

    for name, yaw in rotations:
        src = PHOTOS_DIR / f"{name}.jpg"
        if not src.exists():
            missing.append(name)
            continue
        img = Image.open(src)
        corrected = rotate_equirectangular(img, yaw)
        dest = OUT_DIR / f"{name}.jpg"
        corrected.save(dest, quality=95)
        written.append(name)
        print(f"  {name}: rotated {yaw}deg -> {dest.name}")

    print(f"\nWrote {len(written)} corrected photos to {OUT_DIR}")
    if missing:
        print(f"Skipped {len(missing)} names with no matching source photo: {missing}")

    if not args.apply:
        print("\nReview the corrected photos, then rerun with --apply to replace the originals.")
        return

    if not written:
        print("Nothing to apply.")
        return

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = BACKUP_ROOT / f"photos_360_pre_rotation_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in written:
        shutil.copy2(PHOTOS_DIR / f"{name}.jpg", backup_dir / f"{name}.jpg")
    print(f"\nBacked up {len(written)} originals to {backup_dir}")

    for name in written:
        shutil.copy2(OUT_DIR / f"{name}.jpg", PHOTOS_DIR / f"{name}.jpg")
    print(f"Applied {len(written)} corrected photos into {PHOTOS_DIR}")


if __name__ == "__main__":
    main()
