#!/usr/bin/env python3
"""
OTTER · optional SpeciesNet pre-fill
====================================

SpeciesNet (Google) names the species MegaDetector found. It does NOT do
buck/doe/fawn (that's sex/age, not species) — that stays human. This script is
purely a convenience: it copies SpeciesNet's species guess onto each OTTER
detection so the review GUI shows "raccoon" or "white-tailed deer" instead of
"animal", saving you clicks. If a guess is wrong, you just click the right one.

Because SpeciesNet runs its own MegaDetector pass, its boxes won't be pixel-
identical to ours, so we match detections by best box overlap (IoU). This is
best-effort: SpeciesNet's JSON schema has shifted across versions, so if the
guesses don't attach, print one record with --debug and adjust the field names
in `iter_speciesnet_dets()` below.

Workflow
--------
1) Run SpeciesNet over the SAME image folder, with geofencing for your state:

     python -m speciesnet.scripts.run_md_and_speciesnet \
         --folders /path/to/trailcam/folder \
         --predictions_json speciesnet_preds.json \
         --country USA --admin1_region IN

2) Merge its guesses into the OTTER detections file:

     python merge_speciesnet.py \
         --detections otter_work/otter_detections.json \
         --speciesnet speciesnet_preds.json
"""

import argparse
import json
from pathlib import Path


def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


def common_name(label):
    """SpeciesNet labels look like 'uuid;mammalia;...;odocoileus virginianus;
    white-tailed deer'. Take the human-readable tail; fall back to the raw string."""
    if not label:
        return "animal"
    parts = [p for p in str(label).split(";") if p]
    name = parts[-1] if parts else str(label)
    return name.strip().lower() or "animal"


def iter_speciesnet_dets(sn_json, img_w, img_h):
    """Yield (bbox_xyxy_pixels, species_name, score) for one image's record.
    Handles the MegaDetector-format output of run_md_and_speciesnet, where each
    detection carries a 'classifications' list and bbox is normalized [x,y,w,h]."""
    for det in sn_json.get("detections", []):
        bbox = det.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        x, y, w, h = bbox  # normalized
        xyxy = [x * img_w, y * img_h, (x + w) * img_w, (y + h) * img_h]
        species, score = "animal", None
        cls = det.get("classifications")
        if isinstance(cls, dict):  # {"classes":[...], "scores":[...]}
            classes, scores = cls.get("classes", []), cls.get("scores", [])
            if classes:
                species, score = common_name(classes[0]), (scores[0] if scores else None)
        elif isinstance(cls, list) and cls:  # [[label, score], ...]
            top = cls[0]
            if isinstance(top, (list, tuple)):
                species, score = common_name(top[0]), (top[1] if len(top) > 1 else None)
        yield xyxy, species, score


def main():
    ap = argparse.ArgumentParser(description="Attach SpeciesNet species guesses to OTTER detections.")
    ap.add_argument("--detections", required=True, help="otter_detections.json from detect.py")
    ap.add_argument("--speciesnet", required=True, help="SpeciesNet predictions JSON")
    ap.add_argument("--min-iou", type=float, default=0.45)
    ap.add_argument("--debug", action="store_true", help="Print one parsed SpeciesNet record and exit.")
    args = ap.parse_args()

    det_data = json.loads(Path(args.detections).read_text())
    sn = json.loads(Path(args.speciesnet).read_text())

    # index SpeciesNet records by filename stem
    sn_images = sn.get("images", sn.get("predictions", []))
    sn_by_stem = {}
    for rec in sn_images:
        f = rec.get("file") or rec.get("filepath") or rec.get("filename", "")
        sn_by_stem[Path(f).stem] = rec

    if args.debug and sn_images:
        print(json.dumps(sn_images[0], indent=2)[:1500]); return

    attached = 0
    for im in det_data["images"]:
        rec = sn_by_stem.get(im["image_id"])
        if not rec:
            continue
        sn_dets = list(iter_speciesnet_dets(rec, im["width"], im["height"]))
        for d in im["detections"]:
            best, best_iou = None, args.min_iou
            for xyxy, sp, sc in sn_dets:
                v = iou(d["bbox"], xyxy)
                if v >= best_iou:
                    best, best_iou = (sp, sc), v
            if best:
                d["species_pred"], d["species_conf"] = best
                attached += 1

    Path(args.detections).write_text(json.dumps(det_data, indent=2))
    print(f"Attached species guesses to {attached} detections in {args.detections}")


if __name__ == "__main__":
    main()
