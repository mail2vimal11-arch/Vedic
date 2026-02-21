#!/usr/bin/env python3
"""
Vimshottari Dasha Engine
=========================
Pure-logic engine for the Vimshottari Dasha system.

Inputs  : Moon's sidereal longitude (Lahiri) + birth date/time.
Outputs : A list of Maha Dasha dicts covering 120 years, each expandable
          into Antardashas and Pratyantardashas.

This module has **no** interactive prompts or print statements.  It is
designed to be imported by higher-level scripts (CLI, web, GUI).

Algorithm summary
-----------------
1. Nakshatra index   = floor(moon_longitude / 13.333333)      (0-26)
2. Nakshatra lord    = DASHA_SEQUENCE[index % 9]
3. Balance at birth  = (1 − fraction_elapsed) × lord_years
4. Maha Dashas       = birth lord (balance) then next 8 lords (full)
5. Antardashas       = 9 sub-periods per Maha Dasha, proportionally scaled
6. Pratyantardashas  = 9 sub-sub-periods per Antardasha
"""

from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

# Vimshottari Dasha lords in fixed sequence.
# Starting from Ashwini (Nakshatra #1) the lords repeat every 9 Nakshatras.
#   Ashwini→Ketu, Bharani→Venus, Krittika→Sun, … (×3 cycles = 27 stars)
DASHA_SEQUENCE = [
    "Ketu", "Venus", "Sun", "Moon", "Mars",
    "Rahu", "Jupiter", "Saturn", "Mercury",
]

# Standard Maha Dasha durations in years (total = 120).
DASHA_YEARS = {
    "Ketu":    7,
    "Venus":   20,
    "Sun":     6,
    "Moon":    10,
    "Mars":    7,
    "Rahu":    18,
    "Jupiter": 16,
    "Saturn":  19,
    "Mercury": 17,
}

TOTAL_CYCLE_YEARS = 120            # sum of all durations
NAKSHATRA_SPAN    = 13 + 20 / 60   # 13°20' = 13.33333…°
NAKSHATRA_COUNT   = 27
PADA_SPAN         = NAKSHATRA_SPAN / 4  # 3°20' per pada

# The 27 Nakshatras (name only — the lord is DASHA_SEQUENCE[index % 9]).
NAKSHATRA_NAMES = [
    "Ashwini",            # 0   Ketu
    "Bharani",            # 1   Venus
    "Krittika",           # 2   Sun
    "Rohini",             # 3   Moon
    "Mrigashira",         # 4   Mars
    "Ardra",              # 5   Rahu
    "Punarvasu",          # 6   Jupiter
    "Pushya",             # 7   Saturn
    "Ashlesha",           # 8   Mercury
    "Magha",              # 9   Ketu
    "Purva Phalguni",     # 10  Venus
    "Uttara Phalguni",    # 11  Sun
    "Hasta",              # 12  Moon
    "Chitra",             # 13  Mars
    "Swati",              # 14  Rahu
    "Vishakha",           # 15  Jupiter
    "Anuradha",           # 16  Saturn
    "Jyeshtha",           # 17  Mercury
    "Moola",              # 18  Ketu
    "Purva Ashadha",      # 19  Venus
    "Uttara Ashadha",     # 20  Sun
    "Shravana",           # 21  Moon
    "Dhanishta",          # 22  Mars
    "Shatabhisha",        # 23  Rahu
    "Purva Bhadrapada",   # 24  Jupiter
    "Uttara Bhadrapada",  # 25  Saturn
    "Revati",             # 26  Mercury
]


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 2 — Nakshatra Calculation
# ═══════════════════════════════════════════════════════════════════════════

