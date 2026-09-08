# IBVAP — Technical Requirements Document (TRD)

## 1. Project Overview

**Project Name:** IBVAP — Intelligent Border Video Analytics Platform

**Project Type:** 100% software-based AI/CV surveillance platform

**Primary Objective:** Transform existing CCTV/IP-camera infrastructure into an intelligent surveillance system capable of detecting, tracking, identifying, understanding, prioritizing, and logging security-relevant events without requiring dedicated surveillance hardware.

### Core Idea

```text
Existing CCTV / Recorded Video
          ↓
Video Ingestion
          ↓
Object Detection
          ↓
Multi-Object Tracking
          ↓
Spatial + Temporal Analysis
          ↓
Identity Analysis
          ↓
Vehicle / ANPR Analysis
          ↓
Behaviour Understanding
          ↓
Context Fusion
          ↓
Risk Scoring
          ↓
Alert + Event Logging
          ↓
Dashboard
```

---

# 2. Problem Statement

Traditional CCTV systems primarily provide video recording and live monitoring. Continuous observation depends heavily on human operators, which can lead to missed events, delayed responses, and alert fatigue.

IBVAP addresses this limitation by using AI and computer vision software over existing CCTV streams. The platform converts low-level detections into higher-level, explainable security events such as:

- Person entering a restricted area
- Fence crossing
- Prolonged loitering
- Movement in an unusual direction
- Night-time movement
- Unknown person near a restricted zone
- Suspicious vehicle movement
- Number-plate identification
- Multiple contextual conditions occurring together

**Hardware is explicitly out of scope.** The platform works with existing CCTV/IP-camera streams or recorded video.

---

# 3. Goals

## 3.1 Primary Goals

1. Ingest live RTSP/IP CCTV streams and recorded video.
2. Detect people, vehicles and relevant objects.
3. Track objects across video frames.
4. Maintain persistent tracking IDs.
5. Define virtual restricted zones.
6. Detect zone entry and virtual-fence crossing.
7. Analyze movement direction and trajectories.
8. Detect loitering using temporal and trajectory information.
9. Detect night-time movement.
10. Detect and recognize faces where legally and ethically appropriate.
11. Detect vehicle number plates and perform OCR.
12. Fuse spatial, temporal, identity and vehicle context.
13. Calculate interpretable risk scores.
14. Generate prioritized alerts.
15. Store events and evidence.
16. Provide a real-time monitoring dashboard.
17. Evaluate the system experimentally using public datasets and controlled videos.

## 3.2 Secondary Goals

- Reduce redundant alerts.
- Provide explainable reasons for each alert.
- Support multiple cameras.
- Allow camera-specific configuration.
- Keep the platform modular and scalable.
- Run on standard computing hardware without specialized surveillance hardware.

---

# 4. Scope

## In Scope

- CCTV/RTSP video ingestion
- Recorded-video analysis
- Person detection
- Vehicle detection/classification
- Multi-object tracking
- Virtual fencing
- Restricted-zone detection
- Direction analysis
- Loitering detection
- Night movement detection
- Face detection and consent-based recognition
- ANPR
- Behaviour analysis
- Context fusion
- Risk scoring
- Alert generation
- Event database
- Dashboard
- Experimental evaluation

## Out of Scope

- Manufacturing or installing CCTV cameras
- Physical fences
- Sensors
- Drones
- Raspberry Pi
- Arduino
- Jetson/edge hardware
- Access-control hardware
- Weapons or autonomous physical response
- Automated enforcement decisions

---

# 5. Target Users

- Security monitoring operators
- Border/security command centres
- CCTV monitoring teams
- Security administrators
- System administrators
- Researchers developing intelligent surveillance systems

---

# 6. Functional Requirements

## FR-01: Video Input

The system shall accept:

- RTSP/IP-camera streams
- MP4/AVI/MKV or equivalent recorded video
- Multiple camera streams where computational resources permit

The system shall display connection status and handle stream interruptions gracefully.

## FR-02: Object Detection

The system shall detect at minimum:

- Person
- Car
- Motorcycle
- Bus
- Truck

Additional classes may be supported depending on the selected detector.

## FR-03: Multi-Object Tracking

The system shall:

- Assign a unique temporary track ID to detected objects.
- Maintain IDs across frames.
- Store trajectories.
- Handle temporary occlusion as far as supported by the tracker.
- Provide track history for behavioural analysis.

## FR-04: Restricted Zones

The operator shall be able to define polygonal regions such as:

- Restricted zone
- Buffer zone
- Safe zone
- Entry/exit zone

The system shall determine whether a tracked object enters or crosses a configured region.

## FR-05: Virtual Fence

The system shall support a virtual line/polygon representing a security boundary.

Events shall include:

- Approaching boundary
- Crossing boundary
- Direction of crossing
- Crossing time
- Track ID

## FR-06: Direction Analysis

The system shall estimate movement direction using object trajectory history.

Possible categories:

- Toward restricted zone
- Away from restricted zone
- Left/right
- Forward/backward
- Configured camera-specific directions

## FR-07: Loitering Detection

The system shall identify objects that remain in a defined region longer than a configured threshold.

Relevant features:

- Track duration
- Zone occupancy duration
- Movement distance
- Average speed
- Position variance

## FR-08: Night Movement

The system shall identify movement occurring during configured night hours and/or under low-illumination conditions.

Night status shall be treated as context rather than automatically meaning suspicious behaviour.

## FR-09: Face Analysis

The system may perform:

1. Face detection
2. Face alignment
3. Embedding generation
4. Matching against an authorized/consented gallery

The system shall support:

- Known/authorized identity
- Unknown identity
- Low-confidence/uncertain identity

Face recognition shall not be treated as infallible identification.

## FR-10: ANPR

The ANPR subsystem shall perform:

```text
Vehicle Detection
      ↓
License Plate Detection
      ↓
Plate Crop
      ↓
Image Preprocessing
      ↓
OCR
      ↓
Plate Text
      ↓
Confidence + Timestamp
```

The system shall retain OCR confidence and allow uncertain results to be flagged.

## FR-11: Behaviour Engine

