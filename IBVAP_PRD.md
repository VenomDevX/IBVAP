# IBVAP — Team Project Requirements & Understanding

> **AI-Based Intelligent Video Analytics Platform for Border Surveillance using Existing CCTV Infrastructure**

This document is for **team understanding, development planning, demo preparation, and coordination**.  
It is **not a formal project report or submission document**.

The goal is to give every team member a clear understanding of **what IBVAP is supposed to do, what features we are building, what the MVP is, and what can be left for later**.

---

## 1. What is IBVAP?

IBVAP adds an AI-based analytics layer to existing CCTV/video feeds.

Instead of making a person continuously watch every camera, the system analyzes the video and identifies predefined events that may need attention.

### Simple idea

**Normal CCTV:**

> Camera → Video → Human watches

**IBVAP:**

> Camera → Video → AI detects objects → Tracking → Rules → Event → Alert → Human reviews

IBVAP is an **AI-assisted monitoring system**, not a replacement for human security personnel.

The system should help an authorized operator answer:

- What happened?
- Which camera detected it?
- When did it happen?
- What type of event was it?
- What evidence is available?
- Has someone reviewed it?

---

## 2. Problem We Are Solving

CCTV cameras continuously produce large amounts of video. A human operator cannot realistically inspect every frame of multiple cameras continuously.

This creates problems:

- Important events can be missed.
- Operators may notice events late.
- Searching long recordings manually takes time.
- Multiple cameras increase workload.
- Night/low-light conditions can make monitoring harder.
- Traditional CCTV mainly records and displays video rather than turning video into structured events.

### Our product idea

IBVAP should automatically analyze supported video and bring **predefined, meaningful events** to the operator's attention.

The important distinction is:

> We are not trying to label people as “dangerous” or “criminal.”

Instead, we define measurable events such as:

- A person enters a configured restricted zone.
- A vehicle enters a configured restricted zone.
- An object remains in an area for an unusually long configured duration.
- A configured boundary is crossed.
- A camera/video source becomes unavailable.

---

## 3. Main Objectives

### Primary objective

Build an AI-based platform that can analyze existing CCTV/video streams and identify predefined events that require human review.

### Main objectives

1. Use existing CCTV/video infrastructure where possible.
2. Detect people and vehicles.
3. Track detected objects across video frames.
4. Allow an authorized user to create virtual restricted zones.
5. Detect when tracked objects enter configured zones.
6. Generate useful alerts.
7. Store event information for later review.
8. Show camera status and events through a dashboard.
9. Attach snapshots/short evidence clips where supported.
10. Provide basic authentication and role-based access.
11. Keep ANPR and advanced analytics as optional/next-stage features.
12. Measure AI performance instead of claiming perfect accuracy.

---

## 4. Project Scope

### 4.1 What we should build

The core product should include:

- CCTV/video input
- Person detection
- Vehicle detection
- Object tracking
- Virtual restricted zones
- Intrusion/restricted-zone event detection
- Event generation
- Real-time or near-real-time alerts
- Event history
- Basic evidence/snapshot support
- Monitoring dashboard
- Camera online/offline status
- Authentication
- Basic role-based access
- Audit logging for important actions

### 4.2 Features that can come later

These should not block the MVP:

- ANPR
- Better night/low-light analytics
- Advanced suspicious/unusual activity detection
- Multi-camera object association
- Advanced reports
- Mobile notifications
- Advanced tamper-evident/blockchain mechanisms
- Edge deployment
- More advanced map/site visualization

### 4.3 What we are NOT building

The project should not attempt to:

- Replace all CCTV cameras.
- Control physical gates or barriers.
- Perform autonomous physical intervention.
- Use weapons or force.
- Make final security decisions without human review.
- Claim guaranteed identification of every person or vehicle.
- Claim 100% AI accuracy.
- Access camera feeds without authorization.

---

## 5. Who Uses the System?

### Security Operator

Main user of the monitoring interface.

Needs to:

- View camera feeds.
- Receive alerts.
- Open event details.
- Review evidence.
- Mark events as reviewed.
- Search previous events.

### Supervisor

Needs to:

- View important/recent events.
- Understand monitoring activity.
- Review event history.
- Check system status.

### Administrator

Needs to:

- Add/configure cameras.
- Create virtual zones.
- Manage users and roles.
- Configure system settings.
- Check failures.

