\# Changelog



Alle noemenswaardige wijzigingen aan de Portfolio Tracker add-on.

De bovenste versie hoort overeen te komen met `version:` in `config.yaml`.



\## 1.3.0



\- \*\*AI-kosten in de app:\*\* het tokengebruik en de geschatte kost per AI-oproep

&#x20; worden bijgehouden en getoond op de AI-adviseur-pagina: totaal, deze maand, en

&#x20; een uitsplitsing per model en per functie (belastingadvies, marktevaluatie,

&#x20; ratings, koersdoel). Richtprijzen medio 2026; de exacte factuur blijft op het

&#x20; OpenAI-dashboard.

\- \*\*Dividenden — voorheffing-kenmerken:\*\* bij een dividend kan je nu aangeven of

&#x20; de bronbelasting (buitenlandse roerende voorheffing) en/of de Belgische

&#x20; roerende voorheffing al is ingehouden. Het overzicht waarschuwt voor dividenden

&#x20; waarop de Belgische RV nog niet is ingehouden en die je dus mogelijk nog moet

&#x20; aangeven.

\- \*\*Fix:\*\* `use\_container\_width` vervangen door `width='stretch'` om de Streamlit-

&#x20; deprecation (verwijdering na 2025-12-31) voor te zijn.



\## 1.2.1



\- \*\*Fix:\*\* scheduler crashte bij het opstarten op `job.next\_run\_time`

&#x20; (`AttributeError`) met nieuwere APScheduler-versies, waardoor de geplande jobs

&#x20; (koersophaling, dagelijks belastingadvies, marktevaluaties) niet meer draaiden.

&#x20; De volgende runtijd wordt nu veilig bepaald.

\- \*\*Fix:\*\* `apscheduler` vastgepind op de 3.x-reeks (`<4.0`) om te vermijden dat

&#x20; een herbouw per ongeluk de incompatibele 4.x-API binnenhaalt.



\## 1.2.0



\- \*\*Transacties bewerken:\*\* bestaande transacties kunnen gecorrigeerd en

&#x20; aangevuld worden (✏️ in het overzicht); EUR-bedragen worden herberekend.

\- \*\*Algemene rekeningkosten:\*\* kosten die niet aan een aandeel hangen

&#x20; (bv. beheerskosten, bewaarloon) via de tab "🏦 Rekeningkosten". Ze verlagen het

&#x20; nettorendement, maar niet de meerwaardeberekening of de individuele posities.

\- \*\*AI-advies synthese:\*\* synthese van de laatste 9 AI-adviesrondes per ticker

&#x20; (Sterk kopen / Kopen / Behouden / Verkopen / Sterk verkopen) met consensus en

&#x20; koersdoel op de Portefeuille-pagina.

\- \*\*Topadviseur met profiel per rekening:\*\* de AI-adviseur weegt portefeuille,

&#x20; macro-economische trends en technologische ontwikkelingen af, afgestemd op een

&#x20; instelbaar beleggingsprofiel per rekening (agressief, neutraal, speculatief,

&#x20; lange termijn, defensief).

\- \*\*Investeringsvolume:\*\* instelbaar bedrag per maand/jaar voor realistische,

&#x20; op het budget afgestemde AI-voorstellen.

\- \*\*Koersdoel bij transactie:\*\* nieuw koersdoelveld met optionele AI-bepaling;

&#x20; het model hiervoor is apart instelbaar.

\- \*\*Koersdoel in Portefeuille:\*\* kolommen "Koersdoel" en "Potentieel" (%).



\## 1.1.0



\- Integratie van rekeningen (multi-rekening/multi-broker), de evolutiepagina met

&#x20; historische waardereconstructie, volledige EUR-omrekening op transactiedatum,

&#x20; het Belgische huwelijksstelsel (gemeenschap van goederen) en de meerjarige

&#x20; opbouw van de vrijstelling.



\## 1.0.1



\- Basisversie: portefeuillebeheer, FIFO-kostbasis, Belgische

&#x20; meerwaardebelasting, TOB en dividenden.

