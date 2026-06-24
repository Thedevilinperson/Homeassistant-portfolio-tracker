
/
Claude finished the response
ik heb een update uitgevoerd van iets in home assistant (OS of supervisor of core, ik weet het niet) en nu is mijn app weg uit de zijbalk en de lijst van geïnstalleerde apps en zie ik hem ook niet meer in de addon store nadat ik op 'checken op updates' heb geklikt

23 jun

Diagnosed post-update add-on corruption; prioritized supervisor logs inspection
Diagnosed post-update add-on corruption; prioritized supervisor logs inspection
Vervelend, maar in de meeste gevallen is dit goed te herstellen — en je data staat veilig in /share, dus die raak je niet kwijt, wat er ook gebeurt.

Wat je beschrijft (weg uit zijbalk, weg uit de lijst van geïnstalleerde add-ons én niet zichtbaar in de store) wijst meestal op één van twee dingen na een update:

De Supervisor-store/cache is corrupt geraakt door de update — heel gangbaar. De Supervisor "reset" dan een corrupte store en je lokale add-on wordt even niet meer gedetecteerd.
De schemavalidatie van config.yaml is strenger geworden en een veld dat vroeger getolereerd werd, breekt nu stilletjes de zichtbaarheid (precies wat je eerder al eens hebt meegemaakt met panel_icon e.d.).
De snelste manier om te weten wélke van de twee het is, is de Supervisor-log lezen. Die vertelt je letterlijk waarom de add-on niet geladen wordt.

Stap voor stap:

1. Lees de Supervisor-log. Ga naar Instellingen → Systeem → Logboeken en kies bovenaan "Supervisor" in de dropdown. Zoek naar regels die je slug of /addons/ noemen, of naar Can't read .../config.yaml, een validatiefout, of Reset corrupt Store. Via terminal kan ook: ha supervisor logs.

2. Controleer of de bestanden er nog fysiek staan. Kijk in je add-on map (/addons/<jouw_slug>/) of config.yaml, Dockerfile, run.sh enz. er allemaal nog zijn. Een update raakt die map normaal niet aan, maar even checken kan geen kwaad.

3. Forceer een herscan van lokale add-ons. "Checken op updates" ververst vooral de git-repositories van de store, niet per se de lokale add-on-detectie. Doe in plaats daarvan via de terminal:

ha store reload
ha supervisor reload
Als dat niets oplevert, een volledige host-reboot: ha host reboot (of via Instellingen → Systeem → ⋮ → Herstart). Dat lost de corrupte-store-variant vaak in één klap op.

4. Als de log een validatiefout op config.yaml toont, dan is dat je oorzaak. Vergelijk je huidige config.yaml met het actuele add-on-schema; waarschijnlijk is er een veld bijgekomen dat nu strikter is. Bump daarna de version en gebruik "Herbouwen".

Begin met de log — kun je me de relevante regels (alles waar je slug of config.yaml in voorkomt) hier plakken? Dan zie ik meteen of het de store-corruptie of de config-validatie is, en kan ik je gericht verder helpen.

Eén ding ter geruststelling: zelfs in het ergste geval, waarbij je de add-on volledig moet verwijderen en opnieuw toevoegen, blijft je portfolio-database intact omdat die in /share/portfolio_tracker zit en niet in de container.

de logging blijft enkel het volgende herhalen:


2026-06-23 20:48:12.313 WARNING (MainThread) [supervisor.api.ingress] No valid ingress session a8619851c98e71ce75592d1468442bb3012e3688f3159e9be0b6169ec2a3c8181d6c0203e134d6b1b99c2076fc2dedf5ca79ac44be7dfe4c41c1777cf8530cd3
23 jun

Onderscheidde symptoom van oorzaak; adviseerde supervisor-interrogatie
Onderscheidde symptoom van oorzaak; adviseerde supervisor-interrogatie
Goed dat je dit deelt — belangrijkste eerst: die ingress-warning is niet de oorzaak, maar een symptoom. Het betekent dat er ergens nog een browser-tab (of de companion-app, of een dashboard met het panel-iframe) openstaat die je add-on via ingress probeert te bereiken met een oude, ongeldige sessie-token. De Supervisor blijft dat netjes weigeren en logt het elke keer. Het zegt op zich niets over waarom de add-on verdwenen is, en het overstemt waarschijnlijk de log waardoor je de échte fout niet ziet.

Twee dingen los daarvan:

1. Stop de ruis zodat je de echte log kunt lezen. Sluit alle tabbladen/vensters die naar je add-on wezen, doe een harde refresh (Ctrl+Shift+R) of log even uit en weer in bij HA. Daarna stopt die warning. Scroll vervolgens in de Supervisor-log terug naar het moment dat de Supervisor herstartte na je update — dáár staat de eventuele parse-/validatiefout op config.yaml, niet in de staart.

2. Vraag de Supervisor rechtstreeks of hij je add-on nog kent. Dit is de snelste check. Open de terminal (SSH/Terminal-add-on) en draai:

ha addons
Zoek in die lijst naar je slug (lokale add-ons hebben meestal een local_-prefix of je mapnaam). Daarna:

ha addons info <jouw_slug>
De uitkomst vertelt ons precies waar het zit:

Staat je add-on er wél in → dan is hij op Supervisor-niveau gewoon nog geïnstalleerd, en is alleen de frontend/het sidebar-panel de registratie kwijt (cache-probleem). Dat de ingress-sessie nog bestaat, wijst eigenlijk die kant op. Oplossing: ha addons rebuild <jouw_slug> of ha addons start <jouw_slug>, gevolgd door een herstart van Core (Instellingen → Systeem → ⋮ → Herstart) en een harde browser-refresh. Het panel hoort dan terug te komen.
Staat je add-on er níét in → dan heeft de Supervisor hem bij de update laten vallen, vrijwel zeker door de strengere config.yaml-validatie. Draai dan ha store reload en kijk meteen daarna in de log naar de fout op je lokale repo/add-on map.
Wil je ha addons (of in elk geval het stukje met jouw add-on) hier plakken? Dan weet ik welk van de twee paden we in moeten.

net even gekeken via de terminal en de addons folder is leeg. alle bestanden zijn weg. Hoe kan dit?

23 jun

Onderzocht mogelijke oorzaken en recovery-opties voor verloren add-on bestanden
Onderzocht mogelijke oorzaken en recovery-opties voor verloren add-on bestanden
Oké, even diep ademhalen — dit ziet er erger uit dan het waarschijnlijk is. Het belangrijkste eerst: je /addons-map en je /share-map zijn twee totaal verschillende dingen. Je portfolio-database staat in /share/portfolio_tracker, en die map wordt door niets van dit alles geraakt. Laten we dat meteen bevestigen. Draai in de terminal:

ls -la /share/portfolio_tracker
Zolang je .db-bestand (of hoe je het ook genoemd hebt) daar nog staat, is het enige wat je kwijt bent je broncode — en dat is herstelbaar. Je data, het stukje dat echt onvervangbaar is, staat los.

Wat betreft "hoe kan dit": een normale update van HA OS / Supervisor / Core raakt de lokale add-ons-map niet aan; die staat op de datapartitie en hoort updates te overleven. Dus dat de bestanden écht verdwenen zijn is ongebruikelijk. De drie realistische verklaringen, op volgorde van waarschijnlijkheid:

Je kijkt op een andere plek dan waar de bron stond. Het pad /addons dat je ziet hangt af van wélke terminal je gebruikt. De "Terminal & SSH"-add-on mapt /addons naar de lokale add-ons-map; host-SSH (poort 22222) toont /mnt/data/supervisor/addons/local/. Als je nu via een andere ingang binnenkomt dan vorige keer, kan "leeg" gewoon "verkeerde map" betekenen.
Er is tijdens of na de update een restore of rollback gebeurd naar een back-up van vóór je de add-on toevoegde, waardoor de map naar een eerdere staat is teruggezet.
Echte bestandsverlies door een filesystem-probleem — zeldzaam, maar mogelijk.
Om te bepalen welke het is:

ls -la /addons
ls -la /backup
Die laatste is belangrijk: HA maakt automatische back-ups en bewaart .tar-bestanden in /backup. Een volledige back-up bevat een aparte map "Lokale add-ons" — dus als er een back-up van vóór de update staat, kun je je broncode daar zo weer uithalen.

De grote vraag die alles oplost: heb je je broncode nog ergens anders? Bijvoorbeeld in een git-repo of gewoon op je PC waar je hem oorspronkelijk geschreven hebt. Zo ja, dan is dit binnen vijf minuten verholpen: je kopieert de map terug naar /addons/<jouw_slug>/, draait ha store reload, en de add-on verschijnt weer in de store om opnieuw te installeren (met je data nog intact in /share).

Kun je me de uitkomst van die drie ls-commando's geven, plus laten weten of je de broncode nog op je PC of in git hebt staan? Dan weten we precies of we aan het herstellen of aan het terugkopiëren zijn.

ik denk dat ik weet wat er gebeurd is: ik heb de installatie via een backup van een raspberry Pi naar een intel nuc overgezet. Ik vermoed dat die addon-folder niet meegenomen wordt in de backup. Hoe kan ik dit in de toekomst voorkomen bij backup herstel?

23 jun

Ontrafelen van backup-systeemwijzigingen in HA 2025.1.0
Ontrafelen van backup-systeemwijzigingen in HA 2025.1.0
Goede diagnose — en die verklaart precies wat je ziet. Laat me even verifiëren wat HA-backups écht meenemen bij lokale add-ons, want hier zit een belangrijk addertje onder het gras dat ook met je hardware-wissel te maken heeft.


Bevestigde diagnose en formuleerde preventiestrategieën voor toekomstige backups
Bevestigde diagnose en formuleerde preventiestrategieën voor toekomstige backups
Je diagnose klopt, en het is geen toeval of een fout van jou — dit is bekend gedrag dat sinds begin 2025 in HA is veranderd. Sinds Home Assistant 2025.1.0 nemen back-ups de lokale addons/-map (en aanvankelijk ook ssl/) niet meer mee; in de nieuwe back-up-flow zijn alleen nog Media en Share als mappen selecteerbaar. De ssl-map is later weer hersteld, maar de lokale add-on-broncode bleef erbuiten. Daardoor zat jouw bron simpelweg niet in de back-up die je naar de NUC hebt teruggezet — vandaar de lege map. 
GitHub

Er speelt nog een tweede ding mee bij jouw specifieke verhuizing: je ging van een Pi (ARM/aarch64) naar een NUC (x86_64/amd64). Zelfs als de gebouwde Docker-image wél was meegekomen, had die niet gedraaid op de andere architectuur. Wat je dus eigenlijk nodig hebt is niet de image maar de bron (Dockerfile, config.yaml, je Python-bestanden) — die is architectuur-onafhankelijk, en HA herbouwt de image gewoon voor de nieuwe machine. De les: behandel /addons als wegwerpbaar en zorg dat de bron ergens anders veilig staat.

Hoe je dit in de toekomst voorkomt, van sterk naar zwak:

Zet je add-on in een eigen git-repository (de echte oplossing). Host je broncode op GitHub en voeg in HA die repo-URL toe via de add-on store (Store → ⋮ → Repositories). Je add-on is dan geen "lokale" add-on meer maar een repo-add-on — en díé worden door HA-back-ups wél correct afgehandeld: de back-up bewaart de repo-URL en slug, en bij een restore haalt HA de add-on automatisch opnieuw op en herbouwt hem voor de juiste architectuur. Een verhuizing als deze is dan een non-event. Een publieke repo is het eenvoudigst; je OpenAI-key en andere secrets houd je eruit door ze als add-on-config-opties (options/schema in config.yaml) door te geven in plaats van ze hard te coderen.
Houd minstens een git-clone op je PC. Ook als je liever lokaal blijft werken: nooit de Pi/NUC de enige plek laten zijn waar je code staat. Na elke migratie kopieer je de map terug naar /addons/<slug>/ en draai je ha store reload.
Back-up de /addons-map apart als je per se lokaal wilt blijven — bijvoorbeeld via de Samba Backup add-on of een eigen kopieerscript. Dit werkt, maar is fragieler en makkelijker te vergeten dan optie 1.
Optie 1 is veruit de beste voor jouw situatie, juist omdat je tussen architecturen bent verhuisd.

Eén belangrijke check nog, want hetzelfde mechanisme bedreigt je dáta: Share is een aparte aan/uit-schakelaar in de back-up. Als die bij jouw back-up uit stond, is niet alleen je add-on-bron weg, maar ook je portfolio-database mogelijk niet meegekomen. Heb je al gekeken of /share/portfolio_tracker op de NUC nog je .db-bestand bevat? Dat is het enige stukje dat echt onvervangbaar is — laat het me weten, dan kijken we daar als eerste naar.

de databank staat er wel degelijk nog.

23 jun
Mooi, dat is het belangrijkste — de onvervangbare data staat er nog. De rest is broncode, en die kun je opnieuw neerzetten.

Dan is je situatie nu concreet dit: lege /addons-map op de NUC, maar een werkende database in /share/portfolio_tracker. Zodra je de broncode terug op z'n plek hebt, pikt de add-on die database gewoon weer op (want DATA_DIR=/share/portfolio_tracker staat los van de container), en ben je weer waar je was.

De vraag die nu alles bepaalt: heb je je broncode nog ergens? Op je PC, in een git-repo, in een oude back-up van de Pi-installatie? Eén van die drie is genoeg.

Staat het nog op je PC of in git → kopieer de map naar /addons/<jouw_slug>/ (via de Samba- of File-editor-add-on, of scp), draai ha store reload, en de add-on verschijnt weer in de store om te installeren.
Heb je nog een oude Pi-back-up (.tar) van vóór 2025.1.0 → daar zat de lokale add-on-map mogelijk nog wél in. Je kunt zo'n .tar uitpakken en de add-on-bron eruit vissen, ook zonder volledige restore.
Staat het nergens meer → dan moeten we de bron reconstrueren. Dat is vervelend maar te overzien: je hebt eerder database.py, market_data.py, belgian_tax.py, scheduler.py, run.sh, Dockerfile en config.yaml gebouwd, en ik kan je helpen die opnieuw op te zetten op basis van wat we samen al hebben uitgewerkt. De database-structuur kunnen we zelfs uit het bestaande .db-bestand afleiden, zodat de nieuwe database.py precies past op je bestaande data.
Laat me weten welke van de drie het is. En sterk advies: zodra de bron weer draait, zet hem meteen in een git-repo en voeg die als repository toe in HA (optie 1 van daarnet) — dan kan een verhuizing of restore je dit nooit meer flikken.