### Auditor / Authorized Reviewer

Needs to:

- Search historical events.
- Review evidence.
- Inspect relevant audit records.

### Project Team

Needs to:

- Configure demo scenarios.
- Test datasets.
- Test the complete video → AI → event → alert workflow.

---

# 6. How the System Works

The main workflow is:

```text
Existing CCTV / Test Video
          ↓
     Video Input
          ↓
    AI Detection
          ↓
    Object Tracking
          ↓
   Rule / Event Engine
          ↓
   Event is Generated
          ↓
        Alert
          ↓
 Dashboard + Evidence
          ↓
   Human Review
```

### Stage 1 — Video Input

The system receives video from an existing IP camera, CCTV source, or test video.

For IP cameras, **RTSP (Real Time Streaming Protocol)** is a common way to provide a live video stream.

### Stage 2 — Detection

AI looks at video frames and identifies objects such as:

- Person
- Car
- Truck
- Bus
- Motorcycle

depending on what the selected model supports.

### Stage 3 — Tracking

Detection finds an object in an individual frame.

Tracking attempts to follow the same object across multiple frames.

Example:

```text
Frame 100 → Person detected → Track ID 7
Frame 101 → Person detected → Track ID 7
Frame 102 → Person detected → Track ID 7
Frame 103 → Person detected → Track ID 7
```

The tracking ID is temporary and can fail if the object is hidden, leaves the scene, or becomes difficult to distinguish.

### Stage 4 — Rule Analysis

The system checks whether something meaningful happened.

For example:

```text
Person detected
      ↓
Person tracked
      ↓
Person moves toward restricted zone
      ↓
Person crosses configured boundary
      ↓
Restricted Zone Entry Event
```

### Stage 5 — Alert

The system generates an alert containing useful context:

- Event type
- Camera
- Timestamp
- Severity
- Object type
- Confidence information where available
- Evidence reference where available

### Stage 6 — Human Review

The operator reviews the event.

The AI output is an **indication for review**, not a final determination of intent or wrongdoing.

---

# 7. Core Features

## 7.1 CCTV / Video Input

The platform should accept supported CCTV or test video sources.

Each configured camera should have:

- Camera ID
- Basic configuration
- Connection status

The dashboard should clearly show whether a camera is:

- Online
- Offline
- Connecting
- Experiencing an error

---

## 7.2 Person Detection

The AI should detect visible people in supported video.

A detected person can be shown using a bounding box:

```text
+-------------------+
|                   |
|     PERSON        |
|       [ ]         |
|                   |
+-------------------+
```

The system may retain the detection confidence provided by the selected model.

---

## 7.3 Vehicle Detection

The system should detect visible vehicles.

Depending on the model, categories can include:

- Car
- Truck
- Bus
- Motorcycle

Vehicle detections can then be passed to tracking and event analysis.

---

## 7.4 Object Tracking

Tracking connects detections across frames.

It allows the system to understand movement instead of treating every frame as a completely new detection.

Tracking is especially important for:

- Virtual fencing
- Movement analysis
- Duration-based rules
- Event generation

---

## 7.5 Virtual Fence / Restricted Zone

A virtual fence is a **digital boundary** drawn on the camera view.

Example:

```text
Camera View

+----------------------------------+
|                                  |
|             Person              |
|               ↓                  |
|          ----------------        |
|          RESTRICTED ZONE         |
|          ----------------        |
|                                  |
+----------------------------------+
```

An authorized user should be able to:

1. Select a camera.
2. Draw a line/polygon.
3. Save the zone.
4. Enable the rule.
5. Monitor objects relative to that zone.

---

## 7.6 Intrusion Detection

The product converts object movement into a meaningful event.

Example:

```text
Person detected
      ↓
Person tracked
      ↓
Person crosses restricted boundary
      ↓
"Restricted Zone Entry"
      ↓
HIGH alert
```

The system should avoid generating a separate high-priority alert for every frame of the same continuing event.

---

## 7.7 Night / Low-Light Monitoring

The system can support night or low-light analysis where the selected models and video quality are suitable.

Important:

- Day and night performance should be tested separately.
- Poor image quality can reduce detection accuracy.
- The UI should not imply certainty when video quality is poor.

---

## 7.8 ANPR

**ANPR = Automatic Number Plate Recognition**

Basic flow:

```text
Vehicle detected
      ↓
Number plate located
      ↓
Plate image processed
      ↓
OCR extracts characters
      ↓
Plate result displayed
```

ANPR depends heavily on:

- Plate visibility
- Camera angle
- Resolution
- Distance
- Motion blur
- Lighting
- Local plate format

Therefore, ANPR should be treated as a **separate module**, not something that must be perfect for the main MVP.

---

## 7.9 Face Detection / Recognition

### Face detection

Finds a face in an image.

### Face recognition

Attempts to determine whose face it is.

Face recognition is a sensitive capability and should only be used when properly authorized and appropriate.

For the prototype, face detection can remain optional.

If recognition is ever included, the system must not present an uncertain result as a guaranteed identity.

---

## 7.10 Suspicious / Unusual Activity

We should avoid an undefined feature such as:

> “Detect suspicious people.”

That is too vague.

Instead, define measurable rules such as:

- Person remains in an area longer than a configured duration.
- Repeated approaches to a configured boundary.
- Entry into a restricted area.
- Other clearly defined activity scenarios.

Advanced activity recognition should be treated as a later stage.

---

# 8. Event and Alert System

A raw AI detection is not automatically an alert.

### Example

```text
"Person detected"
       ↓
     Detection
```

This may not require an alert.

But:

```text
"Person detected"
       ↓
"Person tracked"
       ↓
"Person entered restricted zone"
       ↓
Meaningful Event
       ↓
Alert
```

This is the core product idea.

## Alert severity

| Severity | Meaning | Example |
|---|---|---|
| INFO | Normal information | Camera connected |
| LOW | Non-critical event | Configured unusual-duration condition |
| MEDIUM | Needs timely review | Approach to restricted boundary |
| HIGH | Immediate operator attention | Configured restricted-zone entry |

Severity describes **how quickly the event should be reviewed**. It should not be interpreted as a statement about a person's intent.

## Event information

Each event should ideally contain:

- Event ID
- Camera ID
- Event type
- Timestamp
- Severity
- Object type
- Confidence where applicable
- Evidence reference where available
- Review status
- Relevant audit information where enabled

---

# 9. Dashboard / UI

The dashboard should be simple enough for an operator to understand without knowing how the AI model works.

## Main dashboard

Should show:

- Camera status
- Live/available feeds
- Recent alerts
- Event count
- Important system notifications

## Live monitoring

The operator should be able to:

- Select a camera.
- View available video.
- See detection overlays.
- See tracking information where enabled.

## Alert center

Each alert should show:

- Event type
- Severity
- Camera
- Timestamp

## Event details

Should show:

- What happened
- Where it happened
- When it happened
- Available evidence
- Confidence/quality information where applicable
- Review status

## Event history

Users should be able to filter by:

- Camera
- Event type
- Severity
- Time range

## Virtual zone configuration

Authorized users should be able to:

- Select a camera.
- Draw a restricted zone.
- Edit it.
- Save it.
- Enable/disable the rule.

---

# 10. Security and Privacy

Because this is a surveillance-related system, security and privacy are part of the product itself.

The product should include:

### Authentication

Only authorized users can access protected functions.

### Role-based access

Different users should have different permissions.

Example:

```text
Administrator
   ├── Manage users
   ├── Configure cameras
   └── Configure zones

Operator
   ├── View cameras
   ├── View alerts
   └── Review events

Auditor
   └── Review permitted historical/audit records
```

### Secure communication

Sensitive communication should use appropriate security protections.

### Credential protection

Camera credentials, passwords, tokens and similar secrets should not appear in normal UI screens or logs.

### Audit logging

Important actions should be traceable.

Examples:

- User login
- Camera configuration change
- Zone configuration change
- Event review
- User/role change

### Event integrity

Important event records should have mechanisms that make unauthorized changes detectable where required.

If the project uses blockchain/tamper-evident logging, the **exact implementation belongs in the TRD**, not this document.

### Privacy

Surveillance information should only be accessed and used for authorized purposes.

Data retention should be defined by the project/team according to applicable rules.

---

# 11. Dataset Plan

There is **no single dataset that covers every IBVAP feature**.

A practical strategy is:

```text
General pretrained model
          ↓
Specialized public datasets
          ↓
Project-specific testing
          ↓
IBVAP prototype
```

## Recommended datasets

