# Estrazione delibere Puglia

Pipeline per cercare le delibere della Giunta regionale dal portale ufficiale Amministrazione Trasparente della Regione Puglia e ricostruire l'uso del FESR.

Fonte dati elenco delibere: <https://trasparenza.regione.puglia.it/provvedimenti/provvedimenti-organi-indirizzo-politico/provvedimenti-della-giunta-regionale>

Fonte dati atti/PDF: <https://burp.regione.puglia.it>

## Uso rapido da VS Code

Apri `scraper.py`, modifica solo le variabili nella sezione iniziale e premi **Run Python File**.

Per scaricare tutto il FESR 2026, CSV e PDF disponibili, usa:

```python
ANNI = "2026"
KEYWORD = "FESR"
SCARICA_LINK_PDF = True
SCARICA_PDF = True
MAX_PAGINE = None
MAX_PDF = None
```

Puoi usare anche un range:

```python
ANNI = "2023-2026"
```

oppure una lista precisa:

```python
ANNI = ["2026", "2025", "2023"]
```

Output principali:

- `data/delibere_2026_fesr.csv`: tutte le righe trovate, con campi normalizzati.
- `data/delibere_2026_fesr.json`: stesso contenuto in JSON.
- `data/riepilogo_azioni_2026_fesr.csv`: conteggio per azione FESR.
- `data/riepilogo_manovre_2026_fesr.csv`: conteggio per tipo di manovra.
- `data/riepilogo_beneficiari_2026_fesr.csv`: primi beneficiari ricavati dall'oggetto.
- `data/riepilogo_proponenti_2026_fesr.csv`: conteggio per struttura proponente.

Il CSV mantiene alcune colonne compatibili con la versione precedente del progetto, per esempio `proponente`, `numero_adozione`, `data_adozione`, `protocollo`, `dettaglio_url` e `pdf_url`. Per la Puglia aggiunge anche `regione`, `struttura`, `burp_url`, `pdf_nome` e i campi normalizzati per programma, azioni, priorita, DGR, CUP, importi e tipo di manovra.

La cartella `data/` e' ignorata da Git: contiene output rigenerabili, inclusi eventuali PDF.

Ricalcolare i riepiloghi da un CSV gia' scaricato:

```bash
python3 analisi.py data/delibere_2026_fesr.csv
```

## Note

Il portale Puglia espone l'elenco delle delibere come pagina HTML filtrabile. Lo scraper usa i filtri ufficiali per oggetto e anno, segue la paginazione del sito e legge i link agli atti pubblicati sul BURP.

Quando `SCARICA_LINK_PDF = True` o `SCARICA_PDF = True`, lo scraper apre il dettaglio BURP di ogni delibera e prova a ricavare il PDF diretto. Alcune delibere recenti possono risultare in elenco ma non avere ancora il PDF disponibile sul BURP: in quel caso `burp_url` resta valorizzato e `pdf_url` resta vuoto.

Quando `SCARICA_PDF = True`, vengono scaricati i PDF disponibili per i record scaricati.

## Pubblicazione su GitHub

Dopo aver creato un repository vuoto su GitHub:

```bash
git remote add origin https://github.com/NOME_UTENTE/NOME_REPO.git
git push -u origin main
```
