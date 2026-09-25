from pathlib import Path
import json
from datetime import date

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT = ROOT / "outputs" / "IBVAP_Full_Project_Report.docx"
METRICS = BACKEND / "outputs" / "eval" / "backend" / "metrics.json"
RUNTIME = BACKEND / "outputs" / "metrics" / "runtime_smoke.json"
DEMO = BACKEND / "outputs" / "metrics" / "demo_video_report.json"
CONFUSION = BACKEND / "outputs" / "eval" / "backend" / "confusion_matrix.png"
CONFUSION_NORM = BACKEND / "outputs" / "eval" / "backend" / "confusion_matrix_normalized.png"
F1_CURVE = BACKEND / "outputs" / "eval" / "backend" / "BoxF1_curve.png"
REPORT_ASSETS = ROOT / "outputs" / "report_assets"
FLOWCHART = REPORT_ASSETS / "ibvap_end_to_end_flow.png"
TWO_STAGE = REPORT_ASSETS / "ibvap_two_stage_pipeline.png"
TRAINING_FLOW = REPORT_ASSETS / "ibvap_training_lifecycle.png"
DATASET_TREE = REPORT_ASSETS / "ibvap_dataset_structure.png"


def _font(size, bold=False):
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _center_text(draw, box, text, font, fill="1F2937"):
    x1, y1, x2, y2 = box
    lines = str(text).split("\n")
    line_h = font.size + 4
    total_h = line_h * len(lines)
    y = y1 + (y2 - y1 - total_h) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        draw.text(((x1 + x2 - (bbox[2] - bbox[0])) / 2, y), line, font=font, fill=fill)
        y += line_h


def _arrow(draw, start, end, fill="1F4E78", width=6):
    draw.line([start, end], fill=fill, width=width)
    import math
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 16
    p1 = (end[0] - size * math.cos(angle - math.pi / 6), end[1] - size * math.sin(angle - math.pi / 6))
    p2 = (end[0] - size * math.cos(angle + math.pi / 6), end[1] - size * math.sin(angle + math.pi / 6))
    draw.polygon([end, p1, p2], fill=fill)


def make_flowcharts():
    REPORT_ASSETS.mkdir(parents=True, exist_ok=True)
    navy, blue, light, pale, ink, green = "#1F4E78", "#2F75B5", "#EAF2F8", "#F5F8FB", "#1F2937", "#2E7D32"
    font = _font(26)
    small = _font(20)
    bold = _font(29, True)

    im = Image.new("RGB", (1800, 470), "#FFFFFF")
    d = ImageDraw.Draw(im)
    d.text((70, 28), "IBVAP operational flow", font=bold, fill=navy)
    labels = [
        ("Video sources", "MP4 / RTSP\n4 configured cameras"),
        ("Ingestion", "Decode, buffer\nand sampling"),
        ("Stage 1", "Coarse detector\nCUDA + TensorRT"),
        ("Tracking", "ByteTrack\ntrack lifecycle"),
        ("Stage 2", "Fine classifier\noptional face / ANPR"),
        ("Context", "Zones, fences,\nbehavior, fusion"),
        ("Risk", "Score, gate,\nstate machine"),
        ("Evidence", "Alert, snapshot,\nclip and dashboard API"),
    ]
    x0, y, w, h, gap = 55, 150, 195, 150, 27
    for i, (title, body) in enumerate(labels):
        x = x0 + i * (w + gap)
        fill = light if i not in (2, 4, 7) else ("#D9EAF7" if i in (2, 4) else "#E2F0D9")
        d.rounded_rectangle((x, y, x + w, y + h), radius=18, fill=fill, outline=navy, width=3)
        _center_text(d, (x + 8, y + 16, x + w - 8, y + 60), title, bold, navy)
        _center_text(d, (x + 8, y + 62, x + w - 8, y + h - 10), body, small, ink)
        if i < len(labels) - 1:
            _arrow(d, (x + w + 5, y + h // 2), (x + w + gap - 5, y + h // 2), blue, 5)
    im.save(FLOWCHART)

    im = Image.new("RGB", (1800, 760), "#FFFFFF")
    d = ImageDraw.Draw(im)
    d.text((70, 28), "Two-stage detection and enrichment pipeline", font=bold, fill=navy)
    # stage bands
    d.rounded_rectangle((55, 105, 1745, 355), radius=20, fill="#F3F8FC", outline=blue, width=3)
    d.rounded_rectangle((55, 410, 1745, 665), radius=20, fill="#F7FBF4", outline=green, width=3)
    d.text((85, 123), "STAGE 1  |  COARSE DETECTION", font=bold, fill=navy)
    d.text((85, 428), "STAGE 2  |  SELECTIVE FINE-GRAINED ENRICHMENT", font=bold, fill=green)
    top = [("Frame", "sampled image"), ("Preprocess", "resize / normalize"), ("YOLO detector", "13 coarse classes"), ("Boxes + scores", "class, bbox, confidence")]
    bot = [("Military crop", "aircraft / helicopter /\ndrone / ground vehicle"), ("Fine classifier", "224px crop, CUDA\nconfidence gate 0.55"), ("Optional enrichments", "face embedding,\nplate OCR / consensus"), ("Enriched track", "specific type, identity\nand plate context")]
    for row, yy, col in [(top, 185, blue), (bot, 495, green)]:
        for i, (title, body) in enumerate(row):
            x = 100 + i * 405
            d.rounded_rectangle((x, yy, x + 295, yy + 120), radius=15, fill="#FFFFFF", outline=col, width=3)
            _center_text(d, (x + 8, yy + 10, x + 287, yy + 55), title, bold, col)
            _center_text(d, (x + 8, yy + 55, x + 287, yy + 110), body, small, ink)
            if i < len(row) - 1:
                _arrow(d, (x + 302, yy + 60), (x + 395, yy + 60), col, 5)
    _arrow(d, (895, 320), (895, 485), navy, 6)
    d.text((930, 365), "route only eligible\ncoarse classes", font=small, fill=navy)
    im.save(TWO_STAGE)

    im = Image.new("RGB", (1800, 610), "#FFFFFF")
    d = ImageDraw.Draw(im)
    d.text((70, 25), "Model development and validation lifecycle", font=bold, fill=navy)
    steps = [
        ("1  Inventory", "119,706 detector images\n557,005 crop images"),
        ("2  Clean", "MD5 and dHash\nexact / near dedup"),
        ("3  Balance", "retain rare classes\n5% backgrounds"),
        ("4  Structure", "13 coarse classes\n29 fine classes"),
        ("5  Split", "group-aware and\nleak-free"),
        ("6  Train", "YOLO at 640px\nEfficientNet at 224px"),
        ("7  Select", "best checkpoint by\nvalidation metrics"),
        ("8  Evaluate", "precision, recall, F1,\nmAP and confusion matrix"),
        ("9  Deploy", "TensorRT / CUDA\nruntime smoke tests"),
    ]
    positions = [(70 + i * 340, 135) for i in range(5)] + [(1430 - i * 340, 380) for i in range(4)]
    for i, ((title, body), (x, y)) in enumerate(zip(steps, positions)):
        col = blue if i < 6 else green
        d.rounded_rectangle((x, y, x + 270, y + 145), radius=18, fill="#F7FAFC", outline=col, width=3)
        _center_text(d, (x + 8, y + 12, x + 262, y + 58), title, bold, col)
        _center_text(d, (x + 8, y + 62, x + 262, y + 135), body, small, ink)
        if i < 4:
            _arrow(d, (x + 277, y + 72), (x + 330, y + 72), blue, 5)
        elif i == 4:
            _arrow(d, (x + 135, y + 152), (x + 135, 365), navy, 5)
        elif 5 <= i < 8:
            _arrow(d, (x - 7, y + 72), (x - 70, y + 72), green, 5)
    im.save(TRAINING_FLOW)

    im = Image.new("RGB", (1800, 760), "#FFFFFF")
    d = ImageDraw.Draw(im)
    d.text((70, 25), "Dataset release structure", font=bold, fill=navy)
    d.rounded_rectangle((60, 95, 1740, 690), radius=20, fill="#FAFCFE", outline=navy, width=3)
    d.text((95, 120), "backend/data/dataset", font=bold, fill=navy)
    tree_font = _font(25)
    mono = _font(23)
    left = [
        "detector/",
        "  dataset.yaml",
        "  images/",
        "    train/    47,501 images",
        "    val/       5,130 images",
        "  labels/",
        "    train/    YOLO text labels",
        "    val/      YOLO text labels",
    ]
    right = [
        "classifier/",
        "  train/<class>/    19,865 crops",
        "  val/<class>/       2,204 crops",
        "  29 fine and fallback classes",
        "",
        "classes.json      shared taxonomy",
        "manifest.json     lineage and counts",
        ".build/           resumable stage records",
    ]
    for i, line in enumerate(left):
        d.text((115, 190 + i * 55), line, font=mono, fill=ink if i else blue)
    for i, line in enumerate(right):
        d.text((930, 190 + i * 55), line, font=mono, fill=ink if i else green)
    d.line((875, 170, 875, 650), fill="#C9D5E2", width=3)
    im.save(DATASET_TREE)


make_flowcharts()


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def borders(table, color="D9D9D9"):
    tbl_pr = table._tbl.tblPr
    border = tbl_pr.first_child_found_in("w:tblBorders")
    if border is None:
        border = OxmlElement("w:tblBorders")
        tbl_pr.append(border)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        node = border.find(qn(tag))
        if node is None:
            node = OxmlElement(tag)
            border.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), color)