| Dataset | Main use in IBVAP |
|---|---|
| **VIRAT** | Main surveillance-oriented video/activity analytics |
| **MOT17** | Object tracking, especially pedestrian tracking |
| **UFPR-Planalto801** | People tracking/re-identification in surveillance-style video |
| **BDD100K** | General detection/tracking and varied driving conditions |
| **Indian Number Plate Dataset** | ANPR / Indian plate detection |
| **UFPR-ALPR** | ANPR / license plate recognition |
| **WIDER FACE** | Optional face detection |
| **ShanghaiTech / Avenue / UCSD Ped2** | Optional anomaly/activity experiments |
| **UA-DETRAC** | Vehicle detection/tracking |

### Important

Do not force one dataset to solve everything.

For example:

```text
VIRAT
  → Main surveillance analytics

MOT17 / UFPR
  → Tracking

Indian Number Plate Dataset / UFPR-ALPR
  → ANPR

WIDER FACE
  → Optional face detection
```

The final test should use scenarios that are representative of the project.

---

# 12. AI Concepts Team Members Should Understand

## AI

Artificial Intelligence is the general area of techniques that allow software to perform tasks involving analysis or prediction.

## Computer Vision

Computer Vision is AI applied to images and video.

## Object Detection

Answers:

> “What objects are visible in this frame, and where are they?”

Output can look like:

```text
Person → Bounding Box → Confidence
Car    → Bounding Box → Confidence
```

## Object Tracking

Answers:

> “Is this probably the same object we saw in earlier frames?”

## OCR

**OCR = Optical Character Recognition**

It attempts to convert visible characters in an image into text.

Used by ANPR to read number plates.

## Event Engine

Combines AI outputs with rules.

```text
Detection + Tracking + Rule
          ↓
       Event
```

## Inference

Running a trained AI model on new video/image input to produce predictions.

---

# 13. Main User Workflows

## Workflow A — Normal Monitoring

```text
Camera connected
      ↓
Video received
      ↓
AI analyzes video
      ↓
People/vehicles detected
      ↓
Objects tracked
      ↓
No event condition
      ↓
Continue monitoring
```

## Workflow B — Restricted-Zone Intrusion

```text
Video received
      ↓
Person/vehicle detected
      ↓
Object tracked
      ↓
Position checked
      ↓
Restricted zone crossed
      ↓
Event created
      ↓
Alert generated
      ↓
Operator reviews
      ↓
Event marked reviewed/pending
```

## Workflow C — ANPR

```text
Vehicle detected
      ↓
Plate located
      ↓
Plate image processed
      ↓
OCR
      ↓
Plate text result
      ↓
Result associated with event
```

## Workflow D — Event Review

```text
Alert appears
      ↓
Operator opens alert
      ↓
Camera + time + event shown
      ↓
Evidence opened if available
      ↓
Operator reviews
      ↓
Event marked reviewed/pending
```

---

# 14. Important Product Requirements

These are the main requirements the team should keep in mind.

| ID | Requirement | Priority |
|---|---|---|
| FR-001 | Configure supported video source | P0 |
| FR-002 | Show camera status | P0 |
| FR-003 | Detect people | P0 |
| FR-004 | Detect vehicles | P0 |
| FR-005 | Track objects | P0 |
| FR-006 | Create virtual zones | P0 |
| FR-007 | Detect restricted-zone entry | P0 |
| FR-008 | Generate alerts | P0 |
| FR-009 | Store events | P0 |
| FR-010 | Associate evidence with events | P0 |
| FR-011 | Search/filter event history | P0 |
| FR-012 | Provide dashboard | P0 |
| FR-013 | ANPR | P1 |
| FR-014 | Low-light analysis | P1 |
| FR-015 | Authentication | P0 |
| FR-016 | Role-based access | P0 |
| FR-017 | Audit logging | P0 |
| FR-018 | Event review status | P0 |
| FR-019 | Show alert details | P0 |
| FR-020 | Show camera/system errors | P0 |

**P0 = must have for the core prototype.**

**P1 = important, but should not block the MVP.**

---

# 15. MVP — What We Actually Need to Finish First

The MVP should demonstrate one complete working flow.

## MVP features

