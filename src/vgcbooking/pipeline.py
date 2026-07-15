"""Pipeline: legge le prenotazioni dal foglio, cerca alloggi e voli, scrive i risultati.

Modalità:
  links (default) — 100% gratuita, senza chiavi: scrive link di ricerca
                    pre-filtrati da aprire nel browser per prenotare a mano
  api             — risultati veri in-foglio via RapidAPI/SerpAPI (servono chiavi)
  mock            — dati finti per provare il giro completo
"""
from __future__ import annotations

import logging
from collections import Counter

from .config import settings
from .models import FlightOption, StayOption, TripRequest
from .providers import links as free_links
from .providers.airbnb import AirbnbProvider
from .providers.booking_com import BookingComProvider
from .providers.google_flights import GoogleFlightsProvider
from .providers.mock import MockFlightProvider, MockStayProvider
from .ranking import filter_and_rank
from .registry import load_team
from .workbook import read_trip_requests, write_link_results, write_results

log = logging.getLogger(__name__)


def run_sync(mode: str = "links", only_event: str | None = None) -> dict:
    requests = read_trip_requests()
    if only_event:
        requests = [r for r in requests if r.event.slug == only_event]
    if not requests:
        log.warning("Nessun evento con prenotazioni (metti una X nel foglio Prenotazioni).")
        return {"events": 0}

    members, default_airport = load_team()
    airport_of = {m["name"]: m["airport"] for m in members}

    if mode == "links":
        return _run_links(requests, airport_of, default_airport)
    return _run_api(requests, airport_of, default_airport, mock=(mode == "mock"))


def _origins(req: TripRequest, airport_of: dict, default_airport: str) -> list[str]:
    return list(Counter(airport_of.get(p, default_airport) for p in req.participants))


def _run_links(requests, airport_of, default_airport) -> dict:
    stays, flights = {}, {}
    for req in requests:
        log.info("%s — %d persone: genero link pre-filtrati", req.event.name, req.people)
        stays[req.event.slug] = (req, free_links.stay_links(req))
        flights[req.event.slug] = (
            req,
            [l for origin in _origins(req, airport_of, default_airport)
             for l in free_links.flight_links(req, origin)],
        )
    write_link_results(stays, flights)
    return {
        "events": len(requests),
        "stays": sum(len(v[1]) for v in stays.values()),
        "flights": sum(len(v[1]) for v in flights.values()),
    }


def _run_api(requests, airport_of, default_airport, mock: bool) -> dict:
    if mock:
        stay_providers = [MockStayProvider("booking.com"), MockStayProvider("airbnb")]
        flight_provider = MockFlightProvider()
    else:
        if not settings.rapidapi_key and not settings.serpapi_key:
            log.warning("Nessuna chiave in .env: usa la modalità gratuita senza --api.")
        stay_providers = [BookingComProvider(), AirbnbProvider()]
        flight_provider = GoogleFlightsProvider()

    stays: dict[str, tuple[TripRequest, list[StayOption]]] = {}
    flights: dict[str, tuple[TripRequest, list[FlightOption]]] = {}

    for req in requests:
        log.info(
            "%s — %d persone (%s), %s -> %s",
            req.event.name, req.people, ", ".join(req.participants),
            req.check_in, req.check_out,
        )
        found: list[StayOption] = []
        for provider in stay_providers:
            results = provider.search(req)
            log.info("  %s: %d risultati", provider.name, len(results))
            found.extend(results)
        stays[req.event.slug] = (req, filter_and_rank(found))

        flight_options: list[FlightOption] = []
        for origin in _origins(req, airport_of, default_airport):
            flight_options.extend(flight_provider.search(req, origin))
        flight_options.sort(key=lambda f: f.price)
        flights[req.event.slug] = (req, flight_options[:8])

    write_results(stays, flights)
    return {
        "events": len(requests),
        "stays": sum(len(v[1]) for v in stays.values()),
        "flights": sum(len(v[1]) for v in flights.values()),
    }