def calc_nakshatra(moon_longitude):
    """
    Determine the birth Nakshatra from the Moon's sidereal (Lahiri)
    longitude.

    Divides ``moon_longitude`` by 13.333333 (13°20') to obtain the
    Nakshatra index (0-26).

    Returns
    -------
    dict
        index             : int 0-26
        number            : int 1-27 (human-friendly)
        name              : str  e.g. "Ashwini"
        lord              : str  Vimshottari lord for this Nakshatra
        pada              : int 1-4
        deg_traversed     : float  degrees already traversed in this Nakshatra
        deg_remaining     : float  degrees left in this Nakshatra
        fraction_elapsed  : float  0.0–1.0
        fraction_remaining: float  0.0–1.0
    """
    moon_longitude = moon_longitude % 360.0  # normalise

    index = int(moon_longitude / NAKSHATRA_SPAN)
    if index >= NAKSHATRA_COUNT:
        index = NAKSHATRA_COUNT - 1           # clamp at 360° edge

    deg_traversed  = moon_longitude - (index * NAKSHATRA_SPAN)
    deg_remaining  = NAKSHATRA_SPAN - deg_traversed
    frac_elapsed   = deg_traversed / NAKSHATRA_SPAN
    frac_remaining = 1.0 - frac_elapsed

    pada = min(int(deg_traversed / PADA_SPAN) + 1, 4)

    lord = DASHA_SEQUENCE[index % 9]

    return {
        "index":              index,
        "number":             index + 1,
        "name":               NAKSHATRA_NAMES[index],
        "lord":               lord,
        "pada":               pada,
        "deg_traversed":      deg_traversed,
        "deg_remaining":      deg_remaining,
        "fraction_elapsed":   frac_elapsed,
        "fraction_remaining": frac_remaining,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 5 — Balance of Dasha at birth
# ═══════════════════════════════════════════════════════════════════════════

def calc_balance(nakshatra):
    """
    Compute the remaining Maha Dasha time at birth.

    The Moon has traversed ``fraction_elapsed`` of its Nakshatra, so
    that same fraction of the lord's total Maha Dasha has already
    elapsed.  The **remaining** fraction gives the balance.

    Parameters
    ----------
    nakshatra : dict
        Output from ``calc_nakshatra()``.

    Returns
    -------
    dict
        lord           : str   starting Maha Dasha planet
        total_years    : int   lord's full Maha Dasha span
        balance_years  : float remaining years at birth
        balance_days   : float remaining days at birth
        elapsed_years  : float portion already elapsed before birth
    """
    lord          = nakshatra["lord"]
    total_years   = DASHA_YEARS[lord]
    frac_remain   = nakshatra["fraction_remaining"]

    balance_years = total_years * frac_remain
    balance_days  = balance_years * 365.25
    elapsed_years = total_years - balance_years

    return {
        "lord":          lord,
        "total_years":   total_years,
        "balance_years": balance_years,
        "balance_days":  balance_days,
        "elapsed_years": elapsed_years,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Helper — lord sequence generator
# ═══════════════════════════════════════════════════════════════════════════

def _lord_iter(start_lord):
    """Yield lords in Vimshottari order starting from *start_lord*, cycling."""
    start = DASHA_SEQUENCE.index(start_lord)
    i = start
    while True:
        yield DASHA_SEQUENCE[i % 9]
        i += 1


def _years_to_ymd(years):
    """Convert fractional years to a (years, months, days) tuple."""
    y = int(years)
    remainder_months = (years - y) * 12
    m = int(remainder_months)
    d = int((remainder_months - m) * 30.4375)
    return y, m, d


# ═══════════════════════════════════════════════════════════════════════════
#  STEP 6 — get_dasha_timeline()   *** PRIMARY PUBLIC API ***
# ═══════════════════════════════════════════════════════════════════════════

def get_dasha_timeline(moon_longitude, birth_datetime):
    """
    Generate the full Vimshottari Maha Dasha timeline for a 120-year cycle.

    This is the **main entry point** of the engine.

    Parameters
    ----------
    moon_longitude : float
        Moon's sidereal longitude in degrees (Lahiri Ayanamsa, 0–360).
    birth_datetime : datetime
        Date and time of birth.

    Returns
    -------
    list of dict — one dict per Maha Dasha (9 entries total), each with:
        'dasha_lord'  : str       planet name
        'start_date'  : datetime
        'end_date'    : datetime
        'duration_years' : float
        'duration_ymd'   : tuple (years, months, days)
        'is_birth_dasha' : bool   True for the first (partial) Dasha
        'nakshatra'   : dict      birth Nakshatra info (same for all entries)
        'balance'     : dict      birth balance info   (same for all entries)
    """
    # Step 2: find birth Nakshatra
    nakshatra = calc_nakshatra(moon_longitude)

    # Step 5: balance of first Dasha
    balance = calc_balance(nakshatra)

    # Step 3+4: walk the Dasha sequence
    lords = _lord_iter(balance["lord"])
    timeline = []
    cursor = birth_datetime

    for i in range(9):
        lord = next(lords)
        full_years = DASHA_YEARS[lord]

        if i == 0:
            # First period: only the remaining balance
            dasha_years = balance["balance_years"]
        else:
            dasha_years = float(full_years)

        dasha_days = dasha_years * 365.25
        end_date   = cursor + timedelta(days=dasha_days)

        timeline.append({
            "dasha_lord":     lord,
            "start_date":     cursor,
            "end_date":       end_date,
            "duration_years": dasha_years,
            "duration_ymd":   _years_to_ymd(dasha_years),
            "is_birth_dasha": (i == 0),
            "nakshatra":      nakshatra,
            "balance":        balance,
        })

        cursor = end_date

    return timeline


# ═══════════════════════════════════════════════════════════════════════════
#  Antardasha (Bhukti) expansion
# ═══════════════════════════════════════════════════════════════════════════

def get_antardashas(maha_dasha_entry):
    """
    Expand a single Maha Dasha into its 9 Antardasha (Bhukti) sub-periods.

    The sub-period sequence starts from the Maha Dasha lord itself, then
    follows the standard Vimshottari order.

    Duration formula (full):
        antar_days = (maha_lord_years × antar_lord_years / 120) × 365.25

    If the Maha Dasha is the birth Dasha (partial), all Antardashas are
    proportionally scaled by (actual_days / full_days).

    Parameters
    ----------
    maha_dasha_entry : dict
        One element from the list returned by ``get_dasha_timeline()``.

    Returns
    -------
    list of dict (9 entries), each with:
        'maha_lord'      : str
        'antar_lord'     : str
        'start_date'     : datetime
        'end_date'       : datetime
        'duration_days'  : float
        'duration_years' : float
        'duration_ymd'   : tuple (y, m, d)
    """
    maha_lord      = maha_dasha_entry["dasha_lord"]
    maha_years     = DASHA_YEARS[maha_lord]
    actual_days    = maha_dasha_entry["duration_years"] * 365.25
    full_days      = maha_years * 365.25
    scale          = actual_days / full_days if full_days > 0 else 1.0

    lords = _lord_iter(maha_lord)
    antardashas = []
    cursor = maha_dasha_entry["start_date"]

    for _ in range(9):
        antar_lord     = next(lords)
        antar_years_f  = DASHA_YEARS[antar_lord]

        # Full (un-scaled) Antardasha duration
        full_antar_days = (maha_years * antar_years_f / TOTAL_CYCLE_YEARS) * 365.25

        # Scale for partial birth Dasha
        antar_days  = full_antar_days * scale
        antar_years = antar_days / 365.25
        end_date    = cursor + timedelta(days=antar_days)

        antardashas.append({
            "maha_lord":      maha_lord,
            "antar_lord":     antar_lord,
            "start_date":     cursor,
            "end_date":       end_date,
            "duration_days":  antar_days,
            "duration_years": antar_years,
            "duration_ymd":   _years_to_ymd(antar_years),
        })

        cursor = end_date

    return antardashas


# ═══════════════════════════════════════════════════════════════════════════
#  Pratyantardasha expansion
# ═══════════════════════════════════════════════════════════════════════════

def get_pratyantardashas(antar_entry):
    """
    Expand a single Antardasha into its 9 Pratyantardasha sub-sub-periods.

    Parameters
    ----------
    antar_entry : dict
        One element from ``get_antardashas()``.

    Returns
    -------
    list of dict (9 entries), each with:
        'maha_lord'       : str
        'antar_lord'      : str
        'pratyantar_lord' : str
        'start_date'      : datetime
        'end_date'        : datetime
        'duration_days'   : float
    """
    maha_lord   = antar_entry["maha_lord"]
    antar_lord  = antar_entry["antar_lord"]
    antar_years = DASHA_YEARS[antar_lord]
    actual_days = antar_entry["duration_days"]
    maha_years  = DASHA_YEARS[maha_lord]

    full_antar_days = (maha_years * antar_years / TOTAL_CYCLE_YEARS) * 365.25
    scale = actual_days / full_antar_days if full_antar_days > 0 else 1.0

    lords = _lord_iter(antar_lord)
    pratyantars = []
    cursor = antar_entry["start_date"]

    for _ in range(9):
        prat_lord  = next(lords)
        prat_years = DASHA_YEARS[prat_lord]

        full_prat_days = full_antar_days * prat_years / TOTAL_CYCLE_YEARS
        prat_days      = full_prat_days * scale
        end_date       = cursor + timedelta(days=prat_days)

        pratyantars.append({
            "maha_lord":       maha_lord,
            "antar_lord":      antar_lord,
            "pratyantar_lord": prat_lord,
            "start_date":      cursor,
            "end_date":        end_date,
            "duration_days":   prat_days,
        })

        cursor = end_date

    return pratyantars


# ═══════════════════════════════════════════════════════════════════════════
#  Convenience — find active periods for any query date
# ═══════════════════════════════════════════════════════════════════════════

def find_active_periods(timeline, query_date):
    """
    Given a Maha Dasha timeline and a date, find the active Maha Dasha,
    Antardasha, and Pratyantardasha at that moment.

    Parameters
    ----------
    timeline : list
        Output from ``get_dasha_timeline()``.
    query_date : datetime

    Returns
    -------
    dict with 'maha', 'antar', 'pratyantar' keys, or None.
    """
    for md in timeline:
        if md["start_date"] <= query_date < md["end_date"]:
            antardashas = get_antardashas(md)
            for ad in antardashas:
                if ad["start_date"] <= query_date < ad["end_date"]:
                    pratyantars = get_pratyantardashas(ad)
                    for pd in pratyantars:
                        if pd["start_date"] <= query_date < pd["end_date"]:
                            return {"maha": md, "antar": ad, "pratyantar": pd}
                    return {"maha": md, "antar": ad, "pratyantar": pratyantars[-1]}
            return {"maha": md, "antar": antardashas[-1], "pratyantar": None}
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  Convenience — compute Moon longitude via pyswisseph (Lahiri)
# ═══════════════════════════════════════════════════════════════════════════

def compute_moon_longitude(year, month, day, hour, minute, second,
                           utc_offset):
    """
    Compute the Moon's sidereal longitude using pyswisseph + Lahiri
    Ayanamsa.  This is a convenience wrapper so callers don't need to
    interact with swisseph directly.

    Parameters
    ----------
    year, month, day   : int
    hour, minute, second : int   (local time)
    utc_offset         : float   hours ahead of UTC (e.g. 5.5 for IST)

    Returns
    -------
    float  Moon's sidereal longitude (0-360°).
    """
    import swisseph as swe
    import os

    ephe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")
    swe.set_ephe_path(ephe_path)
    swe.set_sid_mode(swe.SIDM_LAHIRI)

    decimal_hour_ut = hour + minute / 60.0 + second / 3600.0 - utc_offset
    jd = swe.julday(year, month, day, decimal_hour_ut)

    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    pos, _ = swe.calc_ut(jd, swe.MOON, flags)

    return pos[0]


# ═══════════════════════════════════════════════════════════════════════════
#  JSON-compatible nested report
# ═══════════════════════════════════════════════════════════════════════════

def _dt_to_str(dt):
    """Convert a datetime to an ISO-8601 string for JSON serialisation."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_full_dasha_report(birth_date, moon_lon):
    """
    Compute the complete Vimshottari Dasha report with nested Antardashas,
    returned as a JSON-serialisable Python structure.

    This function:
      1. Calculates the balance of Dasha at birth from the Moon's
         fractional position in its Nakshatra.
      2. For each of the 9 Maha Dashas, nests the 9 corresponding
         Antardashas with precise start/end dates.

    Antardasha formula:
        duration = (MD_years × AD_years) / 120 years
        e.g. Venus MD – Sun AD  = (20 × 6) / 120 = 1.0 year
        Scaled proportionally for the birth (partial) Maha Dasha.

    Antardasha sequence: starts from the Maha Dasha lord itself,
    then follows Ketu→Venus→Sun→Moon→Mars→Rahu→Jupiter→Saturn→Mercury
    (looping back to Ketu).

    Date math uses ``timedelta`` objects to account for leap years.

    Parameters
    ----------
    birth_date : datetime
        Date and time of birth.
    moon_lon : float
        Moon's sidereal longitude (Lahiri Ayanamsa, 0–360°).

    Returns
    -------
    dict (JSON-compatible) with:
        'birth_date'       : str   ISO date
        'moon_longitude'   : float
        'nakshatra'        : dict  (name, number, pada, lord, fractions)
        'dasha_balance'    : dict  (lord, balance years/days, ymd)
        'maha_dashas'      : list of 9 dicts, each containing:
            'maha_dasha_lord'  : str
            'start_date'       : str
            'end_date'         : str
            'duration_years'   : float
            'duration_ymd'     : dict {years, months, days}
            'is_birth_dasha'   : bool
            'antardashas'      : list of 9 dicts:
                'antar_dasha_lord' : str
                'start_date'       : str
                'end_date'         : str
                'duration_days'    : float
                'duration_years'   : float
                'duration_ymd'     : dict {years, months, days}
    """
    # Nakshatra + balance
    nakshatra = calc_nakshatra(moon_lon)
    balance   = calc_balance(nakshatra)

    # Full timeline
    timeline = get_dasha_timeline(moon_lon, birth_date)

    # Build nested structure
    maha_list = []
    for md in timeline:
        antars_raw = get_antardashas(md)
        antar_list = []
        for ad in antars_raw:
            ay, am, adx = ad["duration_ymd"]
            pratys_raw = get_pratyantardashas(ad)
            praty_list = []
            for pd in pratys_raw:
                pd_y, pd_m, pd_d = _years_to_ymd(pd["duration_days"] / 365.25)
                praty_list.append({
                    "pratyantar_lord": pd["pratyantar_lord"],
                    "start_date":     _dt_to_str(pd["start_date"]),
                    "end_date":       _dt_to_str(pd["end_date"]),
                    "duration_days":  round(pd["duration_days"], 2),
                    "duration_ymd":   {"years": pd_y, "months": pd_m, "days": pd_d},
                })
            antar_list.append({
                "antar_dasha_lord":  ad["antar_lord"],
                "start_date":        _dt_to_str(ad["start_date"]),
                "end_date":          _dt_to_str(ad["end_date"]),
                "duration_days":     round(ad["duration_days"], 2),
                "duration_years":    round(ad["duration_years"], 4),
                "duration_ymd":      {"years": ay, "months": am, "days": adx},
                "pratyantardashas":  praty_list,
            })

        my, mm, md_d = md["duration_ymd"]
        maha_list.append({
            "maha_dasha_lord": md["dasha_lord"],
            "start_date":      _dt_to_str(md["start_date"]),
            "end_date":        _dt_to_str(md["end_date"]),
            "duration_years":  round(md["duration_years"], 4),
            "duration_ymd":    {"years": my, "months": mm, "days": md_d},
            "is_birth_dasha":  md["is_birth_dasha"],
            "antardashas":     antar_list,
        })

    by, bm, bd = _years_to_ymd(balance["balance_years"])

    return {
        "birth_date":     _dt_to_str(birth_date),
        "moon_longitude": round(moon_lon, 4),
        "nakshatra": {
            "name":               nakshatra["name"],
            "number":             nakshatra["number"],
            "pada":               nakshatra["pada"],
            "lord":               nakshatra["lord"],
            "deg_traversed":      round(nakshatra["deg_traversed"], 4),
            "deg_remaining":      round(nakshatra["deg_remaining"], 4),
            "fraction_elapsed":   round(nakshatra["fraction_elapsed"], 6),
            "fraction_remaining": round(nakshatra["fraction_remaining"], 6),
        },
        "dasha_balance": {
            "lord":          balance["lord"],
            "total_years":   balance["total_years"],
            "balance_years": round(balance["balance_years"], 4),
            "balance_days":  round(balance["balance_days"], 2),
            "balance_ymd":   {"years": by, "months": bm, "days": bd},
        },
        "maha_dashas": maha_list,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  CLI demo (only when run directly)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # --- Example: Chennai, 15 June 1990, 10:30 AM IST --------------------
    BIRTH = datetime(1990, 6, 15, 10, 30, 0)
    MOON  = compute_moon_longitude(1990, 6, 15, 10, 30, 0, utc_offset=5.5)

    print(f"Moon sidereal longitude : {MOON:.4f}°")

    # Step 2: Nakshatra
    nak = calc_nakshatra(MOON)
    print(f"Birth Nakshatra         : {nak['name']} (#{nak['number']}, "
          f"Pada {nak['pada']})")
    print(f"Nakshatra lord          : {nak['lord']}")
    print(f"Traversed / Remaining   : {nak['deg_traversed']:.4f}° / "
          f"{nak['deg_remaining']:.4f}° of {NAKSHATRA_SPAN:.4f}°")

    # Step 5: Balance
    bal = calc_balance(nak)
    y, m, d = _years_to_ymd(bal["balance_years"])
    print(f"Dasha balance at birth  : {y}y {m}m {d}d  "
          f"({bal['balance_years']:.4f} years)")

    # Step 6: Full 120-year timeline
    timeline = get_dasha_timeline(MOON, BIRTH)

    print(f"\n{'='*72}")
    print(f" MAHA DASHA TIMELINE  (120-year Vimshottari cycle)")
    print(f"{'='*72}")
    print(f" {'#':<3} {'Dasha Lord':<10} {'Start':<14} {'End':<14} "
          f"{'Duration':<16} {'Birth?'}")
    print(f"{'-'*72}")

    for i, entry in enumerate(timeline, 1):
        y, m, d = entry["duration_ymd"]
        tag = "<-- birth" if entry["is_birth_dasha"] else ""
        print(f" {i:<3} {entry['dasha_lord']:<10} "
              f"{entry['start_date'].strftime('%d-%b-%Y'):<14} "
              f"{entry['end_date'].strftime('%d-%b-%Y'):<14} "
              f"{y}y {m}m {d}d{'':<8} {tag}")

    # Antardasha breakdown for the birth Maha Dasha
    birth_md = timeline[0]
    antars = get_antardashas(birth_md)

    print(f"\n{'='*72}")
    print(f" ANTARDASHAS within {birth_md['dasha_lord']} Maha Dasha")
    print(f"{'='*72}")
    print(f" {'#':<3} {'Antar Lord':<12} {'Start':<14} {'End':<14} "
          f"{'Days':>8}  {'Duration'}")
    print(f"{'-'*72}")

    for i, ad in enumerate(antars, 1):
        y, m, d = ad["duration_ymd"]
        print(f" {i:<3} {ad['antar_lord']:<12} "
              f"{ad['start_date'].strftime('%d-%b-%Y'):<14} "
              f"{ad['end_date'].strftime('%d-%b-%Y'):<14} "
              f"{ad['duration_days']:>8.1f}  {y}y {m}m {d}d")

    # Show what's active right now
    now = datetime.now()
    active = find_active_periods(timeline, now)
    if active:
        print(f"\n Active right now ({now.strftime('%d-%b-%Y')}):")
        print(f"   Maha Dasha   : {active['maha']['dasha_lord']}")
        print(f"   Antardasha   : {active['antar']['antar_lord']}")
        if active["pratyantar"]:
            print(f"   Pratyantardasha : {active['pratyantar']['pratyantar_lord']}")

    # --- JSON report demo -------------------------------------------------
    import json
    report = get_full_dasha_report(BIRTH, MOON)
    print(f"\n{'='*72}")
    print(" get_full_dasha_report() — JSON preview (first Maha Dasha):")
    print(f"{'='*72}")
    # Print just the first Maha Dasha with nested Antardashas
    first = report["maha_dashas"][0]
    print(json.dumps(first, indent=2))

    # Verify Antardasha formula: Venus MD – Sun AD = (20×6)/120 = 1.0 year
    venus_tl = get_dasha_timeline(MOON, BIRTH)
    for md in venus_tl:
        if md["dasha_lord"] == "Venus" and not md["is_birth_dasha"]:
            venus_ads = get_antardashas(md)
            for ad in venus_ads:
                if ad["antar_lord"] == "Sun":
                    print(f"\n Verification: Venus MD – Sun AD = "
                          f"{ad['duration_years']:.4f} years "
                          f"(expected: {20*6/120:.1f})")
            break

    print()
