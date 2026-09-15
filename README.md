# IBVAP — Intelligent Border Video Analytics Platform

> AI-Based Intelligent Video Analytics Platform for Border Surveillance using Existing CCTV Infrastructure — SIH 2026 (PS 26187)

## Overview

IBVAP transforms existing CCTV/IP-camera infrastructure into an intelligent surveillance system. It detects, tracks, identifies, and prioritizes security-relevant events using computer vision and AI, presenting them through a real-time monitoring dashboard.

The distinguishing idea is **context fusion**: instead of raising one alert per raw detection, IBVAP combines spatial, temporal, identity, and behavioural signals for a single tracked object into **one explainable, risk-scored security event**.

### Core Pipeline

```
CCTV/Video → Ingestion → Detection → Tracking → Spatial/Temporal Analysis
    → Behaviour Engine → Context Fusion → Risk Scoring → Alert → Dashboard
```

## Repository Layout

This is a monorepo with three deployable parts:

```
SIH 26187/
├── backend/          # Python AI microservice + REST/WebSocket API (FastAPI)
│   ├── main.py           # Entry point (uvicorn launcher)
│   ├── configs/          # YAML config: cameras, zones, thresholds, risk weights, dataset
│   ├── scripts/          # Training & data-prep scripts (YOLO, ResNet, dataset merge)
│   ├── src/
│   │   ├── ingestion/    # Video input (OpenCV), frame buffering, reconnect
│   │   ├── detection/    # YOLOv8 object detection wrapper
│   │   ├── tracking/     # ByteTrack (via `supervision`) multi-object tracking
│   │   ├── spatial/      # Zones, virtual fence, direction, heatmap accumulator
│   │   ├── temporal/     # Loitering, night/low-light detection
│   │   ├── face/         # Face detect / embed / match (ArcFace-style) — module only
│   │   ├── anpr/         # Plate detector + OCR (module only)
│   │   ├── features/     # Dominant-colour extractor, plate OCR helper (pytesseract)
│   │   ├── behavior/     # Rule-based behaviour classification
│   │   ├── fusion/       # Context fusion engine (core novelty)
│   │   ├── risk/         # Weighted rule-based risk engine + optional ML classifier
│   │   ├── alerts/       # Alert generation, dedup, snapshot + SHA-256 hashing, notifiers
│   │   ├── database/     # SQLAlchemy models + repository (SQLite runtime store)
│   │   ├── api/          # FastAPI app, routes, auth, security middleware, WebSocket
│   │   └── pipeline/     # Per-camera + master pipeline orchestration
│   ├── ml/               # training / data-prep / eval (separate from the runtime src/)
│   │   ├── taxonomy.py       # SINGLE source of truth for detector classes
│   │   ├── remap_to_coarse.py, verify_dataset.py, eval_detector.py
│   └── requirements.txt
│
├── frontend/         # Next.js 16 static export + Tailwind v4 (operator console)
│   ├── app/              # Routes: dashboard, alerts, events, event, cameras, zones,
│   │                     #   multiview, map, audit, settings, login, signup
│   ├── src/
│   │   ├── components/   # UI kit, app shell, video streams, charts (Recharts), map (Leaflet)
│   │   ├── api/          # REST client + Supabase client (auth/session)
│   │   ├── context/      # Auth + theme (light, dark or system)
│   │   └── hooks/        # Alert WebSocket, polling, URL state, session timeout
│   └── tests/            # Vitest unit tests; Playwright e2e in tests/e2e
│
├── supabase/         # Supabase project — auth + Postgres schema
│   ├── config.toml
│   └── migrations/       # Tables + Row-Level Security policies
│
├── docs/
│   ├── IBVAP_PRD.md      # Product requirements / team understanding
│   └── IBVAP_TRD.md      # Technical requirements document
│
└── docker-compose.yml    # backend + frontend containers
```

## Features

