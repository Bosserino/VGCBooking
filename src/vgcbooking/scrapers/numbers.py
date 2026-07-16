"""Parsing di importi in formato misto italiano/inglese.

Booking può servire "10.000,50" (it) o "10,000.50" (en) nella stessa pagina:
un gruppo finale di 3 cifre dopo il separatore va letto come migliaia.
"""
from __future__ import annotations

import re


def parse_amount(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[^\d.,]", "", str(value or ""))
    if not s:
        return None
    if "," in s and "." in s:
        # l'ultimo separatore che compare è quello decimale
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # 1.234,56 -> 1234.56
        else:
            s = s.replace(",", "")                     # 1,234.56 -> 1234.56
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 3:
            s = s.replace(",", "")                     # 10,000 -> 10000 (en)
        else:
            s = s.replace(",", ".")                    # 10,5 -> 10.5 (it)
    elif "." in s:
        parts = s.split(".")
        if len(parts[-1]) == 3 or len(parts) > 2:
            s = s.replace(".", "")                     # 10.000 / 1.234.567 -> migliaia (it)
        # altrimenti è un decimale: 8.7 resta 8.7
    try:
        return float(s)
    except ValueError:
        return None
