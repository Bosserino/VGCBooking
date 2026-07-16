"""Caricamento eventi e team dai file YAML in data/."""
from __future__ import annotations

from datetime import date

import yaml

from .config import DATA_DIR
from .models import Event


def load_events() -> list[Event]:
    raw = yaml.safe_load((DATA_DIR / "events_2027.yaml").read_text(encoding="utf-8"))
    events = []
    for e in raw["events"]:
        events.append(
            Event(
                slug=e["slug"],
                name=e["name"],
                type=e["type"],
                city=e["city"],
                country=e["country"],
                start=_as_date(e["start"]),
                end=_as_date(e["end"]),
                venue=e["venue"],
                venue_confirmed=bool(e["venue_confirmed"]),
                lat=float(e["lat"]),
                lon=float(e["lon"]),
                airport=e["airport"],
                max_km=float(e["max_km"]) if e.get("max_km") else None,
            )
        )
    return sorted(events, key=lambda ev: ev.start)


def load_team() -> tuple[list[dict], str]:
    raw = yaml.safe_load((DATA_DIR / "team.yaml").read_text(encoding="utf-8"))
    default_airport = raw.get("default_airport", "MXP")
    members = [
        {"name": m["name"], "airport": m.get("airport", default_airport)}
        for m in raw["members"]
    ]
    return members, default_airport


def _as_date(v) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))
