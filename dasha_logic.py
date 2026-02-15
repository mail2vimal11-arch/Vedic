#!/usr/bin/env python3
"""
Vimshottari Dasha Calculator
=============================
Calculates the full Vimshottari Dasha system (120-year cycle) based on the
Moon's sidereal longitude at birth, using Lahiri Ayanamsa via pyswisseph.

Features:
    - Determines birth Nakshatra from the Moon's precise sidereal position
    - Identifies the starting Maha Dasha lord
    - Computes the balance of Dasha remaining at birth
    - Generates all 9 Maha Dashas with exact start/end dates
    - Breaks any Maha Dasha into its 9 Antardasha sub-periods
    - Breaks any Antardasha into its 9 Pratyantardasha sub-sub-periods

Usage:
    python dasha_logic.py

Requires:
    - pyswisseph
    - Ephemeris files (.se1) in the ./ephe directory
"""

import os
from datetime import datetime, timedelta

import swisseph as swe


# ---------------------------------------------------------------------------
# Ephemeris path
# ---------------------------------------------------------------------------

EPHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")


# ---------------------------------------------------------------------------
# Vimshottari Dasha constants
# ---------------------------------------------------------------------------

# The 9 Dasha lords in Vimshottari sequence, with their Maha Dasha
# durations in years.  Total = 120 years.
DASHA_LORDS = [
    ("Ketu",    7),
    ("Venus",   20),
    ("Sun",     6),
    ("Moon",    10),
    ("Mars",    7),
    ("Rahu",    18),
    ("Jupiter", 16),
    ("Saturn",  19),
    ("Mercury", 17),
]

TOTAL_DASHA_YEARS = 120  # sum of all Maha Dasha durations

# Quick lookup: lord name → total Maha Dasha years
LORD_YEARS = {name: years for name, years in DASHA_LORDS}

# The Vimshottari sequence as just the lord names (used for cycling)
DASHA_SEQUENCE = [name for name, _ in DASHA_LORDS]

# ---------------------------------------------------------------------------
# Nakshatra data
# ---------------------------------------------------------------------------

# Each Nakshatra spans 13°20' = 13.33333…° of sidereal longitude.
NAKSHATRA_SPAN = 13.0 + 20.0 / 60.0  # 13.333... degrees

# The 27 Nakshatras in order, starting from 0° Aries (Mesha).
# Each is paired with its Vimshottari Dasha lord.
# The lords cycle: Ketu → Venus → Sun → Moon → Mars → Rahu → Jupiter →
#                  Saturn → Mercury, repeating 3 times for 27 Nakshatras.
NAKSHATRAS = [
    # --- Cycle 1 (Aries / Taurus / Gemini) ---
    ("Ashwini",           "Ketu"),      #  1:  0°00' –  13°20' Aries
    ("Bharani",           "Venus"),     #  2: 13°20' –  26°40' Aries
    ("Krittika",          "Sun"),       #  3: 26°40' Aries – 10°00' Taurus
    ("Rohini",            "Moon"),      #  4: 10°00' –  23°20' Taurus
    ("Mrigashira",        "Mars"),      #  5: 23°20' Taurus – 6°40' Gemini
    ("Ardra",             "Rahu"),      #  6:  6°40' –  20°00' Gemini
    ("Punarvasu",         "Jupiter"),   #  7: 20°00' Gemini – 3°20' Cancer
    ("Pushya",            "Saturn"),    #  8:  3°20' –  16°40' Cancer
    ("Ashlesha",          "Mercury"),   #  9: 16°40' –  30°00' Cancer
    # --- Cycle 2 (Leo / Virgo / Libra) ---
    ("Magha",             "Ketu"),      # 10:  0°00' –  13°20' Leo
    ("Purva Phalguni",    "Venus"),     # 11: 13°20' –  26°40' Leo
    ("Uttara Phalguni",   "Sun"),       # 12: 26°40' Leo – 10°00' Virgo
    ("Hasta",             "Moon"),      # 13: 10°00' –  23°20' Virgo
    ("Chitra",            "Mars"),      # 14: 23°20' Virgo – 6°40' Libra
    ("Swati",             "Rahu"),      # 15:  6°40' –  20°00' Libra
    ("Vishakha",          "Jupiter"),   # 16: 20°00' Libra – 3°20' Scorpio
    ("Anuradha",          "Saturn"),    # 17:  3°20' –  16°40' Scorpio
    ("Jyeshtha",          "Mercury"),   # 18: 16°40' –  30°00' Scorpio
    # --- Cycle 3 (Sagittarius / Capricorn / Aquarius / Pisces) ---
    ("Moola",             "Ketu"),      # 19:  0°00' –  13°20' Sagittarius
    ("Purva Ashadha",     "Venus"),     # 20: 13°20' –  26°40' Sagittarius
    ("Uttara Ashadha",    "Sun"),       # 21: 26°40' Sag – 10°00' Capricorn
    ("Shravana",          "Moon"),      # 22: 10°00' –  23°20' Capricorn
    ("Dhanishta",         "Mars"),      # 23: 23°20' Capricorn – 6°40' Aquarius
    ("Shatabhisha",       "Rahu"),      # 24:  6°40' –  20°00' Aquarius
    ("Purva Bhadrapada",  "Jupiter"),   # 25: 20°00' Aquarius – 3°20' Pisces
    ("Uttara Bhadrapada", "Saturn"),    # 26:  3°20' –  16°40' Pisces
    ("Revati",            "Mercury"),   # 27: 16°40' –  30°00' Pisces
]

