"""Filtri e ordinamento dei risultati alloggio.

Regole richieste dal team:
  - solo entro MAX_DISTANCE_KM dalla fiera
  - solo cancellazione gratuita (None = policy sconosciuta, tenuta ma segnalata)
  - prima i più economici tra quelli con buone recensioni (>= MIN_REVIEW_SCORE);
    in coda i senza recensioni o sotto soglia, sempre ordinati per prezzo
"""
from __future__ import annotations

from .config import settings
from .models import StayOption


def filter_and_rank(options: list[StayOption]) -> list[StayOption]:
    eligible = [
        o
        for o in options
        if o.distance_km <= settings.max_distance_km and o.free_cancellation is not False
    ]

    def sort_key(o: StayOption):
        good_reviews = o.review_score is not None and o.review_score >= settings.min_review_score
        return (0 if good_reviews else 1, o.total_price)

    ranked = sorted(eligible, key=sort_key)
    return ranked[: settings.max_results_per_event]
