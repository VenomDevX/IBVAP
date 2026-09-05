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

## Programming

- Python 3.x

## Computer Vision

- OpenCV
- FFmpeg

## Deep Learning

- PyTorch
- Ultralytics/YOLO-based detector
- ArcFace-based face embeddings

## Tracking

- ByteTrack

## OCR / ANPR

- PaddleOCR or another benchmarked OCR engine
- YOLO-based license-plate detector

## Backend

- FastAPI or Flask

## Frontend

- HTML
- CSS
- JavaScript

## Database

- SQLite initially
- PostgreSQL for scaling

## Data Processing

- NumPy
- Pandas
- scikit-learn

## Visualization / Evaluation

- Matplotlib
- Precision
- Recall
- F1-score
- mAP
- IDF1
- HOTA
- MOTA
- RMSE/MAE where applicable

---

# 10. Dataset Strategy

The project shall NOT rely on one dataset for every task.

A modular dataset strategy will be used.

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

Example endpoints:

```text
GET  /api/cameras
POST /api/cameras
GET  /api/cameras/{id}/status

GET  /api/events
GET  /api/events/{id}

GET  /api/alerts
GET  /api/alerts/{id}

POST /api/zones
GET  /api/zones/{camera_id}

GET  /api/tracks/{track_id}

GET  /api/statistics
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