# Nakshatra padas (quarters): each Nakshatra has 4 padas of 3°20' each
PADA_SPAN = NAKSHATRA_SPAN / 4.0  # 3.333... degrees


# ---------------------------------------------------------------------------
# Moon longitude via pyswisseph
# ---------------------------------------------------------------------------

def get_moon_longitude(year, month, day, hour, minute, second, utc_offset):
    """
    Compute the Moon's precise sidereal longitude using Swiss Ephemeris
    with Lahiri Ayanamsa.

    Parameters
    ----------
    year, month, day : int
    hour, minute, second : int
        Local birth time.
    utc_offset : float
        Hours ahead of UTC (e.g. 5.5 for IST).

    Returns
    -------
    float
        Moon's sidereal longitude in degrees (0–360).
    """
    swe.set_ephe_path(EPHE_PATH)
    swe.set_sid_mode(swe.SIDM_LAHIRI)

    decimal_hour_ut = hour + minute / 60.0 + second / 3600.0 - utc_offset
    jd = swe.julday(year, month, day, decimal_hour_ut)

    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    pos, _ = swe.calc_ut(jd, swe.MOON, flags)

    return pos[0]  # sidereal longitude


# ---------------------------------------------------------------------------
# Nakshatra determination
# ---------------------------------------------------------------------------

def get_nakshatra(moon_longitude):
    """
    Determine the Nakshatra and pada from the Moon's sidereal longitude.

    Parameters
    ----------
    moon_longitude : float
        Moon's sidereal longitude (0–360).

    Returns
    -------
    dict with:
        'index'          : int 0-26 (Nakshatra number minus 1)
        'number'         : int 1-27
        'name'           : Nakshatra name (e.g. "Ashwini")
        'lord'           : Vimshottari Dasha lord (e.g. "Ketu")
        'pada'           : int 1-4
        'deg_in_nakshatra' : degrees traversed within this Nakshatra
        'fraction_elapsed' : fraction (0-1) of this Nakshatra completed
    """
    idx = int(moon_longitude / NAKSHATRA_SPAN)
    idx = min(idx, 26)  # clamp for 360° edge case

    deg_in_nak = moon_longitude - (idx * NAKSHATRA_SPAN)
    fraction_elapsed = deg_in_nak / NAKSHATRA_SPAN

    pada = int(deg_in_nak / PADA_SPAN) + 1
    pada = min(pada, 4)

    name, lord = NAKSHATRAS[idx]

    return {
        "index": idx,
        "number": idx + 1,
        "name": name,
        "lord": lord,
        "pada": pada,
        "deg_in_nakshatra": deg_in_nak,
        "fraction_elapsed": fraction_elapsed,
    }


# ---------------------------------------------------------------------------
# Dasha balance at birth
# ---------------------------------------------------------------------------

