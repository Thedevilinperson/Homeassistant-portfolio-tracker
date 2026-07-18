# Portfolio Tracker op Windows

Deze map bevat alles om de app rechtstreeks op een Windows-PC te draaien, los van
Home Assistant. Het is dezelfde codebase: geen fork, geen aparte versie van de
Python-bestanden. Alleen de opstartlaag verschilt, want `run.sh` is een bash-script
en Windows spreekt dat niet.

## Wat er verandert ten opzichte van de add-on

| | Home Assistant add-on | Windows |
|---|---|---|
| Opstarten | `run.sh` in de container | `start.bat` |
| Datamap | `/share/portfolio_tracker` | `%LOCALAPPDATA%\PortfolioTracker\data` |
| Openen | HA-paneel via ingress | `http://127.0.0.1:8501` |
| Pakketten | in het Docker-image | virtuele omgeving in `.venv` |

De app zelf merkt niets van dat verschil: alle instellingen, ook je OpenAI-sleutel,
zitten in de database en niet in de HA-configuratie.

## Installatie

**1. Python installeren.** Versie **3.11 of 3.12** van <https://www.python.org/downloads/>.
Vink tijdens de installatie *Add python.exe to PATH* aan. Gebruik nog geen 3.13:
de app draait op numpy 1.x en daarvan bestaan voor 3.13 geen kant-en-klare pakketten.

**2. De repo op je PC zetten**, bijvoorbeeld met `git clone`, of als ZIP downloaden
en uitpakken. Zet ze op een pad zonder rare tekens, bijvoorbeeld `C:\PortfolioTracker`.

**3. `setup.bat` dubbelklikken.** Dat maakt een virtuele omgeving in `.venv`,
installeert de pakketten (enkele minuten de eerste keer) en zet de database klaar.

**4. Optioneel: je bestaande data meenemen.** Kopieer `portfolio.db` uit
`\share\portfolio_tracker` op je Home Assistant naar de datamap die `setup.bat`
toonde. Doe dat *voor* je de app de eerste keer start. De migraties in `init_db()`
draaien er daarna vanzelf overheen; het schema is identiek aan dat van de add-on.

**5. `start.bat` dubbelklikken.** De browser opent vanzelf.

## Dagelijks gebruik

- **Starten**: `start.bat`. Het venster dat openblijft toont de logs van Streamlit.
- **Stoppen**: Ctrl+C in dat venster, of het venster sluiten. De scheduler stopt mee.
- **Scheduler apart stoppen**: `stop.bat`.
- **Logs van de scheduler**: `logs\scheduler.log` en `logs\scheduler.err.log`.

Wil je dat de app bij het aanmelden meteen meestart, maak dan een snelkoppeling naar
`start.bat` en zet die in de map die je krijgt via Windows-toets + R → `shell:startup`.

## Instellingen aanpassen

Alles staat in `config.bat`: datamap, poort, netwerkadres, tijdzone, of de browser
automatisch opengaat en of de scheduler meedraait.

Pas `config.bat` zelf **niet** aan als je de map in git bijhoudt. Maak in plaats
daarvan `config.local.bat` in deze map met alleen de regels die je wil wijzigen:

```bat
@echo off
set "DATA_DIR=D:\Data\PortfolioTracker"
set "BIND_ADDRESS=0.0.0.0"
```

Dat bestand wordt automatisch ingelezen na `config.bat` en staat in `.gitignore`,
dus een `git pull` geeft nooit een conflict op je persoonlijke instellingen.

Zet je `BIND_ADDRESS` op `0.0.0.0`, dan is de app ook bereikbaar vanaf je telefoon
of een andere PC in je netwerk. Windows vraagt dan eenmalig om een firewall-uitzondering.
Let op: er zit geen wachtwoord op de app. Doe dit alleen in een netwerk dat je vertrouwt,
en nooit met een poortdoorschakeling naar het internet.

## Belangrijk: niet twee keer tegelijk

Laat de Windows-versie en de Home Assistant add-on **nooit gelijktijdig op dezelfde
database werken**, bijvoorbeeld via een netwerkschijf. SQLite in WAL-modus verwacht
één schrijver; twee processen over SMB kunnen de database beschadigen. Kies één
plek als de echte, of werk op een kopie.

## Als er iets misloopt

**"Python is niet gevonden"** - Python staat niet in PATH. Herinstalleer met de
optie *Add python.exe to PATH*, of open het Python-installatieprogramma opnieuw
en kies *Modify*.

**Installeren van de pakketten faalt met een compileerfout** - dan wordt er
geprobeerd iets vanaf broncode te bouwen. Bijna altijd een teken dat je Python-versie
te nieuw is voor de vastgelegde pakketversies. Controleer met `python --version`
dat je op 3.11 of 3.12 zit.

**`ZoneInfoNotFoundError: Europe/Brussels`** - het pakket `tzdata` ontbreekt.
Windows heeft, anders dan Linux, geen tijdzonedatabank in het systeem zelf.
`setup.bat` installeert dit normaal mee via `requirements-windows.txt`; draai dat
script opnieuw.

**Poort 8501 is al in gebruik** - er draait nog een oude Streamlit. Sluit dat venster,
of zet `APP_PORT` op iets anders in `config.local.bat`.

**De koersen verversen niet** - kijk in `logs\scheduler.err.log`. Draait het proces
nog? Controleer met `tasklist /FI "IMAGENAME eq python.exe"`. Merk op dat de
scheduler alleen draait zolang `start.bat` open staat: sluit je het venster, dan
gaan ook de achtergrondjobs uit. Dat is bewust, zodat er geen wees-processen
achterblijven.