The behaviour engine shall combine detections, tracking and context to detect:

- Restricted-zone intrusion
- Fence crossing
- Loitering
- Wrong/unexpected direction
- Night movement
- Abnormal movement
- Suspicious vehicle behaviour
- Combined suspicious events

## FR-12: Context Fusion

The platform shall combine multiple observations.

Example:

```text
Unknown person
      +
Night time
      +
Restricted zone
      +
Long dwell time
      +
Movement toward boundary
      ↓
High-risk event
```

The system shall avoid generating a separate high-priority alert for every individual low-level observation when those observations describe the same event.

## FR-13: Risk Engine

The initial interpretable risk model shall use:

```text
R = w1*S + w2*T + w3*B + w4*I + w5*V
```

Where:

- S = spatial risk
- T = temporal risk
- B = behavioural risk
- I = identity-related context
- V = vehicle-related context
- w1...w5 = configurable weights

The risk engine shall produce:

- Low
- Medium
- High
- Critical

risk categories.

A learned event-level risk classifier may later be compared against the rule-based baseline.

## FR-14: Alert Engine

Alerts shall contain:

- Alert ID
- Camera ID
- Timestamp
- Event type
- Track ID
- Risk level
- Risk score
- Triggering conditions
- Snapshot/evidence where available
- Related plate/identity result where available

## FR-15: Dashboard

The dashboard shall provide:

- Live video
- Camera status
- Bounding boxes
- Track IDs
- Restricted zones
- Current alerts
- Alert history
- Event statistics
- Search/filter functionality
- Event details
- Evidence snapshots

## FR-16: Event Database

The system shall store:

- Cameras
- Tracks
- Events
- Alerts
- Plate results
- Identity results
- Risk scores
- Timestamps
- Evidence paths

SQLite shall be used initially. PostgreSQL may be used for a larger deployment.

---

# 7. Non-Functional Requirements

## NFR-01 Performance

The system should support near-real-time processing depending on:

- Model size
- Resolution
- GPU/CPU
- Number of cameras
- Tracking complexity

## NFR-02 Reliability

The system shall:

- Recover from temporary stream failures.
- Avoid application crashes from malformed frames.
- Log processing errors.
- Preserve important event records.

## NFR-03 Explainability

Every high-priority alert should provide human-readable reasons.

Example:

```text
HIGH RISK

Reason:
- Person detected
- Entered restricted zone
- Night-time context
- Loitering > configured threshold
- Moving toward boundary
```

## NFR-04 Scalability

The architecture shall separate:

- Ingestion
- Detection
- Tracking
- Behaviour
- Fusion
- Risk
- Dashboard
- Storage

so that individual components can be upgraded independently.

## NFR-05 Security

The platform shall:

- Authenticate dashboard users where required.
- Protect stored event data.
- Restrict access to face/identity information.
- Log administrative actions.
- Avoid unnecessary storage of personal information.

**As built:**

- Supabase JWT auth on every `/api/*` route and on the alert WebSocket; role guards
  (`require_auth`, `require_admin`).
- Middleware: TrustedHost + CORS allow-lists, `slowapi` rate limiting, security headers
  (XSS / clickjacking / MIME-sniffing), request logging with client IP, input validation
  (path traversal, injection patterns, upload-size cap).
- No fixed default credentials — seed passwords come from `IBVAP_ADMIN_PASSWORD` /
  `IBVAP_OPERATOR_PASSWORD`, else a random password is generated and logged once.
- Evidence integrity: SHA-256 hash of every snapshot stored with its event/alert.
- Audit log (`/api/audit`, admin-only): action, username, IP, timestamp.
- Client-side session timeout after 30 min inactivity (`useSessionTimeout`).
- API docs (`/docs`, `/openapi.json`) disabled in `production` mode.
- Secrets read from environment only; DB URL passwords masked in logs.

## NFR-06 Privacy

Face recognition shall use only lawfully obtained/consented enrollment data for research and demonstration.

The system shall support configurable retention and deletion of stored evidence.

---

# 8. System Architecture

```text
+----------------------------+
| Existing CCTV / Video     |
| RTSP / Recorded Files     |
+-------------+--------------+
              |
              v
+----------------------------+
| Video Ingestion Layer      |
| OpenCV / FFmpeg            |
+-------------+--------------+
              |
              v
+----------------------------+
| Object Detection           |
| YOLO-based detector        |
+-------------+--------------+
              |
              v
+----------------------------+
| Multi-Object Tracking      |
| ByteTrack                  |
+-------------+--------------+
              |
       +------+------+
       |             |
       v             v
Spatial Analysis   Temporal Analysis
       |             |
       +------+------+
              |
              v
+----------------------------+
| Identity Analysis          |
| Face Detection + ArcFace   |
+----------------------------+
              |
              v
+----------------------------+
| Vehicle / ANPR             |
| Plate Detector + OCR       |
+-------------+--------------+
              |
              v
+----------------------------+
| Behaviour Engine           |
+-------------+--------------+
              |
              v
+----------------------------+
| Context Fusion Layer       |
+-------------+--------------+
              |
              v
+----------------------------+
| Risk Engine                |
| Rules + Optional ML        |
+-------------+--------------+
              |
       +------+------+
       |             |
       v             v
 Alert Engine     Event DB
       |
       v
+----------------------------+
| Web Dashboard              |
| FastAPI/Flask + HTML/JS    |
+----------------------------+
```

---

# 9. Technology Stack

> This section reflects the stack **as implemented**. Where an earlier design choice
> was superseded, both are noted.

## 9.0 Language & Core CV

- Python 3.10+
- OpenCV (`opencv-python`) for capture, frame ops, drawing
- NumPy, Pandas, `shapely` (zone/fence geometry), `scikit-learn`

## 9.1 Deep Learning / Perception

