"""
fcpe_pricing.py — waardering van FCPE-hefboomfondsen volgens de formule van het fonds
("Participation à la Hausse Moyenne Protégée").

WAAROM EEN APARTE METHODE
De bestaande afgeleide koers rekent lineair op de SPOTKOERS van de onderliggende
waarde: koers = basis + multiplicator × (spot − referentie). Voor de Link
Classic/Liberty-fondsen klopt dat exact (één deelbewijs = één aandeel), maar voor de
Multiple-fondsen niet. Die hangen niet aan de koers van vandaag, maar aan het
GEMIDDELDE van zestig maandelijkse waarnemingen, elk afgetopt op een ondergrens:

    Deelbewijswaarde = Prix de Souscription + Rendement + Participation
    Participation     = α × (gemiddelde van de Relevés − Prix de Référence)
    Relevé i          = max(slotkoers op waarnemingsdatum i, Prix de Référence)

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
    "monthly_reading_dates", "reading_value", "part_value",
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

def monthly_reading_dates(first: str | date, count: int) -> list[str]:
    """Waarnemingsdata: de laatste dag van elke maand, 'count' maanden lang, te
    beginnen met de maand van 'first'.

    Het reglement zegt "de laatste beursdag van de maand". Die kan een dag eerder
    vallen dan de laatste kalenderdag (weekend, feestdag). Deze functie geeft de
    laatste KALENDERDAG en is dus enkel een vertrekpunt: de werkelijke waarnemingen
    worden per stuk bewaard en mogen afwijken. Voor de waardering telt alleen de
    bewaarde waarde, niet de datum waarop ze theoretisch hoorde te vallen.
    """
    d = _as_date(first)
    if d is None or count < 1:
        return []
    out, y, m = [], d.year, d.month
    for _ in range(count):
        out.append(date(y, m, calendar.monthrange(y, m)[1]).isoformat())
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

    return {
        "value":          round(sub + rendement + participation + md_total, 6),
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
        # waarde bepaald en beweegt ze niet meer mee.
        "sensitivity":    round(float(alpha) * n_open / n, 6),
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
                   start_date=None, annual_rate: float = DEFAULT_ANNUAL_RATE,
                   ref_range=None, ref_step: float = 0.05) -> dict | None:
    """Zoek α en de referentieprijs die het best bij de gepubliceerde NAV passen.

    Bedoeld voor het geval dat je de parameters van je jaargang niet bij de hand hebt.
    Voor een vaste referentieprijs is de waarde lineair in α, dus die volgt in één
    stap uit een kleinstekwadratenschatting; over de referentieprijs zelf lopen we een
    raster af. Het resultaat is een SCHATTING: lees altijd de gevonden afwijking mee,
    en houd de parameters uit je fondsdocumenten aan wanneer je die hebt.
    """
    if not official or not spots:
        return None
    dates = sorted(set(official) & set(spots))
    if len(dates) < 3:
        return None

    if ref_range is None:
        lo = min(min(spots.values()), min(
            (r.get("close") if isinstance(r, dict) else r) for r in readings) if readings else min(spots.values()))
        hi = max(max(spots.values()), max(
            (r.get("close") if isinstance(r, dict) else r) for r in readings) if readings else max(spots.values()))
        ref_range = (lo * 0.5, hi)

    best = None
    ref = float(ref_range[0])
    while ref <= float(ref_range[1]) + 1e-9:
        xs, ys = [], []
        ok = True
        for d in dates:
            dd = _as_date(d)
            known = [r for r in readings
                     if (_as_date(r.get("date") if isinstance(r, dict) else None) or dd) <= dd]
            base = part_value(known, n_readings=n_readings, reference_price=ref,
                              alpha=1.0, subscription_price=subscription_price,
                              spot=spots[d], on_date=dd, start_date=start_date,
                              annual_rate=annual_rate)
            if base is None:
                ok = False
                break
            # value = sub + rendement + alpha * (avg - ref); bij alpha=1 is
            # participation net (avg - ref), dus dat is de verklarende variabele.
            xs.append(base["participation"])
            ys.append(float(official[d]) - base["subscription"] - base["rendement"])
        if ok and xs:
            denom = sum(x * x for x in xs)
            if denom > 1e-12:
                alpha = sum(x * y for x, y in zip(xs, ys)) / denom
                resid = sum((alpha * x - y) ** 2 for x, y in zip(xs, ys)) / len(xs)
                if best is None or resid < best["residual"]:
                    best = {"reference_price": round(ref, 4), "alpha": round(alpha, 4),
                            "residual": resid, "rmse": round(resid ** 0.5, 4),
                            "n_points": len(xs)}
        ref += ref_step
    return best
