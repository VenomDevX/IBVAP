"""Human-readable vehicle summaries built only from measured fields."""

from datetime import UTC, datetime


def describe_vehicle(track) -> str:
    parts = []
    if track.color and track.color != "Unknown":
        parts.append(track.color)
    parts.append((track.fine_type if track.fine_type != "unknown" else track.object_type).replace("_", " ").title())
    summary = " ".join(parts)
    if track.license_plate and track.license_plate.upper() != "UNKNOWN":
        summary += f", plate {track.license_plate.upper()}"
    if track.movement_direction and track.movement_direction != "unknown":
        summary += f", travelling {track.movement_direction.replace('_', ' ')}"
    if track.current_zones:
        summary += f", observed in {track.current_zones[0]} zone"
    seen = datetime.fromtimestamp(track.last_seen, tz=UTC).strftime("%H:%M:%S UTC")
    return f"{summary} at {seen}."