| Task | Implementation |
|---|---|
| Framework | PyTorch, `torchvision` |
| Object detection (live pipeline) | Ultralytics **YOLOv8n**, COCO classes `[0,2,3,5,7]` (person, car, motorcycle, bus, truck) — `src/detection/detector.py` |
| Object detection (custom) | YOLOv8 trained on a merged **91-class border/military dataset** — see **§9A**. Trained via `scripts/train_yolo.py`; **not yet loaded by the live pipeline** |
| Stage-2 fine-grained classifier | **ResNet-50** (ImageNet-pretrained, custom head), fine-tuned on cropped detections — `scripts/train_classifier.py`, `scripts/inference_two_stage.py`. Experimental |
| Multi-object tracking | **ByteTrack** via the `supervision` library (`sv.ByteTrack`) — `src/tracking/tracker.py` |
| Face (module only) | ArcFace-style embeddings + cosine matching against a JSON gallery — `src/face/`. **Not called from the pipeline** |
| Dominant colour | HSV histogram heuristic — `src/features/color_extractor.py` |
| ANPR OCR | `pytesseract` + contour heuristics with a mock fallback — `src/features/anpr.py`. **TRD target remains PaddleOCR / EasyOCR**; treat current output as experimental |

## 9.2 Backend Service

- **FastAPI** + Uvicorn (Flask was dropped)
- WebSocket endpoint `/ws/alerts` for real-time alert push (JWT-authenticated via query param)
- Middleware stack: `TrustedHostMiddleware`, `CORSMiddleware`, `slowapi` rate limiting (`200/min` default),
  `SecurityHeadersMiddleware`, `RequestLoggingMiddleware` (IP + audit trail), `InputValidationMiddleware`
  (path-traversal / injection / upload-size checks)
- Interactive docs auto-disabled when `IBVAP_ENV=production`

## 9.3 Frontend (operator dashboard)

- **React 19 + TypeScript + Vite** (the "HTML/CSS/JS" plan is superseded)
- **Tailwind CSS v4**, React Router 7
- ApexCharts (`react-apexcharts`), Grid.js, Leaflet / `react-leaflet` (Map view)
- `@supabase/supabase-js` for auth session + token handling
- Served separately from the backend (own Vite dev server / nginx container)

## 9.4 Data & Auth

| Concern | Implementation |
|---|---|
| Runtime data store | **SQLite** via SQLAlchemy 2.x (`sqlite:///./ibvap.db`), `DATABASE_URL`-overridable. Models in `src/database/models.py`, access via `Repository` |
| Auth | **Supabase Auth** — JWT issued by Supabase, verified locally in `src/api/auth.py` with `SUPABASE_JWT_SECRET` (HS256); Supabase API fallback |
| User profiles / RBAC | `user_profiles` table + Row-Level Security policies in `supabase/migrations/`. Route guards: `require_auth`, `require_admin` |
| Local `users` / `audit_logs` tables | SQLAlchemy tables used for the seeded `admin`/`operator` rows and audit logging. API request auth itself is Supabase JWT, not these rows |
| Postgres | The `supabase/migrations` schema also defines `cameras/tracks/events/alerts/zones` mirrors + realtime publication. **Not currently written by the pipeline** — consolidation is an open decision (§17) |

## 9.5 Evaluation / Visualisation

- Matplotlib for plots
- Metric set unchanged: Precision, Recall, F1, mAP@50, mAP@50:95, FPS, MOTA, IDF1, HOTA,
  ID switches, FAR/FRR, character/full-plate accuracy, ROC-AUC, alert-reduction, detection latency
- **Status:** `backend/outputs/metrics/` is currently empty — experiments (§21) not yet run

---

# 9A. Coarse Detection Taxonomy (border/military aware)

> **Superseded design note.** An earlier iteration trained a **91-class** detector covering 73
> fine-grained military aircraft types (F-16 vs F-18 vs Rafale …). That was abandoned: on the
> project's 6 GB budget a nano/small backbone cannot separate near-identical airframes, all 73
> types combined held < 12 k boxes against Person's 350 k, and the surveillance logic never
> consumes the airframe type. Fine-grained type ID moved to **Phase 2** (§9B).

## 9A.1 Rationale

PS 26187 is border surveillance. Generic COCO classes cannot distinguish a tank from a truck or
flag an aircraft near a border, so the taxonomy is extended beyond person/vehicle — but only to
the granularity the product actually reasons about.

## 9A.2 Coarse classes (13)

Defined once in **`backend/ml/taxonomy.py`**, which is the single source of truth for the data
scripts *and* the live pipeline.

| id | class | sourced from |
|---|---|---|
| 0 | `person` | Person, Soldier, thermal head/face boxes, MOT17, VIRAT, people_det |
| 1 | `car` | Car (incl. VIRAT vehicles) |
| 2 | `bus` | Bus |
| 3 | `truck` | Forklift / heavy goods |
| 4 | `motorcycle` | Motorcycle |
| 5 | `bicycle` | Bicycle |
| 6 | `license_plate` | License Plate Recognition v13 (Roboflow) |
| 7 | `military_ground_vehicle` | Tank / armour |
| 8 | `aircraft` | Generic Jet, Large Military Plane + 59 fixed-wing types |
| 9 | `helicopter` | AH64, CH47, Ka27, Ka52, Mi24, Mi28, UH60, V22, Z19 |
| 10 | `drone_uav` | MQ9, RQ4, TB2, TB001, WZ7 |
| 11 | `night_vision_object` | night-vision.v3i (12 IR sub-classes collapsed upstream — legacy catch-all) |
| 12 | `animal` | Dog, Cat, Bird, Horse, Cow, Sheep |

`taxonomy.FINE_TO_COARSE` maps every old 91-class id onto these; `taxonomy.normalize()` canonicalises
any model-supplied name (`"Car"`, `"License_Plate"`, `"Tank"`) to the lowercase vocabulary the
runtime already keys off.

## 9A.3 Dataset build pipeline

```text
unified_yolo (91-class, legacy)
        │  ml/remap_to_coarse.py      FINE_TO_COARSE + geometry cleaning; images hard-linked
        ▼
detector_yolo (13-class)
        │  scripts/add_plates.py      v13 plate set -> class 6, --limit for balance
        ▼
        │  scripts/make_clean_split.py   group by source image AND MOT/VIRAT clip
        ▼
configs/dataset_coarse.yaml + data/splits/{train,val}_coarse.txt
        │  ml/verify_dataset.py       histogram / parity / leak / box-size gate
        ▼
scripts/train_yolo.py  ->  ml/eval_detector.py (per-class mAP)
```

