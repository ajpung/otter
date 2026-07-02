#!/usr/bin/env python3
"""
OTTER · Stage 1 review GUI
==========================

A local web app for labeling the detections produced by `detect.py`.
For each image it shows the full frame with MegaDetector's boxes drawn on it,
plus a cropped thumbnail per detection with a row of one-click labels
(buck, doe, fawn, turkey, ...). Your clicks are saved instantly to a CSV, so
you can close the tab and resume later. When you're done, "Export dataset"
sorts the crops into per-class folders and writes an OTTER-style counts sheet.

Nothing leaves your machine. Run it, open the link, label, export.

Usage
-----
    python review_app.py --work ./otter_work
    # then open http://127.0.0.1:5000

Outputs (inside --work)
-----------------------
    otter_labels.csv          one row per detection, your assigned label
    dataset/<label>/*.jpg     crops sorted by label  (after Export)
    otter_counts.csv          per-image species counts, OTTER schema (after Export)
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path

from flask import Flask, jsonify, request, send_file, abort
from PIL import Image

# Repo root = folder containing src/ (this script lives in src/). Anchoring here
# keeps defaults working from any launch directory and avoids absolute paths.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

# ---------------------------------------------------------------------------
# Label vocabulary.  Edit this to match the species you actually see.
# Each entry: (value, display, group).  `value` is what gets saved.
# ---------------------------------------------------------------------------
CLASSES = [
    ("buck",          "Buck",         "Deer"),
    ("doe",           "Doe",          "Deer"),
    ("fawn",          "Fawn",         "Deer"),
    ("deer_unknown",  "Deer (?)",     "Deer"),
    ("turkey",        "Turkey",       "Birds"),
    ("crow",          "Crow",         "Birds"),
    ("cardinal",      "Cardinal",     "Birds"),
    ("woodpecker",    "Woodpecker",   "Birds"),
    ("eagle",         "Eagle",        "Birds"),
    ("coyote",        "Coyote",       "Mammals"),
    ("bobcat",        "Bobcat",       "Mammals"),
    ("cat",           "Cat",          "Mammals"),
    ("raccoon",       "Raccoon",      "Mammals"),
    ("possum",        "Possum",       "Mammals"),
    ("woodchuck",     "Woodchuck",    "Mammals"),
    ("butterfly",     "Butterfly",    "Other"),
    ("other",         "Other",        "Other"),
    ("false_positive","Not an animal","Other"),
]
VALID = {c[0] for c in CLASSES}

# Map each leaf label to the OTTER counts-sheet columns it contributes to.
# "Deer" is the rolled-up total (matches your existing sheet: buck+doe = deer).
COUNT_COLUMNS = ["Buck", "Doe", "Fawn", "Deer", "Coyote", "Cat", "Turkey",
                 "Raccoon", "Bobcat", "Crow", "Woodpecker", "Cardinal",
                 "Possum", "Woodchuck", "Eagle", "Butterfly"]
LABEL_TO_COLUMNS = {
    "buck": ["Buck", "Deer"], "doe": ["Doe", "Deer"], "fawn": ["Fawn", "Deer"],
    "deer_unknown": ["Deer"], "coyote": ["Coyote"], "cat": ["Cat"],
    "turkey": ["Turkey"], "raccoon": ["Raccoon"], "bobcat": ["Bobcat"],
    "crow": ["Crow"], "woodpecker": ["Woodpecker"], "cardinal": ["Cardinal"],
    "possum": ["Possum"], "woodchuck": ["Woodchuck"],
    "eagle": ["Eagle"], "butterfly": ["Butterfly"],
    # other / false_positive contribute to no species column
}

LABELS_CSV_FIELDS = ["image_id", "det_index", "crop", "x1", "y1", "x2", "y2",
                     "det_conf", "species_pred", "label", "updated_at"]


def parse_date_from_id(image_id):
    """Filenames look like 260212_KEN1_00 -> 2026-02-12.  Returns (Y, M, D) or ('','','')."""
    m = re.match(r"^(\d{2})(\d{2})(\d{2})_", image_id)
    if not m:
        return "", "", ""
    yy, mm, dd = (int(g) for g in m.groups())
    return 2000 + yy, mm, dd


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------
class Store:
    def __init__(self, work_dir, images_root):
        self.work = Path(work_dir).resolve()
        self.images_root = Path(images_root).resolve()
        self._img_index = None
        self.det_path = self.work / "otter_detections.json"
        self.labels_path = self.work / "otter_labels.csv"
        if not self.det_path.exists():
            raise SystemExit(
                f"No otter_detections.json in {self.work.resolve()}.\n"
                f"Run the detector first, e.g.:\n"
                f"    python detect.py --images {(PROJECT_ROOT / 'data')}\n"
                f"(then re-run this with the same --work folder)."
            )
        self.data = json.loads(self.det_path.read_text())
        self.images = self.data["images"]
        self.by_id = {im["image_id"]: im for im in self.images}
        self.labels = {}   # (image_id, det_index) -> label
        self._load_labels()
        self.reconciled = self._reconcile_paths()

    def _build_img_index(self):
        """Map filename (lowercased) -> absolute path for every image under the
        images root, so a moved/reorganized file can still be located by name."""
        idx = {}
        if self.images_root.exists():
            for p in self.images_root.rglob("*"):
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                    idx.setdefault(p.name.lower(), p.resolve())
        return idx

    def _lookup_by_name(self, filename):
        if self._img_index is None:
            self._img_index = self._build_img_index()
        return self._img_index.get(filename.lower())

    def _reconcile_paths(self):
        """If stored image paths no longer exist (e.g. files were moved between
        data/ subfolders), relocate them by filename and persist the corrected
        paths ONCE. Labels and crops are never touched."""
        fixed, missing = 0, []
        for im in self.images:
            p = Path(im["path"])
            if not p.is_absolute():
                p = self.work / p
            if p.resolve().exists():
                continue
            found = self._lookup_by_name(im["filename"])
            if found:
                im["path"] = Path(os.path.relpath(found, self.work)).as_posix()
                fixed += 1
            else:
                missing.append(im["filename"])
        if fixed:
            self._save_detections()
        return {"fixed": fixed, "missing": missing}

    def image_file(self, im):
        """Resolve a stored (relative) image path against the work dir. If the
        file isn't there (moved since detection), locate it by name under the
        images root so the app self-heals."""
        p = Path(im["path"])
        if not p.is_absolute():
            p = self.work / p
        p = p.resolve()
        if p.exists():
            return p
        found = self._lookup_by_name(im["filename"])
        if found and found.exists():
            im["path"] = Path(os.path.relpath(found, self.work)).as_posix()
            return found
        return p  # genuinely missing — let the caller surface a clear error

    def _load_labels(self):
        if not self.labels_path.exists():
            return
        with self.labels_path.open(newline="") as f:
            for row in csv.DictReader(f):
                if row.get("label"):
                    self.labels[(row["image_id"], int(row["det_index"]))] = row["label"]

    def set_label(self, image_id, det_index, label):
        self.labels[(image_id, det_index)] = label
        self._rewrite()

    def _save_detections(self):
        """Persist the detections JSON so manually-added boxes survive a restart."""
        self.data["n_detections"] = sum(len(im["detections"]) for im in self.images)
        self.det_path.write_text(json.dumps(self.data, indent=2))

    def add_box(self, image_id, x1, y1, x2, y2):
        """Crop a user-drawn box from the original frame and append it as a new
        detection, so it flows through labeling and export like any other."""
        im = self.by_id.get(image_id)
        if not im:
            return None
        # order + clamp to image bounds
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(im["width"], int(x2)), min(im["height"], int(y2))
        if x2 - x1 < 4 or y2 - y1 < 4:
            return None  # ignore stray clicks / tiny drags
        next_idx = (max((d["det_index"] for d in im["detections"]), default=-1) + 1)
        crop_name = f"{image_id}_det{next_idx}.jpg"
        with Image.open(self.image_file(im)) as src:
            src.convert("RGB").crop((x1, y1, x2, y2)).save(self.work / "crops" / crop_name, quality=92)
        det = {
            "bbox": [x1, y1, x2, y2], "det_conf": None, "md_class": -1,
            "md_label": "manual", "det_index": next_idx, "crop": f"crops/{crop_name}",
            "species_pred": "manual", "species_conf": None, "manual": True,
        }
        im["detections"].append(det)
        self._save_detections()
        return det

    def delete_box(self, image_id, det_index):
        """Remove a manually-added box (and its crop + any label). Detector boxes
        are left alone — hiding a real detection should be a label, not deletion."""
        im = self.by_id.get(image_id)
        if not im:
            return False
        keep, removed = [], None
        for d in im["detections"]:
            if d["det_index"] == det_index and d.get("manual"):
                removed = d
            else:
                keep.append(d)
        if not removed:
            return False
        im["detections"] = keep
        crop = (self.work / removed["crop"])
        if crop.exists():
            crop.unlink()
        self.labels.pop((image_id, det_index), None)
        self._save_detections()
        self._rewrite()
        return True

    def _rewrite(self):
        with self.labels_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LABELS_CSV_FIELDS)
            w.writeheader()
            for im in self.images:
                for d in im["detections"]:
                    key = (im["image_id"], d["det_index"])
                    bx = d["bbox"]
                    w.writerow({
                        "image_id": im["image_id"], "det_index": d["det_index"],
                        "crop": d["crop"], "x1": round(bx[0]), "y1": round(bx[1]),
                        "x2": round(bx[2]), "y2": round(bx[3]),
                        "det_conf": d.get("det_conf"), "species_pred": d.get("species_pred"),
                        "label": self.labels.get(key, ""),
                        "updated_at": dt.datetime.now().isoformat(timespec="seconds")
                        if key in self.labels else "",
                    })

    def progress(self):
        total = sum(len(im["detections"]) for im in self.images)
        done = len(self.labels)
        return done, total

    def export(self):
        ds = self.work / "dataset"
        # sort crops into class folders
        per_class = {}
        for im in self.images:
            for d in im["detections"]:
                label = self.labels.get((im["image_id"], d["det_index"]))
                if not label:
                    continue
                per_class.setdefault(label, 0)
                src = self.work / d["crop"]
                if src.exists():
                    dst_dir = ds / label
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst_dir / Path(d["crop"]).name)
                    per_class[label] += 1
        # OTTER counts sheet
        counts_path = self.work / "otter_counts.csv"
        with counts_path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Image", "Year", "Month", "Day"] + COUNT_COLUMNS)
            for im in self.images:
                y, mo, da = parse_date_from_id(im["image_id"])
                counts = {c: 0 for c in COUNT_COLUMNS}
                for d in im["detections"]:
                    label = self.labels.get((im["image_id"], d["det_index"]))
                    for col in LABEL_TO_COLUMNS.get(label, []):
                        counts[col] += 1
                w.writerow([im["image_id"], y, mo, da] + [counts[c] for c in COUNT_COLUMNS])
        return {"per_class": per_class, "dataset_dir": str(ds), "counts": str(counts_path)}


app = Flask(__name__)
STORE: Store = None  # set in main()


@app.get("/")
def index():
    return PAGE


@app.get("/api/state")
def api_state():
    done, total = STORE.progress()
    imgs = []
    for im in STORE.images:
        labeled = sum(1 for d in im["detections"]
                      if (im["image_id"], d["det_index"]) in STORE.labels)
        imgs.append({
            "image_id": im["image_id"], "filename": im["filename"],
            "n_det": len(im["detections"]), "n_labeled": labeled,
        })
    return jsonify({
        "classes": [{"value": v, "display": disp, "group": g} for v, disp, g in CLASSES],
        "images": imgs, "done": done, "total": total,
    })


@app.get("/api/image/<image_id>")
def api_image(image_id):
    im = STORE.by_id.get(image_id)
    if not im:
        abort(404)
    dets = []
    for d in im["detections"]:
        dets.append({
            "det_index": d["det_index"], "bbox": d["bbox"],
            "det_conf": d.get("det_conf"), "species_pred": d.get("species_pred"),
            "species_conf": d.get("species_conf"), "manual": d.get("manual", False),
            "label": STORE.labels.get((image_id, d["det_index"]), ""),
        })
    return jsonify({"image_id": image_id, "filename": im["filename"],
                    "width": im["width"], "height": im["height"], "detections": dets})


@app.get("/img/full/<image_id>")
def img_full(image_id):
    im = STORE.by_id.get(image_id)
    if not im:
        abort(404)
    return send_file(STORE.image_file(im))


@app.get("/img/crop/<image_id>/<int:det_index>")
def img_crop(image_id, det_index):
    im = STORE.by_id.get(image_id)
    if not im:
        abort(404)
    for d in im["detections"]:
        if d["det_index"] == det_index:
            return send_file((STORE.work / d["crop"]).resolve())
    abort(404)


@app.post("/api/label")
def api_label():
    body = request.get_json(force=True)
    label = body.get("label", "")
    if label and label not in VALID:
        return jsonify({"error": f"unknown label {label}"}), 400
    STORE.set_label(body["image_id"], int(body["det_index"]), label)
    done, total = STORE.progress()
    return jsonify({"ok": True, "done": done, "total": total})


@app.post("/api/add_box")
def api_add_box():
    b = request.get_json(force=True)
    det = STORE.add_box(b["image_id"], b["x1"], b["y1"], b["x2"], b["y2"])
    if not det:
        return jsonify({"error": "box too small or image not found"}), 400
    return jsonify({"ok": True, "detection": {
        "det_index": det["det_index"], "bbox": det["bbox"], "det_conf": None,
        "species_pred": "manual", "species_conf": None, "label": "", "manual": True}})


@app.post("/api/delete_box")
def api_delete_box():
    b = request.get_json(force=True)
    ok = STORE.delete_box(b["image_id"], int(b["det_index"]))
    if not ok:
        return jsonify({"error": "not a manual box"}), 400
    done, total = STORE.progress()
    return jsonify({"ok": True, "done": done, "total": total})


@app.post("/api/export")
def api_export():
    return jsonify(STORE.export())


# ---------------------------------------------------------------------------
# Single-page front end.  Vanilla JS, no build step.
# ---------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>OTTER · review</title>
<style>
  :root{
    --bg:#11130f; --panel:#1b1e17; --panel2:#23271d; --line:#34392b;
    --ink:#eef0e6; --mut:#9aa087; --accent:#c8a24a; --accent2:#7d9b5a;
    --buck:#c8a24a; --doe:#7d9b5a; --fawn:#b8743a; --warn:#8a6a3a;
    --r:10px; --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  header{display:flex;align-items:baseline;gap:16px;padding:12px 18px;
    border-bottom:1px solid var(--line);background:var(--panel)}
  header h1{font:600 16px var(--mono);letter-spacing:.14em;margin:0;color:var(--accent)}
  header .sub{color:var(--mut);font-size:13px}
  .bar{flex:1;height:6px;background:var(--panel2);border-radius:3px;overflow:hidden;max-width:340px}
  .bar > i{display:block;height:100%;background:var(--accent2);width:0}
  header .count{font:13px var(--mono);color:var(--mut)}
  button{font:inherit;cursor:pointer;border:1px solid var(--line);
    background:var(--panel2);color:var(--ink);border-radius:8px;padding:6px 12px}
  button:hover{border-color:var(--accent)}
  button.primary{background:var(--accent);color:#1a1a14;border-color:var(--accent);font-weight:600}
  main{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(360px,1fr);
    gap:1px;background:var(--line);height:calc(100vh - 53px)}
  .stage,.side{background:var(--bg);overflow:auto;padding:18px}
  .frame{position:relative;display:inline-block;max-width:100%}
  .frame img{display:block;max-width:100%;height:auto;border-radius:var(--r)}
  .box{position:absolute;border:2px solid var(--accent);border-radius:3px;
    box-shadow:0 0 0 1px #0008;pointer-events:none}
  .box.sel{border-color:#fff;box-shadow:0 0 0 2px var(--accent)}
  .box.manual{border-color:#56b6c2;border-style:dashed}
  .box.manual b{background:#56b6c2}
  .box b{position:absolute;top:-19px;left:-2px;font:11px var(--mono);
    background:var(--accent);color:#1a1a14;padding:0 5px;border-radius:3px}
  .frame.drawing{cursor:crosshair}
  .frame.drawing img{user-select:none}
  #rubber{position:absolute;border:2px dashed #56b6c2;background:#56b6c233;
    pointer-events:none;display:none}
  .nav button.on{background:#56b6c2;color:#0c1416;border-color:#56b6c2;font-weight:600}
  .det.manual{border-color:#56b6c2}
  .det .rm{margin-left:auto;border-color:var(--warn);color:#d7a86a;font-size:12px;padding:3px 8px}
  .det .rm:hover{border-color:#c4623a;color:#e89a78}
  .nav{display:flex;gap:8px;align-items:center;margin-bottom:14px}
  .nav .id{font:14px var(--mono);color:var(--accent)}
  .det{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
    padding:12px;margin-bottom:12px}
  .det.sel{border-color:var(--accent)}
  .det .top{display:flex;gap:12px;margin-bottom:10px}
  .det .crop{width:120px;height:120px;object-fit:cover;border-radius:8px;
    background:var(--panel2);flex:none}
  .det .meta{font-size:13px;color:var(--mut)}
  .det .meta .guess{color:var(--ink)}
  .grp{margin:8px 0 4px;font:11px var(--mono);letter-spacing:.1em;color:var(--mut)}
  .opts{display:flex;flex-wrap:wrap;gap:6px}
  .opts button{padding:5px 10px;font-size:13px}
  .opts button.on[data-v=buck]{background:var(--buck);color:#1a1a14;border-color:var(--buck)}
  .opts button.on[data-v=doe]{background:var(--doe);color:#10130c;border-color:var(--doe)}
  .opts button.on[data-v=fawn]{background:var(--fawn);color:#160d06;border-color:var(--fawn)}
  .opts button.on{background:var(--accent2);color:#10130c;border-color:var(--accent2);font-weight:600}
  .filmstrip{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
  .filmstrip a{font:11px var(--mono);padding:2px 6px;border:1px solid var(--line);
    border-radius:5px;color:var(--mut);text-decoration:none}
  .filmstrip a.cur{border-color:var(--accent);color:var(--accent)}
  .filmstrip a.done{color:var(--accent2)}
  .hint{color:var(--mut);font-size:12px;margin-top:10px}
  kbd{font:11px var(--mono);background:var(--panel2);border:1px solid var(--line);
    border-radius:4px;padding:1px 5px}
  .toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);
    background:var(--panel2);border:1px solid var(--accent);color:var(--ink);
    padding:10px 16px;border-radius:8px;opacity:0;transition:opacity .2s;font-size:13px}
  .toast.show{opacity:1}
</style></head>
<body>
<header>
  <h1>OTTER</h1>
  <span class="sub">stage 1 · review &amp; label</span>
  <div class="bar"><i id="pbar"></i></div>
  <span class="count" id="pcount">—</span>
  <span style="flex:1"></span>
  <button id="export" class="primary">Export dataset</button>
</header>
<main>
  <section class="stage">
    <div class="nav">
      <button id="prev">&larr; Prev</button>
      <button id="next">Next &rarr;</button>
      <button id="draw" title="Draw a box the detector missed">+ Draw box</button>
      <span class="id" id="imgid"></span>
    </div>
    <div class="frame" id="frame"><div id="rubber"></div></div>
    <div class="filmstrip" id="strip"></div>
    <div class="hint">Hover a box or crop to link them.
      Keys: <kbd>&larr;</kbd>/<kbd>&rarr;</kbd> change image,
      <kbd>1</kbd>–<kbd>4</kbd> label the focused deer crop buck/doe/fawn/deer?,
      <kbd>b</kbd> toggle draw mode. Drag on the frame to add a box the detector
      missed; <kbd>Esc</kbd> cancels.</div>
  </section>
  <section class="side" id="side"></section>
</main>
<div class="toast" id="toast"></div>

<script>
let STATE=null, CUR=0, IMG=null, FOCUS=0;
let FRAMEIMG=null, DRAW=false, dragging=false, startX=0, startY=0;
const $=s=>document.querySelector(s);
const toast=(m)=>{const t=$('#toast');t.textContent=m;t.classList.add('show');
  clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),1400);};

async function boot(){
  STATE=await (await fetch('/api/state')).json();
  drawProgress(STATE.done,STATE.total);
  await load(0);
  buildStrip();
}
function drawProgress(done,total){
  $('#pbar').style.width=(total?100*done/total:0)+'%';
  $('#pcount').textContent=done+' / '+total+' detections';
}
function buildStrip(){
  const s=$('#strip');s.innerHTML='';
  STATE.images.forEach((im,i)=>{
    const a=document.createElement('a');a.textContent=im.image_id;
    if(i===CUR)a.className='cur';
    else if(im.n_det&&im.n_labeled===im.n_det)a.className='done';
    a.onclick=()=>load(i);s.appendChild(a);
  });
}
async function load(i){
  if(i<0||i>=STATE.images.length)return;
  CUR=i;FOCUS=0;
  const id=STATE.images[i].image_id;
  IMG=await (await fetch('/api/image/'+encodeURIComponent(id))).json();
  $('#imgid').textContent=id+'  ·  '+IMG.detections.length+' detections';
  renderFrame();renderSide();buildStrip();
}
function renderFrame(){
  const f=$('#frame');f.innerHTML='';
  const rubber=document.createElement('div');rubber.id='rubber';f.appendChild(rubber);
  const img=new Image();FRAMEIMG=img;img.src='/img/full/'+encodeURIComponent(IMG.image_id);
  const drawBoxes=()=>{
    f.querySelectorAll('.box').forEach(e=>e.remove());
    const sx=img.clientWidth/IMG.width, sy=img.clientHeight/IMG.height;
    IMG.detections.forEach((d,k)=>{
      const b=document.createElement('div');
      b.className='box'+(k===FOCUS?' sel':'')+(d.manual?' manual':'');
      b.style.left=(d.bbox[0]*sx)+'px';b.style.top=(d.bbox[1]*sy)+'px';
      b.style.width=((d.bbox[2]-d.bbox[0])*sx)+'px';
      b.style.height=((d.bbox[3]-d.bbox[1])*sy)+'px';
      const tag=document.createElement('b');tag.textContent=(d.label||(d.manual?'manual':'#'+k));
      b.appendChild(tag);b.dataset.k=k;f.appendChild(b);
    });
  };
  img.onload=drawBoxes;
  f.appendChild(img);
  f.classList.toggle('drawing',DRAW);
  if(img.complete)setTimeout(drawBoxes,0);
}
function group(){
  const g={};STATE.classes.forEach(c=>{(g[c.group]=g[c.group]||[]).push(c);});return g;}
function renderSide(){
  const side=$('#side');side.innerHTML='';
  const groups=group();
  IMG.detections.forEach((d,k)=>{
    const card=document.createElement('div');card.className='det'+(k===FOCUS?' sel':'')+(d.manual?' manual':'');
    card.onmouseenter=()=>{FOCUS=k;markFocus();};
    const conf=d.det_conf!=null?(d.det_conf*100).toFixed(0)+'%':'—';
    const guess=d.manual?'manually added':
      (d.species_pred&&d.species_pred!=='animal'?d.species_pred:'animal (unlabeled)');
    card.innerHTML=`<div class="top">
        <img class="crop" src="/img/crop/${encodeURIComponent(IMG.image_id)}/${d.det_index}">
        <div class="meta">box #${k}<br>detector conf <span class="guess">${conf}</span>
          <br>guess: <span class="guess">${guess}</span></div>
      </div>`;
    if(d.manual){
      const rm=document.createElement('button');rm.className='rm';rm.textContent='✕ Remove';
      rm.onclick=(ev)=>{ev.stopPropagation();delBox(d.det_index);};
      card.querySelector('.top').appendChild(rm);
    }
    for(const gname in groups){
      const lab=document.createElement('div');lab.className='grp';lab.textContent=gname;card.appendChild(lab);
      const row=document.createElement('div');row.className='opts';
      groups[gname].forEach(c=>{
        const btn=document.createElement('button');btn.textContent=c.display;btn.dataset.v=c.value;
        if(d.label===c.value)btn.classList.add('on');
        btn.onclick=()=>setLabel(k,c.value);row.appendChild(btn);
      });
      card.appendChild(row);
    }
    side.appendChild(card);
  });
}
function markFocus(){
  document.querySelectorAll('.det').forEach((e,i)=>e.classList.toggle('sel',i===FOCUS));
  document.querySelectorAll('.box').forEach(e=>e.classList.toggle('sel',+e.dataset.k===FOCUS));
}
async function setLabel(k,value){
  const d=IMG.detections[k];
  const r=await (await fetch('/api/label',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({image_id:IMG.image_id,det_index:d.det_index,label:value})})).json();
  d.label=value;drawProgress(r.done,r.total);
  // keep cached strip/state counts roughly in sync
  const im=STATE.images[CUR];im.n_labeled=IMG.detections.filter(x=>x.label).length;
  renderSide();renderFrame();buildStrip();
}
$('#prev').onclick=()=>load(CUR-1);
$('#next').onclick=()=>load(CUR+1);
$('#draw').onclick=()=>setDraw(!DRAW);
$('#export').onclick=async()=>{
  const r=await (await fetch('/api/export',{method:'POST'})).json();
  const n=Object.values(r.per_class).reduce((a,b)=>a+b,0);
  toast('Exported '+n+' crops to dataset/ and wrote otter_counts.csv');
};

function setDraw(on){DRAW=on;$('#draw').classList.toggle('on',on);
  $('#frame').classList.toggle('drawing',on);
  toast(on?'Draw mode on — drag a box around the missed animal':'Draw mode off');}
function imgPoint(e){
  const r=FRAMEIMG.getBoundingClientRect();
  let x=Math.max(0,Math.min(r.width,e.clientX-r.left));
  let y=Math.max(0,Math.min(r.height,e.clientY-r.top));
  return {x,y,r};
}
function initDraw(){
  const f=$('#frame');
  f.addEventListener('mousedown',e=>{
    if(!DRAW||!FRAMEIMG)return; e.preventDefault();
    dragging=true; const p=imgPoint(e); startX=p.x; startY=p.y;
    const rb=$('#rubber'); rb.style.display='block';
    rb.style.left=startX+'px'; rb.style.top=startY+'px'; rb.style.width='0px'; rb.style.height='0px';
  });
  window.addEventListener('mousemove',e=>{
    if(!dragging)return; const p=imgPoint(e); const rb=$('#rubber');
    rb.style.left=Math.min(startX,p.x)+'px'; rb.style.top=Math.min(startY,p.y)+'px';
    rb.style.width=Math.abs(p.x-startX)+'px'; rb.style.height=Math.abs(p.y-startY)+'px';
  });
  window.addEventListener('mouseup',async e=>{
    if(!dragging)return; dragging=false;
    $('#rubber').style.display='none';
    const p=imgPoint(e), r=p.r;
    const sx=IMG.width/r.width, sy=IMG.height/r.height;
    const x1=Math.min(startX,p.x)*sx, y1=Math.min(startY,p.y)*sy;
    const x2=Math.max(startX,p.x)*sx, y2=Math.max(startY,p.y)*sy;
    if(Math.abs(x2-x1)<5||Math.abs(y2-y1)<5)return;
    const res=await (await fetch('/api/add_box',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({image_id:IMG.image_id,x1,y1,x2,y2})})).json();
    if(res.error){toast(res.error);return;}
    IMG=await (await fetch('/api/image/'+encodeURIComponent(IMG.image_id))).json();
    FOCUS=IMG.detections.length-1;
    STATE=await (await fetch('/api/state')).json();
    drawProgress(STATE.done,STATE.total);
    renderFrame();renderSide();buildStrip();
    toast('Box added — now label it');
  });
}
async function delBox(det_index){
  const r=await (await fetch('/api/delete_box',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({image_id:IMG.image_id,det_index})})).json();
  if(r.error){toast(r.error);return;}
  IMG=await (await fetch('/api/image/'+encodeURIComponent(IMG.image_id))).json();
  FOCUS=Math.max(0,Math.min(FOCUS,IMG.detections.length-1));
  drawProgress(r.done,r.total);
  const im=STATE.images[CUR];im.n_det=IMG.detections.length;
  im.n_labeled=IMG.detections.filter(x=>x.label).length;
  renderFrame();renderSide();buildStrip();
  toast('Box removed');
}

document.addEventListener('keydown',e=>{
  if(e.key==='ArrowRight'){load(CUR+1);}
  else if(e.key==='ArrowLeft'){load(CUR-1);}
  else if(e.key==='b'||e.key==='B'){setDraw(!DRAW);}
  else if(e.key==='Escape'){if(dragging){dragging=false;$('#rubber').style.display='none';}else setDraw(false);}
  else if(['1','2','3','4'].includes(e.key)&&IMG&&IMG.detections[FOCUS]){
    setLabel(FOCUS,['buck','doe','fawn','deer_unknown'][+e.key-1]);
  }
});
initDraw();
boot();
</script>
</body></html>"""


def main():
    global STORE
    ap = argparse.ArgumentParser(description="OTTER review GUI.")
    ap.add_argument("--work", default=str(PROJECT_ROOT / "otter_work"),
                    help="Folder produced by detect.py (holds otter_detections.json + crops/). "
                         "Default: <repo>/otter_work")
    ap.add_argument("--images", default=str(PROJECT_ROOT / "data"),
                    help="Root of your image folders. Used to relocate frames by "
                         "filename if they've been moved since detection. Default: <repo>/data")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    STORE = Store(args.work, args.images)
    done, total = STORE.progress()
    rec = STORE.reconciled
    if rec["fixed"]:
        print(f"Relocated {rec['fixed']} image(s) that had moved and updated their "
              f"paths in otter_detections.json (labels and crops untouched).")
    if rec["missing"]:
        print(f"WARNING: {len(rec['missing'])} image file(s) could not be found under "
              f"{STORE.images_root} — full frames won't display for these: "
              f"{', '.join(rec['missing'][:5])}{' ...' if len(rec['missing']) > 5 else ''}")
    print(f"Loaded {len(STORE.images)} images, {total} detections ({done} already labeled).")
    print(f"Open http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
