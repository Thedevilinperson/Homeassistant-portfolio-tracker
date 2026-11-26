# Plaatsing 1.8.21 — NumPy 2 en Python 3.14

Lost de crash op van elke tabel (o.a. het dashboard) na het herbouwen van 1.8.20:
`ImportError: pyarrow requires NumPy 2.0 or newer`.

## Gewijzigde bestanden
| Bestand | Wat |
|---|---|
| `portfolio_tracker/requirements.txt` | NumPy 2, geen onnodige bovengrenzen meer |
| `portfolio_tracker/Dockerfile` | Python 3.14, tzlocal correct geïnstalleerd |
| `portfolio_tracker/windows/setup.bat`, `INSTALL_WINDOWS.md` | Python 3.11+ zonder bovengrens, installeren met `--upgrade` |
| `portfolio_tracker/README.md` | Python-versie |
| `portfolio_tracker/.gitignore` | Python-cachebestanden uitsluiten |
| `portfolio_tracker/config.yaml` | Versie 1.8.21 |

Geen databasemigratie nodig.

## Home Assistant
1. Instellingen → Add-ons → Add-on Store → ⋮ (rechtsboven) → **Controleren op updates**.
2. Open Portfolio Tracker en kies **Bijwerken** naar 1.8.21. Dat bouwt de container
   opnieuw op. Het duurt langer dan gewoonlijk, omdat het basisimage naar Python 3.14
   wisselt.
3. Controleer daarna het dashboard: de tabellen laden opnieuw, en GNOM staat in EUR.

## Windows-versie
Start `setup.bat` opnieuw: het werkt de pakketten bij naar NumPy 2 en de nieuwste
versies. Je bestaande Python (3.11 of nieuwer) mag blijven.