Legacy mergers (`merge_datasets.py`, `merge_military.py`, `add_external.py`,
`add_granular_external.py`, `fix_existing_labels.py`, `fix_labels_and_split.py`,
`download_plates.py`) are retired to `backend/scripts/legacy/` — see its README for why each failed.

## 9A.4 Class balance after remap

Instances in `detector_yolo` before the plate merge (517,414 boxes total):

| class | instances | | class | instances |
|---|---:|---|---|---:|
| person | 388,815 | | bicycle | 4,566 |
| night_vision_object | 48,839 | | truck | 2,181 |
| car | 46,853 | | motorcycle | 2,150 |
| aircraft | 12,979 | | helicopter | 1,000 |
| animal | 7,994 | | bus | 887 |
| license_plate | (added next) | | military_ground_vehicle | 682 |
| | | | drone_uav | 468 |

The collapse lifted the rare tail from 10–40 instances per class (old fine taxonomy) to 468–1,000.
Person still dominates at ~75 %; that is acceptable — person detection is the product's first
priority — and is mitigated by `copy_paste`/`mixup` augmentation rather than by discarding images.

## 9A.5 Training configuration (6 GB RTX 40-series)

| setting | value | reason |
|---|---|---|
| model | `yolo11s.pt` (fallback `yolov8s.pt`) | 13 classes is tractable for `s`; large mAP gain over `n` |
| imgsz | 640 | plates and distant objects are small; 480 loses them |
| batch | `-1` (auto-fit) | batch 2 gave unusably noisy BatchNorm/gradients |
| epochs / patience | 150 / 40 | converge with early-stop insurance |
| schedule | `cos_lr`, `close_mosaic=15` | standard finish-strong recipe |
| augmentation | `+mixup 0.10`, `copy_paste 0.15`, `degrees 5`, `scale 0.5` | copy-paste specifically lifts the rare military classes |
| cache | `disk` | the dataset volume is slow; large wall-clock win |
| env | `CUBLAS_WORKSPACE_CONFIG=:4096:8`, `deterministic=False` | cuDNN STREAM_MISMATCH workaround on RTX 40-series |

## 9A.6 Runtime integration

- `configs/thresholds.yaml → detection.weights_path` points at the trained `best.pt`. When set and
  present, `ObjectDetector` loads it, reads the model's own `names` map, and emits **all** classes
  (`detect_all=True`); `target_classes` then applies only to the stock COCO fallback model.
- `ObjectDetector` normalises every emitted name through `taxonomy.normalize()`.
- `MultiObjectTracker` no longer re-derives names from `COCO_TARGET_CLASSES`; it carries the name the
  detector attached to each `DetectionResult` (COCO map kept only as a fallback).
- Downstream consumers (`track_manager`, `detection_result.vehicle_count`, the ANPR gate in
  `pipeline._process_track`, `risk_classifier` features) already key off
  `person/car/bus/truck/motorcycle` and therefore need no change.

---

# 9B. Phase 2 — fine-grained two-stage refinement (designed, not built)

Stage 1 stays the coarse detector. A stage-2 classifier runs **only** on `aircraft`, `helicopter`,
`drone_uav` and `military_ground_vehicle` crops — never on person/vehicle — and returns the specific
type. This is where a cascade actually helps: detectors are weak at fine-grained discrimination, and
restricting the second stage prevents a mediocre classifier from degrading good person/vehicle calls.

Planned when it is picked up:

- **Backbone:** ConvNeXt-tiny or EfficientNetV2-S @ 288–384 px via `timm` (both beat ResNet-50 on
  fine-grained tasks).
