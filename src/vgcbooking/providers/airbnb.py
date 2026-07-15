"""Airbnb via RapidAPI (airbnb19.p.rapidapi.com).

Airbnb non ha API pubbliche ufficiali: questo wrapper usa un'API di terze parti.
La cancellazione gratuita non è un filtro nativo: si post-filtra sulla policy
quando presente nella risposta, altrimenti l'opzione è marcata "da verificare".
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from ..geo import haversine_km
from ..models import StayOption, TripRequest

log = logging.getLogger(__name__)

HOST = "airbnb19.p.rapidapi.com"
BASE = f"https://{HOST}/api/v1"

FLEXIBLE_POLICIES = {"flexible", "moderate", "firm_14_day", "flexible_new"}


class AirbnbProvider:
    name = "airbnb"

    def search(self, request: TripRequest) -> list[StayOption]:
        if not settings.rapidapi_key:
            log.warning("RAPIDAPI_KEY mancante: salto airbnb")
            return []
        ev = request.event
        params = {
            "latitude": ev.lat,
            "longitude": ev.lon,
            "range": int(settings.max_distance_km * 1000) + 500,  # metri, filtro fine lato client
            "checkin": request.check_in.isoformat(),
            "checkout": request.check_out.isoformat(),
            "adults": request.people,
            "category": "Apartment",
            "currency": settings.currency,
            "totalRecords": 40,
        }
        try:
            resp = httpx.get(
                f"{BASE}/searchPropertyByGEO",
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001 - la pipeline deve proseguire
            log.error("airbnb: richiesta fallita (%s)", exc)
            return []

        listings = ((payload.get("data") or {}).get("list")) or []
        options: list[StayOption] = []
        for item in listings:
            listing = item.get("listing") or item
            lat, lon = listing.get("lat"), listing.get("lng")
            if lat is None or lon is None:
                continue
            distance = haversine_km(ev.lat, ev.lon, float(lat), float(lon))
            pricing = item.get("pricingQuote") or {}
            total = _extract_amount(pricing)
            if total is None:
                continue
            policy = (listing.get("cancellationPolicy") or "").lower() or None
            options.append(
                StayOption(
                    source=self.name,
                    name=listing.get("name", "?"),
                    property_type=listing.get("roomTypeCategory", "entire_home"),
                    total_price=total,
                    currency=settings.currency,
                    review_score=_review_to_10(listing.get("avgRating")),
                    review_count=listing.get("reviewsCount"),
                    distance_km=distance,
                    free_cancellation=None if policy is None else policy in FLEXIBLE_POLICIES,
                    url=f"https://www.airbnb.com/rooms/{listing.get('id', '')}",
                )
            )
        return options

    @staticmethod
    def _headers() -> dict:
        return {
            "X-RapidAPI-Key": settings.rapidapi_key,
            "X-RapidAPI-Host": HOST,
        }


def _extract_amount(pricing: dict) -> float | None:
    for key in ("structuredStayDisplayPrice", "rate", "price"):
        node = pricing.get(key)
        if isinstance(node, dict):
            for amount_key in ("amount", "priceString", "total"):
                v = node.get(amount_key)
                if isinstance(v, (int, float)):
                    return round(float(v), 2)
    v = pricing.get("amount")
    return round(float(v), 2) if isinstance(v, (int, float)) else None


def _review_to_10(rating) -> float | None:
    """Airbnb usa una scala 0-5: normalizza a 0-10 per confronto con Booking."""
    try:
        return round(float(rating) * 2, 1)
    except (TypeError, ValueError):
        return None