def set_cell(cell, text, bold=False, color="000000", align=WD_ALIGN_PARAGRAPH.LEFT, size=9):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    run.font.name = "Aptos"
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def table(doc, headers, rows, widths=None, font_size=8.5):
    t = doc.add_table(rows=1, cols=len(headers))
    t.autofit = False
    borders(t)
    for i, h in enumerate(headers):
        set_cell(t.rows[0].cells[i], h, bold=True, color="FFFFFF", align=WD_ALIGN_PARAGRAPH.CENTER, size=font_size)
        shade(t.rows[0].cells[i], "1F4E78")
    tr_pr = t.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)
    for r_idx, row in enumerate(rows):
        cells = t.add_row().cells
        for i, value in enumerate(row):
            align = WD_ALIGN_PARAGRAPH.CENTER if i > 0 else WD_ALIGN_PARAGRAPH.LEFT
            set_cell(cells[i], value, align=align, size=font_size)
            if r_idx % 2 == 1:
                shade(cells[i], "F3F6F9")
    if widths:
        for row in t.rows:
            for i, width in enumerate(widths):
                row.cells[i].width = Inches(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def add_bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2)
    p.add_run(text)
    return p


def add_caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    r.italic = True
    r.font.size = Pt(8.5)
    r.font.color.rgb = RGBColor(89, 89, 89)


def add_heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    p.paragraph_format.keep_with_next = True
    return p


metrics = json.loads(METRICS.read_text(encoding="utf-8"))
runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
demo = json.loads(DEMO.read_text(encoding="utf-8"))["summary"]

doc = Document()
sec = doc.sections[0]
sec.top_margin = Inches(0.65)
sec.bottom_margin = Inches(0.65)
sec.left_margin = Inches(0.75)
sec.right_margin = Inches(0.75)

styles = doc.styles
styles["Normal"].font.name = "Aptos"
styles["Normal"].font.size = Pt(10)
styles["Normal"].paragraph_format.space_after = Pt(6)
for name, size, color in [("Title", 24, "000000"), ("Heading 1", 16, "1F4E78"), ("Heading 2", 12, "1F4E78")]:
    st = styles[name]
    st.font.name = "Aptos Display" if name == "Title" else "Aptos"
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = RGBColor.from_string(color)

title = doc.add_paragraph(style="Title")
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
title.paragraph_format.space_before = Pt(95)
title.paragraph_format.space_after = Pt(20)
title.add_run("IBVAP Full Project Report")
title_pr = title._p.get_or_add_pPr()
title_borders = OxmlElement("w:pBdr")
title_bottom = OxmlElement("w:bottom")
title_bottom.set(qn("w:val"), "nil")
title_borders.append(title_bottom)
title_pr.append(title_borders)
sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = sub.add_run("Intelligent Border Video Analytics Platform")
r.font.size = Pt(16)
r.font.bold = True
r.font.color.rgb = RGBColor.from_string("1F4E78")
sub2 = doc.add_paragraph()
sub2.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = sub2.add_run("AI Based Video Analytics for Existing CCTV Infrastructure")
r.font.size = Pt(12)
r.font.color.rgb = RGBColor(89, 89, 89)
meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
meta.paragraph_format.space_before = Pt(65)
r = meta.add_run(
    f"Smart India Hackathon 2026\nProblem Statement 26187\nProject report date {date.today().isoformat()}\nPrepared by the IBVAP Project Team"
)
r.font.size = Pt(11)
r.font.color.rgb = RGBColor(89, 89, 89)
doc.add_page_break()

add_heading(doc, "Abstract", 1)
doc.add_paragraph(
    "IBVAP is a software-based intelligent video analytics platform that transforms existing CCTV, IP-camera and recorded-video sources into structured, explainable security events. "
    "The system combines GPU-accelerated object detection, multi-object tracking, restricted-zone and virtual-fence analysis, temporal behaviour detection, optional identity and number-plate enrichment, context fusion, interpretable risk scoring, evidence capture and a web operator dashboard. "
    "Its central design principle is to convert low-level detections into one risk-scored event for human review instead of generating independent alerts for every signal."
)
doc.add_paragraph(
    "The completed implementation uses a FastAPI and SQLite backend, a Next.js and React operator interface, Supabase-based authentication, a 13-class border-aware detector, a selective 29-class fine classifier, ByteTrack tracking and TensorRT acceleration on NVIDIA CUDA hardware. "
    f"The final labelled detector evaluation covered 12,200 images and measured precision {metrics['precision']:.3f}, recall {metrics['recall']:.3f}, macro F1 {metrics['f1_macro']:.3f}, mAP@50 {metrics['map50']:.3f} and mAP@50-95 {metrics['map50_95']:.3f}. "
    "The merged report documents the problem, requirements, architecture, implementation, dataset construction, model training, validation, security controls, deployment procedure, limitations and future development roadmap."
)