| Area | Feature | Status |
|---|---|---|
| Ingestion | RTSP/IP streams, recorded video files, reconnect handling | Implemented |
| Detection | People + vehicles (YOLOv8, COCO classes) in the live pipeline | Implemented |
| Detection | **Coarse 13-class** border detector — person, car/bus/truck/motorcycle/bicycle, license_plate, military_ground_vehicle, aircraft, helicopter, drone_uav, night_vision_object, animal (`backend/ml/taxonomy.py`) | Dataset built + verified; **training run pending** (TRD §9A) |
| Detection | Fine-grained military type ID (F-16 vs Rafale, 73 types) | Deferred to Phase 2 as a second-stage classifier over aircraft/helicopter/UAV crops only (TRD §9B) |
| Tracking | Persistent track IDs + trajectory history (ByteTrack via `supervision`) | Implemented |
| Spatial | Polygon zones (restricted / buffer / safe / entry-exit), virtual fence, crossing direction | Implemented |
| Spatial | Movement-direction analysis, "moving toward restricted zone" | Implemented |
| Temporal | Loitering (dwell-time), night / low-light context | Implemented |
| Behaviour | Rule-based classification + "combined suspicious" (3+ flags) | Implemented |
| Fusion | Multi-signal context fusion → one deduplicated event + semantic description | Implemented |
| Risk | Explainable weighted score `R = w1·S + w2·T + w3·B + w4·I + w5·V`, 4 levels | Implemented |
| Risk | Optional ML event-level classifier (RandomForest) for baseline comparison | Scaffolded — no trained model / feature dataset yet |
| Alerts | Dedup + rate-limit + min-risk threshold, WebSocket push | Implemented |
| Evidence | Snapshot SHA-256 + append-only HMAC **hash chain** over event/alert rows; `verify_evidence_chain.py` detects tampering (tamper-evident, not tamper-proof) | Implemented |
| Identity | Face detect / embed / match modules | Module code present — **not called by the pipeline** |
| ANPR | Plate crop + OCR | `pytesseract` helper with mock fallback — TRD target is PaddleOCR |
| Dashboard | Live feed, alerts, events, event detail, camera status | Implemented |
| Dashboard | Heatmap overlay, live Threat-Score panel, Multi-Camera grid, Map view | Implemented |
| Reports | Daily aggregation endpoint (feeds CSV/PDF export on the frontend) | Implemented (endpoint) |
| Notifications | Email (smtplib) + SMS (Twilio) for critical alerts, with mock fallback | Implemented |
| Security | Supabase JWT auth, RBAC guards, security headers, rate limiting, input validation, audit log, client session timeout | Implemented |

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend language | Python 3.10+ |
| Detection | Ultralytics YOLO — stock `yolov8n` fallback; custom **coarse 13-class** `yolo11s` @ 640 is the target model (`configs/dataset_coarse.yaml`) |
| Stage-2 classifier | Phase 2 only — fine-grained military type ID over aircraft/UAV crops (TRD §9B); not in the runtime |
| Tracking | ByteTrack via `supervision` |
| Face (module) | InsightFace / ArcFace-style embeddings + cosine matching |
| ANPR OCR | `pytesseract` helper (TRD target: PaddleOCR / EasyOCR) |
| DL framework | PyTorch |
| CV library | OpenCV |
| Backend API | FastAPI + Uvicorn, WebSocket for alert push |
| API security | `slowapi` rate limiting, TrustedHost + CORS, custom security-headers / request-logging / input-validation middleware |
| Runtime data store | SQLite via SQLAlchemy 2.x (`ibvap.db`) |
| Auth & identity | Supabase Auth (JWT, verified locally with `SUPABASE_JWT_SECRET`); `user_profiles` + RLS in Postgres |
| Frontend | Next.js 15 (App Router/static export), React 19, TypeScript, Tailwind CSS v4 |
| Frontend libs | ApexCharts, Grid.js, Leaflet / react-leaflet, `@supabase/supabase-js` |
| Containers | Docker / docker-compose (backend + frontend + nginx) |