- [x] Video input
- [x] Person detection
- [x] Vehicle detection
- [x] Object tracking
- [x] Virtual restricted zone
- [x] Restricted-zone intrusion detection
- [x] Event generation
- [x] Alert generation
- [x] Event history
- [x] Basic dashboard
- [x] Basic authentication/roles

## MVP demo story

The strongest demo is:

```text
Test CCTV/video
      ↓
Person detected
      ↓
Person tracked
      ↓
Virtual restricted zone visible
      ↓
Person crosses boundary
      ↓
Intrusion event created
      ↓
Alert appears
      ↓
Operator opens event
      ↓
Timestamp + camera + evidence shown
```

If this flow works reliably, the team has demonstrated the **core value of IBVAP**.

---

# 16. Phase 2 / Future Features

After the MVP is stable, we can add:

1. ANPR
2. Better night/low-light performance
3. Advanced activity analytics
4. Multi-camera analytics
5. Advanced event reporting
6. Mobile/secondary notifications
7. Tamper-evident event ledger
8. Map/site visualization
9. Additional camera-source support
10. Edge deployment
11. Easier replacement/upgrading of AI models

These are enhancements, not requirements for the first working version.

---

# 17. Example Scenario

Consider a test scenario:

> Camera C-04 is monitoring a configured restricted area.

The flow is:

```text
Camera C-04
    ↓
Video stream received
    ↓
Person detected
    ↓
Tracking ID assigned
    ↓
Movement followed
    ↓
Person enters restricted zone
    ↓
"Restricted Zone Entry" event
    ↓
HIGH severity
    ↓
Alert:
"Restricted Zone Entry detected
 at Camera C-04 at 02:15:32"
    ↓
Snapshot/evidence attached if available
    ↓
Operator reviews event
    ↓
Event marked reviewed/pending
```

The important idea is that:

> **“Person detected” is raw AI output.**

Whereas:

> **“Person entered a configured restricted zone” is a meaningful product event.**

---

# 18. What Can Go Wrong?

The team should expect AI limitations.

### False positive

The system says an event happened when it did not.

Example:

```text
No actual intrusion
       ↓
AI/rules generate intrusion alert
```

### False negative

The system fails to detect an event that actually happened.

### Poor lighting

Nighttime conditions can reduce detection quality.

### Occlusion

One object may block another.

### Motion blur

Fast movement can make objects difficult to detect.

### Distance

Small/distant objects are harder to detect.

### Camera angle

A model trained on one viewpoint may perform differently on another.

### Tracking failure

An object can temporarily disappear or become confused with another object.

### Dataset mismatch

A public dataset may look different from the project's intended CCTV environment.

### Camera/network failure

The video stream can become unavailable.

The UI must show this clearly rather than pretending the system is operating normally.

---

# 19. Success Metrics

The team should measure performance instead of making unsupported claims.

Useful metrics include:

### Detection accuracy

How well people/vehicles are detected on a defined test set.

### Tracking accuracy

How consistently objects retain tracking identities.

### Event detection accuracy

How often configured events are correctly detected.

### False-alert rate

How often an alert is generated when the configured event did not happen.

### Alert latency

Time between an event occurring and the alert appearing.

### Camera availability

How often configured video sources are available.

### Event logging completeness

Whether generated events contain the required information.

### User task completion

Whether an operator can successfully perform tasks such as:

- Open an alert.
- Review evidence.
- Search an event.
- Configure a zone.

**Do not claim 100% accuracy.** Numerical targets should be decided after baseline testing.

---

# 20. Key Limitations

The team should remember:

- AI predictions are probabilistic.
- False positives and false negatives are possible.
- Lighting and weather affect performance.
- Occlusion can affect tracking.
- ANPR depends strongly on plate visibility.
- Face recognition, if used, has additional technical, legal and privacy limitations.
- Public-dataset performance may differ from project-camera performance.
- Prototype performance may differ from production-scale performance.
- An AI-generated event is an indication for human review, not a final judgment.

---

# 21. What Belongs in the PRD vs TRD?

This document should answer:

> **WHAT are we building and WHY?**

The TRD should answer:

> **HOW are we technically building it?**

### PRD — this document

Should contain:

- Problem
- Objectives
- Scope
- Features
- User workflows
- User needs
- Product requirements
- MVP
- Acceptance criteria
- Dataset purpose
- Security/privacy expectations
- Limitations
- Success metrics

### TRD — technical document

Should contain things such as:

- Exact programming languages
- Frameworks
- Model architecture
- Model versions
- Hyperparameters
- API design
- Database schema
- Detailed system architecture
- Deployment configuration
- GPU/CPU requirements
- Code structure
- Networking implementation
- RTSP handling implementation
- OCR implementation details
- Tracking algorithm configuration
- Detailed cybersecurity implementation

**Rule for the team:**

> If the question is “What should the product do?” → PRD.  
> If the question is “How exactly will we implement it?” → TRD.

---

# 22. One-Page Team Summary

## IBVAP in one sentence

> **IBVAP is an AI-assisted video analytics platform that uses existing CCTV/video feeds to detect predefined events, generate alerts, and help authorized personnel review those events quickly.**

## Core pipeline

```text
Existing CCTV
     ↓
Video Input
     ↓
Detection
     ↓
Tracking
     ↓
Rules
     ↓
Event
     ↓
Alert
     ↓
Dashboard
     ↓
Human Review
```

## MVP

```text
CCTV/video
+ Person detection
+ Vehicle detection
+ Tracking
+ Virtual fence
+ Intrusion detection
+ Alerts
+ Event history
+ Dashboard
+ Basic authentication
```

## Later

```text
ANPR
Night analytics
Advanced activity recognition
Multi-camera analytics
Advanced reporting
Tamper-evident ledger
Edge deployment
```

## Core principle

> **Don't try to make the AI “decide who is dangerous.” Make it detect clearly defined events and help a human review them.**

---

# 23. Glossary

| Term | Meaning |
|---|---|
| **AI** | Artificial Intelligence |
| **Computer Vision** | AI techniques used to analyze images and video |
| **CCTV** | Closed-Circuit Television |
| **IP Camera** | Network-connected camera that can send video |
| **RTSP** | Common protocol used for live network camera streams |
| **Object Detection** | Finding and locating objects in an image/video frame |
| **Bounding Box** | Rectangle drawn around a detected object |
| **Object Tracking** | Following an object across multiple frames |
| **Tracking ID** | Temporary ID assigned to a tracked object |
| **Virtual Fence** | Digital boundary used to define a rule |
| **Restricted Zone** | Configured area where specific events can be triggered |
| **Event** | Structured record that a configured condition occurred |
| **Alert** | Notification shown to an authorized user |
| **ANPR** | Automatic Number Plate Recognition |
| **OCR** | Optical Character Recognition |
| **Confidence Score** | Model-provided indication of prediction confidence; not a guarantee |
| **False Positive** | System reports something that did not actually happen |
| **False Negative** | System misses something that actually happened |
| **Inference** | Running a trained AI model on new input |
| **Dataset** | Collection of data used for training/testing AI |
| **RBAC** | Role-Based Access Control |
| **Audit Log** | Record of relevant system/user actions |
| **Edge Computing** | Processing data near the source instead of only on a distant server |

---

## Final Team Direction

**Build the smallest complete system first.**

Do not start by trying to implement every AI feature.

The recommended development order is:

```text
1. Get video input working
        ↓
2. Get person/vehicle detection working
        ↓
3. Add tracking
        ↓
4. Add virtual fence
        ↓
5. Generate intrusion event
        ↓
6. Generate alert
        ↓
7. Store event
        ↓
8. Build dashboard
        ↓
9. Add authentication/roles
        ↓
10. Test the complete demo
        ↓
11. Only then add ANPR / advanced features
```

This keeps the project manageable and ensures that the team always has a working end-to-end product to demonstrate.
1. 🚨 Intelligent Context-Aware Alarm System

Instead of generating an alarm for every detection, IBVAP will fuse multiple surveillance events and determine their overall threat level.

For example:

Person detected + restricted-zone entry + prolonged presence + movement toward boundary

will be treated as one high-risk incident, rather than four separate alerts.

The alarm system can have levels:

Risk	System Response
🟢 Low	Log event
🟡 Medium	Dashboard notification
🟠 High	Prominent operator alert
🔴 Critical	Immediate alarm + incident escalation

Innovation: Context-aware intelligent alarm generation and alert prioritization.

2. 🌙 Adaptive Night-Time Surveillance

IBVAP will have a dedicated Night Awareness Mode that becomes more sensitive when surveillance conditions become difficult.

At night, the system can combine:

low-light/illumination estimation
person detection confidence
tracking persistence
movement trajectory
restricted-zone information
duration of presence
time-of-day context