add_heading(doc, "Project at a Glance", 1)
table(doc, ["Item", "Project detail"], [
    ["Project", "IBVAP Intelligent Border Video Analytics Platform"],
    ["Purpose", "AI-assisted monitoring and prioritization of predefined security events from existing video infrastructure"],
    ["Primary users", "Security operators, supervisors, administrators and authorized auditors"],
    ["Core pipeline", "Ingest, detect, track, analyze context, fuse signals, score risk, alert, preserve evidence and support human review"],
    ["Main stack", "Python, OpenCV, PyTorch, Ultralytics, TensorRT, FastAPI, SQLAlchemy, SQLite, Next.js, React, TypeScript and Supabase Auth"],
    ["Validated hardware", "NVIDIA GeForce RTX 4050 Laptop GPU with CUDA and TensorRT"],
    ["Validation status", "Backend, frontend, browser, GPU runtime, labelled detector evaluation and demo-video coverage completed"],
], widths=[1.65, 5.7], font_size=8.5)

add_heading(doc, "Report Contents", 1)
for item in [
    "Project background, problem statement and objectives",
    "Scope, stakeholders, functional requirements and non-functional requirements",
    "System architecture, technology stack and two-stage AI pipeline",
    "Backend, frontend, database, API, dashboard and module implementation",
    "Dataset engineering, model construction and training configuration",
    "Testing methodology, smoke validation and quantitative accuracy results",
    "Security, privacy, evidence integrity, deployment and operations",
    "Limitations, risks, recommendations, future scope and conclusion",
]:
    add_bullet(doc, item)

add_heading(doc, "Executive Summary", 1)
doc.add_paragraph(
    "IBVAP addresses the limits of continuous human CCTV observation by automatically detecting supported objects, maintaining track identities, interpreting configured spatial and temporal conditions and presenting prioritized events for operator review. "
    "It is an AI-assisted decision-support platform rather than an autonomous enforcement system. Human operators remain responsible for reviewing evidence and deciding the appropriate response."
)
doc.add_paragraph(
    "The implemented platform supports recorded files and camera streams, GPU detection, ByteTrack tracking, polygon zones, virtual fences, direction and loitering analysis, night context, ANPR, optional face recognition, context fusion, explainable risk scoring, rate-limited alerts, evidence snapshots and clips, audit logging, reporting and a multi-view web dashboard. "
    "The application completed an end-to-end validation run on the RTX 4050 GPU: 352 backend tests passed, 21 frontend tests passed, TypeScript checking passed, warmed browser flows passed, all four configured cameras processed frames, and full detector metrics and confusion matrices were produced."
)

add_heading(doc, "Project Background and Problem Statement", 1)
doc.add_paragraph(
    "Traditional CCTV systems are effective at recording and displaying video but depend heavily on operators to watch many feeds continuously. As camera counts grow, important events may be missed, responses may be delayed, and the time required to search recordings increases. "
    "Low light, occlusion, distance, movement and network interruptions further reduce the reliability of manual observation."
)
doc.add_paragraph(
    "IBVAP adds a modular analytics layer over existing authorized video sources. The platform does not attempt to classify a person as dangerous or replace security personnel. It detects measurable conditions such as entry into a restricted area, fence crossing, prolonged dwell, unexpected movement, a watchlist or plate match, or camera unavailability, and then packages the available evidence for human review."
)

add_heading(doc, "Project Objectives", 1)
for item in [
    "Use existing CCTV, IP-camera and recorded-video infrastructure wherever possible.",
    "Detect security-relevant people, vehicles, plates, aircraft, drones, military ground vehicles, animals and night-vision objects.",
    "Track objects across frames and maintain trajectory and lifecycle information.",
    "Support polygon zones, virtual fences, direction analysis, loitering and night context.",
    "Combine spatial, temporal, behavioural, identity and vehicle observations into one explainable event.",
    "Assign configurable risk scores and generate prioritized, rate-limited alerts.",
    "Store events, alerts, evidence and audit actions for review and reporting.",
    "Provide an operator dashboard with camera status, live views, alerts, maps, reports and configuration tools.",
    "Measure detection and application performance without claiming perfect accuracy.",
]:
    add_bullet(doc, item)

add_heading(doc, "Project Scope", 1)
table(doc, ["In scope", "Outside project scope"], [
    ["Authorized RTSP streams and recorded-video ingestion", "Manufacturing or installing cameras and physical sensors"],
    ["Detection, tracking, zones, virtual fences and event generation", "Weapons, autonomous physical intervention or final enforcement decisions"],
    ["ANPR and optional consent-based face matching", "Unlawful surveillance or access to unauthorized camera feeds"],
    ["Context fusion, explainable risk scoring and alert prioritization", "Claims of guaranteed identification or 100 percent accuracy"],
    ["Event database, evidence, audit logging, reports and dashboard", "Physical gate, barrier or access-control hardware"],
    ["Evaluation on labelled datasets and controlled demo videos", "Unvalidated production-scale performance claims"],
], widths=[3.65, 3.7], font_size=8.2)

add_heading(doc, "Stakeholders and User Roles", 1)
table(doc, ["Role", "Primary responsibilities"], [
    ["Security operator", "Monitor cameras, receive alerts, open event details, review evidence and update review status"],
    ["Supervisor", "Review high-priority events, system activity, camera availability and operational reports"],
    ["Administrator", "Configure cameras, zones, users, roles, thresholds, retention and integrations"],
    ["Authorized auditor", "Search historical events, inspect evidence and review permitted audit records"],
    ["Project or research team", "Prepare datasets, train models, configure demonstrations, run experiments and maintain the platform"],
], widths=[1.8, 5.55], font_size=8.5)

add_heading(doc, "Functional Requirements Summary", 1)
table(doc, ["Capability group", "Implemented requirement"], [
    ["Video ingestion", "Accept authorized RTSP or file sources, expose connection status and recover safely from interruptions"],
    ["Perception", "Detect the 13-class operational taxonomy and optionally refine eligible military-object crops"],
    ["Tracking", "Assign temporary identities, maintain trajectories, manage lifecycle and tolerate brief occlusion"],
    ["Spatial and temporal analysis", "Evaluate zones, fences, direction, dwell time, movement and night or low-light context"],
    ["Identity and vehicle enrichment", "Perform optional face embedding and matching, plate localization, OCR, consensus and watchlist checks"],
    ["Fusion and risk", "Combine observations, suppress duplicates, calculate explainable risk and manage event state"],
    ["Alerts and evidence", "Rate-limit alerts, store snapshots and clips, hash evidence and publish real-time notifications"],
    ["Operator application", "Provide camera views, alerts, events, maps, audit records, reports, configuration and role-aware access"],
], widths=[2.05, 5.3], font_size=8)

add_heading(doc, "Non Functional Requirements Summary", 1)
table(doc, ["Quality attribute", "Project requirement"], [
    ["Performance", "Use GPU acceleration, batched inference and configurable frame sampling while reporting measured latency and throughput"],
    ["Reliability", "Handle camera failure, empty frames, corrupt video, model errors and database errors without unsafe silent success"],
    ["Explainability", "Store contributing factors, semantic descriptions, confidence values and risk reasons with events"],
    ["Security", "Use authenticated routes, role checks, rate limits, trusted-host and CORS policies, input validation and audit logging"],
    ["Privacy", "Limit identity features to approved use, support retention controls and avoid treating uncertain recognition as fact"],
    ["Maintainability", "Keep modules configurable, testable and isolated through YAML settings, repositories, service boundaries and fallback paths"],
    ["Scalability", "Support multiple camera workers and shared inference coordination within available CPU, GPU, memory and storage capacity"],
], widths=[1.7, 5.65], font_size=8)