def get_dasha_balance(nakshatra_info):
    """
    Calculate the balance of the birth Maha Dasha remaining at birth.

    The Moon has already traversed some fraction of its birth Nakshatra.
    The remaining fraction gives the remaining time in the ruling lord's
    Maha Dasha period.

    Parameters
    ----------
    nakshatra_info : dict
        Output from ``get_nakshatra()``.

    Returns
    -------
    dict with:
        'lord'              : Starting Maha Dasha lord name
        'total_years'       : Lord's full Maha Dasha duration
        'elapsed_fraction'  : Fraction of Dasha already elapsed at birth
        'balance_years'     : Remaining Dasha years (float)
        'balance_days'      : Remaining Dasha days (float)
    """
    lord = nakshatra_info["lord"]
    total_years = LORD_YEARS[lord]
    fraction_elapsed = nakshatra_info["fraction_elapsed"]
    fraction_remaining = 1.0 - fraction_elapsed

    balance_years = total_years * fraction_remaining
    balance_days = balance_years * 365.25

    return {
        "lord": lord,
        "total_years": total_years,
        "elapsed_fraction": fraction_elapsed,
        "balance_years": balance_years,
        "balance_days": balance_days,
    }


# ---------------------------------------------------------------------------
# Maha Dasha periods
# ---------------------------------------------------------------------------

def _lord_sequence_from(start_lord):
    """
    Yield the Vimshottari lord sequence starting from ``start_lord``,
    cycling infinitely.
    """
    start_idx = DASHA_SEQUENCE.index(start_lord)
    i = start_idx
    while True:
        yield DASHA_SEQUENCE[i % 9]
        i += 1


def generate_maha_dashas(birth_date, nakshatra_info):
    """
    Generate all 9 Maha Dasha periods covering the full 120-year cycle,
    starting from the birth Dasha lord with the correct balance.

    Parameters
    ----------
    birth_date : datetime
        Date and time of birth.
    nakshatra_info : dict
        Output from ``get_nakshatra()``.

    Returns
    -------
    list of dict, each with:
        'lord'       : Planet name
        'years'      : Duration of this Maha Dasha in years (float)
        'days'       : Duration in days (float)
        'start_date' : datetime
        'end_date'   : datetime
    """
    balance = get_dasha_balance(nakshatra_info)
    lord_gen = _lord_sequence_from(balance["lord"])

    dashas = []
    current_date = birth_date

    for i in range(9):
        lord = next(lord_gen)
        total_years = LORD_YEARS[lord]

        if i == 0:
            # First Dasha: only the remaining balance
            dasha_years = balance["balance_years"]
        else:
            dasha_years = float(total_years)

        dasha_days = dasha_years * 365.25
        end_date = current_date + timedelta(days=dasha_days)

        dashas.append({
            "lord": lord,
            "years": dasha_years,
            "days": dasha_days,
            "start_date": current_date,
            "end_date": end_date,
        })

        current_date = end_date

    return dashas


# ---------------------------------------------------------------------------
# Antardasha (Bhukti) sub-periods
# ---------------------------------------------------------------------------

def generate_antardashas(maha_dasha):
    """
    Break a single Maha Dasha into its 9 Antardasha (Bhukti) sub-periods.

    The Antardasha sequence starts from the Maha Dasha lord itself, then
    follows the standard Vimshottari order.

    Duration of each Antardasha =
        (Maha lord years × Antar lord years) / 120 × (actual Maha duration
        / full Maha lord years)

    This proportional scaling ensures that if the Maha Dasha is the birth
    Dasha (with partial balance), the Antardashas are scaled down too.

    Parameters
    ----------
    maha_dasha : dict
        One element from the list returned by ``generate_maha_dashas()``.

    Returns
    -------
    list of dict, each with:
        'maha_lord'  : Maha Dasha lord
        'antar_lord' : Antardasha lord
        'years'      : Duration in years (float)
        'days'       : Duration in days (float)
        'start_date' : datetime
        'end_date'   : datetime
    """
    maha_lord = maha_dasha["lord"]
    maha_total_years = LORD_YEARS[maha_lord]
    actual_maha_days = maha_dasha["days"]

    # Full (un-scaled) Maha Dasha duration in days
    full_maha_days = maha_total_years * 365.25

    # Scaling factor: 1.0 for full Dashas, < 1.0 for the birth balance Dasha
    scale = actual_maha_days / full_maha_days if full_maha_days > 0 else 1.0

    lord_gen = _lord_sequence_from(maha_lord)
    antardashas = []
    current_date = maha_dasha["start_date"]

    for _ in range(9):
        antar_lord = next(lord_gen)
        antar_total_years = LORD_YEARS[antar_lord]

        # Standard Antardasha duration (within a full Maha Dasha)
        full_antar_days = (maha_total_years * antar_total_years / TOTAL_DASHA_YEARS) * 365.25

        # Scale for partial birth Dasha
        antar_days = full_antar_days * scale
        antar_years = antar_days / 365.25
        end_date = current_date + timedelta(days=antar_days)

        antardashas.append({
            "maha_lord": maha_lord,
            "antar_lord": antar_lord,
            "years": antar_years,
            "days": antar_days,
            "start_date": current_date,
            "end_date": end_date,
        })

        current_date = end_date

    return antardashas


