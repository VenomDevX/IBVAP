"""Small dependency-free PDF renderer for operational text reports."""


def _escape(text: object) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def daily_report_pdf(report: dict) -> bytes:
    summary = report["summary"]
    lines = [
        "IBVAP Security Operations Report",
        f"Generated: {report['generated_at']}",
        f"Period: {report['report_period']}",
        "",
        f"Alerts: {summary['total_alerts_24h']}",
        f"Critical alerts: {summary['critical_alerts_24h']}",
        f"Active threats: {summary['current_active_threats']}",
        "",
        "Recent alerts",
        "ID | Camera | Type | Risk | Timestamp",
    ]
    for alert in report["alerts"][:40]:
        lines.append(
            f"{alert['alert_id']} | {alert['camera_id']} | {alert['event_type']} | "
            f"{alert['risk_level']} | {alert['timestamp']}"
        )
    if not report["alerts"]:
        lines.append("No alerts in this period")

    commands = ["BT", "/F1 10 Tf", "48 800 Td", "14 TL"]
    for index, line in enumerate(lines):
        if index:
            commands.append("T*")
        commands.append(f"({_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode())
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(document)