add_heading(doc, "Validation Scope", 1)
table(doc, ["Area", "Validation performed", "Result"], [
    ["Backend", "352 Python tests covering API, database, pipeline, security, evidence, watchlists and detection", "PASS"],
    ["Frontend", "21 Vitest tests and TypeScript typecheck", "PASS"],
    ["Browser E2E", "18 Playwright tests across auth, navigation, events, alerts, storage and watchlists", "16 PASS, 1 SKIP, 1 startup timeout; rerun PASS"],
    ["GPU runtime", "TensorRT pipeline smoke across 4 configured demo cameras", "PASS"],
    ["Detector accuracy", "Full labelled validation split at 640 pixels on CUDA", "PASS; metrics generated"],
    ["Demo coverage", "19 local videos, 3 sampled frames per video", "PASS; coverage report generated"],
], widths=[1.25, 4.75, 1.25], font_size=8.5)

add_heading(doc, "System Architecture and Design", 1)
doc.add_paragraph(
    "IBVAP is organized as a connected perception-to-decision pipeline rather than as a collection of isolated models. Video sources are opened by ingestion workers, frames are buffered and sampled, "
    "the TensorRT detector produces object boxes, ByteTrack maintains object identities, and spatial and temporal modules interpret trajectories. Behaviour and enrichment signals are combined by context fusion, "
    "the risk engine assigns an explainable score, and the alert and evidence layers persist events for the dashboard and review APIs."
)
table(doc, ["Pipeline stage", "Project component", "Responsibility and verified evidence"], [
    ["Ingestion", "src/ingestion/video_source.py and frame_buffer.py", "Four configured MP4 cameras opened and processed"],
    ["Detection", "src/detection/detector.py and batch_coordinator.py", "TensorRT engine loaded on CUDA; detections and latency recorded"],
    ["Tracking", "src/tracking/track_manager.py, tracker.py and track.py", "Active tracks and frame-to-frame routing covered by tests and runtime"],
    ["Spatial analysis", "src/spatial/zone_manager.py and fence_detector.py", "Zones and fences loaded; zone and crossing tests passed"],
    ["Temporal analysis", "src/temporal/loitering_detector.py and night_detector.py", "Loitering lifecycle and night context covered by backend tests"],
    ["Fusion and risk", "src/fusion and src/risk", "Deduplication, escalation, risk determinism and suppression tests passed"],
    ["Evidence and alerts", "src/alerts and database repository", "Snapshots, clips, HMAC chain, retention and alert lifecycle covered"],
    ["API and dashboard", "FastAPI routes plus Next.js frontend", "REST health, auth, navigation and browser flows passed"],
], widths=[1.35, 2.75, 3.25], font_size=7.8)

add_heading(doc, "Technology Stack", 1)
table(doc, ["Layer", "Implemented technology", "Purpose"], [
    ["Computer vision", "Python, OpenCV and NumPy", "Video capture, frame operations, image processing and visualization"],
    ["Deep learning", "PyTorch, torchvision, timm and Ultralytics", "Coarse object detection and fine-grained crop classification"],
    ["GPU inference", "CUDA and TensorRT with FP16 support", "Accelerated model execution on NVIDIA hardware"],
    ["Tracking and geometry", "ByteTrack through supervision and Shapely", "Persistent object tracks, trajectories, zones and fence intersections"],
    ["Backend", "FastAPI, Uvicorn and WebSocket", "REST services, health, streaming, alerts, reports and real-time push"],
    ["Persistence", "SQLAlchemy 2 and SQLite", "Canonical application records for cameras, tracks, events, alerts, zones, identities and audit data"],
    ["Authentication", "Supabase Auth, locally verified JWT and role guards", "User sessions, protected routes and administrator authorization"],
    ["Frontend", "Next.js, React, TypeScript and Tailwind CSS", "Static-export operator console, visual analytics, maps and configuration"],
    ["Deployment", "Docker Compose, nginx and environment configuration", "Containerized or local service startup and production reverse proxy"],
    ["Evaluation", "Pytest, Vitest, Playwright, Matplotlib and Ultralytics metrics", "Unit, integration, browser and model-performance verification"],
], widths=[1.35, 2.6, 3.4], font_size=7.6)

add_heading(doc, "Module Design and Implementation", 1)
table(doc, ["Module", "Implementation summary"], [
    ["Ingestion", "OpenCV-based RTSP and file readers, frame buffering, reconnect handling, camera watchdog and per-camera processing threads"],
    ["Detection", "13-class YOLO detector with TensorRT engine discovery, class normalization, configurable thresholds and shared multi-camera batch coordination"],
    ["Tracking", "ByteTrack association, persistent UUID-backed track state, trajectories, expiry management and best-frame selection"],
    ["Spatial intelligence", "Polygon zone membership, virtual-fence crossing, direction estimation and heatmap accumulation"],
    ["Temporal intelligence", "Loitering duration, stationary analysis, night-hour and low-brightness context"],
    ["Fine classification", "Selective EfficientNetV2 crop classification for aircraft, helicopters, UAVs and military ground vehicles"],
    ["Face and watchlists", "Optional face detection, embedding, matching and authorized watchlist enrichment with uncertainty handling"],
    ["ANPR", "Plate assignment, OCR engine cascade, format checks, multi-frame consensus and plate watchlist matching"],
    ["Behaviour and fusion", "Behaviour flags, context fusion, cooldowns, semantic event descriptions and event lifecycle state machine"],
    ["Risk and alerts", "Configurable weighted risk scoring, severity levels, deduplication, rate limits, snapshots, clips and notifications"],
    ["API and persistence", "FastAPI route groups backed by a SQLAlchemy repository and authenticated WebSocket alert delivery"],
    ["Frontend", "Dashboard, cameras, multiview, map, alerts, events, zones, audit, reports, settings and watchlists"],
], widths=[1.7, 5.65], font_size=7.8)

flow_heading = add_heading(doc, "Operational Flowcharts", 1)
doc.add_paragraph(
    "The following diagrams show the validated runtime path from video acquisition to decision and evidence delivery. "
    "The flow separates high-throughput detection from selective enrichment so that expensive second-stage analysis is applied only where it adds operational value."
)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.add_run().add_picture(str(FLOWCHART), width=Inches(7.0))
add_caption(doc, "Figure 3. End to end IBVAP operational flow")

add_heading(doc, "Two Stage Detection Pipeline", 1)
doc.add_paragraph(
    "IBVAP uses a two-stage computer-vision design. Stage 1 is the coarse detector: it processes sampled frames with the CUDA TensorRT engine and emits the 13-class surveillance vocabulary used by tracking, spatial rules and risk logic. "
    "Stage 2 is a selective enrichment path. It receives only crops belonging to military-relevant coarse classes and attempts to identify a more specific type. "
    "If the fine classifier is unavailable, below its confidence threshold, or unable to produce a safe answer, the system retains the coarse label rather than replacing it with an uncertain prediction."
)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.add_run().add_picture(str(TWO_STAGE), width=Inches(7.0))
add_caption(doc, "Figure 4. Stage 1 coarse detection and Stage 2 selective enrichment")
table(doc, ["Stage", "Input", "Processing", "Output and control"], [
    ["Stage 1: coarse detection", "Sampled BGR frame from each camera", "Resize and normalize; TensorRT detector on CUDA; decode class, bounding box and confidence", "13 coarse classes, object boxes and scores. Every detected object can enter tracking."],
    ["Track and context", "Stage 1 boxes across frames", "ByteTrack association, track lifecycle, zones, fences, direction, loitering and night context", "Stable track identity and behavioural context for fusion and risk scoring."],
    ["Stage 2: fine classifier", "Crops from aircraft, helicopter, drone_uav or military_ground_vehicle tracks", "Crop preprocessing at 224 pixels; fine model inference on CUDA; minimum confidence gate 0.55; re-check interval 2 seconds", "Specific type when confidence is sufficient; otherwise the original coarse class is preserved."],
    ["Optional identity enrichment", "Eligible person or plate crops", "Face detector and embedding matcher when configured; ANPR OCR with consensus and format checks", "Identity and plate context are attached to the track only when the corresponding service is active and validated."],
    ["Decision and evidence", "Enriched track plus behaviour context", "Context fusion, risk score, event state machine, alert rate limits, snapshot hashing and clip capture", "Explainable event, alert, dashboard record and reviewable evidence."],
], widths=[1.4, 2.0, 2.35, 1.5], font_size=7.2)

