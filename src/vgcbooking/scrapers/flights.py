"""Voli reali da Google Flights via fast-flights (gratuito, senza chiavi).

Nota: dal territorio UE Google mostra il muro dei cookie e la richiesta
fallisce; dai runner GitHub Actions (USA) funziona. Il cookie SOCS iniettato
sotto aiuta ma non è garantito dall'UE.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Cookie di consenso pre-accettato: evita il redirect GDPR in alcuni casi
_SOCS = "CAISHAgBEhJnd3NfMjAyNDA3MDktMF9SQzIaAml0IAEaBgiAo_S0Bg"


def _patched_fetch(params: dict):
    from fast_flights.primp import Client

    client = Client(impersonate="chrome_126", verify=False, headers={"Cookie": f"SOCS={_SOCS}"})
    res = client.get("https://www.google.com/travel/flights", params=params)
    assert res.status_code == 200, f"status {res.status_code}"
    return res


# Il filtro tfs di Google vuole codici aeroporto: espandiamo i city-code noti
CITY_AIRPORTS = {"ROM": ["FCO", "CIA"], "LON": ["LHR", "LGW", "STN"], "CHI": ["ORD"], "SAO": ["GRU"]}


def search_flights(origin: str, destination: str, depart: str, ret: str, adults: int) -> list[dict]:
    """Ritorna voli A/R ordinati per prezzo: [{airline, departure, arrival, stops, duration, price_pp, source}]
    Cerca su tutte le combinazioni di aeroporti dei city-code (es. ROM -> FCO e CIA).
    Alza RuntimeError col motivo se nessuna combinazione produce dati."""
    flights: list[dict] = []
    last_error = None
    for orig in CITY_AIRPORTS.get(origin, [origin]):
        for dest in CITY_AIRPORTS.get(destination, [destination]):
            try:
                flights.extend(_search_one(orig, dest, depart, ret))
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)[:120]
                log.warning("google-flights %s->%s: %s", orig, dest, last_error)
    if not flights:
        raise RuntimeError(last_error or "nessun volo trovato")
    flights.sort(key=lambda x: x["price_pp"])
    return flights[:5]


def _search_one(origin: str, destination: str, depart: str, ret: str) -> list[dict]:
    import fast_flights.core as ffcore
    from fast_flights import FlightData, Passengers, get_flights

    ffcore.fetch = _patched_fetch
    result = get_flights(
            flight_data=[
                FlightData(date=depart, from_airport=origin, to_airport=destination),
                FlightData(date=ret, from_airport=destination, to_airport=origin),
            ],
            trip="round-trip",
            seat="economy",
            # prezzo per persona: la disponibilità di gruppo si verifica al momento
            # dell'acquisto, il confronto costi si fa a testa
            passengers=Passengers(adults=1),
            fetch_mode="common",
        )

    flights = []
    for f in result.flights:
        price = _parse_price(f.price)
        if price is None:
            continue
        flights.append(
            {
                "airline": f.name,
                "departure": f"{f.departure} ({origin}→{destination})",
                "arrival": f.arrival,
                "stops": f.stops if isinstance(f.stops, int) else 0,
                "duration": f.duration,
                "price_pp": price,
                "source": "google-flights",
            }
        )
    return flights


def _parse_price(text) -> float | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return float(digits) if digits else None
