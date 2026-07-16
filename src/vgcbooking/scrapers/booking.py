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

# Navighiamo "da telefono": Booking mostra le offerte mobile-only (10-20% in meno)
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
MOBILE_VIEWPORT = {"width": 390, "height": 844}


def search_booking(url: str, nights: int, people: int, max_distance_km: float) -> list[dict]:
    """Apre l'URL di ricerca pre-filtrato e legge le card risultato.

    Se la variabile BOOKING_STORAGE_STATE punta a un file di sessione Playwright
    (login Booking dell'utente, vedi comando `booking-login`), i prezzi sono
    quelli reali del suo account — sconti Genius inclusi, col badge in card."""
    import json
    import os

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("booking.com: playwright non installato")
        return []

    storage_state = None
    state_path = os.getenv("BOOKING_STORAGE_STATE", "")
    if state_path and os.path.exists(state_path):
        try:
            json.loads(open(state_path, encoding="utf-8").read())
            storage_state = state_path
            log.info("booking.com: uso la sessione loggata (%s)", state_path)
        except ValueError:
            log.warning("booking.com: BOOKING_STORAGE_STATE non è JSON valido, ignoro")

    cards: list[dict] = []
    last_error = "WAF o zero risultati"
    for attempt in range(3):  # il WAF di Booking è intermittente: riprova
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    user_agent=UA, locale="it-IT",
                    viewport=MOBILE_VIEWPORT, is_mobile=True, has_touch=True,
                    storage_state=storage_state,
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_selector('[data-testid="property-card"]', timeout=25_000)
                except Exception:  # noqa: BLE001
                    browser.close()
                    log.warning("booking.com: nessuna card (tentativo %d)", attempt + 1)
                    continue
                # accetta i cookie se compare il banner, per sbloccare il rendering
                try:
                    page.click("#onetrust-accept-btn-handler", timeout=3_000)
                except Exception:  # noqa: BLE001
                    pass

                for el in page.query_selector_all('[data-testid="property-card"]')[:25]:
                    cards.append(_parse_card(el))
                browser.close()
                break
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)[:120]
            log.warning("booking.com tentativo %d: %s", attempt + 1, last_error)
    if not cards:
        raise RuntimeError(last_error)

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
                "mobile_deal": c["mobile_deal"],
                "genius_deal": c["genius_deal"],
                "unit_desc": c["unit_desc"],
                "multi_unit": c["multi_unit"],
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
    # layout mobile: "Include tasse e costi"; layout desktop: "+ € X tasse e costi"
    raw = el.inner_text()
    taxes_m = re.search(r"\+\s*€?\s*([\d.,]+)\s*(?:di\s+)?tasse", raw, re.IGNORECASE)
    if price is not None and taxes_m:
        extra = _it_number(taxes_m.group(1))
        if extra:
            price = round(price + extra, 2)
    review_block = text('[data-testid="review-score"]')
    score_m = re.search(r"(\d+[.,]\d)", review_block)
    count_m = re.search(r"([\d.]+)\s+recensioni", review_block)
    link = el.query_selector('a[data-testid="title-link"]') or el.query_selector("a")
    body = raw.lower()
    # layout desktop: elemento dedicato; layout mobile: distanza solo nel testo
    dist_text = text('[data-testid="distance"]') or body
    dist_m = re.search(r"(?:a\s+)?([\d.,]+)\s*(km|m)\s+da", dist_text)
    distance = None
    if dist_m:
        distance = _it_number(dist_m.group(1))
        if dist_m.group(2) == "m" and distance is not None:
            distance = round(distance / 1000, 2)
    return {
        "name": name,
        "total_price": price,
        "review_score": _it_number(score_m.group(1)) if score_m else None,
        "review_count": int(count_m.group(1).replace(".", "")) if count_m else None,
        "distance_km": distance,
        # il filtro fc=2 è già nell'URL: se il badge non c'è resta "da verificare"
        "free_cancellation": True if "cancellazione gratuita" in body else None,
        "mobile_deal": ("dispositivi mobili" in body) or ("mobile" in body and "offerta" in body),
        # compare solo navigando con la sessione loggata di un account Genius
        "genius_deal": "genius" in body,
        "unit_desc": _unit_desc(raw),
        "multi_unit": bool(re.search(r"\d+\s*[x×]\s*(appartament|monolocal|suite|camer)", body)),
        "url": (link.get_attribute("href") or "").split("?")[0] if link else "",
    }


def _unit_desc(raw: str) -> str | None:
    """Es. 'Intero appartamento – 14 m²: 3 letti • 1 camera da letto • 1 bagno'."""
    m = re.search(r"^(?:\d+\s*[x×]\s*)?(?:Intero appartamento|Appartamento|Monolocale|Aparthotel|Suite)[^\n]*", raw, re.MULTILINE)
    return m.group(0).strip() if m else None


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