add_heading(doc, "Database and Persistence Design", 1)
doc.add_paragraph(
    "SQLite is the canonical application datastore and is accessed through SQLAlchemy models and a repository layer. Supabase Postgres is limited to authentication identity and user-profile role information. "
    "This separation keeps the video analytics pipeline independent from external cloud availability while preserving managed authentication."
)
table(doc, ["Entity", "Information retained"], [
    ["Cameras", "Identifier, name, source, location, coordinates, configuration and online status"],
    ["Tracks", "Camera, object type, lifecycle timestamps, trajectory, enrichment and current risk context"],
    ["Events", "Event type, track, timestamp, duration, confidence, risk, contributing factors and evidence references"],
    ["Alerts", "Severity, review state, snapshot, identity or plate result and operator actions"],
    ["Zones", "Camera-specific polygon definitions, types, enabled state and rule configuration"],
    ["Identity results", "Track, identity label, similarity score, status and timestamp"],
    ["ANPR results", "Track, plate text, OCR confidence, consensus and timestamp"],
    ["Audit logs", "User action, target, timestamp, source IP and relevant metadata"],
], widths=[1.75, 5.6], font_size=8)

add_heading(doc, "API and Integration Design", 1)
table(doc, ["Interface", "Representative operations"], [
    ["Health and models", "Application readiness, pipeline state, camera availability and loaded-model registry"],
    ["Cameras and streams", "Camera list and configuration, status, snapshots, MJPEG or annotated frame access"],
    ["Events and alerts", "Search, detail, counts, review, escalation, closure and false-positive feedback"],
    ["Zones and fences", "Create, read and update camera-specific spatial rules"],
    ["Tracks and statistics", "Track detail, runtime summaries, class counts and operational metrics"],
    ["Reports", "Daily aggregation and export-ready operational summaries"],
    ["Audit", "Administrator-only review of security-relevant user actions"],
    ["Authentication", "JWT-protected routes, role guards and server-side token revocation on logout"],
    ["Real-time alerts", "Authenticated WebSocket delivery through the bearer sub-protocol handshake"],
], widths=[1.8, 5.55], font_size=8)

add_heading(doc, "Dashboard and User Workflows", 1)
table(doc, ["Workflow", "Operator experience"], [
    ["Normal monitoring", "Open the dashboard, review camera health, recent alerts, event counts and system notifications"],
    ["Live investigation", "Select a camera, view the annotated stream, track identifiers, zones and current risk context"],
    ["Alert review", "Open an alert, inspect what happened, when and where, review evidence and update disposition"],
    ["Event search", "Filter historical events by camera, event type, severity and time range"],
    ["Spatial configuration", "Draw or edit a restricted zone or virtual fence and enable or disable its rule"],
    ["Operational awareness", "Use multiview, map, trend charts, heatmaps, reports and audit history"],
    ["Watchlist administration", "Manage authorized plate and face lists subject to role and policy controls"],
], widths=[1.8, 5.55], font_size=8.2)

add_heading(doc, "Security Privacy and Evidence Integrity", 1)
table(doc, ["Control area", "Implemented approach"], [
    ["Authentication", "Supabase JWT validation with protected REST routes and authenticated WebSocket connections"],
    ["Authorization", "Role-aware guards for operator and administrator actions"],
    ["Network protection", "Trusted-host policy, configured CORS allow-list, rate limiting and real-client IP handling"],
    ["Input hardening", "Path-traversal, injection, encoded-path, upload-size and webhook URL validation"],
    ["Credential handling", "Environment-based secrets and no fixed default administrator or operator password"],
    ["Auditability", "Request and user-action audit records with timestamps and source information"],
    ["Evidence integrity", "SHA-256 snapshot hashes, HMAC chain checks, checkpointing and tamper-detection tests"],
    ["Privacy", "Authorized use, configurable retention, uncertainty-aware identity handling and human review"],
], widths=[1.8, 5.55], font_size=8)

add_heading(doc, "Deployment and Configuration", 1)
doc.add_paragraph(
    "The platform supports local development, a Windows production-style launcher and Docker Compose deployment. The frontend is built as a static export and can be served by nginx, which proxies API, WebSocket, snapshot and static requests to the FastAPI backend. "
    "Training is separate from serving: the runtime loads completed model artifacts and never starts a training job."
)
table(doc, ["Configuration or service", "Operational purpose"], [
    ["configs/cameras.yaml", "Authorized camera identifiers, locations, source paths or RTSP URLs and per-camera limits"],
    ["configs/zones.yaml", "Restricted, buffer, safe and entry-exit polygons plus virtual fences"],
    ["configs/thresholds.yaml", "Detection, tracking, behaviour, face, ANPR, alert, evidence and model settings"],
    ["configs/risk_weights.yaml", "Risk factors, weights, severity thresholds and score tables"],
    ["Environment variables", "Authentication secrets, database URL, allowed hosts, CORS, environment mode and notification providers"],
    ["Backend service", "Python environment, model artifacts and FastAPI server on the configured application port"],
    ["Frontend service", "Static Next.js build for nginx or development server during active UI work"],
    ["Docker Compose", "Repeatable backend, frontend and reverse-proxy container startup"],
], widths=[2.05, 5.3], font_size=8)

add_heading(doc, "Known Limitations and Risk Mitigation", 1)
table(doc, ["Risk or limitation", "Current mitigation and required follow-up"], [
    ["False positives and false negatives", "Use confidence thresholds, temporal confirmation, event cooldowns, human review and labelled regression evaluation"],
    ["Low light, weather, distance and motion blur", "Use night context, representative data, targeted augmentation and future domain-specific evaluation"],
    ["Occlusion and tracking identity changes", "Use ByteTrack lifecycle settings, bounded history and evidence linked to stable internal track records"],
    ["Dataset mismatch", "Keep split manifests, evaluate deployment-like videos and expand data through reviewed active learning"],
    ["ANPR uncertainty", "Store OCR confidence, require consensus and allow unknown or uncertain results"],
    ["Face-recognition risk", "Keep optional, require approved data and providers, apply thresholds and avoid treating matches as infallible identity"],
    ["Camera or network failure", "Expose health state, watchdog recovery and clear unavailable status rather than silent operation"],
    ["GPU throughput", "Measure queue and service latency, profile batching and run sustained multi-camera soak tests"],
    ["Storage growth", "Apply retention policies, storage limits, free-space checks and cleanup previews"],
], widths=[2.15, 5.2], font_size=7.8)

