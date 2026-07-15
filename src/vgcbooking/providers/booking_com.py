"""Booking.com via RapidAPI (booking-com15.p.rapidapi.com).

Filtri applicati:
  - solo appartamenti/aparthotel (categories_filter property_type)
  - solo cancellazione gratuita (facility free_cancellation)
  - raggio massimo dalla fiera verificato lato client con haversine
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from ..geo import haversine_km
from ..models import StayOption, TripRequest

log = logging.getLogger(__name__)

HOST = "booking-com15.p.rapidapi.com"
BASE = f"https://{HOST}/api/v1"

# Tassonomia Booking.com: 201 = Appartamenti, 226 = Aparthotel
APARTMENT_FILTER = "property_type::201,property_type::226"
FREE_CANCELLATION_FILTER = "free_cancellation::1"


class BookingComProvider:
    name = "booking.com"

    def search(self, request: TripRequest) -> list[StayOption]:
        if not settings.rapidapi_key:
            log.warning("RAPIDAPI_KEY mancante: salto booking.com")
            return []
        ev = request.event
        params = {
            "latitude": ev.lat,
            "longitude": ev.lon,
            "arrival_date": request.check_in.isoformat(),
            "departure_date": request.check_out.isoformat(),
            "adults": request.people,
            "room_qty": max(1, round(request.people / 2)),
            "radius": max(3, int(settings.max_distance_km) + 1),  # filtro fine lato client
            "categories_filter": f"{APARTMENT_FILTER},{FREE_CANCELLATION_FILTER}",
            "sort_by": "price",
            "currency_code": settings.currency,
            "languagecode": settings.locale,
            "page_number": 1,
        }
        try:
            resp = httpx.get(
                f"{BASE}/hotels/searchHotelsByCoordinates",
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001 - la pipeline deve proseguire
            log.error("booking.com: richiesta fallita (%s)", exc)
            return []

        results = (payload.get("data") or {}).get("result") or []
        options: list[StayOption] = []
        for h in results:
            lat, lon = h.get("latitude"), h.get("longitude")
            if lat is None or lon is None:
                continue
            distance = haversine_km(ev.lat, ev.lon, float(lat), float(lon))
            price_block = h.get("composite_price_breakdown") or {}
            gross = (price_block.get("gross_amount") or {}).get("value") or h.get("min_total_price")
            if gross is None:
                continue
            options.append(
                StayOption(
                    source=self.name,
                    name=h.get("hotel_name", "?"),
                    property_type=h.get("accommodation_type_name", "Appartamento"),
                    total_price=round(float(gross), 2),
                    currency=price_block.get("gross_amount", {}).get("currency", settings.currency),
                    review_score=_maybe_float(h.get("review_score")),
                    review_count=h.get("review_nr"),
                    distance_km=distance,
                    free_cancellation=bool(h.get("is_free_cancellable", h.get("free_cancellable", False))),
                    url=h.get("url") or f"https://www.booking.com/hotel/{h.get('hotel_id', '')}.html",
                )
            )
        return options

    @staticmethod
    def _headers() -> dict:
        return {
            "X-RapidAPI-Key": settings.rapidapi_key,
            "X-RapidAPI-Host": HOST,
        }


def _maybe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
