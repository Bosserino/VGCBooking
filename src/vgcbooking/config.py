"""Configurazione: legge .env e i file dati in data/."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Settings:
    rapidapi_key: str = field(default_factory=lambda: os.getenv("RAPIDAPI_KEY", ""))
    serpapi_key: str = field(default_factory=lambda: os.getenv("SERPAPI_KEY", ""))
    currency: str = field(default_factory=lambda: os.getenv("CURRENCY", "EUR"))
    locale: str = field(default_factory=lambda: os.getenv("LOCALE", "it"))
    max_distance_km: float = field(default_factory=lambda: float(os.getenv("MAX_DISTANCE_KM", "2.0")))
    min_review_score: float = field(default_factory=lambda: float(os.getenv("MIN_REVIEW_SCORE", "8.0")))
    max_results_per_event: int = field(default_factory=lambda: int(os.getenv("MAX_RESULTS_PER_EVENT", "10")))
    workbook_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / os.getenv("WORKBOOK_PATH", "VGC_2027.xlsx")
    )


settings = Settings()