add_heading(doc, "How We Built and Trained the Models", 1)
doc.add_paragraph(
    "The model-development workflow was designed to make the reported accuracy reproducible and resistant to data leakage. Raw source files remain unchanged under backend/data/raw_dataset. "
    "A six-stage builder creates a clean release dataset, and the training scripts consume only the emitted train and validation structures. The full lifecycle is shown below."
)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.add_run().add_picture(str(TRAINING_FLOW), width=Inches(7.0))
add_caption(doc, "Figure 5. Dataset preparation, training, evaluation and deployment lifecycle")

add_heading(doc, "Dataset Sources and Preparation", 1)
doc.add_paragraph(
    "Two complementary source collections were used. The detector collection contains full images with YOLO bounding-box labels. The crop collection contains object crops arranged by class for the fine classifier. "
    "The builder indexes every image with cryptographic and perceptual hashes, removes exact and near duplicates before splitting, preserves rare security-relevant classes, resolves aggregate folders, and creates group-aware train and validation partitions."
)
table(doc, ["Preparation stage", "Measured input or output", "Purpose"], [
    ["Source inventory", "119,706 detector images and 557,005 classification crops indexed", "Establish a complete, hash-based inventory before any selection."],
    ["Deduplication", "67,950 detector images and 240,976 crops retained; 6,201 label conflicts identified", "Prevent duplicate or conflicting images from inflating validation results."],
    ["Detector rebalance", "52,631 images selected, including 11,935 rare-class images and 2,631 backgrounds", "Preserve all rare-class examples while limiting dominant common classes and retaining 5 percent backgrounds."],
    ["Classifier restructure", "29 trainable classes; minimum 200 unique images; maximum 1,500 images per class", "Fold unsupported fine classes into honest coarse fallback classes and limit class imbalance."],
    ["Leak-free split", "Detector 47,501 train and 5,130 validation; classifier 19,865 train and 2,204 validation", "Keep related frames and near-duplicates on the same side of the split using seed 42 and a 10 percent validation target."],
    ["Integrity gate", "Image-label pairing, class ranges, split overlap and expected counts verified", "Stop the build if labels are missing, class identifiers are invalid, or stale files remain."],
], widths=[1.55, 3.05, 2.75], font_size=7.5)

add_heading(doc, "Dataset Structure", 1)
doc.add_paragraph(
    "The emitted release follows the native structures expected by the two training frameworks. Stage 1 uses YOLO image and label folders plus dataset.yaml. Stage 2 uses an ImageFolder-compatible class tree, where each class has matching train and validation directories. "
    "classes.json records the shared taxonomy and manifest.json records configuration, counts and lineage for reproducibility."
)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.add_run().add_picture(str(DATASET_TREE), width=Inches(7.0))
add_caption(doc, "Figure 6. Clean detector and classifier dataset directory structure")

add_heading(doc, "Training Configuration", 1)
table(doc, ["Item", "Stage 1 Coarse Detector", "Stage 2 Fine Classifier"], [
    ["Model role", "Locate objects and assign one of 13 operational coarse classes", "Identify a more specific type for eligible military-object crops"],
    ["Architecture", "Ultralytics YOLO detector, warm-started and resumable", "EfficientNetV2-S transfer-learning model with a 29-class output head"],
    ["Input", "640 pixel detector images with YOLO boxes", "224 pixel class crops from ImageFolder train and validation trees"],
    ["Observed or defined run", "50 epochs, batch 8, CUDA device 0, two workers", "Repository recipe: 30 epochs, batch 64, CUDA when available, two workers"],
    ["Optimization", "SGD, initial learning rate 0.01, cosine schedule, momentum 0.937, weight decay 0.0005", "AdamW, learning rate 0.0003, weight decay 0.05, cosine annealing and AMP"],
    ["Augmentation", "Mosaic, mixup 0.10, copy-paste 0.15, color, scale, translation and horizontal flip", "Random resized crop, horizontal flip, color jitter and random erasing"],
    ["Class imbalance control", "Rare-class-preserving selection and copy-paste/mixup", "Per-class inverse-frequency weighted sampler and class caps"],
    ["Checkpoint rule", "Best validation checkpoint plus resumable last checkpoint", "Best checkpoint selected by macro recall rather than overall accuracy"],
], widths=[1.35, 3.05, 2.95], font_size=7.1)

add_heading(doc, "Training and Evaluation Dataset Distinction", 1)
doc.add_paragraph(
    "The recorded Stage 1 training run used backend/data/dataset/detector/dataset.yaml, containing 47,501 training images and 5,130 validation images from the clean release. "
    "The final accuracy evaluation reported in this document used configs/dataset_coarse.yaml, whose lists contain 107,438 training references and 12,200 validation images. Therefore, the precision, recall, F1 and mAP values in this report are measurements from the larger 12,200-image evaluation split, not the smaller training-release validation split."
)

add_heading(doc, "How We Accomplished the Reported Result", 1)
table(doc, ["Step", "Action completed", "Result or evidence"], [
    ["1", "Defined a shared 13-class coarse taxonomy and fine-to-coarse mapping", "Training, inference, tracking and evaluation use the same operational class names."],
    ["2", "Indexed source data and generated hashes for every detector image and crop", "Created a reproducible inventory and enabled exact and perceptual duplicate detection."],
    ["3", "Removed duplicates before splitting and resolved label conflicts", "Reduced memorisation risk and prevented the same visual content from appearing on both sides of validation."],
    ["4", "Preserved rare detector classes and retained controlled background examples", "Military vehicles, helicopters, drones, buses and other low-frequency classes remained represented."],
    ["5", "Restructured crop classes using thresholds, caps and coarse fallback buckets", "Produced 29 viable fine-class categories without forcing unsupported type predictions."],
    ["6", "Created group-aware train and validation splits and ran integrity checks", "Verified image-label pairs, valid class identifiers, expected counts and no filename overlap."],
    ["7", "Trained and resumed the Stage 1 model for 50 epochs on CUDA", "Generated best.pt, last.pt, training curves, sample predictions and confusion matrices."],
    ["8", "Prepared and loaded the Stage 2 EfficientNet checkpoint on CUDA", "Runtime smoke test confirmed a 29-class fine classifier was active."],
    ["9", "Evaluated the detector on 12,200 labelled validation images", "Measured precision 0.759, recall 0.695, macro F1 0.715, mAP50 0.727 and mAP50-95 0.523."],
    ["10", "Integrated TensorRT detection with tracking, fusion, risk, alerts and evidence", "All four configured cameras processed frames during the GPU runtime smoke test."],
    ["11", "Executed backend, frontend and browser-level regression suites", "352 backend tests, 21 frontend tests, type checking and the warmed browser flows passed."],
], widths=[0.55, 3.4, 3.35], font_size=7.3)

add_heading(doc, "Backend Test Coverage Detail", 1)
doc.add_paragraph("The backend collection contained 352 tests. The following areas were represented in the collection and final passing run.")
table(doc, ["Coverage area", "What was checked"], [
    ["Authentication and authorization", "JWT validation, role guards, admin/operator access, token revocation and scoped cameras"],
    ["Security hardening", "Injection blocking, path traversal, trusted proxy handling, WebSocket token checks and safe webhook URLs"],
    ["Camera lifecycle", "YAML seeding, persistence, user toggles, retired cameras, watchdog restarts and exponential backoff"],
    ["Detection and tracking", "Detector result conversion, class names, batch routing, late result isolation and fallback behavior"],
    ["Dataset quality", "Deduplication, clip-aware splits, leakage checks, class remapping, rare-class retention and YAML emission"],
    ["Spatial and temporal logic", "Zone trigger classes, fence crossing, track expiry, loitering clear-down and bounded history"],
    ["Incident lifecycle", "Persistence, escalation, review, closure, false-positive feedback and reports"],
    ["Evidence integrity", "Snapshot hashing, HMAC chain tamper detection, checkpoints, clip retention and orphan cleanup"],
    ["Watchlists and ANPR", "Plate normalization, exact and fuzzy matching, encrypted face embeddings and wanted-hit severity"],
], widths=[1.75, 5.6], font_size=8)