# ---------------------------------------------------------------------------
# Pratyantardasha (sub-sub-periods)
# ---------------------------------------------------------------------------

def generate_pratyantardashas(antardasha):
    """
    Break a single Antardasha into its 9 Pratyantardasha sub-sub-periods.

    Parameters
    ----------
    antardasha : dict
        One element from ``generate_antardashas()``.

    Returns
    -------
    list of dict, each with:
        'maha_lord'      : Maha Dasha lord
        'antar_lord'     : Antardasha lord
        'pratyantar_lord': Pratyantardasha lord
        'days'           : Duration in days (float)
        'start_date'     : datetime
        'end_date'       : datetime
    """
    antar_lord = antardasha["antar_lord"]
    antar_total_years = LORD_YEARS[antar_lord]
    actual_antar_days = antardasha["days"]

    full_antar_days = (LORD_YEARS[antardasha["maha_lord"]] *
                       antar_total_years / TOTAL_DASHA_YEARS) * 365.25
    scale = actual_antar_days / full_antar_days if full_antar_days > 0 else 1.0

    lord_gen = _lord_sequence_from(antar_lord)
    pratyantars = []
    current_date = antardasha["start_date"]

    for _ in range(9):
        prat_lord = next(lord_gen)
        prat_total_years = LORD_YEARS[prat_lord]

        full_prat_days = (antar_total_years * prat_total_years / TOTAL_DASHA_YEARS) * 365.25
        prat_days = full_prat_days * scale
        end_date = current_date + timedelta(days=prat_days)

        pratyantars.append({
            "maha_lord": antardasha["maha_lord"],
            "antar_lord": antar_lord,
            "pratyantar_lord": prat_lord,
            "days": prat_days,
            "start_date": current_date,
            "end_date": end_date,
        })

        current_date = end_date

    return pratyantars


# ---------------------------------------------------------------------------
# Find the currently active Dasha at a given date
# ---------------------------------------------------------------------------

def find_active_dasha(maha_dashas, query_date):
    """
    Find which Maha Dasha and Antardasha are active on ``query_date``.

    Parameters
    ----------
    maha_dashas : list
        Output from ``generate_maha_dashas()``.
    query_date : datetime

    Returns
    -------
    dict with:
        'maha_dasha'  : the active Maha Dasha dict
        'antardasha'  : the active Antardasha dict
    or None if the date is outside the 120-year range.
    """
    for md in maha_dashas:
        if md["start_date"] <= query_date < md["end_date"]:
            antardashas = generate_antardashas(md)
            for ad in antardashas:
                if ad["start_date"] <= query_date < ad["end_date"]:
                    return {"maha_dasha": md, "antardasha": ad}
            # Edge case: return last Antardasha
            return {"maha_dasha": md, "antardasha": antardashas[-1]}
    return None


# ---------------------------------------------------------------------------
# Console display
# ---------------------------------------------------------------------------

