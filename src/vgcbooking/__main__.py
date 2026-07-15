"""CLI: python -m vgcbooking <comando>"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import settings


def main() -> int:
    parser = argparse.ArgumentParser(prog="vgcbooking", description="Trasferte team VGC 2027")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Crea il file Excel con eventi e team")
    p_init.add_argument("--force", action="store_true", help="Sovrascrive il file esistente")

    p_sync = sub.add_parser("sync", help="Cerca alloggi e voli per gli eventi con prenotazioni")
    p_sync.add_argument("--api", action="store_true", help="Risultati in-foglio via API (servono chiavi)")
    p_sync.add_argument("--mock", action="store_true", help="Dati finti, senza chiavi API")
    p_sync.add_argument("--event", help="Limita a un solo evento (slug, es. euic-london)")

    sub.add_parser("events", help="Mostra il calendario caricato")

    p_snap = sub.add_parser("snapshot", help="Scrive docs/data/prices.json per la dashboard")
    p_snap.add_argument("--mock", action="store_true", help="Dati finti per provare la dashboard")
    p_snap.add_argument("--event", help="Limita a un solo evento (slug)")

    sub.add_parser("dashboard", help="Apre la dashboard in locale (http://localhost:8734)")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "init":
        if settings.workbook_path.exists() and not args.force:
            print(f"{settings.workbook_path} esiste già: usa --force per ricrearlo (perderai le X!).")
            return 1
        from .workbook import create_workbook

        path = create_workbook()
        print(f"Creato {path}")
        return 0

    if args.command == "sync":
        from .pipeline import run_sync

        mode = "mock" if args.mock else "api" if args.api else "links"
        if mode == "links":
            print("Modalità gratuita: genero link di ricerca pre-filtrati (nessuna chiave richiesta).\n")
        stats = run_sync(mode=mode, only_event=args.event)
        print(
            f"\nFatto: {stats.get('events', 0)} eventi, "
            f"{stats.get('stays', 0)} alloggi e {stats.get('flights', 0)} voli scritti in {settings.workbook_path.name}"
        )
        return 0

    if args.command == "snapshot":
        from .snapshot import run_snapshot

        stats = run_snapshot(mock=args.mock, only_event=args.event)
        print(
            f"\nSnapshot: {stats['events']} eventi "
            f"({stats['with_flights']} con voli, {stats['with_stays']} con alloggi) -> docs/data/prices.json"
        )
        return 0

    if args.command == "dashboard":
        import http.server
        import webbrowser
        from functools import partial

        from .config import PROJECT_ROOT

        handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(PROJECT_ROOT / "docs"))
        webbrowser.open("http://localhost:8734")
        print("Dashboard su http://localhost:8734 (Ctrl+C per chiudere)")
        http.server.HTTPServer(("127.0.0.1", 8734), handler).serve_forever()

    if args.command == "events":
        from .registry import load_events

        for ev in load_events():
            flag = "" if ev.venue_confirmed else "  [sede da confermare]"
            print(f"{ev.start} – {ev.end}  {ev.name:<55} {ev.city} ({ev.airport}){flag}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
