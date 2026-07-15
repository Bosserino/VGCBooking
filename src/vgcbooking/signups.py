"""Prenotazioni del team.

Fonte primaria: Google Sheet pubblicato come CSV (variabile SIGNUP_CSV_URL),
così i ragazzi mettono le X dal telefono senza toccare niente altro.
Formato atteso (come il template data/signups_template.csv):
  colonna 1 = Evento (deve iniziare col nome evento del calendario)
  colonne opzionali Check-in / Check-out (gg/mm/aaaa o aaaa-mm-gg)
  una colonna per membro, X = prenotato
Fallback: il file Excel locale (foglio Prenotazioni), se esiste.
"""
from __future__ import annotations

import csv
import io
import logging
import os
from datetime import date

import httpx

from .config import settings
from .models import Event, TripRequest
from .registry import load_events, load_team

log = logging.getLogger(__name__)


def load_signups() -> dict[str, TripRequest]:
    """slug evento -> TripRequest (solo eventi con almeno una X)."""
    url = os.getenv("SIGNUP_CSV_URL", "").strip()
    if url:
        try:
            return _from_csv_url(url)
        except Exception as exc:  # noqa: BLE001
            log.error("Google Sheet non leggibile (%s): provo l'Excel locale", str(exc)[:120])
    if settings.workbook_path.exists():
        from .workbook import read_trip_requests

        return {r.event.slug: r for r in read_trip_requests()}
    log.warning("Nessuna fonte prenotazioni: dashboard con ricerca base per tutti gli eventi.")
    return {}


def _from_csv_url(url: str) -> dict[str, TripRequest]:
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    rows = list(csv.reader(io.StringIO(resp.text)))
    if not rows:
        return {}

    header = [h.strip() for h in rows[0]]
    member_names = {m["name"] for m in load_team()[0]}
    name_cols = {i: h for i, h in enumerate(header) if h in member_names}
    ci_col = _find(header, "check-in")
    co_col = _find(header, "check-out")
    events = load_events()

    requests: dict[str, TripRequest] = {}
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        event = _match_event(row[0].strip(), events)
        if event is None:
            continue
        participants = [
            name for i, name in name_cols.items()
            if i < len(row) and row[i].strip().upper() == "X"
        ]
        if not participants:
            continue
        check_in = _parse_date(row[ci_col]) if ci_col is not None and ci_col < len(row) else None
        check_out = _parse_date(row[co_col]) if co_col is not None and co_col < len(row) else None
        requests[event.slug] = TripRequest(
            event, participants,
            check_in or event.default_check_in,
            check_out or event.default_check_out,
        )
    log.info("Prenotazioni dal Google Sheet: %d eventi", len(requests))
    return requests


def _match_event(cell: str, events: list[Event]) -> Event | None:
    low = cell.lower()
    for ev in events:
        if low.startswith(ev.name.lower()) or ev.name.lower().startswith(low) or ev.slug in low:
            return ev
    return None


def _find(header: list[str], name: str) -> int | None:
    for i, h in enumerate(header):
        if h.lower().replace(" ", "") == name.replace("-", "").replace(" ", "") or h.lower() == name:
            return i
    return None


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            from datetime import datetime

            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
