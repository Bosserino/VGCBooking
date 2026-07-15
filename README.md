# VGCBooking — Trasferte team VGC, stagione 2027

Sistema per organizzare le trasferte del team, **100% gratuito e automatico**:

1. I ragazzi si "prenotano" con una **X** su un Google Sheet condiviso.
2. Ogni notte una GitHub Action (gratis) cerca **appartamenti reali** (Booking.com
   via Playwright + Airbnb via pyairbnb) entro **2 km dalla fiera**, con
   **cancellazione gratuita**, ordinati per **prezzo con buone recensioni prima**,
   e i **voli reali** Google Flights da **Roma (FCO/CIA)** via fast-flights.
3. I risultati finiscono su una **dashboard web** (GitHub Pages) con la stima di
   costo a testa per ogni evento e lo storico prezzi. Si prenota a mano dai link.

**Per metterla online oggi: segui [PUBBLICAZIONE.md](PUBBLICAZIONE.md)** (solo browser, ~20 min).

## Eventi coperti (fonte: [calendario ufficiale](https://championships.pokemon.com/it-it/events/))

Tutti gli **Internazionali** (LAIC San Paolo, EUIC Londra, NAIC Chicago) + tutte le
tappe **europee** (Francoforte, Nizza, Danzica, Stoccarda, Birmingham, Lisbona, Praga,
Bologna). L'elenco vive in [data/events_2027.yaml](data/events_2027.yaml): le sedi sono
quelle storiche/presunte (`venue_confirmed: false`) — quando RK9 pubblica la sede
ufficiale, aggiorna `venue`, `lat`, `lon` e rilancia `init`.

## Setup (nessuna chiave richiesta)

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Uso (CLI locale)

```bash
.venv/bin/python -m vgcbooking events            # mostra il calendario
.venv/bin/python -m vgcbooking snapshot          # prezzi reali -> docs/data/prices.json
.venv/bin/python -m vgcbooking snapshot --mock   # dati finti per provare la dashboard
.venv/bin/python -m vgcbooking dashboard         # apre la dashboard in locale
.venv/bin/python -m vgcbooking init              # (alternativa Excel) crea VGC_2027.xlsx
.venv/bin/python -m vgcbooking sync              # (alternativa Excel) link pre-filtrati
```

Nota per l'esecuzione locale dall'Italia: Google Flights risponde col muro cookie
UE (voli vuoti) e pyairbnb richiede Python ≥ 3.10 — sul runner GitHub Actions
(USA, Python 3.12) funzionano entrambi; Booking via Playwright funziona anche in locale.

La modalità di default (`sync`) è **100% gratuita**: per ogni evento con almeno
una X scrive nei fogli *Alloggi* e *Voli* i link di ricerca già filtrati
(appartamenti, cancellazione gratuita, recensioni 8+, prezzo crescente; su Airbnb
riquadro mappa di ±2 km centrato sulla fiera; su Google Flights date, aeroporti e
numero passeggeri precompilati). Si apre il link, si sceglie, si prenota a mano.

### Opzionale: risultati veri dentro al foglio (`sync --api`)

Se un domani vorrete i prezzi direttamente in Excel, copiate `.env.example` in
`.env` con le chiavi (`RAPIDAPI_KEY` per *booking-com15*/*airbnb19*,
`SERPAPI_KEY` per Google Flights — piani con quota gratuita limitata) e lanciate
`sync --api`. Con `sync --mock` si prova il giro completo con dati finti.

## Il file Excel (`VGC_2027.xlsx`)

- **Prenotazioni** — una riga per evento, una colonna per ciascuno dei 14 membri.
  Metti **X** per prenotarti; la colonna *Tot persone* si aggiorna da sola e la
  pipeline usa quel numero per dimensionare le ricerche. Check-in/check-out sono
  precompilati (giorno prima → giorno dopo) ma modificabili.
- **Alloggi** — risultati scritti da `sync`: fonte, prezzo totale e a notte,
  recensioni, distanza dalla fiera, cancellazione, link per prenotare.
- **Voli** — migliori tariffe A/R da MXP (aeroporto per-persona configurabile in
  [data/team.yaml](data/team.yaml)), con link Google Flights per acquistare.
- **Eventi** — calendario di riferimento con stato conferma sede.

> Il file può stare su OneDrive/Drive condiviso: la pipeline lo legge/scrive in
> locale, basta che sia sincronizzato e chiuso quando lanci `sync`.

## Limiti onesti delle API

- **Booking.com e Airbnb** non hanno API pubbliche self-service: si usano wrapper
  RapidAPI (non ufficiali). I nomi dei campi possono variare tra versioni: gli
  adapter in `src/vgcbooking/providers/` sono difensivi e vanno ritoccati lì se
  il fornitore cambia schema.
- **Google Flights** non ha API di booking: si cercano le tariffe reali via SerpAPI
  e si prenota dal link. Per l'emissione biglietti 100% via API servono
  [Duffel](https://duffel.com) o [Amadeus](https://developers.amadeus.com)
  (Flight Create Orders): l'interfaccia `FlightProvider` è già pronta per
  aggiungere un provider del genere.