> **Data-store note (ADR-001).** SQLite is the single application datastore — the pipeline persists cameras/tracks/events/alerts/zones/audit through the SQLAlchemy repository and the frontend reads them via the FastAPI REST API. Postgres (`supabase/migrations`) holds **only** `user_profiles` for auth/RBAC; the mirrored `events`/`alerts` tables and realtime publication there are vestigial. See `docs/ADR-001-datastore.md`.

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 20+ (for the frontend)
- A GPU is recommended for real-time inference but not required
- (Optional) Supabase CLI + Docker for local auth; (optional) Tesseract OCR for ANPR

### 1. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows  (source venv/bin/activate on Linux/macOS)
pip install -r requirements.txt

copy .env.example .env           # then edit .env (see below)
python main.py                   # serves the API on http://localhost:8002
```

Key `.env` values:

| Variable | Purpose |
|---|---|
| `IBVAP_ENV` | `development` (docs at `/docs`) or `production` (docs disabled) |
| `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_JWT_SECRET` | Auth — required for the API to accept logins |
| `DATABASE_URL` | Defaults to `sqlite:///./ibvap.db` |
| `IBVAP_ADMIN_PASSWORD`, `IBVAP_OPERATOR_PASSWORD` | Seed passwords for the local `admin` / `operator` rows. **If unset, a random password is generated and printed to the log at startup** — there are no fixed default credentials. |
| `CORS_ORIGINS`, `TRUSTED_HOSTS` | Comma-separated allow-lists |
| `SMTP_*`, `TWILIO_*` | Optional critical-alert notifications |

Configure the surveillance inputs before running:

1. `backend/configs/cameras.yaml` — camera IDs and sources (RTSP URL or path to a video file)
2. `backend/configs/zones.yaml` — restricted zones and virtual fences
3. `backend/configs/thresholds.yaml` — detection confidence, tracker, behaviour thresholds, alert limits
4. `backend/configs/risk_weights.yaml` — risk-engine weights and score tables

### 2. Frontend

```bash
cd frontend
npm install
# create .env with NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY
npm run dev                       # http://localhost:3001; API is http://127.0.0.1:8002
```

On Windows, the reliable one-command launcher builds the offline-capable
production frontend and starts both services:

```powershell
.\scripts\run-local.ps1
# Use .\scripts\run-local.ps1 -Dev only when actively editing the frontend.
```

### 3. Docker (optional)

```bash
docker compose up --build
```

## Model Training (separate from the running app)

Training scripts live in `backend/scripts/` and write to `backend/outputs/`. They are **not** invoked by `main.py`.

# 1. Build the coarse (13-class) dataset from the legacy 91-class merge
python -m ml.remap_to_coarse

# 2. Merge the license-plate dataset (class 6) — hard-links, keeps aug groups intact
python scripts/add_plates.py --src "F:/Projects/SIH 26187/License Plate Recognition.v13i.yolov8"        --dst data/detector_yolo --purge-old --limit 18000

# 3. Leak-free, clip-aware split -> configs/dataset_coarse.yaml
python scripts/make_clean_split.py --src data/detector_yolo

# 4. Gate: histogram / parity / leakage / box sizes
python -m ml.verify_dataset --data configs/dataset_coarse.yaml

# 5. Train (smoke-test with --epochs 3 first)
python scripts/train_yolo.py --data configs/dataset_coarse.yaml --model yolo11s.pt

# 6. Per-class mAP — tune against THIS table, not the aggregate number
python -m ml.eval_detector --weights outputs/training/ibvap_coarse/weights/best.pt
```

See **TRD §9A** for the class taxonomy, the imbalance-handling strategy, and the plan to integrate the trained weights into `src/detection/detector.py`.

## Documentation

- **[docs/IBVAP_PRD.md](docs/IBVAP_PRD.md)** — what we are building and why (product requirements, MVP, workflows, limitations, success metrics)
- **[docs/IBVAP_TRD.md](docs/IBVAP_TRD.md)** — how it is built (architecture, tech stack, dataset strategy, models, database, API, experiments, implementation status)

## License

Developed for Smart India Hackathon 2026.