def print_dasha_report(year, month, day, hour, minute, second,
                       utc_offset, name="Native"):
    """
    Full Vimshottari Dasha report: Nakshatra, balance, all Maha Dashas,
    and Antardashas for the birth Maha Dasha.
    """
    moon_lon = get_moon_longitude(year, month, day, hour, minute, second,
                                  utc_offset)
    nak = get_nakshatra(moon_lon)
    balance = get_dasha_balance(nak)
    birth_dt = datetime(year, month, day, hour, minute, second)
    maha_dashas = generate_maha_dashas(birth_dt, nak)

    print("=" * 72)
    print("  VIMSHOTTARI DASHA REPORT — Lahiri Ayanamsa")
    print("=" * 72)
    print(f"  Name           : {name}")
    print(f"  Birth date     : {birth_dt.strftime('%d-%b-%Y %H:%M:%S')}")
    print(f"  Moon longitude : {moon_lon:.4f}° (sidereal)")
    print("-" * 72)
    print(f"  Birth Nakshatra: {nak['name']} (#{nak['number']}, "
          f"Pada {nak['pada']})")
    print(f"  Nakshatra Lord : {nak['lord']}")
    print(f"  Traversed      : {nak['deg_in_nakshatra']:.4f}° of "
          f"{NAKSHATRA_SPAN:.4f}° "
          f"({nak['fraction_elapsed'] * 100:.2f}%)")
    print("-" * 72)
    print(f"  Dasha Balance at Birth")
    print(f"    Starting lord: {balance['lord']}")
    bal_y = int(balance["balance_years"])
    bal_m = int((balance["balance_years"] - bal_y) * 12)
    bal_d = int(((balance["balance_years"] - bal_y) * 12 - bal_m) * 30)
    print(f"    Balance      : {bal_y} years, {bal_m} months, {bal_d} days")

    # --- Maha Dashas ------------------------------------------------------
    print("\n" + "=" * 72)
    print("  MAHA DASHA PERIODS (120-year cycle)")
    print("=" * 72)
    print(f"  {'#':<3} {'Lord':<10} {'Start':<14} {'End':<14} {'Duration'}")
    print("-" * 72)

    for i, md in enumerate(maha_dashas, 1):
        y = int(md["years"])
        m = int((md["years"] - y) * 12)
        d = int(((md["years"] - y) * 12 - m) * 30)
        dur = f"{y}y {m}m {d}d"
        print(f"  {i:<3} {md['lord']:<10} "
              f"{md['start_date'].strftime('%d-%b-%Y'):<14} "
              f"{md['end_date'].strftime('%d-%b-%Y'):<14} {dur}")

    # --- Antardashas for the birth (first) Maha Dasha ---------------------
    first_md = maha_dashas[0]
    antardashas = generate_antardashas(first_md)

    print("\n" + "=" * 72)
    print(f"  ANTARDASHAS within {first_md['lord']} Maha Dasha "
          f"({first_md['start_date'].strftime('%d-%b-%Y')} – "
          f"{first_md['end_date'].strftime('%d-%b-%Y')})")
    print("=" * 72)
    print(f"  {'#':<3} {'Antar Lord':<12} {'Start':<14} {'End':<14} "
          f"{'Days':>8}")
    print("-" * 72)

    for i, ad in enumerate(antardashas, 1):
        print(f"  {i:<3} {ad['antar_lord']:<12} "
              f"{ad['start_date'].strftime('%d-%b-%Y'):<14} "
              f"{ad['end_date'].strftime('%d-%b-%Y'):<14} "
              f"{ad['days']:>8.1f}")

    # --- Currently active Dasha (at birth date for demo) ------------------
    active = find_active_dasha(maha_dashas, birth_dt)
    if active:
        print("\n" + "-" * 72)
        print(f"  Active at birth:")
        print(f"    Maha Dasha : {active['maha_dasha']['lord']}")
        print(f"    Antardasha : {active['antardasha']['antar_lord']}")

    print("=" * 72)

    return {
        "moon_longitude": moon_lon,
        "nakshatra": nak,
        "balance": balance,
        "maha_dashas": maha_dashas,
    }


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------

def main():
    """Prompt for birth details and print the full Dasha report."""
    print("\n" + "=" * 50)
    print("  VIMSHOTTARI DASHA CALCULATOR")
    print("  (Lahiri Ayanamsa | pyswisseph)")
    print("=" * 50 + "\n")

    name = input("  Name                 : ").strip() or "Native"
    print("\n  --- Date of Birth ---")
    year   = int(input("  Year  (e.g. 1990)    : "))
    month  = int(input("  Month (1-12)         : "))
    day    = int(input("  Day   (1-31)         : "))

    print("\n  --- Time of Birth ---")
    hour   = int(input("  Hour   (0-23)        : "))
    minute = int(input("  Minute (0-59)        : "))
    second = int(input("  Second (0-59)        : ") or "0")

    print("\n  --- UTC Offset ---")
    utc_offset = float(input("  UTC offset (e.g. 5.5 for IST) : "))

    print()
    print_dasha_report(year, month, day, hour, minute, second,
                       utc_offset, name)


if __name__ == "__main__":
    main()