Instead of simply saying:

“It is nighttime → increase risk.”

the system reasons:

“Nighttime + low visibility + unknown person + restricted zone + persistent movement → elevated threat.”

It can also use temporal confirmation at night to reduce false alarms caused by shadows, noise, or temporary detection failures.

Innovation: Adaptive context-aware surveillance for low-illumination environments.

3. 🧠 Explainable AI-Based Threat Assessment

The system should not behave like a black box that simply says:

🚨 HIGH RISK

It should explain why.

Example:

🚨 HIGH-RISK INCIDENT

Risk Score: 86/100

Contributing Factors:
✓ Unknown identity
✓ Night-time operation
✓ Restricted-zone entry
✓ 48 seconds of loitering
✓ Movement toward boundary
✓ Abnormal trajectory

Assessment:
HIGH RISK

Recommended Action:
Immediate operator verification

This makes every AI decision auditable and understandable to the security operator.

Innovation: Explainable, evidence-based threat assessment.
Dataset                 | Purpose in IBVAP                                                                                    | Priority         | Link                                                                                                                |
| ----------------------- | --------------------------------------------------------------------------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------- |
| *VIRAT Video Dataset* | Main *surveillance-video dataset* for people, vehicles, activities and event/activity recognition | 🥇 *MAIN*      | [VIRAT Official Dataset](https://www.crcv.ucf.edu/research/data-sets/virat/?utm_source=chatgpt.com)                 |
| *UFPR-Planalto801*    | *Person detection, tracking and re-identification* in real-world fixed-camera surveillance        | 🥈 *HIGH*      | [UFPR-Planalto801 Official Dataset](https://web.inf.ufpr.br/vri/databases/ufpr-planalto801/?utm_source=chatgpt.com) |
| *MOT17*               | *Multi-object pedestrian tracking* — maintaining IDs and trajectories across frames               | 🥉 *HIGH*      | [MOT17 Official Dataset](https://motchallenge.net/data/MOT17/?utm_source=chatgpt.com)                               |
| *BDD100K*             | *Vehicle/person detection and tracking, especially outdoor road/vehicle scenes                   | ⭐ **SUPPORTING* | [BDD100K Official Dataset](https://bdd-data.berkeley.edu/?utm_source=chatgpt.com)    
Advanced Feature Extraction & Event Snapshots
You are asking for a transition from a basic object detector to a Multi-Modal AI Surveillance System.

To achieve high accuracy, clothing/color detection, license plate reading, and text descriptions, we cannot just use a single YOLO model. Instead, we need a cascaded AI pipeline.

Here is the proposed technical implementation plan to achieve exactly what you described:

Proposed Architecture Upgrades
1. Higher Accuracy & Fine-Grained Features (Colors/Textures)
YOLOv8 is great for drawing boxes around a "person" or "car", but it doesn't know what color the car is.

Model Upgrade: We will switch from yolov8n.pt (Nano) to yolov8m.pt (Medium) for a massive immediate boost in baseline detection accuracy.
Secondary Feature Extractor: When YOLO detects a person or car, we will crop that box and pass it to a secondary lightweight model (like OSNet or a simple Color Histogram algorithm) to extract attributes like "Red Shirt" or "White SUV".
2. Number Plate Reading (ANPR)
ALPR Pipeline: When a car is detected, we will pass the car's cropped image to our ANPR module.
We will integrate EasyOCR or Tesseract to automatically read the characters on the license plate and attach them to the vehicle's track data.
3. AI Semantic Descriptions (Vision-Language)
To generate descriptions like "A person in a red shirt loitering near the fence", we will use a template-based generator that combines the YOLO class, the extracted color, and the triggered Zone/Event.
(Optional): If you want truly intelligent descriptions, we can integrate a lightweight open-source Vision-Language Model (like Moondream or Florence-2) to "look" at the snapshot and write a paragraph describing it.
4. Capturing & Displaying Photos (Snapshots)
Backend Storage: We will modify the CameraPipeline so that whenever a High-Risk Event or Alert triggers, it saves the current full video frame (with drawn boxes) to outputs/snapshots/{alert_id}.jpg.
Frontend UI: We will update the Dashboard's Events and Alerts pages to display a thumbnail of this photo. Clicking it will show the full high-resolution image of the action.