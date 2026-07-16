"""Snapshot prezzi: per ogni evento raccoglie voli e alloggi reali e scrive
docs/data/prices.json (+ storico in docs/data/history.json) per la dashboard.

Eventi senza prenotati: ricerca base per BASELINE_PEOPLE persone, così i
ragazzi vedono comunque un costo indicativo prima di mettere la X.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from datetime import datetime, timezone

from .config import PROJECT_ROOT, settings
from .models import Event, TripRequest
from .providers import links as link_builder
from .ranking import filter_and_rank  # noqa: F401  (regole condivise, vedi _rank_stays)
from .registry import load_events, load_team
from .signups import load_signups

log = logging.getLogger(__name__)

DOCS_DATA = PROJECT_ROOT / "docs" / "data"
BASELINE_PEOPLE = 4
MAX_STAYS = 6
HISTORY_KEEP = 90


def run_snapshot(mock: bool = False, only_event: str | None = None) -> dict:
    events = load_events()
    if only_event:
        events = [e for e in events if e.slug == only_event]
    signups = load_signups()
    members, default_airport = load_team()
    airport_of = {m["name"]: m["airport"] for m in members}
    origin = os.getenv("ORIGIN_AIRPORT", default_airport)

    out_events = []
    for ev in events:
        req = signups.get(ev.slug)
        participants = req.participants if req else []
        people = len(participants) or BASELINE_PEOPLE
        check_in = (req.check_in if req else ev.default_check_in).isoformat()
        check_out = (req.check_out if req else ev.default_check_out).isoformat()
        nights = ( (req.check_out - req.check_in).days if req
                   else (ev.default_check_out - ev.default_check_in).days )

        search_req = _search_request(ev, people, req)
        errors: list[str] = []

        if mock:
            flights, stays = _mock_data(ev, people, nights)
            return_flights = [dict(f, departure=f["departure"].replace("(", "(rientro ")) for f in flights[:3]]
        else:
            leg_data = _collect_flights(ev, origin, check_in, check_out, people, errors)
            flights, return_flights = leg_data["outbound"], leg_data["return"]
            stays = _collect_stays(ev, search_req, check_in, check_out, nights, people, errors)

        # membri prenotati che partono da un altro aeroporto (es. Jean da Lione):
        # uno specchietto voli dedicato per ciascun aeroporto alternativo
        extra_origins = []
        alt: dict[str, list[str]] = {}
        for p in participants:
            ap = airport_of.get(p, origin)
            if ap != origin:
                alt.setdefault(ap, []).append(p)
        for ap, names in sorted(alt.items()):
            if mock:
                alt_out = [dict(f, departure=f["departure"] + f" (da {ap})") for f in flights[:3]]
                alt_ret = alt_out[:2]
            else:
                alt_errors: list[str] = []
                alt_data = _collect_flights(ev, ap, check_in, check_out, len(names), alt_errors)
                alt_out, alt_ret = alt_data["outbound"], alt_data["return"]
                errors.extend(f"{ap}: {e}" for e in alt_errors)
            extra_origins.append(
                {"origin": ap, "participants": names, "flights": alt_out, "return_flights": alt_ret}
            )

        stays = _rank_stays(stays)[:MAX_STAYS]
        min_flight = min((f["price_pp"] for f in flights), default=None)
        min_stay_pp = min(
            (s["per_person_night"] * nights for s in stays), default=None
        )
        out_events.append(
            {
                "slug": ev.slug,
                "name": ev.name,
                "type": ev.type,
                "city": ev.city,
                "country": ev.country,
                "start": ev.start.isoformat(),
                "end": ev.end.isoformat(),
                "venue": ev.venue,
                "venue_confirmed": ev.venue_confirmed,
                "airport": ev.airport,
                "check_in": check_in,
                "check_out": check_out,
                "nights": nights,
                "participants": participants,
                "people_for_search": people,
                "links": _links(search_req, origin),
                "flights": flights,
                "return_flights": return_flights,
                "extra_origins": extra_origins,
                "stays": stays,
                "estimate_pp": {
                    "flight": min_flight,
                    "stay": round(min_stay_pp, 2) if min_stay_pp is not None else None,
                    "total": round(min_flight + min_stay_pp, 2)
                    if min_flight is not None and min_stay_pp is not None
                    else None,
                },
                "errors": errors,
            }
        )
        log.info(
            "%s: %d voli, %d alloggi%s",
            ev.slug, len(flights), len(stays),
            f" [{'; '.join(errors)}]" if errors else "",
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "origin": origin,
        "settings": {
            "max_distance_km": settings.max_distance_km,
            "min_review_score": settings.min_review_score,
            "currency": settings.currency,
        },
        "events": out_events,
    }

    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    (DOCS_DATA / "prices.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    _append_history(out_events)
    return {
        "events": len(out_events),
        "with_flights": sum(1 for e in out_events if e["flights"]),
        "with_stays": sum(1 for e in out_events if e["stays"]),
    }


def _search_request(ev: Event, people: int, req: TripRequest | None) -> TripRequest:
    if req:
        return req
    base = TripRequest(ev, ["baseline"] * people, ev.default_check_in, ev.default_check_out)
    return base


def _collect_flights(ev, origin, check_in, check_out, people, errors) -> dict:
    from .scrapers.flights import search_flights

    try:
        return search_flights(origin, ev.airport, check_in, check_out, people)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"google-flights: {str(exc)[:120]}")
        return {"outbound": [], "return": []}


def _collect_stays(ev, search_req, check_in, check_out, nights, people, errors) -> list[dict]:
    from .scrapers.airbnb import search_airbnb
    from .scrapers.booking import search_booking

    max_km = ev.max_km or settings.max_distance_km
    stays: list[dict] = []
    booking_url = _links(search_req, "")["booking"]
    try:
        stays.extend(search_booking(booking_url, nights, people, max_km))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"booking.com: {str(exc)[:120]}")
    try:
        stays.extend(
            search_airbnb(ev.lat, ev.lon, check_in, check_out, nights, people,
                          max_km, settings.currency)
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"airbnb: {str(exc)[:120]}")
    return stays


def _rank_stays(stays: list[dict]) -> list[dict]:
    # stesse regole di ranking.filter_and_rank, ma su dict già filtrati per distanza
    def key(s):
        good = s["review_score"] is not None and s["review_score"] >= settings.min_review_score
        return (0 if good else 1, s["total_price"])

    return sorted([s for s in stays if s.get("free_cancellation") is not False], key=key)


def _links(req: TripRequest, origin: str) -> dict:
    stay = link_builder.stay_links(req)
    flight = link_builder.flight_links(req, origin or "ROM")
    return {
        "booking": stay[0].url,
        "airbnb": stay[1].url,
        "flights": flight[0].url,
    }


def _append_history(out_events: list[dict]) -> None:
    path = DOCS_DATA / "history.json"
    history = {"snapshots": []}
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    today = datetime.now(timezone.utc).date().isoformat()
    snapshot = {
        "date": today,
        "events": {
            e["slug"]: {
                "min_flight_pp": e["estimate_pp"]["flight"],
                "min_stay_pp_night": round(e["estimate_pp"]["stay"] / e["nights"], 2)
                if e["estimate_pp"]["stay"] is not None and e["nights"]
                else None,
            }
            for e in out_events
        },
    }
    history["snapshots"] = [s for s in history["snapshots"] if s["date"] != today]
    history["snapshots"].append(snapshot)
    history["snapshots"] = history["snapshots"][-HISTORY_KEEP:]
    path.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")


def _mock_data(ev, people, nights):
    import random

    rng = random.Random(ev.slug)
    inter = ev.airport in {"GRU", "CHI"}
    flights = sorted(
        (
            {
                "airline": rng.choice(["ITA Airways", "Ryanair", "Lufthansa", "LATAM", "United"]),
                "departure": f"{ev.default_check_in} 0{rng.randint(6, 9)}:{rng.randint(10, 55)}",
                "arrival": "—",
                "stops": rng.choice([0, 0, 1, 2]) if inter else rng.choice([0, 0, 1]),
                "duration": f"{rng.randint(11, 16)}h" if inter else f"{rng.randint(1, 3)}h{rng.randint(10, 55)}",
                "price_pp": round((rng.uniform(450, 900) if inter else rng.uniform(45, 180)), 0),
                "source": "[MOCK] google-flights",
            }
            for _ in range(5)
        ),
        key=lambda f: f["price_pp"],
    )
    stays = [
        {
            "source": rng.choice(["booking.com", "airbnb"]),
            "name": f"[MOCK] Apt {ev.city} {i + 1}",
            "total_price": round(rng.uniform(45, 110) * people / 2 * nights, 0),
            "per_night": 0.0,
            "per_person_night": 0.0,
            "review_score": round(rng.uniform(7.5, 9.8), 1),
            "review_count": rng.randint(15, 800),
            "distance_km": round(rng.uniform(0.2, 1.9), 2),
            "free_cancellation": rng.choice([True, True, None]),
            "mobile_deal": rng.choice([True, False, False]),
            "genius_deal": rng.choice([True, False, False]),
            "unit_desc": f"Intero appartamento – {rng.randint(30, 90)} m²: {rng.randint(2, 5)} letti",
            "multi_unit": rng.random() > 0.8,
            "url": "https://example.com",
        }
        for i in range(6)
    ]
    for s in stays:
        s["per_night"] = round(s["total_price"] / nights, 2)
        s["per_person_night"] = round(s["per_night"] / people, 2)
    return flights, stays