ik ben aan het kijken op de SD kaart van de raspberry pi, maar het is mij niet duiedlijk waar ik moet zoeken

23 jun

Navigeerde door HA OS partitiestructuur en locatiepad
Navigeerde door HA OS partitiestructuur en locatiepad
Top, dan zit je broncode hoogstwaarschijnlijk gewoon op die SD-kaart — want op de Pi heb je de add-on lokaal gebouwd, en lokale add-ons leven op de datapartitie. Je moet alleen op de juiste plek kijken, en daar zit een addertje onder het gras afhankelijk van waarmee je de kaart uitleest.

De partitie. Een HA OS-SD-kaart heeft meerdere partities. De enige die voor jou telt is de grootste, met label hassos-data. Die is ext4-geformatteerd. Belangrijk: als je de kaart in Windows steekt, zie je waarschijnlijk alleen een klein FAT-partitietje (hassos-boot) — daar staat niks bruikbaars in — en Windows zal je voor de andere partities vragen of je ze wilt formatteren. Doe dat absoluut niet, dan ben je je bron pas echt kwijt. Windows en macOS kunnen ext4 niet uit zichzelf lezen.

Het pad binnen hassos-data. Zodra je die partitie open hebt, navigeer je naar:

supervisor/addons/local/<jouw_slug>/
Dáár horen je config.yaml, Dockerfile, run.sh en je Python-bestanden te staan.

Om te bevestigen dat je in de juiste partitie zit, kun je in diezelfde supervisor/-map ook deze twee terugvinden:

supervisor/share/portfolio_tracker/ → daar staat je oude database (zo herken je dat het de goede partitie is)
supervisor/homeassistant/ → dat is je config-map
Vind je addons/local/ met je slug erin, dan ben je klaar: die map kopieer je straks naar /addons/<slug>/ op de NUC.

De grote vraag is waarmee je nu naar de kaart kijkt, want dat bepaalt of je überhaupt bij hassos-data kunt:

Windows → je hebt een tool nodig die ext4 leest, bijvoorbeeld "Linux File Systems for Windows" (Paragon) of DiskInternals Linux Reader. Of je gebruikt WSL.
macOS → ext4 lukt niet zonder extra software (bv. een extFS-tool); een Linux live-USB is vaak makkelijker.
Linux → je kunt de partitie gewoon mounten, geen extra software nodig.
Op welk systeem steek je de kaart nu in? Dan zeg ik je precies hoe je bij die hassos-data-partitie komt.

1782241956739_image.png
gevonden, maar het zag er eerder zo uit, zie screenshot

23 jun

Geverifieerd maplocatie en overwogen installatieproces
Geverifieerd maplocatie en overwogen installatieproces
Dat is precies de juiste map — gevonden dus. En geen zorgen over het verschil: ik noemde het addons, jij ziet apps. Dat is hetzelfde ding. Home Assistant is bezig "add-ons" overal te hernoemen naar "apps", en in recente versies is die naam ook op schijf doorgevoerd (supervisor/apps/local/ in plaats van supervisor/addons/local/). Functioneel identiek: dit is de map waar de bron van je lokale add-on hoort te staan.

Doe nu eerst dit, vóór je iets kopieert: open portfolio_tracker en controleer of je bestanden er echt allemaal in zitten. Je zou minstens moeten zien:

config.yaml
Dockerfile
run.sh
database.py, market_data.py, belgian_tax.py, scheduler.py (en je hoofd-Streamlit-bestand)
de map .streamlit/ met config.toml (let op: bestanden/mappen die met een punt beginnen zijn soms verborgen — zet "verborgen items tonen" aan in je bestandsbeheerder)
Zitten die erin, dan is je broncode compleet gered en is de rest puur een kwestie van overzetten.

De hele map veiligstellen. Kopieer portfolio_tracker nu meteen naar een veilige plek — je PC of een USB-stick. Dan heb je sowieso een kopie, los van de SD-kaart.

Daarna op de NUC plaatsen. De makkelijkste route is via de Samba share- of File editor-add-on op de NUC: in beide verschijnt de lokale add-on-map als de share addons (of apps, afhankelijk van je versie). Daar plak je de hele portfolio_tracker-map in. Via de terminal kan ook — dan kopieer je hem naar het equivalente pad onder /mnt/data/supervisor/apps/local/ op de NUC. Vervolgens:

ha store reload
en je add-on verschijnt weer in de store, klaar om te installeren. Omdat je database al op z'n plek staat in /share/portfolio_tracker, pikt hij die bij de eerste start meteen weer op — geen dataverlies, geen herconfiguratie.

Kun je bevestigen dat de bestanden in portfolio_tracker zitten? Zodra dat klopt, loop ik met je de overzet-stap op de NUC door. En daarna zou ik echt even tien minuten nemen om die map in een git-repo te zetten — dan is dit de laatste keer dat een verhuizing je dit lapt.

ik heb nu nog een andere probleem, want met diskinternals linux reader, slaag ik er niet in om de kaart te lezen

23 jun

Weighed SD card reading obstacles en prioritized Pi-boot solution
Weighed SD card reading obstacles en prioritized Pi-boot solution
Vervelend, maar hier heb je waarschijnlijk een veel simpelere uitweg die je het ext4-gedoe op Windows helemaal bespaart.

De makkelijkste route: laat de Pi zelf de kaart lezen. Je Pi-hardware bestaat nog en die leest z'n eigen ext4-partitie moeiteloos — geen enkele Windows-tool nodig. Steek de SD-kaart terug in de Pi, zet hem aan, en haal portfolio_tracker er via het netwerk af met de Samba share- of File editor-add-on (of via SSH met scp). Dat is verreweg het meest betrouwbaar. Eén kanttekening: twee HA-installaties tegelijk op je netwerk kan kleine naam/IP-botsingen geven, dus zet desnoods de NUC even uit terwijl je de Pi gebruikt; voor een snelle bestandskopie maakt het verder niet uit. Daarna zet je de Pi weer uit en ben je klaar.

Als de Pi om een of andere reden geen optie is en je toch via de P

Claude's response was interrupted.
vergeet mijn laatste opmerking, het is net gelukt. Ik ga nu alls naar github overzetten

23 jun
Mooi, dan ben je over het moeilijkste deel heen — bron gered, database intact. En je gaat meteen de juiste les toepassen door alles naar GitHub te zetten; daarmee maak je deze hele ellende structureel onmogelijk voor de toekomst.

Een paar dingen om het meteen goed te doen:

Secrets eruit houden. Het allerbelangrijkste vóór je iets pusht: zorg dat je OpenAI-key (en eventuele andere geheimen) nergens hardcoded in je bestanden staan. Voeg een .gitignore toe en check je code even na. Een redelijke start voor dit project:

__pycache__/
*.pyc
*.db
*.sqlite
*.sqlite3
.streamlit/secrets.toml
.env
.DS_Store
Je database hoort sowieso níét in git — die leeft in /share op de NUC. Mocht je per ongeluk ooit een .db of een key gecommit hebben, laat het me weten; dan helpen we die uit de geschiedenis verwijderen (een gelekte key in git-historie blijft zichtbaar, ook na een latere commit, dus die moet je dan ook bij OpenAI intrekken en vernieuwen).

Key netjes via add-on-config. De schone manier is je key niet in code maar als add-on-optie doorgeven. In config.yaml zet je iets als:

yaml
options:
  openai_api_key: ""
schema:
  openai_api_key: str
Dan vul je hem in via het Configuratie-tabblad van de add-on in HA, en lees je hem in je code uit /data/options.json. Zo staat je key alleen op je eigen machine en nooit in de repo.

Repo als HA-store-repository toevoegen. Zodra het op GitHub staat, voeg je in HA de repo-URL toe via Store → ⋮ → Repositories. Dan is je add-on geen "lokale" add-on meer maar een repo-add-on, en die worden bij back-up/restore wél correct meegenomen en herbouwd voor de juiste architectuur. Hou er rekening mee: HA verwacht de add-on in een submap van de repo (bijv. portfolio_tracker/config.yaml), niet los in de root, en een repository.yaml in de root helpt. Een publieke repo werkt het eenvoudigst; voor een private repo moet je auth regelen.

Loop je bij het opzetten ergens tegenaan — .gitignore, de mapstructuur voor een HA-repo, of het ombouwen van je key naar options.json — zeg het maar, dan help ik gericht.

github desktop zegt het volgende: "This diff contains a change in line endings from 'LF' to 'CRLF'"

23 jun

Analyseerde line-ending probleem en formuleerde configuratieoplossing
Analyseerde line-ending probleem en formuleerde configuratieoplossing
Dat is op zichzelf een onschuldig ogende waarschuwing, maar voor jóuw project moet je hem serieus nemen — niet zomaar doorklikken. De reden zit in één bestand: run.sh.

Wat er gebeurt: je bestanden zijn op de Pi/Linux gemaakt en hebben dus Unix-regeleindes (LF). Nu je ze op Windows aanraakt, wil Git ze omzetten naar Windows-regeleindes (CRLF). Voor je Python-bestanden maakt dat niets uit, maar een shellscript met CRLF breekt in de Docker-container. Je krijgt dan precies het soort cryptische fout dat je eerder al hebt doorworsteld — iets als /bin/bash^M: bad interpreter of een add-on die meteen crasht bij het starten. Ook je Dockerfile kun je beter op LF houden.

De robuuste oplossing is een .gitattributes-bestand in de root van je repo. Dat dwingt de juiste regeleindes af, ongeacht op welke machine je later werkt of wie de repo cloont — het reist mee in de repo zelf. Maak dit bestand aan:

# Forceer LF op alles wat op Linux moet draaien
* text=auto eol=lf
*.sh    text eol=lf
*.py    text eol=lf
*.yaml  text eol=lf
*.yml   text eol=lf
*.toml  text eol=lf
Dockerfile text eol=lf
Daarna moet je de al-omgezette bestanden terugnormaliseren naar LF. Open in GitHub Desktop het menu Repository → Open in Command Prompt (of een terminal in je repo-map) en draai:

git add --renormalize .
git commit -m "Normaliseer regeleindes naar LF"
--renormalize herschrijft alle bestanden volgens je nieuwe .gitattributes, zodat wat je commit gegarandeerd LF is.

Optioneel, als extra vangnet, zet je Git's autoconversie op Windows uit:

git config --global core.autocrlf false
.gitattributes overschrijft die instelling toch al per repo, maar zo voorkom je verrassingen in andere projecten.

Eén controle achteraf die het waard is: nadat je dit gepusht hebt en straks de add-on op de NUC herbouwt, even checken dat run.sh daadwerkelijk start. Als de container netjes opkomt, weet je dat je regeleindes goed staan. Doe je het nu meteen goed met die .gitattributes, dan is dit geen issue meer.

ik krijg dit als fout in de desktop omgeving: ''git' is not recognized as an internal or external command,
operable program or batch file.'

23 jun

Analyseerde Git PATH-probleem en overwoog installatieoplossingen
Analyseerde Git PATH-probleem en overwoog installatieoplossingen
Logisch, en het ligt niet aan jou: GitHub Desktop heeft z'n eigen git ingebakken voor intern gebruik, maar zet die niet op het systeem-PATH. Daardoor weet een gewone opdrachtprompt niet waar git staat. De oplossing is git als losse tool installeren — dat heb je voor dit project toch nodig, en daarna werkt git overal, ook in dat command prompt-venster.

Git for Windows installeren. Download het van de officiële bron: git-scm.com/download/win. De installer mag je vrijwel overal op "volgende" doorklikken; twee dingen om op te letten:

Bij "Adjusting your PATH environment" laat je de aanbevolen standaard staan ("Git from the command line and also from 3rd-party software"). Dát is wat git op je PATH zet.
Bij "Configuring the line ending conversions" kies je gerust de standaard — je .gitattributes overschrijft die instelling toch per repo, dus het komt sowieso goed. Wil je extra veilig zijn, kies dan "Checkout as-is, commit as-is".
Je krijgt er meteen Git Bash bij, een prettige terminal die je los kunt openen.

Na de installatie: sluit je huidige command prompt-venster helemaal en open een nieuwe (anders is het oude PATH nog actief en blijft de fout). Open daarna vanuit GitHub Desktop opnieuw Repository → Open in Command Prompt, of klik in je repo-map met rechts → "Open Git Bash here". Test even:

git --version
Krijg je nu een versienummer, dan ben je goed. Vervolgens de twee commando's van daarnet om de regeleindes recht te trekken:

git add --renormalize .
git commit -m "Normaliseer regeleindes naar LF"
Mocht je écht geen extra software willen installeren: je kunt de regeleinde-fix ook omzeilen door run.sh en je Dockerfile in een editor als Notepad++ of VS Code te openen en ze expliciet als LF op te slaan (rechtsonder in de statusbalk kun je CRLF → LF omzetten), waarna je gewoon via de GitHub Desktop-interface commit. Maar git installeren is op termijn handiger, want --renormalize pakt in één klap álle bestanden mee in plaats van handmatig per bestand.

ik heb de commando's uitgevoerd: 
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean

23 jun
Dat is precies wat je wilt zien — geen reden tot zorg. "Nothing to commit, working tree clean" betekent dat er niets meer recht te trekken viel: je bestanden staan al met de juiste regeleindes in de repo. Dat kan twee onschuldige oorzaken hebben: je had de wijzigingen via de GitHub Desktop-interface al gecommit voordat je de commando's draaide, óf je .gitattributes was al actief toen de bestanden voor het eerst werden toegevoegd, zodat er nooit een echte CRLF-conversie in de repo terecht is gekomen.

Hoe dan ook, het komt erop neer dat je niets meer hoeft te doen aan de regeleindes. Even kort verifiëren dat het ook echt goed zit, dan weet je het zeker in plaats van het te hopen:

Staat .gitattributes daadwerkelijk in de repo? Draai:

git ls-files | findstr .gitattributes
Krijg je .gitattributes terug, dan reist de regel mee met je repo en ben je voorgoed beschermd.

Heeft run.sh echt LF? Dit is het bestand dat ertoe doet. Snelste check:

git ls-files --eol run.sh
Je wilt in de uitkomst lf zien staan (kolommen tonen iets als i/lf w/lf). Zie je daar crlf, dan moeten we nog ingrijpen; zie je lf, dan is je add-on veilig om straks op de NUC te herbouwen.

Als beide checks goed zijn, ben je klaar met dit hele hoofdstuk: bron veilig op GitHub, regeleindes correct, database intact op de NUC. De laatste stap is dan de repo als store-repository in HA toevoegen en de add-on opnieuw installeren — laat maar weten wanneer je daaraan toe bent, dan loop ik die met je door.

beide checks zijn OK

23 jun
Perfect — dan staat alles zoals het hoort. Bron veilig op GitHub, .gitattributes doet z'n werk, run.sh heeft LF, en je database staat klaar op de NUC. Daarmee is de schade van de migratie volledig hersteld én heb je meteen de structurele fix te pakken die dit in de toekomst voorkomt.

De laatste stap is de add-on terugzetten op de NUC, nu als repo-add-on in plaats van lokaal. Globaal komt het hierop neer:

1. Repo toevoegen in HA. Ga op de NUC naar Instellingen → Add-ons → Add-on store → ⋮ (rechtsboven) → Repositories, en plak je GitHub-URL (de gewone https://github.com/<jij>/<repo>-link). HA scant de repo en je add-on hoort dan onderaan in de store te verschijnen onder een eigen kopje.

2. Mapstructuur — dé valkuil. HA verwacht je add-on in een submap van de repo, met config.yaml daarin (dus portfolio_tracker/config.yaml), niet los in de root. Verschijnt de add-on niet, dan is dit bijna altijd de oorzaak. Een repository.yaml in de root helpt HA de repo netjes te benoemen:

yaml
name: Mijn HA add-ons
url: https://github.com/<jij>/<repo>
maintainer: <jij>
3. Installeren en configureren. Klik op de add-on → Installeren. Vul daarna op het Configuratie-tabblad je OpenAI-key in (als je die naar options/schema hebt omgebouwd), en controleer dat DATA_DIR nog naar /share/portfolio_tracker wijst. Bij de eerste start pikt hij je bestaande database meteen weer op.

4. Eerste start controleren. Houd bij de eerste keer starten het log van de add-on in de gaten — dat is meteen je bevestiging dat run.sh met de juiste regeleindes draait en dat alles op de NUC-architectuur correct herbouwd is.

Een ding om vooraf te checken: staat in je repo-versie van config.yaml nog version netjes ingevuld, en is image: níét gezet? Bij een lokaal-gebouwde add-on hoort er geen image-veld in te staan, anders probeert HA een kant-en-klare image te trekken in plaats van zelf te bouwen uit je Dockerfile.

Zeg maar wanneer je begint, of als de add-on niet meteen in de store opduikt — dan kijken we direct naar de mapstructuur. Je staat er goed voor.

geeft een foutmelding bij stap 1: https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker.git is not a valid app repository

23 jun

Diagnosed repository structure issue en repository URL format
Diagnosed repository structure issue en repository URL format
Goede foutmelding om te krijgen — die vertelt ons precies wat er mis is. Laat me even in je repo kijken zodat ik geen gokwerk doe.


Weighed fetching options en diagnosticeerde repository-structuurprobleem
Weighed fetching options en diagnosticeerde repository-structuurprobleem
Geen probleem, de foutmelding zelf is al verklarend genoeg. "Is not a valid app repository" betekent dat HA je repo wél kan bereiken, maar er geen geldige add-on-structuur in vindt. Twee dingen zijn bijna altijd de oorzaak, en waarschijnlijk speelt het eerste bij jou:

1. Je bestanden staan los in de root in plaats van in een submap. Dit is dé klassieker. HA verwacht dat elke add-on in een eigen submap zit met daarin config.yaml. Een add-on die los in de root van de repo staat, wordt niet herkend — vandaar de foutmelding. Je structuur moet er zo uitzien:

Homeassistant-portfolio-tracker/   ← repo-root
├── repository.yaml
└── portfolio_tracker/             ← submap = de add-on
    ├── config.yaml
    ├── Dockerfile
    ├── run.sh
    ├── database.py
    ├── market_data.py
    ├── belgian_tax.py
    ├── scheduler.py
    └── .streamlit/
        └── config.toml
Staat alles nu plat in de root (config.yaml, Dockerfile, enz. direct onder de repo)? Dan is dat je probleem. Verplaats alle add-on-bestanden naar een submap portfolio_tracker/, en zet in de root alleen repository.yaml:

yaml
name: Portfolio Tracker add-ons
url: https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker
maintainer: Thedevilinperson
In GitHub Desktop kun je de bestanden lokaal in een nieuwe portfolio_tracker-map slepen, committen en pushen. Let op: je .gitattributes houd je wél in de root.

2. Haal .git van het eind van de URL. Voeg in HA de repo toe als:

https://github.com/Thedevilinperson/Homeassistant-portfolio-tracker
zonder de .git-suffix. Die suffix is voor het clonen via git, niet voor de HA-store, en kan op zichzelf al voor afkeuring zorgen.

Doe beide, klik daarna in HA op vernieuwen, en de add-on hoort onder een eigen kopje in de store te verschijnen.

Wil je dat ik meekijk, dan kun je me vertellen hoe je repo er nu uitziet — staan de bestanden in de root of al in een submap? Dan bevestig ik meteen of dit de fix is of dat er nog iets anders speelt.

hoe maak ik een nieuwe folder in de webversie van github?

23 jun
In de webversie van GitHub kun je niet rechtstreeks een lege map aanmaken — GitHub bewaart geen lege mappen. De truc is dat je een map "maakt" door in het pad van een bestand een / te typen; GitHub maakt de map dan automatisch aan rondom dat bestand. Zo doe je dat:

Ga naar je repo en klik bovenaan op Add file → Create new file.
In het naamveld bovenaan typ je eerst de mapnaam, dan een schuine streep, dan een bestandsnaam. Dus bijvoorbeeld:
   portfolio_tracker/config.yaml
Zodra je die / typt, zie je portfolio_tracker als map verschijnen en config.yaml als bestand erin.
3. Plak de inhoud van het bestand eronder, scroll naar beneden en klik op Commit changes.

Daarmee heb je in één keer de map én het eerste bestand erin.

Voor jouw situatie is dit alleen wat omslachtig, want je hebt al een hele set bestanden die nu in de root staan en die je naar portfolio_tracker/ moet verplaatsen. Twee snellere routes dan elk bestand handmatig overtypen:

Bestaande bestanden verplaatsen via de web-editor. Open een bestand dat in de root staat, klik op het potlood-icoon (Edit), en zet in het naamveld bovenaan portfolio_tracker/ vóór de bestandsnaam (bijv. van config.yaml naar portfolio_tracker/config.yaml). Bij het committen verplaatst GitHub het bestand naar de nieuwe map. Dit moet je per bestand herhalen — bij een handvol bestanden te doen, maar bewerkelijk.

Veel makkelijker: doe het lokaal in GitHub Desktop. Je hebt de bestanden toch al lokaal staan. Maak in Verkenner een map portfolio_tracker in je repo-map, sleep alle add-on-bestanden daarin (dus alles behalve .gitattributes en straks repository.yaml, die in de root blijven), en commit + push via GitHub Desktop. Eén handeling in plaats van bestand-voor-bestand klikken in de browser. Git ziet dit netjes als een verplaatsing.

Gezien je alles al lokaal hebt, raad ik de Desktop-route aan — sneller en minder foutgevoelig. Wil je liever toch volledig in de browser blijven werken, dan loop ik de per-bestand-methode met je door.

stap 1 was de juiste stap: de folder structuur

23 jun
Mooi, dat was 'm dus — de submap-structuur was het hele probleem. Goed gevonden.

Dan zou je add-on nu in de store moeten opduiken onder een eigen kopje. Vanaf hier zijn het nog een paar laatste stappen tot je weer draait op de NUC:

Installeren. Klik de add-on aan in de store en installeer hem. Bij de eerste keer bouwt HA de Docker-image lokaal uit je Dockerfile — dat duurt op een NUC een paar minuten. Verschijnt hij nog niet meteen, klik dan even op vernieuwen in de store (rechtsboven ⋮ → vernieuwen).
Configureren. Vul op het Configuratie-tabblad je OpenAI-key in, en controleer dat DATA_DIR naar /share/portfolio_tracker wijst zodat hij je bestaande database terugvindt.
Eerste start + log. Start de add-on en houd het log in de gaten. Dat is je bevestiging dat alles klopt: dat run.sh met de juiste regeleindes draait, dat de image goed gebouwd is voor de NUC-architectuur, en dat je database wordt opgepikt.
Als de eerste start schoon door komt, ben je helemaal terug — en deze keer met je bron veilig op GitHub, zodat een toekomstige verhuizing of restore je dit niet meer kan flikken.

Zeg maar hoe de installatie en eerste start verlopen. Loopt er iets vast in het log, plak het hier dan, dan kijken we er meteen naar.

Er zijn nog een paar wijzigingen die ik zou willen doorvoeren aan de code: 
1) bij elke transactie moet het mogelijk zijn om kosten toe te voegen in een munt naar keuze
2) ik zou graag kunnen filteren in het overzicht van de portfeuille en in het dashboard op oorsprong van de aandelen: ik heb namelijk 3 verschillende rekeningen waar die op staan
3) ik zou graag blad zien waarin een evolutie van de waarde te zien is en waar ook een vergelijking in procentuele wijziging van de portefeuille-waarde zichtbaar is tussen de verschillende bronnen. Deze wijziging bekijkt de meer- of minwaarde die geboekt wordt ten opzichte van de aangekochte prijs en dus niet het absolute resultaat

23 jun

Geanalyseerd drie functionaliteiten en overwogen codebase-benadering
Geanalyseerd drie functionaliteiten en overwogen codebase-benadering
Goede uitbreidingen — alle drie zinnig voor een serieuze portfolio-tracker. Voor ik code ga schrijven wil ik eerst je actuele code lezen, zodat de wijzigingen precies op je bestaande schema en structuur passen en ik niets kapotmaak. Je repo staat nu publiek op GitHub, dus laat me die ophalen.


Analyseerde codebase en formuleerde implementatieplan met architectuurvragen
Analyseerde codebase en formuleerde implementatieplan met architectuurvragen
Ik heb je hele codebase doorgenomen — database.py, market_data.py, belgian_tax.py en de volledige app.py. Ik snap nu hoe alles in elkaar zit: FIFO draait in build_fifo_positions, transacties hebben nu ticker / type / datum / aantal / prijs / totaal / munt / tob_tax / notes, en de pagina's lezen alles via calculate_tax_overview. Goed nieuws: alle drie je wensen passen netjes in deze structuur. Hieronder mijn plan per onderdeel, met de keuzes die ik standaard zou maken.

2) Filteren op rekening/oorsprong (dit is het fundament, dus ik begin ermee)
Ik voeg een account-kolom toe aan transactions. Belangrijk voor de correctheid: FIFO moet dan per (ticker, rekening) rekenen — een verkoop op rekening A mag geen aankooploten van rekening B opeten, anders klopt je kostenbasis en je meerwaarde niet. Je rekeningnamen beheer je in Instellingen (een lijstje), en op het transactieformulier kies je er één uit een dropdown. In Portefeuille én Dashboard komt er een filter "Rekening: Alle / A / B / C". Bestaande transacties krijgen automatisch een rekening "Niet toegewezen" die je daarna per stuk kunt aanpassen.

1) Kosten in een munt naar keuze per transactie
Twee nieuwe velden: costs en costs_currency. Mijn standaardkeuze fiscaal: aankoopkosten verhogen de kostenbasis, verkoopkosten verlagen de opbrengst — zo verlagen ze je belastbare meerwaarde. Dat is de gangbare en voor jou voordeligste behandeling (al blijft het "schatting — check een fiscalist", zoals je pagina al netjes vermeldt).

3) Nieuwe pagina: waarde-evolutie + %-vergelijking tussen rekeningen
Voor de evolutie reconstrueer ik de portefeuillewaarde over tijd uit je transactiehistoriek × historische dagkoersen (yfinance levert die), zodat je meteen geschiedenis ziet i.p.v. te moeten wachten tot er snapshots opbouwen. De %-vergelijking toont per rekening (huidige waarde − kostenbasis) / kostenbasis, dus exact de procentuele meer-/minwaarde t.o.v. aankoopprijs die je beschrijft, niet het absolute resultaat.

Eén ding dat ik moet voorleggen vóór ik 1 en 3 bouw, want het bepaalt of de cijfers kloppen: je app rekent op dit moment niet om naar EUR. total_amount en de huidige waarde blijven in de munt van het aandeel, en de totalen worden gewoon opgeteld. Voor je Euronext-posities geen probleem, maar voor je NYSE/NASDAQ-posities in USD zijn de EUR-totalen en straks de %-vergelijking tussen rekeningen vertekend. Daarom de vraag:

Q: Hoe wil je met munten omgaan? (Nu telt de app USD en EUR ongewijzigd bij elkaar op.)
A: Reken alles om naar EUR (correcter, vooral voor je USD-posities)

Q: Hoe moeten transactiekosten meetellen in de belasting?
A: Apart bijhouden, niet in de meerwaardeberekening

23 jun

Architected multi-currency refactor met per-account FIFO-tracking
Architected multi-currency refactor met per-account FIFO-tracking
Top — duidelijke keuzes. Dan ga ik het zo bouwen:

Alles in EUR: bedragen worden bij het invoeren omgerekend met de wisselkoers op de transactiedatum, en huidige waarden met de actuele koers. Je bestaande transacties reken ik achteraf om (knop in Instellingen, met historische koersen).
Kosten apart: nieuw veld kosten + munt, omgerekend naar EUR, maar buiten de meerwaardeberekening — puur als zichtbare "drag" op je rendement.
Rekeningen: per (ticker, rekening) FIFO, beheerbare rekeningenlijst, filters op Dashboard en Portefeuille.
Nieuwe pagina met waarde-evolutie en %-vergelijking per rekening.
Laat me het bouwen en de logica meteen testen met een tijdelijke database.


Deliberating over yfinance installation feasibility
Deliberating over yfinance installation feasibility
Nu de logica testen met een tijdelijke database en nagebootste koersen, vóór ik de UI aanpas.


App.py aanpassen: valutaconversie en EUR-weergave implementeren
App.py aanpassen: valutaconversie en EUR-weergave implementeren
Kernlogica klopt. Nu de historische reconstructie testen met synthetische koersreeksen.


Verfijning van KPI-rij met kostenmetriek toevoegen
Verfijning van KPI-rij met kostenmetriek toevoegen
Backend is volledig getest en correct. Nu de UI (app.py) aanpassen — gericht, met behoud van alles wat al werkt. Ik begin met de hulpfuncties en het gefilterde overzicht.


Reorganiseerde dashboard-metriek rij met kostenkolom
Reorganiseerde dashboard-metriek rij met kostenkolom
Nu de Portefeuille-pagina met rekeningfilter:


Refined portfolio table labels voor duidelijkheid
Refined portfolio table labels voor duidelijkheid
Nu het transactieformulier — rekening, kosten in eigen munt, en EUR-omrekening bij opslaan:


Restructureerde transactieoverzicht met rekeningfilter en kosten
Restructureerde transactieoverzicht met rekeningfilter en kosten
Nu het transactie-overzicht — filter op rekening, kosten tonen, en rekening per transactie kunnen aanpassen:


Refactored dividend submission logic to convert currencies to EUR
Refactored dividend submission logic to convert currencies to EUR
Dividenden omrekenen naar EUR bij opslaan:


Architected account management tab en EUR-backfill functionaliteit
Architected account management tab en EUR-backfill functionaliteit
Settings uitbreiden: rekeningbeheer en een EUR-herbereken-knop. Eerst een kleine helper in database.py voor dividend-omrekening:


Architectureren van Evolution-pagina met filters en datumbereik
Architectureren van Evolution-pagina met filters en datumbereik
Nu de backfill_eur-helper en het rekeningbeheer in app.py:


Architected portfolio evolution page met caching en meervaluta-conversie
Architected portfolio evolution page met caching en meervaluta-conversie
Nu de nieuwe Evolutie-pagina met waarde-evolutie en %-vergelijking per rekening:


Diagnosing importmodule execution en streamlitscriptuitvoering
Diagnosing importmodule execution en streamlitscriptuitvoering
Nu de pagina registreren in de navigatie:


Ontrafelen van API-inconsistenties tussen OpenAI en Anthropic
Ontrafelen van API-inconsistenties tussen OpenAI en Anthropic
App compileert. Laat me controleren of alle imports kloppen en doe een gerichte importtest van de gewijzigde modules samen.


Orchestreren van importtests en stubben van dependencies
Orchestreren van importtests en stubben van dependencies
De AI-advisor leest openai_api_key, maar de Instellingen-tab en de AI-pagina verwijzen nog naar je oude Anthropic-sleutel — daardoor kun je de OpenAI-key nu niet via de app instellen. Dat is een kleine, veilige coherentie-fix die ik meteen meeneem.


Diagnosing waarom page_evolution-functie niet gedefinieerd is
Diagnosing waarom page_evolution-functie niet gedefinieerd is
Laat me een importtest doen met lichte stubs voor de externe libs, zodat ik runtime-naamfouten in de volledige module opspoor (niet alleen syntax).


Diagnosing verloren inhoud en vervangen regels
Diagnosing verloren inhoud en vervangen regels
De grote invoeging van page_evolution is niet correct geland (de vorige tool-call was misvormd). Laat me de zone vóór de PAGES-dict bekijken.


Orchestrated code insertion to restore lost function definitions
Orchestrated code insertion to restore lost function definitions
De functie ontbreekt. Ik voeg page_evolution + _evolution_df nu correct in, vlak vóór de PAGES-dict.


Page_evolution en _evolution_df correct invoegen vóór de PAGES-dict
Page_evolution en _evolution_df correct invoegen vóór de PAGES-dict
kan je verder gaan waar je gisteren gestopt ben?

06:50

Hervattte implementatie en verificeerde vorige werkstand
Hervattte implementatie en verificeerde vorige werkstand
Ja — ik was net klaar met het invoegen van de page_evolution-functie. Laat me verifiëren dat alles nu compileert en de importtest doorstaat, en daarna lever ik de bestanden.


Finaliserend vier bestanden naar outputs verzenden
Finaliserend vier bestanden naar outputs verzenden
Module laadt nu volledig zonder fouten. Laat me de logica-tests nog eens draaien als eindcontrole, en dan lever ik op.


Verificeerde tests en bereidde vier bestanden voor levering voor
Verificeerde tests en bereidde vier bestanden voor levering voor
Alles geslaagd. Eén laatste check: of scheduler.py (die op de achtergrond draait) nog compatibel is met de aangepaste functies.


Geverifieerd compatibiliteit en voorbereiding voor verdere implementatie
Geverifieerd compatibiliteit en voorbereiding voor verdere implementatie
Klaar — alle drie de features zijn gebouwd, getest en de vier bestanden staan hierboven klaar. Ze vervangen de bestaande in de map portfolio_tracker/ van je repo.

Wat er gewijzigd is

Rekeningen (oorsprong). FIFO rekent nu per (ticker, rekening): een verkoop op Bolero raakt je Degiro-loten niet aan. Je beheert je rekeningen via ⚙️ Instellingen → 🏦 Rekeningen, kiest er één bij elke transactie, en filtert erop in het Dashboard en de Portefeuille. De belastingberekening blijft bewust globaal — de €10.000-vrijstelling geldt per persoon, niet per rekening.

Kosten in een munt naar keuze. Elk transactieformulier heeft nu een kostenveld met eigen muntkeuze. De kosten worden naar EUR omgerekend en apart bijgehouden als zichtbare "drag" (KPI op het Dashboard + per transactie), maar tellen niet mee in de meerwaardeberekening, precies zoals je wou.

Alles in EUR. Bedragen worden bij het invoeren omgerekend met de wisselkoers op de transactiedatum; huidige waarden met de actuele koers. Dit corrigeert de oude situatie waarin USD en EUR nominaal werden opgeteld.

Nieuwe pagina 📈 Evolutie. Waarde-evolutie in EUR (per rekening + totaal), een lijn met de procentuele meer-/minwaarde t.o.v. aankoopprijs per rekening over tijd, en een momentopname-vergelijking. De historiek wordt gereconstrueerd uit je transacties × historische dagkoersen, dus je ziet meteen geschiedenis.

Bonus. De Instellingen- en AI-pagina verwezen nog naar je oude Anthropic-sleutel terwijl de advisor al OpenAI gebruikt — die heb ik gelijkgetrokken (OpenAI-sleutel + modelkeuze), zodat je de key weer via de app kunt instellen.

Belangrijk na het deployen — twee eenmalige stappen:

Ga naar ⚙️ Instellingen → 🏦 Rekeningen en voer je drie rekeningnamen in. Wijs daarna je bestaande transacties toe via het dropdownmenu in het transactie-overzicht (ze staan nu op "Niet toegewezen").
Ga naar ⚙️ Instellingen → 🗃️ Data → 💱 Herbereken EUR-bedragen om je bestaande (vooral USD) transacties met de historische koers naar EUR om te zetten.
Het schema migreert automatisch bij de eerste start (nieuwe kolommen worden idempotent toegevoegd), dus je database in /share/portfolio_tracker blijft behouden. Eén aandachtspunt: de evolutie- en omrekenfuncties halen historische koersen op via yfinance, wat soms traag of onvolledig kan zijn voor exotische tickers — de code valt dan netjes terug op de actuele koers.

Zal ik er een korte changelog bij schrijven voor je commit message, of wil je eerst nog iets aanpassen aan de Evolutie-pagina?


App
PY 

Database
PY 

Belgian tax
PY 

Market data
PY 
je haalt nog een belangrijk punt aan: wij zijn getrouwd in gemeenschap van goederen en de effectenrekeningen zijn van ons beiden (1 van mijn vrouw en 2 van mij bv.). dit heeft effect op de meerwaardebelasting dacht ik? Kan je dit mee integreren in de applicatie als instelling?

06:54

Onderzocht Belgische belastingwetgeving en overwoog functionaliteit voor meerdere belastingplichtigen
Onderzocht Belgische belastingwetgeving en overwoog functionaliteit voor meerdere belastingplichtigen
Goed punt — en ja, dat kan wel degelijk fiscaal uitmaken. Maar dit is een vrij specifiek punt over een gloednieuwe regeling, dus ik wil het even verifiëren met actuele bronnen voordat ik er belastinglogica op bouw.


Ontleed belastingregels en plannen implementatie dubbele vrijstelling
Ontleed belastingregels en plannen implementatie dubbele vrijstelling
Goed dat je dit aankaart — en je herinnert het je correct. Ik heb het geverifieerd bij o.a. FOD Financiën en verschillende banken, en het is eenduidig.

De kern: de vrijstelling van €10.000 geldt per persoon, niet per beleggingsrekening. Ben je gehuwd onder een gemeenschapsstelsel, dan hebben jij én je echtgeno(o)t(e) elk recht op de vrijstelling, ook als de effectenrekening op naam van één van beiden staat. Voor een koppel in gemeenschap van goederen komt dat dus neer op €20.000 vrijstelling per jaar samen (en tot €30.000 als je ongebruikte stukken vijf jaar lang opbouwt). 
Bolero + 2

Belangrijk gevolg voor jouw vraag: omdat alle drie de rekeningen tot het gemeenschappelijk vermogen behoren, maakt het voor de belasting niet uit op wiens naam ze staan — wat telt is dat jullie sámen twee vrijstellingen hebben. Het juiste model is dus: de gezamenlijke meerwaarde verminderen met een dubbele vrijstelling. Dat ga ik als instelling toevoegen.

Laat me dat inbouwen.


Navigeerde naar instellingen voor meerwaardebelasting-configuratie
Navigeerde naar instellingen voor meerwaardebelasting-configuratie
Nu de instelling in de UI. Eerst de Meerwaardebelasting-tab in Instellingen:


Plannen om belastingregime en gemeenschappelijke goederen in te integreren
Plannen om belastingregime en gemeenschappelijke goederen in te integreren
Nu de Belgische-Belasting-pagina regime-bewust maken (correcte uitleg bij de vrijstelling):


Valideren van logica en herleveren van bijgewerkte bestanden
Valideren van logica en herleveren van bijgewerkte bestanden
Nu testen en compileren:


Gevalideerd belastinglogica en bereide geüpdatete bestanden voor levering
Gevalideerd belastinglogica en bereide geüpdatete bestanden voor levering
Ingebouwd en getest. Deze drie bestanden vervangen die van de vorige levering; market_data.py blijft ongewijzigd.

Wat er nu in zit: in ⚙️ Instellingen → 🧾 Meerwaardebelasting kies je je belastingsituatie — "Alleenstaand" (1× vrijstelling) of "Gehuwd/wettelijk samenwonend, gemeenschap van goederen" (2× vrijstelling). Bij de tweede optie verdubbelt de effectieve vrijstelling automatisch in alle berekeningen (Dashboard, Belasting-pagina, voortgangsbalk), met een uitleg erbij dat elke partner een eigen vrijstelling heeft, ook voor een rekening op naam van één van beiden.

De testcase laat het effect mooi zien: bij €15.000 gerealiseerde meerwaarde betaal je als alleenstaande €500, maar als koppel in gemeenschap van goederen €0 — want jullie €20.000 vrijstelling dekt de volledige winst.

Twee zaken om eerlijk bij te vermelden:

De berekening gaat uit van een gelijke 50/50-toerekening van de meerwaarde aan beide partners. Dat is de logische standaard voor gemeenschappelijk vermogen en geeft samen €20.000 vrijstelling. Wat de app (bewust) niet doet, is per partner bijhouden of iemand zijn eigen €10.000 al elders heeft opgebruikt, of de opbouw van ongebruikte vrijstelling over 5 jaar tot €30.000 — dat zou een meerjarige, per-persoon administratie vergen. Voor een momentopname van je jaarlijkse positie klopt het model.

En zoals de app al netjes aangeeft: het blijft een schatting. De vrijstelling moet je sowieso zelf aanvragen via je aangifte in de personenbelasting — de broker houdt bij een opt-in gewoon 10% in en je vordert het vrijgestelde deel terug via je aangifte. 
FOD Financiën

Wil je dat ik ook de meerjarige opbouw van de vrijstelling (de €1.000/jaar overdracht tot €15.000 p.p.) modelleer, of laten we het bij deze jaarlijkse benadering?


App
PY 

Belgian tax
PY 

Database
PY 
Ja graag de meerjarige opbouw mee verwerken.
Een tweede vraag: als ik dit update in Github, wordt dit dan automatisch als een nieuwe versie gezien in homeasisstant of moet daar nog iets extra voor gebeuren?

07:00

Implementeren van meerjarige belastingopbouw aanpakken
Implementeren van meerjarige belastingopbouw aanpakken
Allebei goede punten. Eerst je GitHub/Home Assistant-vraag, dan de meerjarige opbouw.

Wordt een GitHub-update automatisch opgepikt door Home Assistant?

Nee, niet automatisch — en dit is precies waar je vorige keer op vastliep. HA kijkt naar het version-veld in config.yaml, niet naar de git-commits zelf. Als je code pusht zonder dat versienummer te verhogen, blijft HA denken dat er niets veranderd is en draait het de oude gebouwde image verder. Je moet dus:

Verhoog version: in config.yaml (bv. van 1.2.0 → 1.3.0). Dit is wat HA gebruikt om een update te detecteren.
In HA: Instellingen → Add-ons → Add-on Store → ⋮ (rechtsboven) → "Check for updates" (of de repository herladen). Daarna verschijnt de Update-knop bij je add-on.
Omdat het een lokaal gebouwde add-on is (geen image:-veld), kan Docker-layercaching nog roet in het eten gooien. Na het updaten doe je daarom best "Herbouwen" (Rebuild) om een schone build te forceren — net zoals eerder de betrouwbare fix was.
Kort: pushen alleen is niet genoeg; versienummer bumpen + repo herladen + eventueel herbouwen. Laat me even je huidige versie checken zodat ik kan zeggen waarnaar te bumpen.


Herstructurering van belastingfuncties en ledger-integratie voorbereidend
Herstructurering van belastingfuncties en ledger-integratie voorbereidend
Je staat op 1.0.1, en er is geen image:-veld (goed — lokaal gebouwd). Bump dit naar bijvoorbeeld 1.1.0 voor deze feature-release.

Nu de meerjarige opbouw van de vrijstelling. Laat me de regels even precies modelleren — dit is verrassend subtiel.


UI-breakdown bijwerken en metrische captions verfijnen
UI-breakdown bijwerken en metrische captions verfijnen
Nu grondig testen — inclusief het lastige Bolero-voorbeeld (overdracht van restsaldo):


Herstructureerde UI-componenten voor meerjarige vrijstellingsopbouw weergave
Herstructureerde UI-componenten voor meerjarige vrijstellingsopbouw weergave
Logica klopt exact met het officiële voorbeeld. Nu de Belasting-pagina zodat de opbouw zichtbaar wordt:


Herbevestigend welke bestanden aangepast zijn
Herbevestigend welke bestanden aangepast zijn
Nu een korte toelichting in de Instellingen en dan compileren + testen:


Verified tests en bepaalde welke bestanden opnieuw aan te leveren
Verified tests en bepaalde welke bestanden opnieuw aan te leveren
Alles slaagt. Laat me de twee gewijzigde bestanden opnieuw leveren.


Ran a command, read a file
Ran a command, read a file
De meerjarige opbouw zit erin. Deze twee bestanden vervangen die van net; database.py en market_data.py blijven zoals in de vorige levering.

Wat het nu doet. De app berekent automatisch je opgebouwde vrijstelling uit je transactiegeschiedenis vanaf 2026: in jaren waarin je de eerste schijf van €1.000 niet (volledig) benut, wordt het ongebruikte deel overgedragen, maximaal €1.000 per jaar, tot 5 jaar lang, met een plafond van €15.000 per persoon (dus €30.000 voor jullie als koppel). De overgedragen vrijstelling wordt — conform de wet — eerst aangesproken, vóór de basis van €10.000. Op de Belasting-pagina zie je de vrijstelling nu uitgesplitst in "basis" + "opgebouwde overdracht".

Ik heb het getest tegen het officiële voorbeeld van Bolero/FOD Financiën (geen winst in 2026, €100 in 2027 → €11.900 vrijstelling in 2028, inclusief het €900-restsaldo) en dat klopt exact, net als het plafond op €15.000 en de verdubbeling voor een koppel.

Twee eerlijke kanttekeningen: de opbouw start bij het latere van 2026 of je eerste transactiejaar, en gaat uit van die 50/50-verdeling tussen partners. Indexatie van de €10.000/€1.000-bedragen modelleer ik niet — als die bedragen in latere jaren stijgen, pas je gewoon de basisvrijstelling in Instellingen aan.

Voor je deploy, even samengevat: zet de vier (eigenlijk nu: alle gewijzigde) bestanden in portfolio_tracker/, bump version in config.yaml van 1.0.1 naar 1.1.0, push naar GitHub, herlaad in HA de add-on store ("Check for updates"), klik Update, en doe daarna een Herbouwen als de wijzigingen niet meteen zichtbaar zijn. Vergeet na de eerste start de twee eenmalige stappen niet: rekeningen toewijzen en "Herbereken EUR-bedragen" in Instellingen.

Wil je dat ik een beknopte changelog/commit message schrijf voor deze release?


Belgian tax
PY 

App
PY 

Claude Fable 5 is currently unavailable.
Learn more(opens in new tab)





Claude is AI and can make mistakes. Please double-check responses.
App · PY
"""
app.py — Portfolio Tracker — Streamlit hoofdapplicatie
Belgische beleggingsportefeuille met belastingtracking en AI-advies.
"""
from __future__ import annotations
 
from datetime import date, datetime
 
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
 
import ai_advisor
import belgian_tax as tax_mod
import database as db
import market_data as md
 
# ── Pagina-configuratie ───────────────────────────────────────────────────────
 
