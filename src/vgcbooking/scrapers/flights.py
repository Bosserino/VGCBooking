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
    import time

    flights: list[dict] = []
    last_error = None
    for orig in CITY_AIRPORTS.get(origin, [origin]):
        for dest in CITY_AIRPORTS.get(destination, [destination]):
            for attempt in range(2):  # Google a volte risponde vuoto sotto rate-limit
                try:
                    found = _search_one(orig, dest, depart, ret)
                    flights.extend(found)
                    if len(found) >= 3 or attempt == 1:
                        break
                    # lista magra (es. solo la sezione "migliori"): un secondo giro
                    log.info("google-flights %s->%s: solo %d voli, ritento", orig, dest, len(found))
                    time.sleep(4)
                    continue
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc)
                    if "No flights found" in msg:
                        # date oltre la finestra di vendita (~11 mesi), tratta senza voli o rate-limit
                        last_error = "nessun volo in vendita per queste date/tratta"
                    else:
                        last_error = msg[:120]
                    log.warning("google-flights %s->%s (tent. %d): %s", orig, dest, attempt + 1, last_error)
                    time.sleep(4)
            time.sleep(2)  # respiro tra le combinazioni per non farsi limitare
    if not flights:
        raise RuntimeError(last_error or "nessun volo trovato")
    seen, unique = set(), []
    for f in sorted(flights, key=lambda x: x["price_pp"]):
        key = (f["airline"], f["departure"], f["price_pp"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique[:5]


def _search_one(origin: str, destination: str, depart: str, ret: str) -> list[dict]:
    """Prima scelta: parsing degli aria-label (testo stabile, ha anche la compagnia);
    ripiego: il parser CSS di fast-flights (a volte perde nome e orari)."""
    from fast_flights import FlightData, Passengers
    from fast_flights.filter import create_filter

    tfs = create_filter(
        flight_data=[
            FlightData(date=depart, from_airport=origin, to_airport=destination),
            FlightData(date=ret, from_airport=destination, to_airport=origin),
        ],
        trip="round-trip", seat="economy", passengers=Passengers(adults=1),
    )
    res = _patched_fetch({"tfs": tfs.as_b64().decode(), "hl": "en", "curr": "EUR", "tfu": "EgQIABABIgA"})
    flights = parse_aria_labels(res.text, origin, destination)
    if flights:
        return flights
    log.info("google-flights %s->%s: aria-label vuoti, ripiego sul parser fast-flights", origin, destination)
    return _search_one_fastflights(origin, destination, depart, ret)


ARIA_RE = re.compile(
    r'aria-label="From (\d[\d,]*) (?:euros?|US dollars?)[^"]*?flight with ([^."]+)\.'
    r'[^"]*?Leaves [^"]*? at ([^"]+?) on ([^."]+?) and arrives[^"]*?'
    r'Total duration ([^."]*)\.[^"]*"'
)


def parse_aria_labels(html: str, origin: str, destination: str) -> list[dict]:
    import html as html_mod

    text = html_mod.unescape(html)
    flights = []
    seen = set()
    for m in ARIA_RE.finditer(text):
        price_s, airline, dep_time, dep_date, duration = m.groups()
        full = m.group(0)
        stops = 0 if "Nonstop" in full else _stops_from(full)
        key = (airline, dep_time, dep_date, price_s)
        if key in seen:
            continue
        seen.add(key)
        flights.append(
            {
                "airline": airline.strip(),
                "departure": f"{dep_time.strip()}, {dep_date.strip()} ({origin}→{destination})",
                "arrival": "",
                "stops": stops,
                "duration": duration.strip(),
                "price_pp": float(price_s.replace(",", "")),
                "source": "google-flights",
            }
        )
    return flights


def _stops_from(label: str) -> int:
    m = re.search(r"(\d+) stops?", label)
    return int(m.group(1)) if m else 1


def _search_one_fastflights(origin: str, destination: str, depart: str, ret: str) -> list[dict]:
    from fast_flights import FlightData, Passengers, get_flights

    try:  # il patch del cookie serve solo dall'UE: se il layout cambia, si prosegue
        import fast_flights.core as ffcore

        ffcore.fetch = _patched_fetch
    except Exception:  # noqa: BLE001
        log.info("fast_flights.core non patchabile: uso il fetch di default")

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
        if not price:  # None o 0 = tariffa non disponibile
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
