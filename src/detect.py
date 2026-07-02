#!/usr/bin/env python3
"""
OTTER · Stage 1 detector
========================

Runs MegaDetector (V6, via the PyTorch-Wildlife package) over a folder of
trail-camera images. For every detection it:

  * records the bounding box, confidence, and MegaDetector class
  * saves a cropped image of that detection
  * writes everything to a single `otter_detections.json`

This file is the input to `review_app.py`, the human-in-the-loop labeling GUI,
where you confirm/correct species and assign buck / doe / fawn.

MegaDetector finds animals; it does NOT name them. Species pre-fill (optional)
is handled separately by `merge_speciesnet.py`. Buck/doe/fawn is always human.

Usage
-----
    python detect.py --images /path/to/trailcam/folder
    python detect.py --images ./pics --out ./otter_work --threshold 0.2

First run downloads the model weights (a few hundred MB) automatically.
A GPU is used if available; CPU works but is slower.
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Repo root = the folder that contains src/ (this script lives in src/).
# Anchoring to the script location means the defaults work no matter what
# directory you launch from, and nothing depends on an absolute machine path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

# MegaDetector category ids. 1=animal, 2=person, 3=vehicle (V6 convention).
# We keep animals by default; people/vehicles are recorded but flagged.
ANIMAL_CLASS_NAMES = {"animal"}


def parse_args():
    p = argparse.ArgumentParser(description="OTTER stage-1 MegaDetector pass.")
    p.add_argument("--images", default=str(PROJECT_ROOT / "data"),
                   help="Folder of trail-cam images (searched recursively). "
                        "Default: <repo>/data (your bw/, color/, etc.).")
    p.add_argument("--out", default=str(PROJECT_ROOT / "otter_work"),
                   help="Output folder for crops + detections JSON. Default: <repo>/otter_work")
    p.add_argument("--version", default="MDV6-yolov10-e",
                   help="MegaDetectorV6 variant: MDV6-yolov9-c, MDV6-yolov9-e, "
                        "MDV6-yolov10-c, MDV6-yolov10-e, MDV6-rtdetr-c. "
                        "The -c (compact) variants run well on CPU; -e are more accurate.")
    p.add_argument("--threshold", type=float, default=0.2,
                   help="Minimum detection confidence to keep (0.15-0.3 is typical).")
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"],
                   help="Where to run inference.")
    p.add_argument("--keep-nonanimals", action="store_true",
                   help="Also save person/vehicle detections (default: animals only).")
    p.add_argument("--square-crops", action="store_true",
                   help="Pad crops to square (preserves proportions). Off by default — "
                        "tight crops are better for training a species/sex classifier. "
                        "The square pad is what you want later when handing a confirmed "
                        "buck to agemydeer, so this is here for that pipeline too.")
    return p.parse_args()


def resolve_device(choice):
    if choice != "auto":
        return choice
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def find_images(root):
    root = Path(root)
    files = [p for p in sorted(root.rglob("*")) if p.suffix.lower() in IMAGE_EXTS]
    return files


def pad_bbox_to_square(x1, y1, x2, y2, w, h):
    """Expand the shorter side of a box symmetrically to make it square,
    clamped to image bounds. Preserves the animal's true proportions —
    important because the downstream age model reads body proportions."""
    bw, bh = x2 - x1, y2 - y1
    side = max(bw, bh)
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    nx1, ny1 = cx - side / 2.0, cy - side / 2.0
    nx2, ny2 = cx + side / 2.0, cy + side / 2.0
    # clamp
    nx1, ny1 = max(0, nx1), max(0, ny1)
    nx2, ny2 = min(w, nx2), min(h, ny2)
    return int(round(nx1)), int(round(ny1)), int(round(nx2)), int(round(ny2))


def extract_detections(result):
    """PyTorch-Wildlife returns a dict with a `supervision` Detections object
    under 'detections'. Pull boxes / confidences / class ids tolerantly across
    minor version differences."""
    det = result.get("detections", result) if isinstance(result, dict) else result
    xyxy = np.asarray(getattr(det, "xyxy", []))
    conf = getattr(det, "confidence", None)
    cls = getattr(det, "class_id", None)
    labels = result.get("labels") if isinstance(result, dict) else None
    n = len(xyxy)
    conf = np.asarray(conf) if conf is not None else np.full(n, np.nan)
    cls = np.asarray(cls) if cls is not None else np.full(n, -1)
    out = []
    for i in range(n):
        x1, y1, x2, y2 = [float(v) for v in xyxy[i][:4]]
        label_txt = ""
        if labels is not None and i < len(labels):
            # labels look like "animal 0.93"; take the word part
            label_txt = str(labels[i]).split()[0].lower()
        out.append({
            "bbox": [x1, y1, x2, y2],
            "det_conf": float(conf[i]) if not np.isnan(conf[i]) else None,
            "md_class": int(cls[i]) if cls[i] is not None else -1,
            "md_label": label_txt,
        })
    return out


def main():
    args = parse_args()
    out_dir = Path(args.out)
    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    images = find_images(args.images)
    if not images:
        sys.exit(f"No images found under {args.images}")
    print(f"Found {len(images)} images.")

    device = resolve_device(args.device)
    print(f"Loading MegaDetector {args.version} on {device} (first run downloads weights)...")
    try:
        from PytorchWildlife.models import detection as pw_detection
    except ModuleNotFoundError as e:
        if (e.name or "").split(".")[0] == "PytorchWildlife":
            sys.exit("PyTorch-Wildlife not installed. Run: pip install PytorchWildlife")
        # PytorchWildlife IS installed, but one of its dependencies failed to
        # import. Don't swallow it — re-raise so the real traceback shows.
        print(f"\nPyTorch-Wildlife is installed, but a dependency failed to import: "
              f"'{e.name}'. The real error follows.\n", file=sys.stderr)
        raise

    model = pw_detection.MegaDetectorV6(device=device, pretrained=True, version=args.version)

    records = []
    total_dets = 0
    for idx, img_path in enumerate(images, 1):
        image_id = img_path.stem  # e.g. 260212_KEN1_00
        try:
            pil = Image.open(img_path).convert("RGB")
        except Exception as e:
            print(f"  [skip] {img_path.name}: {e}")
            continue
        arr = np.array(pil)
        h, w = arr.shape[:2]

        try:
            result = model.single_image_detection(arr)
        except Exception as e:
            print(f"  [skip] {img_path.name}: detection failed: {e}")
            continue

        dets = extract_detections(result)
        kept = []
        for d in dets:
            if d["det_conf"] is not None and d["det_conf"] < args.threshold:
                continue
            is_animal = (d["md_label"] in ANIMAL_CLASS_NAMES) or (d["md_class"] in (0, 1))
            if not args.keep_nonanimals and d["md_label"] and not is_animal:
                continue
            kept.append(d)

        for di, d in enumerate(kept):
            x1, y1, x2, y2 = d["bbox"]
            if args.square_crops:
                cx1, cy1, cx2, cy2 = pad_bbox_to_square(x1, y1, x2, y2, w, h)
            else:
                cx1, cy1, cx2, cy2 = int(x1), int(y1), int(x2), int(y2)
            cx2, cy2 = max(cx1 + 1, cx2), max(cy1 + 1, cy2)
            crop = pil.crop((cx1, cy1, cx2, cy2))
            crop_name = f"{image_id}_det{di}.jpg"
            crop.save(crops_dir / crop_name, quality=92)
            d.update({
                "det_index": di,
                "crop": f"crops/{crop_name}",
                "species_pred": "animal",   # filled in later by merge_speciesnet.py (optional)
                "species_conf": None,
            })

        records.append({
            "image_id": image_id,
            "filename": img_path.name,
            # Stored RELATIVE to the output dir (where this JSON lives) so the
            # whole project stays portable — Dropbox, another laptop, etc.
            "path": Path(os.path.relpath(img_path.resolve(), out_dir.resolve())).as_posix(),
            "width": w,
            "height": h,
            "detections": kept,
        })
        total_dets += len(kept)
        if idx % 25 == 0 or idx == len(images):
            print(f"  {idx}/{len(images)} images  ·  {total_dets} detections so far")

    payload = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "detector": args.version,
        "threshold": args.threshold,
        "n_images": len(records),
        "n_detections": total_dets,
        "images": records,
    }
    out_json = out_dir / "otter_detections.json"
    out_json.write_text(json.dumps(payload, indent=2))
    print(f"\nDone. {total_dets} detections across {len(records)} images.")
    print(f"  Detections: {out_json}")
    print(f"  Crops:      {crops_dir}")
    print(f"\nNext: python review_app.py --work {out_dir}")


if __name__ == "__main__":
    main()
