"""Modalità 100% gratuita: genera link di ricerca pre-filtrati, senza API.

I filtri sono codificati direttamente nell'URL:
  Booking.com  -> solo appartamenti (ht_id=201) + aparthotel (226),
                  cancellazione gratuita (fc=2), recensioni >= 8 (review_score=80),
                  ordinati per prezzo crescente
  Airbnb       -> intero alloggio, riquadro mappa di +/- MAX_DISTANCE_KM
                  centrato sulla fiera, date e ospiti precompilati
  GoogleFlights-> A/R con aeroporti, date e passeggeri precompilati

Se un portale cambia i parametri URL il link degrada con grazia: si apre
comunque la ricerca base e i filtri si rimettono a mano in un click.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians
from urllib.parse import quote, urlencode

from ..config import settings
from ..models import TripRequest


@dataclass
class SearchLink:
    source: str
    label: str
    url: str
    origin: str = ""


def stay_links(request: TripRequest) -> list[SearchLink]:
    ev = request.event
    rooms = max(1, round(request.people / 2))

    booking_params = {
        "ss": f"{ev.venue.replace(' (presunta)', '')}, {ev.city}",
        # coordinate esplicite: il geocoding del solo testo a volte sbaglia città
        "dest_type": "landmark",
        "place_id_lat": ev.lat,
        "place_id_lon": ev.lon,
        "checkin": request.check_in.isoformat(),
        "checkout": request.check_out.isoformat(),
        "group_adults": request.people,
        "group_children": 0,
        "no_rooms": rooms,
        "order": "price",
        # distance=3000: filtro Booking più vicino ai 2km (gradini 1/3/5 km)
        "nflt": "ht_id=201;ht_id=226;fc=2;review_score=80;distance=3000",
        "selected_currency": settings.currency,
    }
    booking_url = f"https://www.booking.com/searchresults.{settings.locale}.html?{urlencode(booking_params)}"

    # Riquadro mappa di +/- MAX_DISTANCE_KM attorno alla fiera
    dlat = settings.max_distance_km / 111.32
    dlon = settings.max_distance_km / (111.32 * max(cos(radians(ev.lat)), 0.01))
    airbnb_params = {
        "checkin": request.check_in.isoformat(),
        "checkout": request.check_out.isoformat(),
        "adults": request.people,
        "room_types[]": "Entire home/apt",
        "search_by_map": "true",
        "ne_lat": round(ev.lat + dlat, 5),
        "ne_lng": round(ev.lon + dlon, 5),
        "sw_lat": round(ev.lat - dlat, 5),
        "sw_lng": round(ev.lon - dlon, 5),
    }
    airbnb_url = f"https://www.airbnb.it/s/{quote(ev.city)}/homes?{urlencode(airbnb_params)}"

    return [
        SearchLink(
            "booking.com",
            f"Appartamenti {ev.city}: canc. gratuita, recensioni 8+, prezzo crescente "
            f"(verifica distanza dalla fiera sulla mappa)",
            booking_url,
        ),
        SearchLink(
            "airbnb",
            f"Interi alloggi entro ~{settings.max_distance_km:g} km dalla fiera di {ev.city} "
            f"(ordina per prezzo; controlla la policy di cancellazione)",
            airbnb_url,
        ),
    ]


def flight_links(request: TripRequest, origin: str) -> list[SearchLink]:
    ev = request.event
    query = (
        f"Flights from {origin} to {ev.airport} "
        f"on {request.check_in.isoformat()} through {request.check_out.isoformat()} "
        f"for {request.people} passengers"
    )
    params = {"q": query, "curr": settings.currency, "hl": settings.locale}
    url = f"https://www.google.com/travel/flights?{urlencode(params)}"
    return [
        SearchLink(
            "google-flights",
            f"A/R {origin} -> {ev.airport}, {request.people} pax, ordina per prezzo",
            url,
            origin=origin,
        )
    ]