st.set_page_config(
    page_title="Portfolio Tracker 🇧🇪",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
 
st.markdown("""
<style>
div[data-testid="metric-container"] {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 0.8rem 1rem;
}
div[data-testid="stDataFrame"] { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)
 
# ── Database initialiseren ────────────────────────────────────────────────────
db.init_db()
 
# ── Hulpfuncties ──────────────────────────────────────────────────────────────
 
def eur(val: float | None, decimals: int = 2) -> str:
    if val is None:
        return "—"
    return f"€{val:,.{decimals}f}"
 
 
def pct(val: float | None) -> str:
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"
 
 
def sign_icon(val: float | None) -> str:
    if val is None:
        return "⚪"
    return "🟢" if val >= 0 else "🔴"
 
 
def delta_color(val: float | None) -> str:
    if val is None or val == 0:
        return "off"
    return "normal" if val >= 0 else "inverse"
 
 
@st.cache_data(ttl=60, show_spinner=False)
def get_overview(year: int, account: str | None = None) -> dict:
    """Gecachte portfolioverzicht (60 s TTL). account=None -> alle rekeningen."""
    assets = db.get_assets()
    tickers = [a["ticker"] for a in assets]
    prices = md.get_prices_for_tickers(tickers)
    overview = tax_mod.calculate_tax_overview(year=year, current_prices=prices,
                                              account=account)
    return overview, assets, prices
 
 
def clear_cache():
    get_overview.clear()
 
 
def compute_eur(amount: float, currency: str, date_str: str) -> tuple[float, float]:
    """(fx_rate, eur_bedrag) op transactiedatum. Valt terug op 1.0 bij EUR/fout."""
    if not amount or currency == "EUR":
        return 1.0, float(amount or 0.0)
    rate = md.get_historical_exchange_rate(currency, str(date_str), "EUR") or 1.0
    return rate, float(amount) * rate
 
 
def account_filter_widget(key: str) -> str | None:
    """Dropdown 'Alle rekeningen' + gedefinieerde rekeningen. None = alle."""
    opts = ["📂 Alle rekeningen"] + db.get_accounts()
    sel = st.selectbox("Rekening", opts, key=key)
    return None if sel.startswith("📂") else sel
 
 
def backfill_eur(force: bool = False) -> int:
    """Reken bestaande transacties + dividenden om naar EUR (historische koers)."""
    n = 0
    for t in db.get_transactions():
        need = (t.get("total_amount_eur") is None) or (force and t["currency"] != "EUR")
        if not need and t.get("costs_eur") is None and (t.get("costs") or 0) > 0:
            need = True
        if not need:
            continue
        fx, tot_eur  = compute_eur(t["total_amount"], t["currency"], t["date"])
        _, costs_eur = compute_eur(t.get("costs") or 0, t.get("costs_currency") or "EUR", t["date"])
        db.set_transaction_eur(t["id"], fx, tot_eur, costs_eur)
        n += 1
    for d in db.get_dividends():
        if d.get("gross_eur") is not None and not (force and d["currency"] != "EUR"):
            continue
        fx, gross_eur = compute_eur(d["gross_amount"], d["currency"], d["date"])
        _, wh_eur     = compute_eur(d["withholding_tax"], d["currency"], d["date"])
        db.set_dividend_eur(d["id"], fx, gross_eur, wh_eur)
        n += 1
    return n
 
 
# ── PAGINA: Dashboard ─────────────────────────────────────────────────────────
 
def page_dashboard():
    st.title("📊 Dashboard")
 
    fc1, fc2 = st.columns([1, 4])
    with fc1:
        acct = account_filter_widget("dash_acct")
    if acct:
        st.caption(f"📂 Gefilterd op rekening: **{acct}** — belastingcijfers blijven globaal (vrijstelling geldt per persoon).")
 
    year = datetime.now().year
    overview, assets, prices = get_overview(year, acct)
    pv = overview["position_values"]
 
    if not pv:
        st.info("👋 Welkom! Voeg activa toe via **🏢 Activa** en daarna transacties via **➕ Transacties**.")
        return
 
    total_val  = overview["total_portfolio_value"]
    total_cost = overview["total_cost_basis"]
    unreal_gl  = overview["unrealized_gl"]
    real_gl    = overview["total_realized_gl"]
    tax_due    = overview["tax_due"]
    exemption  = overview["annual_exemption"]
    remaining  = overview["remaining_exemption"]
 
    # ── KPI-rij ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💼 Portefeuillewaarde", eur(total_val),
              delta=eur(unreal_gl), delta_color=delta_color(unreal_gl))
    c2.metric("💸 Totaal geïnvesteerd", eur(total_cost))
    c3.metric("📈 Ongerealiseerde W/V",
              pct(unreal_gl / total_cost * 100 if total_cost else None),
              delta=eur(unreal_gl), delta_color=delta_color(unreal_gl))
    c4.metric("💰 Netto dividenden YTD", eur(overview["total_dividends_net"]))
    c5.metric("🧾 Transactiekosten", eur(overview.get("selection_costs", 0)),
              help="Aankoop-/verkoopkosten (excl. TOB). Apart gehouden, niet in de meerwaardeberekening.")
 
    st.divider()
 
    col_l, col_r = st.columns([3, 2])
 
    with col_l:
        # Taarttaart samenstelling
        labels = list(pv.keys())
        values = [pv[t]["current_value"] or 0 for t in labels]
        names_map = {a["ticker"]: a.get("name", a["ticker"]) for a in assets}
        names = [names_map.get(t, t) for t in labels]
 
        fig_pie = go.Figure(go.Pie(
            labels=names, values=values,
            hole=0.45, textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>€%{value:,.2f}<extra></extra>",
        ))
        fig_pie.update_layout(
            title="Samenstelling portefeuille",
            height=300, margin=dict(t=40, b=0, l=0, r=0),
            paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
        )
        st.plotly_chart(fig_pie, use_container_width=True)
 
        # Staafdiagram W/V per positie
        tickers_sorted = sorted(pv.keys(), key=lambda t: pv[t]["unrealized_gain_loss"] or 0)
        gl_vals = [pv[t]["unrealized_gain_loss"] or 0 for t in tickers_sorted]
        colors  = ["#00b894" if v >= 0 else "#d63031" for v in gl_vals]
 
        fig_bar = go.Figure(go.Bar(
            x=tickers_sorted, y=gl_vals, marker_color=colors,
            text=[f"€{v:,.0f}" for v in gl_vals], textposition="outside",
            hovertemplate="<b>%{x}</b><br>€%{y:,.2f}<extra></extra>",
        ))
        fig_bar.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.3)")
        fig_bar.update_layout(
            title="Ongerealiseerde winst/verlies per positie",
            height=280, showlegend=False,
            margin=dict(t=40, b=30, l=20, r=20),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_bar, use_container_width=True)
 
    with col_r:
        # Belastingstatus
        st.subheader(f"🧾 Belasting {year}")
        pct_used = min(100.0, real_gl / exemption * 100) if exemption > 0 else 0
        color_lbl = "🟢" if pct_used < 60 else ("🟡" if pct_used < 90 else "🔴")
 
        st.metric("Netto gerealiseerde W/V", eur(real_gl),
                  delta_color=delta_color(real_gl))
        st.progress(min(1.0, pct_used / 100),
                    text=f"{color_lbl} {pct_used:.1f}% van vrijstelling (€{exemption:,.0f})")
 
        if tax_due > 0:
            st.error(f"💰 Geschatte meerwaardebelasting: **{eur(tax_due)}**")
        else:
            st.success(f"✅ Nog {eur(remaining)} vrije ruimte")
 
        st.divider()
 
        # Laatste AI-advies
        st.subheader("🤖 Laatste AI-advies")
        latest = db.get_ai_evaluations("tax_optimization", limit=1)
        if latest:
            ev = latest[0]
            st.caption(f"📅 {ev['created_at'][:16]}")
            preview = ev["content"][:350]
            st.markdown(preview + ("…" if len(ev["content"]) > 350 else ""))
        else:
            st.caption("Nog geen advies. Genereer het via 🤖 AI Advisor.")
 
 
# ── PAGINA: Portefeuille ───────────────────────────────────────────────────────
 
def page_portfolio():
    st.title("💼 Portefeuille")
 
    col_btn, col_acct, _ = st.columns([1, 2, 3])
    if col_btn.button("🔄 Ververs prijzen"):
        clear_cache()
        md._CACHE.clear()
        st.rerun()
    with col_acct:
        acct = account_filter_widget("port_acct")
 
    year = datetime.now().year
    overview, assets, prices = get_overview(year, acct)
    pv = overview["position_values"]
 
    if not pv:
        st.info("Geen open posities. Voeg transacties toe via ➕ Transacties.")
        return
 
    assets_map = {a["ticker"]: a for a in assets}
    divs_net = {}
    for d in db.get_dividends():
        divs_net[d["ticker"]] = divs_net.get(d["ticker"], 0) + (
            d["gross_amount"] - d["withholding_tax"])
 
    rows = []
    for ticker, pos in pv.items():
        asset = assets_map.get(ticker, {})
        div = divs_net.get(ticker, 0)
        total_return = (pos["unrealized_gain_loss"] or 0) + div
        rows.append({
            "":             sign_icon(pos["unrealized_gain_loss"]),
            "Ticker":       ticker,
            "Naam":         (asset.get("name") or ticker)[:22],
            "Type":         (asset.get("asset_type") or "—").upper(),
            "Munt":         pos["current_price_currency"] or "EUR",
            "Aantal":       f"{pos['quantity']:.4f}",
            "Gem.kostpr.(€)":  f"{pos['avg_cost']:.4f}",
            "Koers (native)":  f"{pos['current_price']:.4f}" if pos["current_price"] else "—",
            "Geïnvesteerd": eur(pos["total_cost"]),
            "Huidige waarde": eur(pos["current_value"]),
            "W/V (€)":      eur(pos["unrealized_gain_loss"]),
            "W/V (%)":      pct(pos["unrealized_gain_loss_pct"]),
            "Dividend":     eur(div),
            "Tot. rendement": eur(total_return),
        })
 
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=420)
 
    # Totaalrij
    total_val  = overview["total_portfolio_value"]
    total_cost = overview["total_cost_basis"]
    tot_gl     = overview["unrealized_gl"]
    tot_div    = overview["total_dividends_net"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Totaal geïnvesteerd", eur(total_cost))
    c2.metric("Totale waarde",       eur(total_val))
    c3.metric("Ongerealiseerde W/V", eur(tot_gl),
              delta=pct(tot_gl / total_cost * 100 if total_cost else 0),
              delta_color=delta_color(tot_gl))
    c4.metric("Netto dividenden",    eur(tot_div))
 
    st.divider()
    st.subheader("📈 Prijsgeschiedenis")
    tickers = list(pv.keys())
    sel = st.selectbox("Selecteer positie:", tickers)
    days = st.slider("Aantal dagen:", 1, 90, 14)
 
    hist = db.get_price_history(sel, days=days)
    if hist:
        df_h = pd.DataFrame(hist)
        df_h["timestamp"] = pd.to_datetime(df_h["timestamp"])
        avg_cost = pv[sel]["avg_cost"]
 
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_h["timestamp"], y=df_h["price"],
            mode="lines", line=dict(color="#74b9ff", width=2),
            fill="tozeroy", fillcolor="rgba(116,185,255,0.08)",
            name=sel,
        ))
        fig.add_hline(y=avg_cost, line_dash="dash", line_color="#fdcb6e",
                      annotation_text=f"Gem. kostprijs {avg_cost:.4f}")
        fig.update_layout(
            title=f"{sel} — {days} dagen",
            height=340, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=40, b=30, l=20, r=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nog geen prijsgeschiedenis. De scheduler slaat elke 5 minuten koersen op.")
 
 
# ── PAGINA: Activa ────────────────────────────────────────────────────────────
 
def page_assets():
    st.title("🏢 Activa beheren")
 
    tab_add, tab_list = st.tabs(["➕ Activum toevoegen", "📋 Overzicht"])
 
    with tab_add:
        with st.form("asset_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                ticker = st.text_input("Ticker *", placeholder="bv. AAPL, VWCE.AS")
                name   = st.text_input("Naam (optioneel)", placeholder="bv. Vanguard FTSE All-World")
                currency = st.selectbox("Munt", ["EUR", "USD", "GBP", "CHF"])
            with c2:
                asset_type  = st.radio("Type", ["stock", "etf"],
                                       format_func=lambda x: "📊 Aandeel" if x == "stock" else "🧺 ETF")
                etf_subtype = "distributing"
                if asset_type == "etf":
                    etf_subtype = st.radio("ETF-type", ["distributing", "accumulating"],
                                           format_func=lambda x: "📤 Distribuerend" if x == "distributing" else "📦 Kapitaliseerend",
                                           help="Bepaalt de TOB-berekening (0,12% / 1,32%)")
                exchange = st.text_input("Beurs (optioneel)", placeholder="bv. Euronext, NYSE")
 
            auto_fill = st.checkbox("✨ Info automatisch ophalen via Yahoo Finance", value=True)
            submitted = st.form_submit_button("✅ Activum toevoegen", type="primary")
 
            if submitted:
                if not ticker.strip():
                    st.error("Vul een ticker in.")
                else:
                    t = ticker.strip().upper()
                    n = name.strip()
                    if auto_fill and not n:
                        with st.spinner("Info ophalen via Yahoo Finance..."):
                            info = md.get_stock_info(t)
                            n        = info.get("name", t)
                            currency = info.get("currency", currency)
                            detected = info.get("type", asset_type)
                            if detected == "etf" and asset_type == "stock":
                                asset_type = "etf"
                    db.add_asset(t, n or t, asset_type, etf_subtype, currency, exchange or None)
                    clear_cache()
                    st.success(f"✅ {t} — {n} toegevoegd!")
                    st.rerun()
 
    with tab_list:
        assets = db.get_assets()
        if not assets:
            st.info("Nog geen activa geregistreerd.")
            return
        for a in assets:
            c1, c2, c3 = st.columns([5, 2, 1])
            with c1:
                subtype_lbl = f" ({a['etf_subtype']})" if a["asset_type"] == "etf" else ""
                st.markdown(f"**{a['ticker']}** — {a.get('name') or '—'}")
                st.caption(f"{a['asset_type'].upper()}{subtype_lbl} | {a['currency']} | {a.get('exchange') or '—'}")
            with c2:
                lp = db.get_latest_price(a["ticker"])
                if lp:
                    st.metric("Laatste koers", f"{lp['price']:.4f} {lp['currency']}",
                              label_visibility="collapsed")
                else:
                    st.caption("Geen koers")
            with c3:
                if st.button("🗑️", key=f"del_asset_{a['ticker']}",
                             help=f"Verwijder {a['ticker']} (inclusief alle transacties)"):
                    db.delete_asset(a["ticker"])
                    clear_cache()
                    st.rerun()
            st.divider()
 
 
# ── PAGINA: Transacties ───────────────────────────────────────────────────────
 
def page_transactions():
    st.title("➕ Transacties")
 
    assets = db.get_assets()
    if not assets:
        st.warning("Voeg eerst activa toe via 🏢 Activa.")
        return
 
    asset_tickers = [a["ticker"] for a in assets]
    assets_map    = {a["ticker"]: a for a in assets}
 
    tab_add, tab_view = st.tabs(["📝 Nieuwe transactie", "📋 Overzicht"])
 
    with tab_add:
        with st.form("txn_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                ticker   = st.selectbox("Activum *", asset_tickers)
                txn_date = st.date_input("Datum *", value=date.today())
                txn_type = st.radio("Type *", ["buy", "sell"],
                                    format_func=lambda x: "🟢 Aankoop" if x == "buy" else "🔴 Verkoop",
                                    horizontal=True)
                account  = st.selectbox("Rekening *", db.get_accounts(),
                                        help="Beheer rekeningen via ⚙️ Instellingen → Rekeningen")
            with c2:
                quantity    = st.number_input("Aantal *", min_value=0.0001, step=0.001,
                                               format="%.4f", value=1.0)
                price_unit  = st.number_input("Prijs per stuk *", min_value=0.0001,
                                               step=0.01, format="%.4f", value=1.0)
                currency    = st.selectbox("Munt", ["EUR", "USD", "GBP", "CHF"],
                                           index=["EUR", "USD", "GBP", "CHF"].index(
                                               assets_map.get(ticker, {}).get("currency", "EUR")))
 
            total_amount = quantity * price_unit
 
            # Kosten (in munt naar keuze, los van TOB)
            ck1, ck2 = st.columns([2, 1])
            with ck1:
                costs = st.number_input("Transactiekosten (optioneel)", min_value=0.0,
                                        step=0.01, format="%.2f", value=0.0,
                                        help="Broker-/beurskosten e.d. — apart gehouden, niet in de meerwaardeberekening.")
            with ck2:
                costs_currency = st.selectbox("Kostenmunt", ["EUR", "USD", "GBP", "CHF"],
                                              key="costs_cur")
 
            # TOB auto-berekening
            asset_info  = assets_map.get(ticker, {})
            tob_amount  = tax_mod.calculate_tob(
                asset_info.get("asset_type", "stock"),
                asset_info.get("etf_subtype", "distributing"),
                total_amount,
            )
            # EUR-voorbeeld tonen
            _fx_prev, _eur_prev = compute_eur(total_amount, currency, txn_date)
            eur_hint = "" if currency == "EUR" else f" ≈ **€{_eur_prev:,.2f}** (koers {_fx_prev:.4f})"
            st.info(f"**Totaalwaarde:** {currency} {total_amount:,.4f}{eur_hint} | **TOB:** {currency} {tob_amount:,.2f}")
 
            manual_tob = st.checkbox("TOB manueel aanpassen")
            if manual_tob:
                tob_amount = st.number_input("TOB (€)", min_value=0.0, value=tob_amount,
                                              step=0.01, format="%.2f")
 
            notes = st.text_area("Notities (optioneel)", height=60)
            submitted = st.form_submit_button("✅ Transactie toevoegen", type="primary")
 
            if submitted:
                if quantity <= 0 or price_unit <= 0:
                    st.error("Aantal en prijs moeten positief zijn.")
                else:
                    fx_rate, tot_eur = compute_eur(total_amount, currency, txn_date)
                    _, costs_eur = compute_eur(costs, costs_currency, txn_date)
                    proceed = True
                    if txn_type == "sell":
                        # Beschikbaarheid controleren BINNEN de gekozen rekening
                        acct_txns = db.get_transactions(ticker=ticker, account=account)
                        positions, _ = tax_mod.build_fifo_positions(acct_txns)
                        available = positions.get(ticker, {}).get("total_quantity", 0)
                        if quantity > available + 1e-9:
                            st.error(f"Onvoldoende positie op rekening '{account}'. Beschikbaar: {available:.4f}")
                            proceed = False
                    if proceed:
                        db.add_transaction(ticker, txn_type, str(txn_date), quantity,
                                           price_unit, total_amount, currency, tob_amount,
                                           notes or None, account=account, costs=costs,
                                           costs_currency=costs_currency, fx_rate=fx_rate,
                                           total_amount_eur=tot_eur, costs_eur=costs_eur)
                        clear_cache()
                        st.success(f"✅ {'Aankoop' if txn_type == 'buy' else 'Verkoop'} van "
                                   f"{quantity:.4f} × {ticker} op {account} toegevoegd!")
                        st.rerun()
 
    with tab_view:
        c1, c2, c3, c4 = st.columns(4)
        f_tick = c1.text_input("Filter ticker")
        f_type = c2.selectbox("Type", ["Alle", "Aankoop", "Verkoop"])
        f_year = c3.selectbox("Jaar", ["Alle"] + [str(y) for y in range(datetime.now().year, 2019, -1)])
        f_acct = c4.selectbox("Rekening", ["Alle"] + db.get_accounts())
 
        txns = db.get_transactions(
            ticker=f_tick.upper() if f_tick else None,
            year=int(f_year) if f_year != "Alle" else None,
            txn_type=("buy" if f_type == "Aankoop" else "sell" if f_type == "Verkoop" else None),
            account=(f_acct if f_acct != "Alle" else None),
        )
 
        if not txns:
            st.info("Geen transacties gevonden.")
            return
 
        # Totalen
        total_tob   = sum(t["tob_tax"] or 0 for t in txns)
        total_costs = sum(t.get("costs_eur") or 0 for t in txns)
        st.caption(f"{len(txns)} transactie(s) | Totale TOB: {eur(total_tob)} | Kosten: {eur(total_costs)}")
 
        accounts = db.get_accounts()
        for t in reversed(txns):  # Nieuwste eerst
            icon  = "🟢" if t["transaction_type"] == "buy" else "🔴"
            label = "Aankoop" if t["transaction_type"] == "buy" else "Verkoop"
            c_info, c_val, c_acct, c_del = st.columns([4, 3, 2, 1])
            with c_info:
                st.markdown(f"{icon} **{t['ticker']}** — {label}")
                st.caption(f"📅 {t['date']}")
                if t.get("notes"):
                    st.caption(f"📝 {t['notes']}")
            with c_val:
                st.markdown(f"{t['quantity']:.4f} × {t['currency']} {t['price_per_unit']:.4f}")
                eur_tot = t.get("total_amount_eur")
                eur_str = f" (€{eur_tot:,.2f})" if eur_tot is not None and t["currency"] != "EUR" else ""
                st.caption(f"Totaal: {t['currency']} {t['total_amount']:,.2f}{eur_str}")
                st.caption(f"TOB: {eur(t['tob_tax'])} | Kosten: {eur(t.get('costs_eur') or 0)}")
            with c_acct:
                cur_acct = t.get("account") or db.DEFAULT_ACCOUNT
                idx = accounts.index(cur_acct) if cur_acct in accounts else 0
                new_acct = st.selectbox("Rekening", accounts, index=idx,
                                        key=f"acct_{t['id']}", label_visibility="collapsed")
                if new_acct != cur_acct:
                    db.update_transaction_account(t["id"], new_acct)
                    clear_cache()
                    st.rerun()
            with c_del:
                if st.button("🗑️", key=f"del_t_{t['id']}"):
                    db.delete_transaction(t["id"])
                    clear_cache()
                    st.rerun()
            st.divider()
 
 
# ── PAGINA: Dividenden ────────────────────────────────────────────────────────
 
def page_dividends():
    st.title("💰 Dividenden")
 
    assets = db.get_assets()
 
    tab_add, tab_view = st.tabs(["📝 Dividend toevoegen", "📋 Overzicht"])
 
    with tab_add:
        tickers = [a["ticker"] for a in assets]
        if not tickers:
            st.warning("Voeg eerst activa toe via 🏢 Activa.")
        else:
            wh_default = float(db.get_setting("withholding_tax_rate", "0.30"))
            with st.form("div_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    d_ticker   = st.selectbox("Activum *", tickers)
                    d_date     = st.date_input("Datum *", value=date.today())
                    d_currency = st.selectbox("Munt", ["EUR", "USD", "GBP"])
                with c2:
                    gross  = st.number_input("Bruto dividend (€) *", min_value=0.01, step=0.01, format="%.2f")
                    wh_pct = st.number_input("Roerende voorheffing (%)", min_value=0.0,
                                              max_value=100.0, value=wh_default * 100, step=0.5)
                    wh_amt = gross * wh_pct / 100
                    net    = gross - wh_amt
                    st.info(f"**Netto ontvangen:** {d_currency} {net:,.2f} (RV: {d_currency} {wh_amt:,.2f})")
                notes = st.text_area("Notities (optioneel)", height=60)
                if st.form_submit_button("✅ Dividend toevoegen", type="primary"):
                    fx_rate, gross_eur = compute_eur(gross, d_currency, d_date)
                    _, wh_eur = compute_eur(wh_amt, d_currency, d_date)
                    db.add_dividend(d_ticker, str(d_date), gross, wh_amt, d_currency, notes or None,
                                    fx_rate=fx_rate, gross_eur=gross_eur, withholding_eur=wh_eur)
                    clear_cache()
                    st.success(f"✅ Dividend {d_currency} {net:.2f} netto voor {d_ticker} toegevoegd!")
                    st.rerun()
 
    with tab_view:
        f_year = st.selectbox("Jaar:", ["Alle"] + [str(y) for y in range(datetime.now().year, 2019, -1)],
                              key="div_year")
        divs = db.get_dividends(year=int(f_year) if f_year != "Alle" else None)
 
        if not divs:
            st.info("Geen dividenden gevonden.")
            return
 
        total_gross = sum(d["gross_amount"] for d in divs)
        total_wh    = sum(d["withholding_tax"] for d in divs)
        total_net   = total_gross - total_wh
 
        c1, c2, c3 = st.columns(3)
        c1.metric("Bruto", eur(total_gross))
        c2.metric("Roerende voorheffing", eur(total_wh))
        c3.metric("Netto ontvangen", eur(total_net))
        st.divider()
 
        for d in divs:
            net = d["gross_amount"] - d["withholding_tax"]
            c_info, c_val, c_del = st.columns([5, 3, 1])
            with c_info:
                st.markdown(f"🎁 **{d['ticker']}**")
                st.caption(f"📅 {d['date']}")
                if d.get("notes"):
                    st.caption(f"📝 {d['notes']}")
            with c_val:
                st.markdown(f"Bruto: **{d['currency']} {d['gross_amount']:,.2f}**")
                st.caption(f"RV: {d['currency']} {d['withholding_tax']:,.2f} | Netto: {d['currency']} {net:,.2f}")
            with c_del:
                if st.button("🗑️", key=f"del_d_{d['id']}"):
                    db.delete_dividend(d["id"])
                    clear_cache()
                    st.rerun()
            st.divider()
 
 
# ── PAGINA: Belgische belasting ────────────────────────────────────────────────
 
def page_tax():
    st.title("🧾 Belgische Meerwaardebelasting")
    st.caption("⚖️ *Schattingen — raadpleeg een erkend belastingconsulent voor uw situatie.*")
 
    cur_year  = datetime.now().year
    sel_year  = st.selectbox("Boekjaar:", list(range(cur_year, cur_year - 6, -1)))
    overview, assets, prices = get_overview(sel_year)
 
    pv          = overview["position_values"]
    real_gl     = overview["total_realized_gl"]
    exemption   = overview["annual_exemption"]
    remaining   = overview["remaining_exemption"]
    taxable     = overview["taxable_amount"]
    tax_rate    = overview["tax_rate"]
    tax_due     = overview["tax_due"]
    unreal_gl   = overview["unrealized_gl"]
    total_val   = overview["total_portfolio_value"]
    total_cost  = overview["total_cost_basis"]
 
    # ── Metrics ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gerealiseerde W/V", eur(real_gl), delta_color=delta_color(real_gl))
    c2.metric("Jaarlijkse vrijstelling", eur(exemption))
    c3.metric("Belastbaar bedrag", eur(taxable))
    c4.metric("Geschatte belasting (10%)", eur(tax_due),
              delta_color="inverse" if tax_due > 0 else "off")
    cnt       = overview.get("exemption_count", 1)
    carry_eff = overview.get("carry_exemption", 0.0)
    base_eff  = overview.get("base_exemption_effective", exemption)
    if cnt == 2 or carry_eff > 0:
        basis_txt = (f"2 × €{overview['base_exemption']:,.0f}" if cnt == 2
                     else f"€{overview['base_exemption']:,.0f}")
        opbouw_txt = f" + €{carry_eff:,.0f} opgebouwde overdracht" if carry_eff > 0 else ""
        partner_txt = " Elke partner heeft een eigen vrijstelling (gemeenschap van goederen)." if cnt == 2 else ""
        st.caption(f"ℹ️ Vrijstelling = {basis_txt} basis{opbouw_txt} = **€{exemption:,.0f}**.{partner_txt}")
 
    st.divider()
    col_l, col_r = st.columns([3, 2])
 
    with col_l:
        pct_used = min(100.0, real_gl / exemption * 100) if exemption > 0 else 0
        color_lbl = "🟢" if pct_used < 60 else ("🟡" if pct_used < 90 else "🔴")
        st.subheader("Vrijstelling gebruik")
        st.progress(max(0.0, min(1.0, pct_used / 100)),
                    text=f"{color_lbl} {pct_used:.1f}% gebruikt ({eur(real_gl)} / {eur(exemption)})")
 
        st.markdown(f"""
| | Bedrag |
|---|---|
| Gerealiseerde meerwaarden | **{eur(real_gl)}** |
| Basisvrijstelling | {eur(overview.get('base_exemption_effective', exemption))} |
| Opgebouwde overdracht | {eur(overview.get('carry_exemption', 0))} |
| **Totale vrijstelling** | **{eur(exemption)}** |
| Resterend vrij | {eur(remaining)} |
| Belastbaar bedrag | **{eur(taxable)}** |
| Tarief | {tax_rate*100:.0f}% |
| **Geschatte belasting** | **{eur(tax_due)}** |
        """)
 
        if tax_due > 0:
            st.error(f"⚠️ Geschatte meerwaardebelasting {sel_year}: **{eur(tax_due)}**")
        else:
            st.success(f"✅ Geen meerwaardebelasting verschuldigd ({eur(remaining)} ruimte over).")
 
    with col_r:
        st.subheader("Totale portefeuille")
        st.metric("Huidige waarde", eur(total_val))
        st.metric("Kostbasis",      eur(total_cost))
        st.metric("Ongerealiseerde W/V", eur(unreal_gl),
                  delta=pct(unreal_gl / total_cost * 100 if total_cost else None),
                  delta_color=delta_color(unreal_gl))
        st.metric("Totale W/V (gerealiseerd + ongerealiseerd)",
                  eur(real_gl + unreal_gl),
                  delta_color=delta_color(real_gl + unreal_gl))
 
        st.divider()
        with st.expander("ℹ️ Fiscale wetgeving"):
            st.markdown(f"""
**Meerwaardebelasting België {sel_year}** (De Wever-hervorming)
 
- **Tarief:** 10% op netto gerealiseerde meerwaarden
- **Vrijstelling:** eerste **{eur(overview.get('base_exemption', exemption))}** per belastingplichtige per jaar{' — bij gemeenschap van goederen telt dit per partner, samen ' + eur(exemption) if overview.get('exemption_count', 1) == 2 else ''}
- **Opbouw:** ongebruikt deel (max €1.000/jaar) overdraagbaar tot 5 jaar → max €15.000 p.p.
- **Minwaarden** compenseren meerwaarden binnen hetzelfde boekjaar
- **Methode:** FIFO (first in, first out)
- **TOB:** apart berekend per transactie (reeds afgehouden)
- **Dividenden:** onderhevig aan 30% roerende voorheffing (apart stelsel)
 
*Raadpleeg een erkend belastingconsulent (accountant / fiscaal adviseur) voor uw specifieke situatie.*
            """)
 
    # ── Gerealiseerde transacties ──────────────────────────────────────────
    year_gains = overview["realized_gains"]
    if year_gains:
        st.divider()
        st.subheader(f"📋 Gerealiseerde transacties {sel_year}")
        rows = [{
            sign_icon(g["gain_loss"]): sign_icon(g["gain_loss"]),
            "Ticker":      g["ticker"],
            "Verkoopdatum": g["date"],
            "Aantal":      f"{g['quantity']:.4f}",
            "Kostbasis":   eur(g["cost_basis"]),
            "Verkoopwaarde": eur(g["sell_total"]),
            "Winst/Verlies": eur(g["gain_loss"]),
        } for g in sorted(year_gains, key=lambda x: x["date"], reverse=True)]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(f"Geen gerealiseerde transacties in {sel_year}.")
 
    # TOB overzicht
    st.divider()
    st.subheader(f"🏛️ TOB betaald {sel_year}")
    txns_year = db.get_transactions(year=sel_year)
    total_tob = sum(t["tob_tax"] or 0 for t in txns_year)
    st.metric("Totale TOB betaald", eur(total_tob))
    if txns_year:
        tob_rows = [{
            "Ticker": t["ticker"],
            "Type":   "Aankoop" if t["transaction_type"] == "buy" else "Verkoop",
            "Datum":  t["date"],
            "Transactiewaarde": eur(t["total_amount"]),
            "TOB":    eur(t["tob_tax"]),
        } for t in txns_year if t["tob_tax"]]
        if tob_rows:
            with st.expander("TOB-detail per transactie"):
                st.dataframe(pd.DataFrame(tob_rows), use_container_width=True, hide_index=True)
 
 
# ── PAGINA: AI Advisor ────────────────────────────────────────────────────────
 
def page_ai_advisor():
    st.title("🤖 AI Beleggingsadviseur")
 
    api_key = db.get_setting("openai_api_key", "")
    if not api_key:
        st.warning("⚠️ Voeg uw OpenAI API-sleutel toe in **⚙️ Instellingen** om AI-functies te gebruiken.")
        return
 
    tab_tax, tab_open, tab_mid, tab_close = st.tabs([
        "💡 Belastingoptimalisatie",
        "🔔 Marktopening",
        "☀️ Middag",
        "🔕 Slotring",
    ])
 
    def render_eval_tab(eval_type: str, timing_filter: str | None,
                        button_label: str, manual_args: dict):
        evals = db.get_ai_evaluations(eval_type, limit=10)
        if timing_filter:
            evals = [e for e in evals if e.get("timing") == timing_filter]
 
        latest = evals[0] if evals else None
        if latest:
            st.caption(f"📅 Gegenereerd op: {latest['created_at'][:16]}")
            if latest.get("tickers"):
                st.caption(f"📊 Tickers: {latest['tickers']}")
            st.markdown(latest["content"])
        else:
            st.info("Nog geen evaluatie beschikbaar. Klik op de knop hieronder of wacht op de dagelijkse scheduler.")
 
        st.divider()
        if st.button(button_label, type="primary", key=f"gen_{eval_type}_{timing_filter}"):
            with st.spinner("GPT analyseert uw portefeuille..."):
                if eval_type == "tax_optimization":
                    ai_advisor.generate_tax_optimization()
                else:
                    ai_advisor.generate_market_evaluation(
                        manual_args["timing"], manual_args["exchanges"])
            clear_cache()
            st.rerun()
 
        if len(evals) > 1:
            with st.expander("📚 Historiek"):
                for ev in evals[1:]:
                    st.caption(f"📅 {ev['created_at'][:16]}")
                    st.markdown(ev["content"])
                    st.divider()
 
    with tab_tax:
        st.subheader("💡 Dagelijks belastingoptimalisatieadvies")
        st.caption("Automatisch gegenereerd op werkdagen om 08:00. Gebaseerd op actuele portefeuille en Belgische fiscale regels.")
        render_eval_tab("tax_optimization", None,
                        "💡 Genereer belastingadvies nu",
                        {})
 
    with tab_open:
        st.subheader("🔔 Evaluatie bij marktopening")
        st.caption("Euronext: 09:05 | NYSE/NASDAQ: 15:35 (Brussels Time)")
        render_eval_tab("market_evaluation", "open",
                        "🔔 Genereer opening-evaluatie nu",
                        {"timing": "open", "exchanges": ["Euronext", "NYSE", "NASDAQ"]})
 
    with tab_mid:
        st.subheader("☀️ Evaluatie midden van de beursdag")
        st.caption("Euronext: 13:15 | NYSE/NASDAQ: 18:45 (Brussels Time)")
        render_eval_tab("market_evaluation", "midday",
                        "☀️ Genereer middag-evaluatie nu",
                        {"timing": "midday", "exchanges": ["Euronext", "NYSE", "NASDAQ"]})
 
    with tab_close:
        st.subheader("🔕 Evaluatie bij slotring")
        st.caption("Euronext: 17:35 | NYSE/NASDAQ: 22:05 (Brussels Time)")
        render_eval_tab("market_evaluation", "close",
                        "🔕 Genereer slotring-evaluatie nu",
                        {"timing": "close", "exchanges": ["Euronext", "NYSE", "NASDAQ"]})
 
 
# ── PAGINA: Instellingen ──────────────────────────────────────────────────────
 
def page_settings():
    st.title("⚙️ Instellingen")
 
    tab_api, tab_acct, tab_tax, tab_tob, tab_data = st.tabs(
        ["🔑 API-sleutel", "🏦 Rekeningen", "🧾 Meerwaardebelasting", "🏛️ TOB-tarieven", "🗃️ Data"])
 
    with tab_api:
        st.subheader("OpenAI API")
        current = db.get_setting("openai_api_key", "")
        new_key = st.text_input("API-sleutel", value=current, type="password",
                                help="Beschikbaar via platform.openai.com/api-keys")
        model = st.selectbox("Model", ["gpt-4.1-mini", "gpt-4.1", "gpt-4.1-nano"],
                             index=["gpt-4.1-mini", "gpt-4.1", "gpt-4.1-nano"].index(
                                 db.get_setting("openai_model", "gpt-4.1-mini")))
        if st.button("💾 Opslaan", key="save_api"):
            db.set_setting("openai_api_key", new_key.strip())
            db.set_setting("openai_model", model)
            st.success("✅ API-sleutel opgeslagen!")
        if current:
            st.success("✅ API-sleutel is geconfigureerd.")
        else:
            st.warning("⚠️ Geen API-sleutel — AI-functies niet beschikbaar.")
 
    with tab_acct:
        st.subheader("Rekeningen / oorsprong")
        st.caption("Definieer je rekeningen (bv. Bolero, Degiro, Saxo). Je kiest er één bij elke transactie en kunt erop filteren in het Dashboard, de Portefeuille en de Evolutie-pagina.")
        current = [a for a in db.get_accounts() if a != db.DEFAULT_ACCOUNT]
        txt = st.text_area("Eén rekening per regel", value="\n".join(current), height=140,
                           help="De rekening 'Niet toegewezen' bestaat altijd als vangnet voor oude transacties.")
        if st.button("💾 Rekeningen opslaan", key="save_accts"):
            db.set_accounts([line.strip() for line in txt.splitlines() if line.strip()])
            clear_cache()
            st.success("✅ Rekeningen opgeslagen!")
        used = db.get_used_accounts()
        if used:
            st.caption("Momenteel in gebruik: " + ", ".join(used))
 
    with tab_tax:
        st.subheader("Meerwaardebelasting (opt-out stelsel)")
        rate  = st.number_input("Belastingtarief (%)",
                                min_value=0.0, max_value=100.0,
                                value=float(db.get_setting("capital_gains_tax_rate", "0.10")) * 100,
                                step=0.5)
        exemp = st.number_input("Jaarlijkse vrijstelling per persoon (€)",
                                min_value=0.0, value=float(db.get_setting("annual_exemption", "10000")),
                                step=500.0)
 
        regimes = {
            "single":    "Alleenstaand / 1 belastingplichtige  →  1× vrijstelling",
            "community": "Gehuwd of wettelijk samenwonend, gemeenschap van goederen  →  2× vrijstelling",
        }
        keys = list(regimes.keys())
        cur_regime = db.get_setting("household_regime", "single")
        regime = st.selectbox("Belastingsituatie / huwelijksstelsel", keys,
                              index=keys.index(cur_regime) if cur_regime in keys else 0,
                              format_func=lambda k: regimes[k])
        if regime == "community":
            st.info(f"💑 Bij gemeenschap van goederen heeft **elke partner** recht op de jaarlijkse vrijstelling — ook als een effectenrekening op naam van één partner staat. "
                    f"De gezamenlijke meerwaarde wordt verminderd met een effectieve vrijstelling van **€{exemp*2:,.0f}**.")
        st.caption("⚖️ Schatting op basis van een gelijke (50/50) toerekening van de meerwaarde aan beide partners. "
                   "De meerjarige opbouw van ongebruikte vrijstelling (max €1.000/jaar, tot €15.000 p.p. over 5 jaar) "
                   "wordt automatisch berekend uit je transactiegeschiedenis vanaf 2026. Raadpleeg een fiscalist voor je concrete situatie.")
 
        if st.button("💾 Opslaan", key="save_tax"):
            db.set_setting("capital_gains_tax_rate", str(rate / 100))
            db.set_setting("annual_exemption", str(exemp))
            db.set_setting("household_regime", regime)
            clear_cache()
            st.success("✅ Belastinginstellingen opgeslagen!")
 
    with tab_tob:
        st.subheader("Taks op Beursverrichtingen (TOB)")
        c1, c2 = st.columns(2)
        with c1:
            r_s  = st.number_input("Aandelen tarief (%)", value=float(db.get_setting("tob_rate_stocks", "0.0035"))*100, step=0.001, format="%.4f")
            r_ed = st.number_input("ETF distribuerend (%)", value=float(db.get_setting("tob_rate_etf_distributing", "0.0012"))*100, step=0.001, format="%.4f")
            r_ea = st.number_input("ETF kapitaliseerend (%)", value=float(db.get_setting("tob_rate_etf_accumulating", "0.0132"))*100, step=0.001, format="%.4f")
        with c2:
            m_s  = st.number_input("Aandelen maximum (€)", value=float(db.get_setting("tob_max_stocks", "1600")), step=100.0)
            m_ed = st.number_input("ETF distr. maximum (€)", value=float(db.get_setting("tob_max_etf_distributing", "1300")), step=100.0)
            m_ea = st.number_input("ETF kap. maximum (€)", value=float(db.get_setting("tob_max_etf_accumulating", "4000")), step=100.0)
        wh = st.number_input("Roerende voorheffing (%)",
                              value=float(db.get_setting("withholding_tax_rate", "0.30"))*100,
                              step=0.5)
        if st.button("💾 Opslaan", key="save_tob"):
            db.set_setting("tob_rate_stocks", str(r_s/100))
            db.set_setting("tob_rate_etf_distributing", str(r_ed/100))
            db.set_setting("tob_rate_etf_accumulating", str(r_ea/100))
            db.set_setting("tob_max_stocks", str(m_s))
            db.set_setting("tob_max_etf_distributing", str(m_ed))
            db.set_setting("tob_max_etf_accumulating", str(m_ea))
            db.set_setting("withholding_tax_rate", str(wh/100))
            st.success("✅ TOB-instellingen opgeslagen!")
 
    with tab_data:
        st.subheader("Databeheer")
        assets = db.get_assets()
        txns   = db.get_transactions()
        divs   = db.get_dividends()
        c1, c2, c3 = st.columns(3)
        c1.metric("Activa", len(assets))
        c2.metric("Transacties", len(txns))
        c3.metric("Dividenden", len(divs))
        st.divider()
        if st.button("🔄 Prijzen nu ophalen en opslaan"):
            with st.spinner("Koersen ophalen..."):
                tickers = [a["ticker"] for a in assets]
                prices  = md.get_prices_for_tickers(tickers)
                for ticker, info in prices.items():
                    if info["price"] is not None:
                        db.save_price(ticker, info["price"], info.get("currency", "EUR"))
                clear_cache()
                md._CACHE.clear()
            st.success(f"✅ Koersen opgeslagen voor {len(prices)} ticker(s).")
        st.divider()
        st.subheader("💱 EUR-omrekening")
        st.caption("Reken bestaande transacties en dividenden om naar EUR met de wisselkoers op hun eigen datum. Nodig na de migratie of na het importeren van oude (USD/GBP/…) data.")
        force = st.checkbox("Ook reeds-omgerekende, niet-EUR rijen opnieuw berekenen", value=False)
        if st.button("💱 Herbereken EUR-bedragen"):
            with st.spinner("Historische wisselkoersen ophalen..."):
                n = backfill_eur(force=force)
                clear_cache()
                md._CACHE.clear()
            st.success(f"✅ {n} rij(en) omgerekend naar EUR.")
        st.divider()
        keep = st.number_input("Prijsgeschiedenis bewaren (dagen)", min_value=7,
                                max_value=365, value=90)
        if st.button("🗑️ Oude prijsdata opruimen"):
            db.cleanup_old_prices(keep_days=keep)
            st.success(f"✅ Prijsdata ouder dan {keep} dagen verwijderd.")
 
 
 
 
# ── PAGINA: Evolutie ──────────────────────────────────────────────────────────
 
@st.cache_data(ttl=1800, show_spinner=False)
def _evolution_df(sig: str):
    """Reconstrueer de historische waarde/kostenbasis per rekening (1800s cache)."""
    txns = db.get_transactions()
    assets = db.get_assets()
    if not txns:
        return None
    ticker_currency = {a["ticker"]: a.get("currency", "EUR") for a in assets}
    start = min(t["date"] for t in txns)[:10]
    price_map, fx_map, currencies = {}, {}, set()
    for a in assets:
        s = md.get_price_series(a["ticker"], start)
        if s is not None:
            price_map[a["ticker"]] = s
        currencies.add(a.get("currency", "EUR"))
    for cur in currencies:
        if cur != "EUR":
            fx_map[cur] = md.get_fx_series(cur, start)
    return tax_mod.reconstruct_portfolio_evolution(txns, price_map, fx_map, ticker_currency)
 
 
def page_evolution():
    st.title("📈 Waarde-evolutie & vergelijking per rekening")
 
    txns = db.get_transactions()
    if not txns:
        st.info("Nog geen transacties. Voeg ze toe via ➕ Transacties.")
        return
 
    sig = f"{len(txns)}:{max(t['id'] for t in txns)}:{min(t['date'] for t in txns)[:10]}"
    with st.spinner("Historische koersen ophalen en portefeuille reconstrueren..."):
        df = _evolution_df(sig)
 
    if df is None or df.empty:
        st.warning("Kon geen historische reeks opbouwen — koersdata (yfinance) niet beschikbaar voor deze tickers.")
        return
 
    acct_cols = sorted(c[len("value::"):] for c in df.columns
                       if c.startswith("value::") and c != "value::TOTAL")
 
    cfg1, cfg2 = st.columns([3, 2])
    with cfg1:
        sel = st.multiselect("Rekeningen", acct_cols, default=acct_cols)
    with cfg2:
        months = st.select_slider("Periode", options=[1, 3, 6, 12, 24, 60], value=12,
                                  format_func=lambda m: f"{m} mnd" if m < 24 else f"{m//12} jaar")
    if not sel:
        st.info("Selecteer minstens één rekening.")
        return
 
    cutoff = df.index.max() - pd.Timedelta(days=30 * months)
    d = df[df.index >= cutoff]
 
    # ── Grafiek 1: absolute waarde-evolutie (EUR) ─────────────────────────────
    st.subheader("💼 Waarde-evolutie (EUR)")
    fig_val = go.Figure()
    palette = ["#74b9ff", "#00b894", "#fdcb6e", "#e17055", "#a29bfe", "#fd79a8"]
    for i, acct in enumerate(sel):
        col = f"value::{acct}"
        if col in d:
            fig_val.add_trace(go.Scatter(
                x=d.index, y=d[col], mode="lines", name=acct,
                line=dict(width=2, color=palette[i % len(palette)]),
            ))
    if len(sel) > 1:
        cols = [f"value::{a}" for a in sel if f"value::{a}" in d]
        tot = d[cols].sum(axis=1)
        fig_val.add_trace(go.Scatter(x=d.index, y=tot, mode="lines", name="Totaal (selectie)",
                                     line=dict(width=3, color="#ffffff", dash="dot")))
    fig_val.update_layout(height=360, margin=dict(t=20, b=30, l=20, r=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", y=-0.15), hovermode="x unified")
    fig_val.update_yaxes(tickprefix="€")
    st.plotly_chart(fig_val, use_container_width=True)
 
    # ── Grafiek 2: procentuele meer-/minwaarde t.o.v. aankoopprijs ────────────
    st.subheader("📊 Procentuele meer-/minwaarde t.o.v. aankoopprijs")
    st.caption("Per rekening: (huidige waarde − kostenbasis) / kostenbasis. Toont het rendement op het belegde geld, niet het absolute bedrag.")
    fig_pct = go.Figure()
    for i, acct in enumerate(sel):
        vcol, ccol = f"value::{acct}", f"cost::{acct}"
        if vcol in d and ccol in d:
            pct_series = (d[vcol] - d[ccol]) / d[ccol].replace(0, float("nan")) * 100
            fig_pct.add_trace(go.Scatter(
                x=d.index, y=pct_series, mode="lines", name=acct,
                line=dict(width=2, color=palette[i % len(palette)]),
            ))
    fig_pct.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.4)")
    fig_pct.update_layout(height=360, margin=dict(t=20, b=30, l=20, r=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", y=-0.15), hovermode="x unified")
    fig_pct.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig_pct, use_container_width=True)
 
    # ── Huidige momentopname per rekening ─────────────────────────────────────
    st.divider()
    st.subheader("📌 Huidige stand per rekening")
    assets = db.get_assets()
    prices = md.get_prices_for_tickers([a["ticker"] for a in assets])
    summ = tax_mod.account_summary(db.get_transactions(), prices)
    rows = []
    for acct in sorted(summ):
        s = summ[acct]
        rows.append({
            "Rekening":       acct,
            "Posities":       s["n_positions"],
            "Kostenbasis":    eur(s["cost_basis"]),
            "Huidige waarde": eur(s["current_value"]),
            "W/V (€)":        eur(s["gain_loss"]),
            "W/V (%)":        pct(s["gain_loss_pct"]),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        fig_cmp = go.Figure(go.Bar(
            x=[r["Rekening"] for r in rows],
            y=[summ[r["Rekening"]]["gain_loss_pct"] for r in rows],
            marker_color=["#00b894" if summ[r["Rekening"]]["gain_loss_pct"] >= 0 else "#d63031" for r in rows],
            text=[pct(summ[r["Rekening"]]["gain_loss_pct"]) for r in rows],
            textposition="outside",
        ))
        fig_cmp.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.3)")
        fig_cmp.update_layout(title="Rendement per rekening (%)", height=300,
                              margin=dict(t=40, b=30, l=20, r=20), showlegend=False,
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig_cmp.update_yaxes(ticksuffix="%")
        st.plotly_chart(fig_cmp, use_container_width=True)
 
 
# ── Navigatie ─────────────────────────────────────────────────────────────────
 
PAGES = {
    "📊 Dashboard":            page_dashboard,
    "💼 Portefeuille":         page_portfolio,
    "📈 Evolutie":             page_evolution,
    "🏢 Activa":               page_assets,
    "➕ Transacties":          page_transactions,
    "💰 Dividenden":           page_dividends,
    "🧾 Belgische Belasting":  page_tax,
    "🤖 AI Advisor":           page_ai_advisor,
    "⚙️ Instellingen":         page_settings,
}
 
with st.sidebar:
    st.title("📈 Portfolio Tracker")
    st.caption("Belgische belegger 🇧🇪")
 
    selected = st.radio("Menu", list(PAGES.keys()), label_visibility="collapsed")
 
    st.divider()
    # Snelle stats
    try:
        assets = db.get_assets()
        if assets:
            tickers = [a["ticker"] for a in assets]
            prices  = md.get_prices_for_tickers(tickers)
            all_txns = db.get_transactions()
            positions, _ = tax_mod.build_fifo_positions(all_txns)
            pos_vals = tax_mod.get_position_values(positions, prices)
            total_v = sum(p["current_value"] for p in pos_vals.values() if p["current_value"])
            total_c = sum(p["total_cost"]    for p in pos_vals.values())
            gl = total_v - total_c
            icon = "🟢" if gl >= 0 else "🔴"
            st.metric("💼 Waarde", eur(total_v))
            st.caption(f"{icon} {eur(gl)} ({pct(gl/total_c*100 if total_c else 0)})")
    except Exception:
        pass
 
    st.divider()
    now = datetime.now()
    st.caption(f"📅 {now.strftime('%d/%m/%Y %H:%M')}")
    st.caption("⏱️ Koersen: elke 5 min")
    st.caption("🤖 AI: 3× per dag + 08:00")
 
PAGES[selected]()
 
