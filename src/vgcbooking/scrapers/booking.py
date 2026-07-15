"""Appartamenti reali da Booking.com via Playwright (browser headless).

Booking blocca i client HTTP puri con un WAF: serve un browser vero.
La ricerca parte già filtrata dall'URL (appartamenti, cancellazione gratuita,
recensioni 8+, prezzo crescente) e centrata sulla sede della fiera; la distanza
mostrata nelle card ("a X km dal luogo di ricerca") viene riverificata qui.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def search_booking(url: str, nights: int, people: int, max_distance_km: float) -> list[dict]:
    """Apre l'URL di ricerca pre-filtrato e legge le card risultato."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("booking.com: playwright non installato")
        return []

    cards: list[dict] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA, locale="it-IT")
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_selector('[data-testid="property-card"]', timeout=25_000)
            except Exception:  # noqa: BLE001
                log.error("booking.com: nessuna card (WAF o zero risultati)")
                browser.close()
                return []
            # accetta i cookie se compare il banner, per sbloccare il rendering
            try:
                page.click("#onetrust-accept-btn-handler", timeout=3_000)
            except Exception:  # noqa: BLE001
                pass

            for el in page.query_selector_all('[data-testid="property-card"]')[:25]:
                cards.append(_parse_card(el))
            browser.close()
    except Exception as exc:  # noqa: BLE001
        log.error("booking.com: %s", str(exc)[:160])
        return []

    stays = []
    for c in cards:
        if not c or c["total_price"] is None:
            continue
        if c["distance_km"] is not None and c["distance_km"] > max_distance_km:
            continue
        stays.append(
            {
                "source": "booking.com",
                "name": c["name"],
                "total_price": c["total_price"],
                "per_night": round(c["total_price"] / max(nights, 1), 2),
                "per_person_night": round(c["total_price"] / max(nights, 1) / max(people, 1), 2),
                "review_score": c["review_score"],
                "review_count": c["review_count"],
                "distance_km": c["distance_km"],
                "free_cancellation": c["free_cancellation"],
                "url": c["url"],
            }
        )
    return stays


def _parse_card(el) -> dict | None:
    def text(selector: str) -> str:
        node = el.query_selector(selector)
        return node.inner_text() if node else ""

    name = text('[data-testid="title"]').strip()
    if not name:
        return None
    price = _it_number(text('[data-testid="price-and-discounted-price"]'))
    review_block = text('[data-testid="review-score"]')
    score_m = re.search(r"(\d+[.,]\d)", review_block)
    count_m = re.search(r"([\d.]+)\s+recensioni", review_block)
    dist_m = re.search(r"([\d.,]+)\s*(km|m)\b", text('[data-testid="distance"]'))
    distance = None
    if dist_m:
        distance = _it_number(dist_m.group(1))
        if dist_m.group(2) == "m" and distance is not None:
            distance = round(distance / 1000, 2)
    link = el.query_selector('a[data-testid="title-link"]') or el.query_selector("a")
    body = el.inner_text().lower()
    return {
        "name": name,
        "total_price": price,
        "review_score": _it_number(score_m.group(1)) if score_m else None,
        "review_count": int(count_m.group(1).replace(".", "")) if count_m else None,
        "distance_km": distance,
        # il filtro fc=2 è già nell'URL: se il badge non c'è resta "da verificare"
        "free_cancellation": True if "cancellazione gratuita" in body else None,
        "url": (link.get_attribute("href") or "").split("?")[0] if link else "",
    }


def _it_number(s: str) -> float | None:
    """'1.240,50' -> 1240.5 ; '€ 744' -> 744.0"""
    s = re.sub(r"[^\d.,]", "", s or "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
        s = s.replace(".", "")  # '1.240' è un migliaio it-IT
    try:
        return float(s)
    except ValueError:
        return None