- **Data:** train/val/**test** split grouped by source image; train on **YOLO-predicted crops** plus
  jittered GT crops to remove the GT-box vs detector-box domain shift; cap the oversampling ratio;
  merge or drop the ~15 types with < 40 images; log a per-class confusion matrix; temperature-scale
  so the refine threshold is meaningful.
- **Serving:** move `scripts/inference_two_stage.py::TwoStageDetector` into
  `src/detection/two_stage_detector.py` with guarded imports; batch a frame's crops into one forward
  pass; run stage 2 only every N frames per track; store the refined type on the `Track` via a
  side-channel (ByteTrack carries a single int `class_id` and cannot).
- **Config:** `detection.mode: two_stage` plus `classifier_weights` / `class_mapping` /
  `refine_threshold` keys in `thresholds.yaml`.

Known defects to fix in `scripts/train_classifier.py` when reviving it: the 5000-image cap combined
with an inverse-frequency `WeightedRandomSampler` oversamples a 10-image class ~500× per epoch
(guaranteed overfit), validation is 20 % of the *capped* pool so rare-class `val_acc` is pure noise,
there is no held-out test set, and three leaf folders (Soldier, Large_Military_Plane, License_Plate)
are empty. The `total_mem` → `total_memory` crash at line 276 has been fixed.

---

# 10. Dataset Strategy

The project shall NOT rely on one dataset for every task.

A modular dataset strategy will be used.

> **Implementation note (2026-09-08).** The detector currently in training does **not** use
> VIRAT as its training source. It is trained on a **merged 91-class border/military dataset**
> assembled from public detection sets + Roboflow exports (`backend/data/unified_yolo`,
> ~91 k train / ~10 k val images) — see §9A. VIRAT / MOT17 / UFPR-Planalto801 / BDD100K
> remain the intended **evaluation and tracking-benchmark** references and for a person/vehicle
> generalisation baseline. The dataset descriptions below (§10.1–§10.7) describe the evaluation
> plan, not the current training set.

## 10.1 Primary Dataset — VIRAT

**Purpose:** Main surveillance-video source.

Used for:

- Surveillance scene understanding
- People
- Vehicles
- Activities
- Event/activity analysis

**Priority:** Highest

## 10.2 UFPR-Planalto801

**Purpose:** Fixed-camera surveillance and person detection/tracking.

Used for:

- Person detection
- Tracking
- Trajectory evaluation

## 10.3 MOT17

**Purpose:** Multi-object pedestrian tracking benchmark.

Used for:

- Track ID consistency
- Trajectory evaluation
- Multi-object tracking

## 10.4 BDD100K

**Purpose:** Outdoor road/vehicle scenes.

Used for:

- Vehicle detection
- Person detection
- Vehicle tracking support
- Generalization testing

## 10.5 Face Dataset

A suitable public face-detection dataset may be used for detector development.

For recognition, use a small controlled, consented enrollment dataset.

## 10.6 ANPR Dataset

Use appropriate public license-plate datasets for development, followed by controlled evaluation using Indian-style plates.

The system shall NOT claim that a Brazilian/Chinese plate dataset alone proves reliable Indian ANPR performance.

## 10.7 Controlled IBVAP Dataset

The team shall create controlled CCTV-style videos containing:

- Normal movement
- Restricted-zone entry
- Fence crossing
- Loitering
- Wrong direction
- Night movement
- Vehicle movement
- Combined suspicious events

This dataset is essential for evaluating the actual IBVAP event-fusion layer.

---

# 11. Event-Level Dataset

The most important project-specific dataset shall be an event-level feature dataset.

Example schema:

```text
event_id
camera_id
timestamp
person_detected
vehicle_detected
night
restricted_zone
fence_crossing
loitering
unknown_identity
movement_toward_fence
duration_seconds
object_count
average_speed
distance_to_boundary
plate_detected
identity_confidence
risk_label
```

The dataset will support development and evaluation of the risk/context-fusion layer.

---

# 12. Dataset Splitting

For trainable models:

```text
70% Train
15% Validation
15% Test
```

For video datasets, splitting shall occur at the **video/sequence level**, not randomly at the frame level.

This prevents near-identical frames from the same video appearing in both training and testing.

> **Verified 2026-09-08 — the shipped `unified_yolo` split leaks badly.**
> `scripts/make_clean_split.py` was added to check and fix it. Findings on the raw export:
>
> - **Augmentation leak:** Roboflow augments each source image several times
>   (`<id>_jpg.rf.<hash>.jpg`) and scatters the copies across train *and* val.
>   **71.5 % of the val set** had a near-identical twin in train → val mAP is inflated.
> - **Missing labels (merge bug):** **100 % of `plate_*` images (19,828) have no label file
>   at all**, so class 7 *License Plate* has zero training instances and those images would
>   otherwise act as harmful negatives (68 `people` images likewise unlabeled).
> - ~9,500 images have an **empty** `.txt` — these are legitimate background negatives and are kept.
>
> `make_clean_split.py` produces a **non-destructive** corrected split without moving any file:
> `data/splits/{train,val}_clean.txt` + `configs/dataset_clean.yaml`. It re-partitions by
> **source image** (all augmentations of one source stay on one side), stratified per family,
> deterministic (seed 42): **73,575 train / 7,963 val (9.8 %)**, 0 source-key overlap.
> **Train and evaluate the detector with `--data configs/dataset_clean.yaml`**, not `dataset.yaml`.
>
> **Residual risk:** only frame-level ids are available, so frames from the same MOT/VIRAT/
> nightvis *clip* may still span the split. Group by clip if that metadata can be recovered.
>
> **Also to fix upstream:** re-run the plate-dataset conversion in the merge scripts so
> `License Plate` gets real labels; then regenerate the split.

---

# 13. Model Strategy

## 13.1 Object Detection

Use a pretrained YOLO-family model and benchmark lightweight variants before freezing the final model.

Selection criteria:

- mAP
- FPS
- Precision
- Recall
- Model size
- CPU/GPU performance

## 13.2 Tracking

Use ByteTrack as the primary tracker.

Evaluate using:

- HOTA
- IDF1
- MOTA
- ID switches

## 13.3 Face Recognition

Pipeline:

```text
Face Detection
      ↓
Alignment
      ↓
ArcFace Embedding
      ↓
Similarity Matching
      ↓
Identity / Unknown / Uncertain
```

## 13.4 ANPR

Pipeline:

```text
Vehicle
 ↓
Plate Detector
 ↓
Plate Crop
 ↓
Preprocessing
 ↓
OCR
 ↓
Text + Confidence
```

## 13.5 Behaviour

Use interpretable features first:

- Position
- Velocity
- Direction
- Duration
- Distance
- Zone occupancy
- Trajectory shape

A temporal ML model may be added if experiments show a meaningful improvement.

## 13.6 Risk Model

Two-stage research design:

### Baseline

Rule-based weighted risk score.

### Proposed Learning Model

Train an event-level ML classifier using fused contextual features.

Possible candidates:

- XGBoost
- Random Forest
- LightGBM
- MLP

The final model shall be selected based on validation performance and interpretability.

---

# 14. Core Novelty

IBVAP shall NOT be positioned simply as:

> YOLO + OCR + Face Recognition + Tracking

The principal research contribution is:

> **A context-aware hierarchical video intelligence framework that fuses object perception, tracking, identity, spatial context, temporal context and behavioural evidence to convert low-level CCTV observations into explainable and prioritized security events.**

## Novelty Pipeline

```text
Low-Level Perception
        ↓
Object + Identity Observations
        ↓
Trajectory Representation
        ↓
Spatial Context
        ↓
Temporal Context
        ↓
Behaviour Interpretation
        ↓
Multi-Event Context Fusion
        ↓
Risk Estimation
        ↓
Explainable Security Event
```

This hierarchical approach should be experimentally compared with isolated-module alerting.

---

# 15. Alert-Fusion Example

Instead of producing:

```text
Alert 1: Person detected
Alert 2: Night detected
Alert 3: Person in zone
Alert 4: Person moving
Alert 5: Loitering
```

IBVAP should generate:

```text
CRITICAL / HIGH RISK EVENT

Unknown person detected in restricted zone
during night-time conditions.

Supporting evidence:
- Person track ID: 27
- Restricted-zone entry: YES
- Loitering: 48 seconds
- Movement toward boundary: YES
- Identity: Unknown
```

This reduces alert flooding and gives operators contextual information.

---

# 16. Camera Context

Optional camera-specific profiles may be supported.

Example:

```text
Road Camera
→ Vehicle + ANPR priority

Fence Camera
→ Intrusion + trajectory priority

Entrance Camera
→ Face + vehicle identity priority

Restricted-Zone Camera
→ Loitering + intrusion priority
```

This allows the same platform to behave differently according to camera purpose.

---

# 17. Database Design

> **As built.** Schema lives in `backend/src/database/models.py` (SQLAlchemy) and is created
> automatically in SQLite on first run. It largely matches the tables below, with these additions:
> `events.evidence_hash` and `alerts.snapshot_hash` (SHA-256 of the evidence image, computed at
> capture time — NFR event-integrity), `cameras.latitude/longitude` (Map view), and local
> `users` / `audit_logs` tables. A parallel Postgres schema exists in `supabase/migrations/`
> (adds `user_profiles` + RLS + a realtime publication) but the pipeline does not write to it yet.
> **Open decision:** consolidate on SQLite, on Supabase/Postgres, or define SQLite = local-dev only.

## Cameras

```text
camera_id
name
location_label
stream_url
camera_type
status
created_at
```

## Tracks

```text
track_id
camera_id
object_type
start_time
end_time
trajectory
```

## Events

```text
event_id
camera_id
track_id
event_type
timestamp
duration
confidence
risk_score
risk_level
evidence_path
```

## Identity Results

```text
identity_id
track_id
identity_label
similarity_score
timestamp
```

## ANPR Results

```text
plate_id
track_id
plate_text
ocr_confidence
timestamp
```

---

# 18. API Requirements

All routes are mounted under `/api/*` and require a valid Supabase JWT
(`Authorization: Bearer <token>`); admin-only routes additionally require the `admin` role.

## As-built routers (`backend/src/api/routes/`)

```text
Cameras      GET/POST  /api/cameras            GET /api/cameras/{id}/status  ...
Events       GET       /api/events             GET /api/events/{id}          GET /api/events/count
Alerts       GET       /api/alerts             GET /api/alerts/{id}          POST /api/alerts/{id}/review
Zones        GET/POST  /api/zones              GET /api/zones/{camera_id}
Tracks       GET       /api/tracks/{track_id}
Statistics   GET       /api/statistics
Stream       GET       /api/stream/...         (MJPEG / annotated frame access)
Reports      GET       /api/reports/daily      (24 h aggregation for CSV/PDF export)
Audit        GET       /api/audit              (admin — user action log with IP + timestamp)
Health       GET       /api/health             (unauthenticated)
WebSocket    WS        /ws/alerts?token=<jwt>  (real-time alert push)
Static       GET       /snapshots/<file>       (evidence images)
```

---

# 19. User Interface

## Main Dashboard

```text
+------------------------------------------------------+
| IBVAP COMMAND DASHBOARD                              |
+----------------------+-------------------------------+
| Camera Feed         | Current Alerts                |
|                      |                               |
| Bounding Boxes       | CRITICAL  Fence Crossing     |
| Track IDs            | HIGH      Loitering          |
| Zones                | MEDIUM    Vehicle Event     |
+----------------------+-------------------------------+
| Event Timeline       | Statistics                    |
+------------------------------------------------------+
```

## Event Detail

Should display:

- Event timestamp
- Camera
- Track ID
- Event type
- Risk score
- Risk level
- Trigger conditions
- Snapshot
- Plate result
- Identity result
- Trajectory

---

# 20. Performance Metrics

## Detection

- Precision
- Recall
- mAP@50
- mAP@50:95
- FPS

## Tracking

- MOTA
- IDF1
- HOTA
- ID switches
- Mostly Tracked / Mostly Lost where applicable

## Face Recognition

- Accuracy
- Precision
- Recall
- F1
- False Acceptance Rate
- False Rejection Rate

## ANPR

- Plate detection precision/recall
- Character accuracy
- Full-plate accuracy
- OCR confidence
- Processing FPS

## Behaviour

- Event precision
- Event recall
- Event F1
- False alarm rate
- Detection latency

## Risk/Fusion

- Accuracy
- Precision
- Recall
- Macro F1
- ROC-AUC where appropriate
- False alarm reduction
- Alert reduction
- Detection latency

---

# 21. Experimental Design

The project shall contain multiple experiments.

## Experiment 1 — Detection

Compare candidate YOLO variants.

## Experiment 2 — Tracking

Evaluate ByteTrack using standard tracking metrics.

## Experiment 3 — Behaviour

Evaluate:

- Intrusion
- Loitering
- Direction
- Night movement

## Experiment 4 — Context Fusion

Compare:

```text
A. Independent alerts
vs.
B. Context-aware fusion
```

Expected research question:

> Does contextual fusion reduce false/redundant alerts while maintaining detection of important events?

## Experiment 5 — Risk Model

Compare:

```text
Rule-based scoring
vs.
ML-based event risk classifier
```

## Experiment 6 — Ablation Study

Remove one context component at a time:

```text
Full Model
- Identity
- Temporal context
- Spatial context
- Behaviour
- Vehicle context
```

Measure the effect on event classification and false-alert rate.

---

# 22. Development Phases

## Phase 1 — Architecture

- Freeze system architecture
- Define interfaces
- Define database schema
- Define event taxonomy

## Phase 2 — Dataset

- Download VIRAT
- Download UFPR-Planalto801
- Download MOT17
- Download BDD100K
- Prepare controlled IBVAP videos
- Define event-level dataset

## Phase 3 — Detection

- Install PyTorch
- Install YOLO framework
- Load pretrained model
- Benchmark detection
- Select final detector

## Phase 4 — Tracking

- Integrate ByteTrack
- Generate persistent track IDs
- Store trajectories

## Phase 5 — Spatial Intelligence

- Polygon zones
- Virtual fence
- Entry/exit
- Direction

## Phase 6 — Temporal Behaviour

- Loitering
- Dwell time
- Speed
- Trajectory analysis
- Night movement

## Phase 7 — Identity

- Face detection
- ArcFace embeddings
- Authorized gallery
- Unknown/uncertain identity

## Phase 8 — ANPR

- Vehicle detection
- Plate detection
- OCR
- Confidence handling

## Phase 9 — Context Fusion

- Event construction
- Feature extraction
- Multi-event fusion
- Alert deduplication

## Phase 10 — Risk Engine

- Rule baseline
- Event-level ML model
- Calibration
- Explainability

## Phase 11 — Dashboard

- Backend
- Frontend
- Live feed
- Alerts
- Event history
- Evidence

## Phase 12 — Evaluation

- Quantitative metrics
- Ablation
- Baselines
- Stress testing
- Error analysis

## Phase 13 — Final Demonstration

```text
CCTV Video
   ↓
Detection
   ↓
Tracking
   ↓
Virtual Fence
   ↓
Behaviour
   ↓
Context Fusion
   ↓
Risk
   ↓
Alert
   ↓
Dashboard
```

---

# 23. Recommended Initial Software Repository

```text
IBVAP/
│
├── data/
│   ├── virat/
│   ├── ufpr/
│   ├── mot17/
│   ├── bdd100k/
│   └── custom/
│
├── models/
│   ├── detection/
│   ├── face/
│   ├── anpr/
│   └── risk/
│
├── src/
│   ├── ingestion/
│   ├── detection/
│   ├── tracking/
│   ├── spatial/
│   ├── temporal/
│   ├── face/
│   ├── anpr/
│   ├── behavior/
│   ├── fusion/
│   ├── risk/
│   ├── alerts/
│   ├── database/
│   └── api/
│
├── dashboard/
│   ├── templates/
│   └── static/
│
├── configs/
│   ├── cameras.yaml
│   ├── zones.yaml
│   └── thresholds.yaml
│
├── experiments/
│   ├── detection/
│   ├── tracking/
│   ├── behavior/
│   ├── fusion/
│   └── risk/
│
├── outputs/
│   ├── videos/
│   ├── snapshots/
│   ├── logs/
│   └── metrics/
│
├── tests/
│
├── requirements.txt
├── README.md
└── main.py
```

---

# 24. Configuration Requirements

Example configuration:

```yaml
camera:
  id: CAM_001
  name: Fence Camera
  source: RTSP_OR_VIDEO_FILE

detection:
  confidence: 0.40

tracking:
  tracker: bytetrack

zones:
  restricted_zone:
    points:
      - [100, 100]
      - [500, 100]
      - [500, 400]
      - [100, 400]

behavior:
  loitering_seconds: 30
  night_start: "19:00"
  night_end: "05:00"

risk:
  low_threshold: 25
  medium_threshold: 50
  high_threshold: 75
```

Values shall be experimentally calibrated rather than arbitrarily claimed as optimal.

---

# 25. Error Handling

The platform shall handle:

- Camera disconnected
- Empty frames
- Corrupt video
- Low-light footage
- Occlusion
- Multiple people
- False detections
- Lost tracking IDs
- OCR failure
- Face recognition uncertainty
- Database failure
- Model loading failure

The system shall fail safely and log errors.

---

# 26. Research Questions

The project shall investigate:

### RQ1
Can hierarchical perception-to-context processing improve surveillance event detection over independent detection modules?

### RQ2
Can spatial and temporal context reduce false/redundant alerts?

### RQ3
Does multi-event context fusion improve risk classification?

### RQ4
Can an explainable risk engine prioritize security events without relying entirely on black-box decisions?

### RQ5
How does the proposed system perform under day/night, occlusion, crowding and varying camera conditions?

---

# 27. Expected Contributions

1. Software-only intelligent CCTV analytics platform.
2. Hierarchical perception-to-event architecture.
3. Context-aware multi-event fusion.
4. Explainable risk scoring.
5. Virtual-fence and trajectory-based spatial reasoning.
6. Event-level dataset for surveillance risk analysis.
7. Experimental comparison of rule-based and ML-based risk estimation.
8. Alert deduplication/contextual prioritization.
9. Modular architecture compatible with existing CCTV infrastructure.

---

# 28. Important Design Decisions

### Decision 1
**No dedicated hardware.**

### Decision 2
Use pretrained/fine-tuned models rather than training every model from scratch.

### Decision 3
Use VIRAT as the primary surveillance dataset.

### Decision 4
Use UFPR-Planalto801 and MOT17 primarily for tracking evaluation/support.

### Decision 5
Use BDD100K primarily for vehicle/road-scene generalization.

### Decision 6
Implement virtual fencing using geometry and tracked coordinates rather than requiring a special neural network.

### Decision 7
Use event-level context fusion as the primary research novelty.

### Decision 8
Use an interpretable rule-based risk baseline before evaluating an ML risk model.

### Decision 9
Split video datasets by sequence/video rather than by individual frames.

### Decision 10
Do not claim general Indian ANPR performance without Indian/Indian-style evaluation data.

---

# 29. Success Criteria

The project will be considered successful if it can demonstrate:

- Reliable person/vehicle detection.
- Persistent tracking.
- Working virtual restricted zones.
- Correct fence-crossing detection.
- Loitering detection.
- Direction analysis.
- Night-context detection.
- Functional ANPR pipeline.
- Functional consent-based face recognition pipeline.
- Contextual event fusion.
- Explainable risk scores.
- Prioritized alerts.
- Event logging.
- Working dashboard.
- Quantitative evaluation against defined baselines.
- Measurable reduction in redundant/false alerts compared with independent alerts.

---

# 30. Final System Concept

IBVAP should ultimately behave as an intelligent surveillance reasoning system rather than a collection of disconnected AI models.

```text
                    CCTV
                      │
                      ▼
               VIDEO INGESTION
                      │
                      ▼
               OBJECT DETECTION
                      │
                      ▼
                OBJECT TRACKING
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
       SPATIAL     TEMPORAL    IDENTITY
       CONTEXT      CONTEXT     CONTEXT
          │           │           │
          └───────────┼───────────┘
                      ▼
                VEHICLE / ANPR
                      │
                      ▼
              BEHAVIOUR ENGINE
                      │
                      ▼
               CONTEXT FUSION
                      │
                      ▼
                 RISK ENGINE
                      │
                      ▼
              PRIORITIZED ALERT
                      │
                      ▼
                 DASHBOARD
                      │
                      ▼
                EVENT DATABASE
```

**Core principle:**

> Detect → Track → Understand → Fuse → Assess Risk → Explain → Alert

This principle defines the technical identity of IBVAP.

---

# 31. Implementation Status (2026-09-08)

Snapshot of where the codebase stands against the functional requirements.
Legend: ✅ done · 🟡 partial / experimental · ⛔ not started.

| FR | Requirement | Status | Notes |
|---|---|---|---|
| FR-01 | Video input (RTSP + file, multi-camera, reconnect) | ✅ | `src/ingestion/`, per-camera threads, file-end + stream-reconnect handling |
| FR-02 | Object detection (person + vehicles) | ✅ | YOLOv8n / COCO in `src/detection/detector.py` |
| FR-02+ | Border/military **coarse 13-class** detector (§9A) | 🟡 | Dataset built & verified (`data/detector_yolo`, `configs/dataset_coarse.yaml`); runtime plumbing done (`detection.weights_path`); **training run pending** |
| FR-02++ | Fine-grained military type ID (73 types) | ⛔ | Deferred to Phase 2 — §9B |
| FR-03 | Multi-object tracking, persistent IDs, trajectories | ✅ | ByteTrack via `supervision`, `TrackManager` history |
| FR-04 | Polygonal zones (restricted/buffer/safe/entry-exit) | ✅ | `src/spatial/zone_manager.py`, config + `/api/zones` |
| FR-05 | Virtual fence + crossing direction/time/track | ✅ | `src/spatial/fence_detector.py` |
| FR-06 | Direction analysis | ✅ | `src/spatial/direction_analyzer.py`, "toward restricted zone" |
| FR-07 | Loitering detection | ✅ | `src/temporal/loitering_detector.py`, dwell-time tiers in risk engine |
| FR-08 | Night / low-light context | ✅ | `src/temporal/night_detector.py` (time-of-day + brightness) |
| FR-09 | Face detection / embedding / matching | 🟡 | Modules in `src/face/` complete but **not called by `pipeline._process_track`**; identity context only carries dominant colour |
| FR-10 | ANPR (plate detect → OCR → confidence) | 🟡 | `src/features/anpr.py` uses `pytesseract` with a `MOCK-PLT` fallback; `src/anpr/` detector stubs exist. TRD target PaddleOCR not integrated |
| FR-11 | Behaviour engine (intrusion, fence, loiter, direction, night, combined) | ✅ | `src/behavior/behavior_engine.py`, "combined suspicious" at 3+ flags |
| FR-12 | Context fusion + alert dedup | ✅ | `src/fusion/context_fusion.py` — one `FusedEvent` + semantic description + cooldown |
| FR-13 | Risk engine `R = w1·S+w2·T+w3·B+w4·I+w5·V`, 4 levels | ✅ | `src/risk/risk_engine.py`, weights in `configs/risk_weights.yaml`, explainable summary |
| FR-13+ | ML event-level risk classifier (baseline comparison) | 🟡 | `src/risk/risk_classifier.py` (RandomForest) scaffolded; **no feature dataset generated, no trained model** |
| FR-14 | Alert engine (dedup, rate-limit, min-risk, evidence, WS push) | ✅ | `src/alerts/alert_engine.py` + `notifiers.py` (email/SMS, mock fallback) |
| FR-15 | Dashboard (live feed, status, boxes, IDs, zones, alerts, history, search, detail, evidence) | ✅ | React SPA in `frontend/src/pages/` |
| FR-15+ | Heatmap overlay, Threat-Score panel, Multi-camera grid, Map view | ✅ | `HeatmapOverlay`, `ThreatScorePanel`, `MultiView`, `MapView` |
| FR-16 | Event database (cameras, tracks, events, alerts, plates, identities, risk, evidence) | 🟡 | SQLite: cameras/tracks/events/alerts/audit implemented; `identity_results` / `anpr_results` tables defined but not populated (FR-09/FR-10 not live) |
| — | Reports (24 h aggregation → CSV/PDF) | ✅ | `/api/reports/daily` + frontend export |
| — | Audit log page | ✅ | `/api/audit`, `frontend/src/pages/AuditLog.tsx` |
| — | Evidence hashing (SHA-256) | ✅ | `alert_engine._save_snapshot`, stored on event + alert |
| — | Experiments 1–6 (§21) + metrics (§20) | ⛔ | `outputs/metrics/` empty; no `experiments/` results yet — **highest-value remaining work for evaluation** |

## Priority open items

1. **Run the coarse training** — `python scripts/train_yolo.py --data configs/dataset_coarse.yaml
   --model yolo11s.pt` (smoke-test with `--epochs 3` first), then
   `python -m ml.eval_detector --weights outputs/training/ibvap_coarse/weights/best.pt`
   and record the per-class mAP baseline.
2. Point `configs/thresholds.yaml → detection.weights_path` at the resulting `best.pt` and
   confirm the dashboard end-to-end (boxes, `object_type`, events, alerts).
3. ~~Verify the train/val split~~ **Done (§12).** The raw export leaked 71 % of val; the split is
   now grouped by source image **and** MOT/VIRAT clip via `scripts/make_clean_split.py`.
4. ~~License Plate has no training data~~ **Done.** 19,828 label-less `plate_*` images purged and
   18,000 correctly-labelled images (19,270 boxes) merged from the v13 Roboflow set.
5. Decide the data-store story (SQLite vs Supabase/Postgres — §17).
6. Either integrate face + a real OCR engine (PaddleOCR/EasyOCR) into the pipeline, or mark
   FR-09/FR-10 explicitly as "modules delivered, not demo-active" in the PRD.
7. `night_vision_object` is a legacy catch-all (12 IR sub-classes were collapsed upstream).
   Optional ~15 min improvement: re-pull `night-vision.v3i` and remap its real sub-classes to
   person/vehicle instead of one generic class.
8. Generate the event-level feature dataset (§11 schema) so the ML risk classifier (FR-13+) can be
   trained and compared against the rule-based baseline.
9. Detection still has **zero** test coverage — `backend/tests/` is empty.
