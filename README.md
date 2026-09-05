# IBVAP — Intelligent Border Video Analytics Platform

> AI-Based Intelligent Video Analytics Platform for Border Surveillance using Existing CCTV Infrastructure

## Overview

IBVAP transforms existing CCTV/IP-camera infrastructure into an intelligent surveillance system. It detects, tracks, identifies, and prioritizes security-relevant events using computer vision and AI, presenting them through a real-time monitoring dashboard.

### Core Pipeline

```
CCTV/Video → Ingestion → Detection → Tracking → Spatial/Temporal Analysis
    → Behavior Engine → Context Fusion → Risk Scoring → Alert → Dashboard
```

## Features

- **Video Ingestion**: RTSP streams, IP cameras, recorded video files
- **Object Detection**: People, cars, motorcycles, buses, trucks (YOLOv8)
- **Multi-Object Tracking**: Persistent track IDs with trajectory history (ByteTrack)
- **Virtual Zones**: Configurable restricted zones, buffer zones, entry/exit zones
- **Virtual Fence**: Boundary crossing detection with direction analysis
- **Loitering Detection**: Duration-based dwelling analysis
- **Night Detection**: Time-based and illumination-aware monitoring
- **Face Analysis**: Optional face detection and recognition (ArcFace)
- **ANPR**: Optional license plate detection and OCR (PaddleOCR)
- **Context Fusion**: Multi-signal event fusion (the core novelty)
- **Risk Scoring**: Explainable weighted risk assessment
- **Alert System**: Prioritized, deduplicated alerts with evidence
- **Dashboard**: Real-time monitoring with zone editor and event history
- **Authentication**: JWT-based auth with role-based access control

## Quick Start

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
# Clone the repository
cd "f:\Projects\SIH 26187"

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Configuration

1. Copy `.env.example` to `.env` and configure:
   ```bash
   copy .env.example .env
   ```

2. Edit `configs/cameras.yaml` to add your camera sources
3. Edit `configs/zones.yaml` to define restricted zones
4. Edit `configs/thresholds.yaml` to tune detection parameters

### Running

```bash
python main.py
```

The dashboard will be available at `http://localhost:8000`

### Default Credentials

- **Admin**: admin / admin123
- **Operator**: operator / operator123

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   CCTV / Video Input                  │
├──────────────────────────────────────────────────────┤
│                  Video Ingestion Layer                │
│                  (OpenCV / FFmpeg)                    │
├──────────────────────────────────────────────────────┤
│                  Object Detection                    │
│                  (YOLOv8)                             │
├──────────────────────────────────────────────────────┤
│                  Multi-Object Tracking               │
│                  (ByteTrack)                          │
├────────────────┬──────────────┬───────────────────────┤
│   Spatial      │   Temporal   │   Identity            │
│   Analysis     │   Analysis   │   Analysis            │
├────────────────┴──────────────┴───────────────────────┤
│                  Behavior Engine                      │
├──────────────────────────────────────────────────────┤
│                  Context Fusion                       │
├──────────────────────────────────────────────────────┤
│                  Risk Engine                          │
├──────────────┬───────────────────────────────────────┤
│  Alert Engine │           Event Database              │
├──────────────┴───────────────────────────────────────┤
│              Web Dashboard (FastAPI)                  │
└──────────────────────────────────────────────────────┘
```

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| Detection | Ultralytics YOLOv8 |
| Tracking | ByteTrack (via supervision) |
| Face | InsightFace / ArcFace |
| ANPR OCR | PaddleOCR |
| Backend | FastAPI |
| Database | SQLite (SQLAlchemy) |
| Frontend | HTML/CSS/JS |
| CV Library | OpenCV |
| DL Framework | PyTorch |

## Project Structure

```
IBVAP/
├── main.py                 # Entry point
├── configs/                # YAML configuration files
├── src/
│   ├── ingestion/          # Video input handling
│   ├── detection/          # YOLOv8 object detection
│   ├── tracking/           # ByteTrack multi-object tracking
│   ├── spatial/            # Zones, fencing, direction
│   ├── temporal/           # Loitering, night detection
│   ├── face/               # Face detection & recognition
│   ├── anpr/               # License plate detection & OCR
│   ├── behavior/           # Behavior classification
│   ├── fusion/             # Context fusion engine
│   ├── risk/               # Risk scoring engine
│   ├── alerts/             # Alert generation
│   ├── database/           # SQLite database layer
│   ├── api/                # FastAPI backend
│   └── pipeline/           # Processing orchestration
├── dashboard/              # Web frontend
├── data/                   # Datasets (gitignored)
├── models/                 # Model weights (gitignored)
├── outputs/                # Snapshots, logs, metrics
├── experiments/            # Evaluation scripts
└── tests/                  # Unit tests
```

## License

This project is developed for SIH 2026.
