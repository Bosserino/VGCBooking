"""Google Flights via SerpAPI (engine=google_flights).

Google non espone un'API pubblica di booking: qui si cercano le tariffe reali
di Google Flights e si scrive nel foglio il link diretto per completare
l'acquisto. Per l'emissione biglietti via API pura vedi Duffel/Amadeus (README).
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from ..models import FlightOption, TripRequest

log = logging.getLogger(__name__)

BASE = "https://serpapi.com/search.json"


class GoogleFlightsProvider:
    name = "google-flights"

    def search(self, request: TripRequest, origin: str) -> list[FlightOption]:
        if not settings.serpapi_key:
            log.warning("SERPAPI_KEY mancante: salto google flights")
            return []
        ev = request.event
        params = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": ev.airport,
            "outbound_date": request.check_in.isoformat(),
            "return_date": request.check_out.isoformat(),
            "adults": request.people,
            "currency": settings.currency,
            "hl": settings.locale,
            "api_key": settings.serpapi_key,
        }
        try:
            resp = httpx.get(BASE, params=params, timeout=45)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001 - la pipeline deve proseguire
            log.error("google flights: richiesta fallita (%s)", exc)
            return []

        raw = (payload.get("best_flights") or []) + (payload.get("other_flights") or [])
        search_url = (payload.get("search_metadata") or {}).get("google_flights_url", "")
        options: list[FlightOption] = []
        for f in raw:
            legs = f.get("flights") or []
            if not legs:
                continue
            first, last = legs[0], legs[-1]
            airlines = sorted({leg.get("airline", "?") for leg in legs})
            options.append(
                FlightOption(
                    source=self.name,
                    origin=origin,
                    destination=ev.airport,
                    outbound=_fmt_leg(first, last),
                    inbound="(vedi link: tariffa A/R)",
                    airline=" + ".join(airlines),
                    stops=max(len(legs) - 1, 0),
                    duration_min=f.get("total_duration", 0),
                    price=float(f.get("price", 0)),
                    currency=settings.currency,
                    url=search_url,
                    legs=[_fmt_leg(leg, leg) for leg in legs],
                )
            )
        return options


def _fmt_leg(first: dict, last: dict) -> str:
    dep = first.get("departure_airport") or {}
    arr = last.get("arrival_airport") or {}
    return (
        f"{dep.get('time', '?')} {dep.get('id', '?')} -> "
        f"{arr.get('time', '?')} {arr.get('id', '?')}"
    )