add_heading(doc, "Reproducibility Commands", 1)
doc.add_paragraph("The completed validation can be reproduced from the project root with the following commands. The GPU evaluator uses a single validation worker on Windows to avoid paging-file exhaustion.")
for cmd in [
    "cd backend",
    "..\\.venv312\\Scripts\\python.exe -m pytest tests -q",
    "..\\.venv312\\Scripts\\python.exe scripts\\smoke_runtime.py --seconds 5",
    "..\\.venv312\\Scripts\\python.exe -m ml.eval_detector --weights models\\ibvap_coarse.pt --data configs\\dataset_coarse.yaml --imgsz 640 --split val --device 0 --batch 8 --workers 0",
    "..\\.venv312\\Scripts\\python.exe scripts\\evaluate_demo_videos.py --video-dir data\\demo --weights models\\ibvap_coarse.pt --samples-per-video 3",
    "cd ..\\frontend",
    "npm.cmd test -- --run",
    "npm.cmd run typecheck",
    "npm.cmd run test:e2e",
]:
    p = doc.add_paragraph(style="No Spacing")
    p.paragraph_format.left_indent = Inches(0.25)
    run = p.add_run(cmd)
    run.font.name = "Consolas"
    run.font.size = Pt(8.5)

add_heading(doc, "Execution Environment", 1)
table(doc, ["Component", "Observed configuration"], [
    ["GPU", "NVIDIA GeForce RTX 4050 Laptop GPU, driver 616.92, 6140 MiB visible"],
    ["PyTorch", "2.14.0+cu126, CUDA available, CUDA device 0"],
    ["Detector", "IBVAP coarse detector with TensorRT engine, 13 classes, 640 input"],
    ["Fine classifier", "CUDA device reported; 29-class EfficientNetV2 model loaded"],
    ["Dataset", "12,200 validation images, 57,449 labelled instances, 1,821 backgrounds"],
    ["Application", "FastAPI backend with static Next.js frontend and SQLite persistence"],
], widths=[1.45, 5.8], font_size=8.7)

add_heading(doc, "Application Smoke Results", 1)
table(doc, ["Metric", "Measured value"], [
    ["Configured cameras", runtime["configured_cameras"]],
    ["Cameras processing frames", runtime["cameras_processing"]],
    ["Total frames processed", runtime["total_frames_processed"]],
    ["Mean pipeline FPS", runtime["mean_pipeline_fps"]],
    ["Detector mean inference", f"{runtime['detector_mean_ms']:.2f} ms"],
    ["Detector service time", f"{runtime['detector_service_ms']:.2f} ms"],
    ["Face recognition", "Disabled because InsightFace was not installed"],
    ["Fine classifier", "Loaded on CUDA"],
], widths=[2.6, 4.65], font_size=9)
doc.add_paragraph(
    "The runtime smoke proves that the configured video sources, ingestion, TensorRT detection, tracking and pipeline shutdown path work together. "
    "The short run also exposed a performance bottleneck: batch detection timed out for some cameras and the observed mean pipeline rate was approximately 0.23 FPS. "
    "This is a performance finding, not an accuracy failure."
)

add_heading(doc, "Per Camera Runtime Detail", 1)
camera_rows = []
for camera_id, row in runtime["cameras"].items():
    camera_rows.append([
        camera_id,
        row["frames_processed"],
        row["frames_dropped_for_analysis"],
        row["detections"],
        row["active_tracks"],
        f"{row['fps']:.2f}",
        f"{row['capture_fps']:.1f}",
    ])
table(doc, ["Camera", "Frames", "Dropped", "Detections", "Tracks", "Pipeline FPS", "Capture FPS"], camera_rows, widths=[1.55, 0.7, 0.75, 0.9, 0.7, 0.9, 0.85], font_size=7.8)
doc.add_paragraph(
    "CAM_IN_BHOPAL produced the highest detector activity in this short sample with 13 detections and two active tracks. The other cameras processed frames successfully but produced fewer detections in the sampled interval. "
    "Because the run lasted only five seconds and used recorded sources, these values are smoke-test observations rather than sustained production capacity measurements."
)

add_heading(doc, "Readiness Matrix", 1)
table(doc, ["Capability", "Status", "Evidence", "Follow-up"], [
    ["Core API and persistence", "Ready for further staging", "352 backend tests passed; health endpoint ready", "Run longer soak test with production-like storage"],
    ["GPU detection", "Operational", "CUDA and TensorRT loaded; labelled metrics generated", "Tune throughput and batch scheduling"],
    ["Tracking and event logic", "Operational in test scope", "Tracking, zones, fusion, risk and lifecycle tests passed", "Validate event rates on longer multi-camera clips"],
    ["Dashboard and browser flows", "Operational in smoke scope", "16 E2E passed and failed flow passed when warmed", "Add startup wait/readiness gate to CI"],
    ["Detector accuracy", "Baseline established", "mAP, F1 and confusion matrices available", "Improve helicopter, aircraft and night-object recall"],
    ["Face recognition", "Not ready", "InsightFace unavailable in runtime smoke", "Install and validate approved model/provider"],
    ["Sustained real-time throughput", "Not yet demonstrated", "Short run averaged 0.23 FPS with batch timeouts", "Profile queue contention and run 10-30 minute soak"],
], widths=[1.55, 1.35, 2.4, 1.95], font_size=7.5)

add_heading(doc, "Detector Accuracy Results", 1)
doc.add_paragraph(
    "The labelled evaluation used the validation split in dataset_coarse.yaml, the ibvap_coarse.pt weights, 640-pixel inference, CUDA device 0, batch size 8, "
    "and a Windows-safe single-process validation loader. F1 is the harmonic mean of precision and recall."
)
table(doc, ["Class", "Precision", "Recall", "F1", "mAP50", "mAP50-95"], [
    [x["class"], f"{x['precision']:.3f}", f"{x['recall']:.3f}", f"{x['f1']:.3f}", f"{x['map50']:.3f}", f"{x['map50_95']:.3f}"]
    for x in metrics["per_class"]
] + [["ALL / MACRO", f"{metrics['precision']:.3f}", f"{metrics['recall']:.3f}", f"{metrics['f1_macro']:.3f}", f"{metrics['map50']:.3f}", f"{metrics['map50_95']:.3f}"]], widths=[2.2, 0.9, 0.9, 0.7, 1.0, 1.1], font_size=8)

doc.add_page_break()
add_heading(doc, "Confusion Matrix and Evaluation Figures", 1)
doc.add_paragraph(
    "The evaluation generated both raw-count and normalized confusion matrices, precision-recall curves, precision curves, recall curves, F1 curves, and prediction JSON. "
    "The matrices below are embedded from the completed GPU run."
)
if CONFUSION.exists() and CONFUSION_NORM.exists():
    fig_table = doc.add_table(rows=1, cols=2)
    fig_table.autofit = False
    borders(fig_table, color="FFFFFF")
    for i, path in enumerate([CONFUSION, CONFUSION_NORM]):
        p = fig_table.cell(0, i).paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(path), width=Inches(3.25))
    add_caption(doc, "Figure 7. Raw confusion matrix and normalized confusion matrix")
