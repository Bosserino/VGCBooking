"""Interfacce dei provider. Ogni provider è tollerante agli errori:
in caso di problemi logga e restituisce lista vuota, la pipeline continua."""
from __future__ import annotations

from typing import Protocol

from ..models import FlightOption, StayOption, TripRequest


class StayProvider(Protocol):
    name: str

    def search(self, request: TripRequest) -> list[StayOption]: ...


class FlightProvider(Protocol):
    name: str

    def search(self, request: TripRequest, origin: str) -> list[FlightOption]: ...
