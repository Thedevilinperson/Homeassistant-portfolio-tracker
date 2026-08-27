"""
fcpe_pricing.py — waardering van FCPE-hefboomfondsen volgens de formule van het fonds
("Participation à la Hausse Moyenne Protégée").

WAAROM EEN APARTE METHODE
De bestaande afgeleide koers rekent lineair op de SPOTKOERS van de onderliggende
waarde: koers = basis + multiplicator × (spot − referentie). Voor de Link
Classic/Liberty-fondsen klopt dat exact (één deelbewijs = één aandeel), maar voor de
Multiple-fondsen niet. Die hangen niet aan de koers van vandaag, maar aan het
GEMIDDELDE van zestig maandelijkse waarnemingen, elk afgetopt op een ondergrens:

    Deelbewijswaarde = Prix de Souscription + Performance + Majorations
    Performance       = max(Rendement, Participation)          ← "la valeur la plus
                        haute entre le Rendement et la Participation à la Hausse
                        Moyenne Protégée" (reglement art. 3.11.1 / 3.12.1)
    Participation     = α × (gemiddelde van de Relevés − Prix de Référence)
    Relevé i          = max(slotkoers op waarnemingsdatum i, Prix de Référence)

LET OP: het Rendement is een BODEM, geen opslag. Het reglement neemt de HOOGSTE van
Rendement en Participation; het wordt dus nooit bij de Participation opgeteld. Tot
1.8.1 telde deze module beide op, wat een langzaam groeiende overwaardering gaf
(≈ €0,16 per jaar bij 1,5% op een inschrijvingsprijs van €10,52). Zodra de koers
boven de referentieprijs noteert, wint de Participation en telt het Rendement niet
meer mee. Op de dag van oprichting is de waarde per reglement (art. 10) exact de
inschrijvingsprijs.

Twee gevolgen die een lineair model niet kan nabootsen:

1. **Traagheid die toeneemt.** Eén waarneming weegt 1/60. Zolang er nog waarnemingen
   openstaan, worden die ingevuld met de huidige koers, dus een koersbeweging van €1
   verschuift de waarde met α × (openstaand/60) × €1. Vroeg in de looptijd beweegt de
   waarde bijna volledig mee; naar het einde toe steeds minder, omdat het grootste deel
   van het gemiddelde al vastligt. Een vaste multiplicator kan dat per definitie niet:
   die is even gevoelig op dag één als op de laatste dag.
2. **Een neerwaartse bodem per waarneming.** Doordat elke Relevé afzonderlijk op de
   referentieprijs wordt afgetopt, kan een koersdaling onder die prijs het gemiddelde
   niet verlagen. Een reeds vastgelegde stijging kan dus niet meer verdwijnen. Het
   lineaire model met een ondergrens op de totaalwaarde beschermt pas op het einde en
   laat verworven winst wél weer wegvallen.

Deze module rekent alleen; ze leest niets en schrijft niets. Alle parameters komen van
de aanroeper, zodat elk fonds (en elke jaargang) zijn eigen waarden kan hebben.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

__all__ = [
    "market_holidays", "is_trading_day", "previous_trading_day", "reading_dates",
    "reading_value", "part_value",
    "value_series", "compare_with_official", "fit_parameters",
    "DEFAULT_ANNUAL_RATE",
]

DEFAULT_ANNUAL_RATE = 0.015          # 1,5% — het tarief uit de aangehaalde documenten


def _as_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None



# ── Beurskalender voor de waarnemingsdata ────────────────────────────────────
# "Date de Relevé i désigne chaque mois, le 15 du mois concerné (et si ce jour n'est
# pas un Jour de Bourse ouvré, le Jour de Bourse ouvré précédent cette date)."
# Welke dagen dat zijn, is niet vrijblijvend: de gepubliceerde reeks van het fonds
# schuift op 14 juli en 15 augustus een dag terug, dus de Franse feestdagen tellen
# mee — niet alleen de sluitingsdagen van Euronext. Deze lijst is de vereniging van
# beide, en is nagerekend tegen 44 gepubliceerde waarnemingsdata (2023-2026): alle
# 44 komen exact uit.

def _easter(year: int) -> date:
    """Paaszondag (algoritme van Meeus/Jones/Butcher, Gregoriaans)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    return date(year, (h + l - 7 * m + 114) // 31, ((h + l - 7 * m + 114) % 31) + 1)


def market_holidays(year: int) -> set:
    """Sluitingsdagen: Franse wettelijke feestdagen plus de dagen waarop Euronext
    dicht is (Goede Vrijdag, tweede kerstdag)."""
    e = _easter(year)
    return {
        date(year, 1, 1),                       # Nieuwjaar
        e - timedelta(days=2),                  # Goede Vrijdag (Euronext)
        e + timedelta(days=1),                  # Paasmaandag
        date(year, 5, 1),                       # Dag van de arbeid
        date(year, 5, 8),                       # 8 mei
        e + timedelta(days=39),                 # Onze-Lieve-Heer-Hemelvaart
        e + timedelta(days=50),                 # Pinkstermaandag
        date(year, 7, 14),                      # Quatorze Juillet
        date(year, 8, 15),                      # Onze-Lieve-Vrouw-Hemelvaart
        date(year, 11, 1),                      # Allerheiligen
        date(year, 11, 11),                     # Wapenstilstand
        date(year, 12, 25),                     # Kerstmis
        date(year, 12, 26),                     # Tweede kerstdag (Euronext)
    }


def is_trading_day(d) -> bool:
    d = _as_date(d)
    return bool(d) and d.weekday() < 5 and d not in market_holidays(d.year)


def previous_trading_day(d):
    """De gegeven dag zelf als het een beursdag is, anders de eerste beursdag ervoor."""
    d = _as_date(d)
    while d and not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def reading_dates(count: int, *, day_of_month: int = 15,
                  first_month: str | date | None = None,
                  first: str | date | None = None) -> list[str]:
    """De 'count' waarnemingsdata: telkens 'day_of_month', of de beursdag ervoor.

    first_month bepaalt de maand waarin de reeks begint (de dag doet er niet toe;
    voor de jaargang 2022 is dat januari 2023, wat 13 januari 2023 oplevert omdat
    15 januari een zondag was).
    """
    start = _as_date(first_month or first)
    if start is None or count < 1:
        return []
    out, y, m = [], start.year, start.month
    for _ in range(count):
        day = min(day_of_month, calendar.monthrange(y, m)[1])
        out.append(previous_trading_day(date(y, m, day)).isoformat())
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def reading_value(close: float, reference_price: float) -> float:
    """Relevé i = max(slotkoers, Prix de Référence)."""
    return max(float(close), float(reference_price))


def part_value(readings, *, n_readings: int, reference_price: float, alpha: float,
               subscription_price: float, spot: float | None = None,
               on_date=None, start_date=None,
               annual_rate: float = DEFAULT_ANNUAL_RATE,
               maturity_date=None, maturity_return: float | None = None,
               md_entries=None) -> dict | None:
    """Waarde van één deelbewijs volgens de formule van het fonds.

    readings          reeds vastgelegde slotkoersen (lijst getallen, of lijst dicts met
                      'close'), in chronologische volgorde. Ze worden hier alsnog op de
                      referentieprijs afgetopt, zodat ruwe slotkoersen bewaard mogen
                      blijven — dat is beter controleerbaar tegen een beursoverzicht.
    n_readings        totaal aantal waarnemingen over de looptijd (bv. 60).
    spot              huidige koers van de onderliggende waarde; vult de nog niet
                      vastgelegde waarnemingen. Ontbreekt hij terwijl er nog
                      waarnemingen openstaan, dan geeft de functie None terug: liever
                      geen waarde dan een verzonnen waarde.
    on_date           waarderingsdatum (standaard vandaag), bepaalt het Rendement.
    maturity_return   rendement op de eindvervaldag (bv. 0,0773 voor 7,73%). Is de
                      vervaldag bereikt, dan geldt dit in plaats van de aangroei.
    md_entries        Majorations de Dividende: [{"date": ..., "amount": ...}] per
                      deelbewijs. Keert ENGIE een dividend met majoration uit, dan
                      wordt de prestatie daarmee verhoogd. Enkel de majorations tot
                      en met de waarderingsdatum tellen mee.

    Returns dict met 'value' en alle tussenstappen, zodat elk cijfer navolgbaar is.
    """
    ref = float(reference_price)
    sub = float(subscription_price)
    n = int(n_readings)
    if n < 1:
        return None

    vals = []
    for r in (readings or []):
        c = r.get("close") if isinstance(r, dict) else r
        if c is None:
            continue
        vals.append(reading_value(c, ref))
    vals = vals[:n]
    n_known = len(vals)
    n_open = n - n_known

    fill = None
    if n_open > 0:
        if spot is None:
            return None
        fill = reading_value(spot, ref)
        vals = vals + [fill] * n_open

    average = sum(vals) / n
    participation = float(alpha) * (average - ref)

    on = _as_date(on_date) or date.today()
    start = _as_date(start_date)
    mat = _as_date(maturity_date)
    at_maturity = bool(mat and on >= mat)

    if at_maturity and maturity_return is not None:
        rendement = float(maturity_return) * sub
        days = (mat - start).days if start else None
    elif start:
        days = (on - start).days
        if days < 0:
            days = 0
        rendement = ((1.0 + float(annual_rate)) ** (days / 365.0) - 1.0) * sub
    else:
        days, rendement = None, 0.0

    md_total = 0.0
    for e in (md_entries or []):
        ed = _as_date(e.get("date")) if isinstance(e, dict) else None
        amt = float(e.get("amount", 0.0)) if isinstance(e, dict) else float(e)
        if ed is None or ed <= on:
            md_total += amt

    # Performance = de HOOGSTE van Rendement en Participation (reglement 3.12.1) —
    # niet de som. Het Rendement is een gegarandeerde bodem die alleen telt zolang
    # de gemiddelde stijging eronder blijft. Op de oprichtingsdag zelf is de waarde
    # per reglement (art. 10) exact de inschrijvingsprijs: er bestaat dan nog geen
    # waarneming en geen vervroegde uitstap, dus geen Performance.
    at_constitution = bool(start and on <= start)
    if at_constitution:
        performance, performance_src = 0.0, "oprichting"
    elif participation >= rendement:
        performance, performance_src = participation, "participatie"
    else:
        performance, performance_src = rendement, "rendement"

    return {
        "value":          round(sub + performance + md_total, 6),
        "performance":    round(performance, 6),
        "performance_source": performance_src,
        "at_constitution": at_constitution,
        "md":             round(md_total, 6),
        "subscription":   sub,
        "rendement":      round(rendement, 6),
        "participation":  round(participation, 6),
        "average":        round(average, 6),
        "reference":      ref,
        "alpha":          float(alpha),
        "n_readings":     n,
        "n_known":        n_known,
        "n_open":         n_open,
        "fill_value":     fill,
        "days_elapsed":   days,
        "at_maturity":    at_maturity,
        # Hoeveel verschuift de waarde bij €1 koersbeweging van de onderliggende
        # waarde? Dit is de 'effectieve hefboom' van vandaag, en hij daalt naarmate
        # er minder waarnemingen openstaan. Nul zodra alles vastligt: dan is de
        # waarde bepaald en beweegt ze niet meer mee. Ook nul zolang het Rendement
        # de bodem vormt (of op de oprichtingsdag): een kleine koersbeweging
        # verandert de waarde dan niet, want de Participation ligt eronder.
        "sensitivity":    round(float(alpha) * n_open / n, 6)
                          if performance_src == "participatie" else 0.0,
    }


def value_series(readings, dates, *, spots=None, **params) -> list[dict]:
    """Waardeer op meerdere datums na elkaar.

    Per datum tellen alleen de waarnemingen die op dat moment al bestonden — anders
    zou je met kennis van later rekenen en lijkt de formule beter te passen dan ze is.
    'spots' geeft per datum de koers van de onderliggende waarde; ontbreekt er een,
    dan valt die datum weg uit het resultaat.
    """
    spots = spots or {}
    rows = []
    for d in dates:
        dd = _as_date(d)
        if dd is None:
            continue
        known = [r for r in readings
                 if (_as_date(r.get("date") if isinstance(r, dict) else None) or dd) <= dd]
        res = part_value(known, spot=spots.get(dd.isoformat(), spots.get(dd)),
                         on_date=dd, **params)
        if res:
            res["date"] = dd.isoformat()
            rows.append(res)
    return rows


def compare_with_official(computed: dict, official: dict) -> dict:
    """Vergelijk berekende waarden met de officiële NAV van de beheerder.

    Dit is de enige eerlijke controle op de parameters: klopt de formule met de
    ingevulde α, referentieprijs en inschrijvingsprijs, dan liggen de berekende
    waarden bovenop de gepubliceerde NAV. Wijken ze stelselmatig af, dan klopt er een
    parameter niet — en dan is de officiële NAV de waarheid, niet de berekening.
    """
    rows, diffs = [], []
    for d in sorted(set(computed) & set(official)):
        c, o = float(computed[d]), float(official[d])
        diff = c - o
        rows.append({"date": d, "computed": round(c, 4), "official": round(o, 4),
                     "diff": round(diff, 4),
                     "diff_pct": round(diff / o * 100, 4) if o else None})
        diffs.append(abs(diff))
    n = len(diffs)
    return {
        "rows": rows,
        "n": n,
        "mean_abs_diff": round(sum(diffs) / n, 4) if n else None,
        "max_abs_diff":  round(max(diffs), 4) if n else None,
        "missing_official": sorted(set(computed) - set(official)),
        "missing_computed": sorted(set(official) - set(computed)),
    }


def fit_parameters(readings, official: dict, *, n_readings: int,
                   subscription_price: float, spots: dict,
                   alpha: float | None = None, fit_alpha: bool = False,
                   fit_subscription: bool = False,
                   start_date=None, annual_rate: float = DEFAULT_ANNUAL_RATE,
                   maturity_date=None, maturity_return: float | None = None,
                   md_entries=None,
                   ref_range=None, ref_step: float = 0.05) -> dict | None:
    """Zoek de referentieprijs (en desgewenst α en/of de inschrijvingsprijs) die het
    best bij de gepubliceerde NAV passen.

    α HOORT NORMAAL VAST TE STAAN. Hij is geen vrije parameter maar een getal uit het
    fondsreglement (16 voor de jaargang 2022, 19 voor 2018). Hem laten meebewegen
    levert altijd een iets kleinere afwijking op — een extra vrijheidsgraad past per
    definitie beter — maar het resultaat is dan geen schatting van de werkelijkheid
    meer, alleen nog een kromme die door de punten loopt. Zet fit_alpha enkel aan als
    je het reglement van je jaargang echt niet hebt.

    Het model volgt het reglement:
        NAV − majoraties = inschrijving + max(Rendement, α × (gemiddelde − referentie))
    Op datums waar de Participation boven het Rendement ligt — in de praktijk vrijwel
    elke datum zodra de koers boven de referentie noteert — is dat lineair in α en de
    inschrijvingsprijs, dus daar loopt de kleinstekwadratenschatting over; de
    gerapporteerde afwijking wordt daarna met het volledige max-model berekend. Bevat
    de NAV-reeks de oprichtingsdag, dan pint die de inschrijvingsprijs vast: de NAV
    is dan per reglement exact de inschrijvingsprijs. Dat anker is onmisbaar wanneer
    geen enkele waarneming onder de referentieprijs ligt — er wordt dan nergens
    afgetopt en alleen de combinatie (inschrijving − α × referentie) is meetbaar.
    Voor de schatting van de referentieprijs zelf telt de oprichtingsdag niet mee.
    Over de referentieprijs lopen we een raster af, dat daarna tweemaal verfijnd
    wordt rond het beste punt.

    Returns o.a. 'alpha', 'reference_price', 'subscription_price', 'rmse',
    'fitted' (welke parameters vrijgelaten zijn) en 'fixed'.
    """
    if not official or not spots:
        return None
    dates = sorted(set(official) & set(spots))
    if len(dates) < 3:
        return None

    a_fixed = None if fit_alpha else (float(alpha) if alpha is not None else None)
    if a_fixed is None and not fit_alpha:
        fit_alpha = True                      # geen α gegeven: dan toch maar schatten
    s_fixed = None if fit_subscription else float(subscription_price)

    # ── Het anker op de oprichtingsdag ──────────────────────────────────────
    # De NAV op de Date de Commencement IS de inschrijvingsprijs (reglement
    # art. 10). Dat is een METING, geen schatting — en hij is onmisbaar: zolang
    # geen enkele waarneming onder de referentieprijs duikt, wordt er nergens
    # afgetopt en hangt de waarde alleen af van (inschrijving − α × referentie).
    # Referentie- en inschrijvingsprijs zijn dan perfect onscheidbaar: elke
    # verschuiving van de één kan door de ander gecompenseerd worden, en een
    # gezamenlijke schatting glijdt naar een willekeurig punt op die richel
    # (typisch een te lage referentie mét een onzinnige, zelfs negatieve
    # inschrijvingsprijs). Het anker breekt de richel.
    warnings_out = []
    anchored = False
    start_a = _as_date(start_date)
    if start_a:
        _anchor_dates = [d for d in official if (_as_date(d) or None) and _as_date(d) <= start_a]
        if _anchor_dates:
            _anchor = float(official[max(_anchor_dates)])
            if fit_subscription:
                s_fixed, fit_subscription, anchored = _anchor, False, True
            elif abs(_anchor - float(subscription_price)) > 0.005:
                warnings_out.append(
                    f"De NAV op de oprichtingsdag ({_anchor:.4f}) wijkt af van de "
                    f"ingevulde inschrijvingsprijs ({float(subscription_price):.4f}); "
                    "per reglement zijn die gelijk. Controleer de inschrijvingsprijs.")

    def _eval(ref: float):
        """Geeft (afwijking², α, inschrijvingsprijs) voor deze referentieprijs."""
        xs, rs, ys = [], [], []
        for d in dates:
            dd = _as_date(d)
            known = [r for r in readings
                     if (_as_date(r.get("date") if isinstance(r, dict) else None) or dd) <= dd]
            # α=1 en inschrijving=1 maken de twee bouwstenen los afleesbaar:
            # 'participation' is dan (gemiddelde − referentie), 'rendement' de factor.
            base = part_value(known, n_readings=n_readings, reference_price=ref,
                              alpha=1.0, subscription_price=1.0, spot=spots[d],
                              on_date=dd, start_date=start_date, annual_rate=annual_rate,
                              maturity_date=maturity_date, maturity_return=maturity_return,
                              md_entries=md_entries)
            if base is None:
                return None
            if base.get("at_constitution"):
                continue                # NAV = inschrijvingsprijs per definitie
            xs.append(base["participation"])          # (gemiddelde − referentie)
            rs.append(base["rendement"])              # rendementsfactor (bodem)
            ys.append(float(official[d]) - base["md"])
        if len(xs) < 2:
            return None

        def _solve(idx):
            """Lineaire schatting op de participatie-tak: y = sub + α·x."""
            X = [xs[i] for i in idx]; Y = [ys[i] for i in idx]
            m = len(X)
            if fit_alpha and fit_subscription:
                sx, sy = sum(X), sum(Y)
                sxx = sum(x*x for x in X); sxy = sum(x*y for x, y in zip(X, Y))
                det = m*sxx - sx*sx
                if abs(det) < 1e-12:
                    return None
                a = (m*sxy - sx*sy) / det
                sub = (sy - a*sx) / m
            elif fit_alpha:
                denom = sum(x*x for x in X)
                if denom < 1e-12:
                    return None
                a = sum(x*(y - s_fixed) for x, y in zip(X, Y)) / denom
                sub = s_fixed
            elif fit_subscription:
                sub = sum(y - a_fixed*x for x, y in zip(X, Y)) / m
                a = a_fixed
            else:
                a, sub = a_fixed, s_fixed
            return a, sub

        # Eerst schatten alsof overal de participatie wint, daarna de datums waar
        # het Rendement de bodem vormt eruit laten en één keer opnieuw schatten.
        idx = list(range(len(xs)))
        got = _solve(idx)
        if got is None:
            return None
        a, sub = got
        idx2 = [i for i in idx if a * xs[i] >= rs[i] * sub]
        if idx2 and len(idx2) < len(idx):
            got = _solve(idx2)
            if got is not None:
                a, sub = got

        # Afwijking met het VOLLEDIGE model: y = sub + max(rendement, α·x).
        resid = sum((sub + max(rs[i] * sub, a * xs[i]) - ys[i]) ** 2
                    for i in range(len(xs))) / len(xs)
        return resid, a, sub

    if ref_range is None:
        pool = list(spots.values()) + [
            (r.get("close") if isinstance(r, dict) else r) for r in (readings or [])]
        pool = [float(v) for v in pool if v is not None]
        if not pool:
            return None
        ref_range = (min(pool) * 0.5, max(pool))

    best, lo, hi, step = None, float(ref_range[0]), float(ref_range[1]), float(ref_step)
    _coarse = []                              # (ref, afwijking²) van de grove pas
    for _pass in range(3):                    # grof, dan tweemaal verfijnen
        ref = lo
        while ref <= hi + 1e-9:
            got = _eval(ref)
            if got:
                resid, a, sub = got
                if _pass == 0:
                    _coarse.append((ref, resid))
                if best is None or resid < best["residual"]:
                    best = {"reference_price": round(ref, 4), "alpha": round(a, 4),
                            "subscription_price": round(sub, 4), "residual": resid,
                            "rmse": round(resid ** 0.5, 4), "n_points": len(dates)}
            ref += step
        if best is None:
            return None
        lo, hi = best["reference_price"] - step, best["reference_price"] + step
        step /= 10.0

    # Zonder anker én zonder aftopping is de gezamenlijke schatting van
    # referentie- en inschrijvingsprijs onbepaald: de afwijking is dan over een
    # brede strook referentieprijzen vrijwel even klein. Meet dat op de grove
    # pas en waarschuw — het "beste" punt is dan numeriek toeval.
    if fit_subscription and len(_coarse) >= 5:
        _res = [r for _, r in _coarse]
        _rmin = min(_res)
        _flat = [ref for ref, r in _coarse if r <= _rmin + max(1e-9, 0.05 * _rmin)]
        if _flat and (max(_flat) - min(_flat)) > 5 * float(ref_step):
            warnings_out.append(
                "Referentie- en inschrijvingsprijs zijn met deze gegevens niet "
                "afzonderlijk te bepalen: geen enkele waarneming ligt onder de "
                "referentieprijs, dus alleen hun combinatie is meetbaar. Neem een "
                "NAV-export mét de oprichtingsdag op (die pint de inschrijvingsprijs "
                "vast), of vul de inschrijvingsprijs uit het reglement in en laat "
                "alleen de referentieprijs zoeken.")
    if best["subscription_price"] <= 0:
        warnings_out.append(
            "De gevonden inschrijvingsprijs is nul of negatief — dat is onzinnig en "
            "wijst op de onbepaaldheid hierboven. Gebruik dit resultaat niet.")

    best["fitted"] = ([("α" if fit_alpha else None), "referentieprijs",
                       ("inschrijvingsprijs" if fit_subscription else None)])
    best["fitted"] = [f for f in best["fitted"] if f]
    best["fixed"] = [f for f in (("α" if not fit_alpha else None),
                                 ("inschrijvingsprijs" if not fit_subscription else None)) if f]
    best["anchored_subscription"] = anchored
    best["warnings"] = warnings_out
    return best
