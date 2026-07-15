"""Provider finti per demo e test senza chiavi API (flag --mock)."""
from __future__ import annotations

import random

from ..config import settings
from ..models import FlightOption, StayOption, TripRequest

STREETS = ["Via della Fiera", "Expo Strasse", "Rue du Palais", "Market St", "ul. Targowa"]


class MockStayProvider:
    def __init__(self, name: str):
        self.name = name

    def search(self, request: TripRequest) -> list[StayOption]:
        rng = random.Random(f"{self.name}:{request.event.slug}")
        nights = request.nights
        out = []
        for i in range(rng.randint(6, 12)):
            per_night = rng.uniform(28, 95) * max(1, request.people / 2)
            out.append(
                StayOption(
                    source=self.name,
                    name=f"[MOCK] Apt {rng.choice(STREETS)} {i + 1} ({request.event.city})",
                    property_type="Appartamento",
                    total_price=round(per_night * nights, 2),
                    currency=settings.currency,
                    review_score=round(rng.uniform(6.5, 9.8), 1),
                    review_count=rng.randint(4, 900),
                    distance_km=round(rng.uniform(0.1, 3.5), 2),
                    free_cancellation=rng.random() > 0.25,
                    url=f"https://example.com/{self.name}/{request.event.slug}/{i}",
                )
            )
        return out


class MockFlightProvider:
    name = "google-flights"

    def search(self, request: TripRequest, origin: str) -> list[FlightOption]:
        rng = random.Random(f"fly:{origin}:{request.event.slug}")
        intercontinental = request.event.airport in {"GRU", "CHI"}
        base = 550 if intercontinental else 90
        out = []
        for i in range(rng.randint(4, 7)):
            stops = rng.choice([0, 0, 1, 1, 2]) if intercontinental else rng.choice([0, 0, 1])
            price = base * rng.uniform(0.8, 1.9) * (1 + 0.08 * stops) * request.people
            out.append(
                FlightOption(
                    source="[MOCK] google-flights",
                    origin=origin,
                    destination=request.event.airport,
                    outbound=f"{request.check_in} 07:{rng.randint(10, 55)} {origin} -> ... {request.event.airport}",
                    inbound=f"{request.check_out} ritorno",
                    airline=rng.choice(["ITA Airways", "Lufthansa", "easyJet", "Ryanair", "LATAM", "United"]),
                    stops=stops,
                    duration_min=rng.randint(90, 200) if not intercontinental else rng.randint(700, 1200),
                    price=round(price, 2),
                    currency=settings.currency,
                    url=f"https://example.com/flights/{request.event.slug}/{i}",
                )
            )
        return out
