"""Modelli dati condivisi."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class Event:
    slug: str
    name: str
    type: str  # international | regional | special
    city: str
    country: str
    start: date
    end: date
    venue: str
    venue_confirmed: bool
    lat: float
    lon: float
    airport: str
    max_km: float | None = None  # raggio dedicato (default: MAX_DISTANCE_KM globale)

    @property
    def default_check_in(self) -> date:
        return self.start - timedelta(days=1)

    @property
    def default_check_out(self) -> date:
        return self.end + timedelta(days=1)


@dataclass
class TripRequest:
    """Una riga del foglio Prenotazioni: evento + chi viene."""
    event: Event
    participants: list[str]
    check_in: date
    check_out: date

    @property
    def people(self) -> int:
        return len(self.participants)

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


@dataclass
class StayOption:
    source: str            # booking.com | airbnb
    name: str
    property_type: str
    total_price: float
    currency: str
    review_score: float | None
    review_count: int | None
    distance_km: float
    free_cancellation: bool | None  # None = da verificare
    url: str

    def price_per_night(self, nights: int) -> float:
        return round(self.total_price / max(nights, 1), 2)


@dataclass
class FlightOption:
    source: str
    origin: str
    destination: str
    outbound: str          # es. "2027-02-18 07:10 MXP -> 09:05 LGW"
    inbound: str
    airline: str
    stops: int
    duration_min: int
    price: float
    currency: str
    url: str
    legs: list[str] = field(default_factory=list)