if F1_CURVE.exists():
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(F1_CURVE), width=Inches(5.8))
    add_caption(doc, "Figure 8. F1 confidence curve generated by the detector evaluator")

add_heading(doc, "Demo Video Smoke Results", 1)
table(doc, ["Metric", "Value"], [
    ["Videos found", demo["videos_found"]],
    ["Videos opened", demo["videos_opened"]],
    ["Sampled frames", demo["sampled_frames"]],
    ["Detections", demo["detections"]],
    ["Wall time", f"{demo['wall_seconds']:.2f} seconds"],
    ["Mean model inference", f"{demo['model_mean_inference_ms']:.2f} ms"],
], widths=[2.8, 4.45], font_size=9)
doc.add_paragraph(
    "This demo-video test measures video opening, sampling, detector execution, class coverage and latency. It does not produce accuracy, precision, recall or F1 because the demo clips do not contain frame-level ground-truth boxes."
)

add_heading(doc, "Browser End to End Results", 1)
table(doc, ["Flow", "Result"], [
    ["Authentication validation", "Empty submit and wrong-password behavior passed"],
    ["Navigation", "Dashboard, cameras, multiview, map, alerts, events, zones, audit and settings passed"],
    ["Event and alert detail", "List-to-detail navigation passed after backend warm-up"],
    ["Storage", "Clip storage display and cleanup preview passed"],
    ["Watchlists", "Plate add/remove and faces tab passed"],
    ["Signup validation", "Skipped because self-service signup is disabled in this build"],
], widths=[2.3, 4.95], font_size=8.7)

add_heading(doc, "Future Scope and Development Roadmap", 1)
doc.add_paragraph(
    "The current build establishes a working GPU baseline and a reproducible accuracy benchmark. Future work should improve throughput and rare-class recall first, then strengthen model operations, deployment scale and governance. "
    "The roadmap below orders work by operational impact rather than by implementation convenience."
)
table(doc, ["Horizon", "Priority", "Planned improvement", "Expected outcome"], [
    ["Immediate", "GPU throughput", "Profile batch-coordinator waits, TensorRT engine reuse, frame sampling and queue contention; run 10 to 30 minute multi-camera soak tests", "Stable sustained throughput measurements and removal of short-run batch timeouts"],
    ["Immediate", "Rare-class accuracy", "Collect and review hard examples for helicopter, aircraft and night-vision objects; perform hard-negative mining and targeted augmentation", "Higher recall and F1 for the weakest operational classes"],
    ["Immediate", "Evaluation governance", "Version the exact dataset manifest, split lists, weights, thresholds and software environment for every benchmark", "Auditable comparisons with no ambiguity between training and reporting splits"],
    ["Near term", "Stage 2 validation", "Generate a dedicated fine-class confusion matrix, per-class precision and recall, calibration curves and rejection-rate analysis", "A defensible threshold for when to keep the coarse label or accept a fine prediction"],
    ["Near term", "Face recognition", "Install and validate the approved InsightFace model and provider; test false-match behavior and permission controls", "Optional identity enrichment that is technically verified and governed"],
    ["Near term", "Active learning", "Capture reviewed false positives and false negatives, prioritize uncertain cases and feed approved labels back into training", "Continuous improvement focused on real deployment errors"],
    ["Medium term", "Model optimization", "Evaluate FP16 and INT8 TensorRT builds, dynamic batching and input-resolution tradeoffs against the fixed accuracy baseline", "Lower latency and higher camera density without unmeasured accuracy loss"],
    ["Medium term", "MLOps", "Add dataset and model versioning, automated regression gates, drift monitoring and reproducible training jobs", "Safer releases and early warning when field data differs from training data"],
    ["Long term", "Deployment scale", "Support edge nodes, centralized fleet health, secure model rollout and multi-site event aggregation", "Operational deployment across larger camera estates"],
    ["Long term", "Broader robustness", "Expand weather, illumination, altitude, occlusion, geography and adversarial-condition coverage", "Better generalization across realistic surveillance environments"],
], widths=[0.9, 1.25, 3.55, 1.65], font_size=6.9)

add_heading(doc, "Findings and Recommendations", 1)
add_bullet(doc, "The primary detector path is operational on CUDA and TensorRT, but the runtime smoke showed batch timeouts and low pipeline throughput. Profile batch coordinator queueing, engine reuse and camera sampling before production deployment.")
add_bullet(doc, "Helicopter and aircraft remain the most important accuracy risks. Helicopter recall was 0.285 and F1 was 0.407; aircraft recall was 0.545 and F1 was 0.585. Add representative data, inspect false negatives, and tune class-specific thresholds.")
add_bullet(doc, "Face recognition is not part of the validated runtime path because InsightFace is unavailable. Install and validate the intended InsightFace model and provider before claiming face-recognition readiness.")
add_bullet(doc, "Keep the evaluator at workers 0 on Windows systems with limited paging-file capacity, or increase system virtual memory before using multi-worker validation.")
add_bullet(doc, "Treat the reported mAP and F1 values as the current baseline for regression comparisons. Re-run the same dataset split and weights after any model, threshold or preprocessing change.")

add_heading(doc, "Project Conclusion", 1)
final_p = doc.add_paragraph(
    "IBVAP demonstrates a complete software pathway from existing video sources to explainable, reviewable security events. The project combines perception, tracking, spatial and temporal reasoning, selective enrichment, context fusion, risk scoring, evidence integrity, authenticated APIs and an operator dashboard in one modular platform. "
    "The full application passed the recorded backend, frontend and warmed browser smoke suites, and the labelled detector evaluation produced a reproducible quantitative baseline with confusion matrices, precision, recall, F1 and mAP metrics. The strongest next steps are sustained multi-camera performance engineering, targeted improvement of rare aerial classes, formal validation of the Stage 2 classifier and governed activation of optional face recognition."
)
final_p.paragraph_format.space_after = Pt(0)
for run in final_p.runs:
    run.font.size = Pt(9)

add_heading(doc, "Artifacts and Reproduction", 1)
for item in [
    "backend/outputs/eval/backend/metrics.json",
    "backend/outputs/eval/backend/confusion_matrix.png",
    "backend/outputs/eval/backend/confusion_matrix_normalized.png",
    "backend/outputs/eval/backend/BoxF1_curve.png",
    "backend/outputs/eval/backend/predictions.json",
    "backend/outputs/metrics/runtime_smoke.json",
    "backend/outputs/metrics/demo_video_report.json",
]:
    add_bullet(doc, item)
footer = sec.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
fr = footer.add_run("IBVAP Full Project Report | Page ")
fr.font.size = Pt(8)
fr.font.color.rgb = RGBColor(120, 120, 120)
page_run = footer.add_run()
field_begin = OxmlElement("w:fldChar")
field_begin.set(qn("w:fldCharType"), "begin")
field_code = OxmlElement("w:instrText")
field_code.set(qn("xml:space"), "preserve")
field_code.text = " PAGE "
field_end = OxmlElement("w:fldChar")
field_end.set(qn("w:fldCharType"), "end")
page_run._r.extend([field_begin, field_code, field_end])
page_run.font.size = Pt(8)
page_run.font.color.rgb = RGBColor(120, 120, 120)

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(OUT)
