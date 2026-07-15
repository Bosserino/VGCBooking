# Metti online la dashboard — guida passo passo (solo browser, ~20 minuti)

Alla fine avrai: un **Google Sheet** dove i ragazzi mettono le X e una **pagina web**
con i prezzi veri di voli e appartamenti, aggiornata da sola ogni notte.

---

## Parte 1 — Il Google Sheet delle prenotazioni (5 min)

1. Vai su [sheets.google.com](https://sheets.google.com) e crea un foglio nuovo. Chiamalo `VGC 2027 Prenotazioni`.
2. Menu **File → Importa → Carica** e trascina il file `data/signups_template.csv` di questo progetto. Scegli "Sostituisci foglio di lavoro".
3. Vedrai gli 11 eventi in riga e i 14 nomi in colonna: ognuno mette una **X** nella sua colonna per prenotarsi. Le date Check-in/Check-out si possono cambiare.
4. Condividi il foglio col team (tasto **Condividi**, "Chiunque abbia il link – Editor").
5. Ora rendilo leggibile dal robot: menu **File → Condividi → Pubblica sul web**.
   Nel primo menu scegli il **foglio** (non "Intero documento"), nel secondo scegli **Valori separati da virgola (.csv)**, poi **Pubblica**.
6. **Copia il link** che compare (finisce con `output=csv`) e tienilo da parte: serve nella Parte 3.

## Parte 2 — Metti il progetto su GitHub (5 min)

1. Vai su [github.com](https://github.com) e crea un account se non ce l'hai (gratis).
2. In alto a destra: **+ → New repository**. Nome: `vgc-trasferte`. Visibilità: **Public** (serve per avere il sito gratis). **Create repository**.
3. Nella pagina del repo appena creato clicca **uploading an existing file**.
4. Apri il Finder nella cartella `VGCBooking` e trascina dentro la finestra del browser **tutto il contenuto visibile** della cartella (le cartelle `data`, `docs`, `src` e i file `pyproject.toml`, `requirements.txt`, `README.md`, `PUBBLICAZIONE.md`...). NON serve trascinare file nascosti.
5. In basso clicca **Commit changes** e aspetta il caricamento.
6. Ora il file "robot" (il Finder non lo trascina perché è nascosto): nel repo clicca **Add file → Create new file**. Come nome scrivi esattamente:
   ```
   .github/workflows/update-prices.yml
   ```
   Poi apri il file `PUBBLICAZIONE.md` appena caricato sul repo, vai alla sezione
   "Contenuto del workflow" e usa il bottone **copia** (l'icona in alto a destra del
   riquadro grigio): copia solo il contenuto, senza le righe ` ```yaml ` e ` ``` `.
   La prima riga incollata deve essere `# Aggiorna i prezzi ogni notte...`, l'ultima
   `          git push`. Incolla e **Commit changes**.

   ⚠️ Se GitHub segnala "Invalid workflow file … Unexpected value 'yaml'" hai copiato
   anche la cornice del blocco: modifica il file (matita) e cancella la prima e
   l'ultima riga.

## Parte 3 — Collega il Google Sheet (2 min)

1. Nel repo: **Settings → Secrets and variables → Actions → scheda Variables → New repository variable**.
2. Nome: `SIGNUP_CSV_URL` — Valore: il link CSV copiato nella Parte 1. **Add variable**.

## Parte 4 — Accendi il sito e il robot (3 min)

1. **Settings → Pages** → sotto "Build and deployment": Source = **Deploy from a branch**, Branch = **main**, cartella = **/docs** → **Save**.
2. Tab **Actions** → se chiede conferma clicca **I understand my workflows, enable them**.
3. Nella colonna a sinistra clicca **Aggiorna prezzi → Run workflow → Run workflow** (bottone verde).
4. Aspetta che il pallino diventi ✅ (5-10 minuti la prima volta): sta cercando voli e appartamenti veri per tutti gli 11 eventi.
5. Torna su **Settings → Pages**: trovi l'indirizzo del sito, tipo
   `https://TUONOME.github.io/vgc-trasferte/` — **quello è il link da girare al team**.

## Da domani, tutto da solo

- Ogni notte alle 06:00 italiane il robot riaggiorna i prezzi e la pagina.
- I ragazzi: mettono la X sul Google Sheet → il giorno dopo la dashboard mostra
  prezzi calcolati sul numero giusto di persone. Per un aggiornamento immediato:
  tab Actions → Aggiorna prezzi → Run workflow.
- Quando viene annunciata la sede vera di un evento: modifica `data/events_2027.yaml`
  direttamente su GitHub (matita in alto a destra sul file), correggi `venue`, `lat`,
  `lon` e metti `venue_confirmed: true` → Commit → i 2 km si ricentrano da soli.

## Contenuto del workflow (per il passo 2.6)

```yaml
# Aggiorna i prezzi ogni notte e li pubblica sulla dashboard (GitHub Pages).
# Si può lanciare anche a mano: tab Actions -> "Aggiorna prezzi" -> Run workflow.
name: Aggiorna prezzi

on:
  schedule:
    - cron: "0 4 * * *"   # ogni giorno alle 06:00 italiane (04:00 UTC)
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: update-prices
  cancel-in-progress: false

jobs:
  snapshot:
    runs-on: ubuntu-latest   # runner USA: niente muro cookie UE su Google Flights
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Installa dipendenze
        run: |
          pip install -e .
          pip install fast-flights pyairbnb playwright
          playwright install --with-deps chromium

      - name: Snapshot prezzi
        env:
          SIGNUP_CSV_URL: ${{ vars.SIGNUP_CSV_URL }}
        run: python -m vgcbooking snapshot

      - name: Pubblica i dati aggiornati
        run: |
          git config user.name "vgc-bot"
          git config user.email "actions@github.com"
          git add docs/data/prices.json docs/data/history.json
          git diff --cached --quiet || git commit -m "Aggiorna prezzi $(date -u +%F)"
          git push
```

## Se qualcosa non va

- **La pagina mostra "dati di esempio"**: il workflow non ha ancora girato con
  successo — controlla il tab Actions, apri l'ultimo run e guarda i log rossi.
- **Un evento dice "booking.com: nessun dato"**: il WAF di Booking a volte blocca
  i server GitHub; di solito al run successivo passa. Airbnb e i link diretti
  restano comunque disponibili sulla card.
- **I voli di Chicago (giugno 2027) non compaiono**: Google Flights vende al massimo
  ~11 mesi in anticipo; appariranno da agosto 2026.
