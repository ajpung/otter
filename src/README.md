# OTTER · Stage 1 — find the deer, label the deer

This is the front half of the OTTER pipeline: turn a folder of raw trail-cam
images into labeled, cropped animals you can (a) hand to agemydeer for aging and
(b) use to train your own buck/doe/fawn classifier later.

It is **three small scripts**, not three models:

| Script | What it does | Model? |
|---|---|---|
| `detect.py` | Runs **MegaDetector** over your images, boxes every animal, saves a crop per box, writes `otter_detections.json`. | Pretrained, you never train it. |
| `merge_speciesnet.py` *(optional)* | Adds **SpeciesNet**'s species guess to each box as a pre-fill. | Pretrained, optional. |
| `review_app.py` | A local web GUI: shows each frame with its boxes and a crop per animal, you click **buck / doe / fawn / turkey / …**. Saves to CSV; exports a sorted dataset + an OTTER-schema counts sheet. | None — *you* are the labeler. |

The only thing that needs *training* is the buck/doe/fawn classifier, and that's
the **next** phase — it learns from the labeled dataset this tool produces.

---

## Why this shape

- **Detection is solved.** MegaDetector is trained on millions of camera-trap
  frames (including night/IR) and finds animals out of the box. Training your
  own detector would need thousands of hand-drawn boxes; you don't have to.
- **MegaDetector doesn't name species, and no model does sex/age.** So species
  is an optional pre-fill (SpeciesNet), and buck/doe/fawn is always human. The
  GUI exists to make that human step fast.
- **Your Excel counts weren't wasted** — they're the wrong *granularity* for
  cropping (counts, not box locations), but they're great for finding clean
  single-animal frames to label first, and for sanity-checking the model's
  output against your tallies.

---

## Install

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

First `detect.py` run downloads the MegaDetector weights automatically (a few
hundred MB). A GPU is used if present; CPU works (use a `-c` compact model).

## Run it

```bash
# 1. Detect + crop every animal
python detect.py --images /path/to/trailcam/folder --out ./otter_work

# 2. (optional) species pre-fill, geofenced to Indiana
python -m speciesnet.scripts.run_md_and_speciesnet \
    --folders /path/to/trailcam/folder \
    --predictions_json speciesnet_preds.json \
    --country USA --admin1_region IN
python merge_speciesnet.py --detections otter_work/otter_detections.json \
                           --speciesnet speciesnet_preds.json

# 3. Label in the browser
python review_app.py --work ./otter_work
#    open http://127.0.0.1:5000  — label, then click "Export dataset"
```

### In the GUI
- Each frame shows MegaDetector's boxes; the right panel has one crop per box.
- Click a species/sex button under a crop to label it. Saves instantly.
- Keys: `←`/`→` change image; `1`–`4` label the focused deer crop
  buck / doe / fawn / deer(?); `b` toggles draw mode; `Esc` cancels.
- **Missed an animal?** Click **+ Draw box** (or press `b`), then drag a
  rectangle around it on the frame. It's cropped from the original image and
  added as a detection (dashed teal box) you can label like any other — useful
  for the poses MegaDetector misses (climbing animals, odd angles, occlusion).
  Manual boxes have a **✕ Remove** button; detector boxes can't be deleted
  (hide a bad one by labeling it "Not an animal" instead).
- **Export dataset** sorts crops into `dataset/<label>/` and writes
  `otter_counts.csv` in your existing schema (dates parsed from the filename).

## Outputs (in `--work`)

```
otter_detections.json     boxes + crop paths + species pre-fill
crops/                     one cropped image per detection
otter_labels.csv          one row per detection with your label (resume-safe)
dataset/<label>/*.jpg      crops sorted by label  ← train the classifier on this
otter_counts.csv          per-image counts, OTTER schema  ← drop-in for your sheet
```

## Customizing

- **Species list:** edit `CLASSES` at the top of `review_app.py`. The
  `LABEL_TO_COLUMNS` map below it controls how labels roll up into the counts
  sheet (`Deer` = buck + doe + fawn + deer?).
- **Detector size/accuracy:** `--version MDV6-yolov10-c` (fast, CPU-friendly)
  through `MDV6-yolov10-e` (more accurate). `--threshold` filters weak boxes;
  small/distant animals get low scores — and those are also too small to age,
  so a higher threshold doubles as a "too far to bother" gate.

## How this connects to agemydeer

agemydeer ages on **body proportions**, so the crop you send it must not be
distorted. Don't stretch a tall deer box into a square — *pad* it. `detect.py`
has `--square-crops` (and a `pad_bbox_to_square()` helper) that expands the
short side symmetrically to make a square while keeping true proportions. Use
tight crops for *training* your classifier (default), and square-padded crops
when handing a confirmed buck to agemydeer in the live pipeline.

## Honest limitations

- MegaDetector misses very small/distant animals and odd angles — label a small
  sample and check recall on *your* cameras before trusting it at scale.
- SpeciesNet returns "animal" when unsure and won't distinguish sex/age; treat
  its guess as a hint only. Its JSON schema varies by version — if pre-fills
  don't attach, run `merge_speciesnet.py --debug` and adjust the field names.
- This is a single-user local tool (Flask dev server). Fine for labeling on your
  machine; not meant to be exposed to a network.
```
