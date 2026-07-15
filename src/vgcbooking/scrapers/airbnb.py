"""Interi alloggi reali da Airbnb via pyairbnb (gratuito, senza chiavi).

pyairbnb richiede Python >= 3.10: sul runner GitHub Actions c'è il 3.12;
su macchine con 3.9 l'import fallisce e la fonte viene saltata.
Filtri nativi usati: intero alloggio + cancellazione gratuita.
In caso di errore alza RuntimeError col motivo (finisce in prices.json).
"""
from __future__ import annotations

import logging
from math import cos, radians

from ..geo import haversine_km

log = logging.getLogger(__name__)


def search_airbnb(lat: float, lon: float, check_in: str, check_out: str,
                  nights: int, people: int, max_distance_km: float, currency: str) -> list[dict]:
    try:
        import pyairbnb
    except (ImportError, SyntaxError) as exc:
        raise RuntimeError(f"pyairbnb non disponibile: {str(exc)[:80]}") from exc

    dlat = max_distance_km / 111.32
    dlon = max_distance_km / (111.32 * max(cos(radians(lat)), 0.01))
    try:
        results = pyairbnb.search_all(
            check_in=check_in, check_out=check_out,
            ne_lat=lat + dlat, ne_long=lon + dlon,
            sw_lat=lat - dlat, sw_long=lon - dlon,
            zoom_value=14,
            price_min=0, price_max=0,          # 0 = nessun limite di prezzo
            place_type="Entire home/apt",
            free_cancellation=True,
            adults=people,
            currency=currency, language="it", proxy_url="",
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"ricerca fallita: {str(exc)[:120]}") from exc

    stays = []
    for r in results:
        coords = r.get("coordinates") or {}
        r_lat, r_lon = coords.get("latitude"), coords.get("longitude")
        total = _amount(r)
        if total is None or r_lat is None or r_lon is None:
            continue
        distance = haversine_km(lat, lon, float(r_lat), float(r_lon))
        if distance > max_distance_km:
            continue
        rating = (r.get("rating") or {})
        score = rating.get("value")
        stays.append(
            {
                "source": "airbnb",
                "name": (r.get("name") or r.get("title") or "?").strip(),
                "total_price": total,
                "per_night": round(total / max(nights, 1), 2),
                "per_person_night": round(total / max(nights, 1) / max(people, 1), 2),
                # scala Airbnb 0-5 normalizzata a 0-10 per confronto con Booking
                "review_score": round(float(score) * 2, 1) if score else None,
                "review_count": rating.get("reviewCount"),
                "distance_km": distance,
                "free_cancellation": True,  # filtro nativo attivo nella ricerca
                "url": f"https://www.airbnb.it/rooms/{r.get('room_id') or r.get('id') or ''}",
            }
        )
    return stays


def _amount(r: dict) -> float | None:
    price = r.get("price") or {}
    for node in (price.get("total"), price.get("unit"), price):
        if isinstance(node, dict):
            v = node.get("amount")
            if isinstance(v, (int, float)) and v > 0:
                return round(float(v), 2)
    return None
