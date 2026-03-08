#!/usr/bin/env python3
"""
Vedic Astrology Chart Generator
================================
Calculates sidereal planetary positions using Swiss Ephemeris with
Lahiri Ayanamsa (Indian Astronomical Ephemeris standard) and renders
a South Indian style birth chart using jyotichart.

Usage:
    python chart_gen.py

Requires:
    - pyswisseph (Swiss Ephemeris Python bindings)
    - jyotichart (South Indian chart renderer)
    - Ephemeris files (.se1) in the ./ephe directory
"""

import os
import math
from datetime import datetime

import swisseph as swe
import jyotichart


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EPHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")

# The 12 Rashis (sidereal zodiac signs) in order, index 0-11.
# Correct English spelling used throughout; jyotichart fallback handled in render_chart().
RASHI_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

# Sanskrit Rashi names (for display)
RASHI_SANSKRIT = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena"
]

# Rashi lords (rulers of each sign)
RASHI_LORDS = [
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"
]

# South Indian chart: fixed grid positions for each Rashi.
# The 4x4 outer grid maps sign indices to (row, col) positions.
#
#   Col 0        Col 1       Col 2       Col 3
#  ┌───────────┬───────────┬───────────┬───────────┐
#  │ Pisces(11)│ Aries(0)  │Taurus(1)  │Gemini(2)  │ Row 0
#  ├───────────┼───────────┴───────────┼───────────┤
#  │Aquar.(10) │                       │Cancer(3)  │ Row 1
#  ├───────────┤        (center)       ├───────────┤
#  │Capri.(9)  │                       │  Leo(4)   │ Row 2
#  ├───────────┼───────────┬───────────┼───────────┤
#  │ Saggi.(8) │Scorpio(7) │ Libra(6)  │ Virgo(5)  │ Row 3
#  └───────────┴───────────┴───────────┴───────────┘
SOUTH_INDIAN_GRID = {
    0:  (0, 1),   # Aries
    1:  (0, 2),   # Taurus
    2:  (0, 3),   # Gemini
    3:  (1, 3),   # Cancer
    4:  (2, 3),   # Leo
    5:  (3, 3),   # Virgo
    6:  (3, 2),   # Libra
    7:  (3, 1),   # Scorpio
    8:  (3, 0),   # Sagittarius
    9:  (2, 0),   # Capricorn
    10: (1, 0),   # Aquarius
    11: (0, 0),   # Pisces
}

# Swiss Ephemeris planet IDs → (display name, short symbol, jyotichart const)
PLANETS = [
    (swe.SUN,     "Sun",     "Su", jyotichart.SUN),
    (swe.MOON,    "Moon",    "Mo", jyotichart.MOON),
    (swe.MARS,    "Mars",    "Ma", jyotichart.MARS),
    (swe.MERCURY, "Mercury", "Me", jyotichart.MERCURY),
    (swe.JUPITER, "Jupiter", "Ju", jyotichart.JUPITER),
    (swe.VENUS,   "Venus",   "Ve", jyotichart.VENUS),
    (swe.SATURN,  "Saturn",  "Sa", jyotichart.SATURN),
]

RAHU_ID = swe.MEAN_NODE  # Mean node for Rahu; Ketu = Rahu + 180°

# Map planet names to jyotichart constants
JYOTICHART_PLANET_MAP = {
    "Sun":     jyotichart.SUN,
    "Moon":    jyotichart.MOON,
    "Mars":    jyotichart.MARS,
    "Mercury": jyotichart.MERCURY,
    "Jupiter": jyotichart.JUPITER,
    "Venus":   jyotichart.VENUS,
    "Saturn":  jyotichart.SATURN,
    "Rahu":    jyotichart.RAHU,
    "Ketu":    jyotichart.KETU,
}


# ---------------------------------------------------------------------------
# Ephemeris initialisation — Lahiri Ayanamsa
# ---------------------------------------------------------------------------

def init_swe():
    """
    Initialise Swiss Ephemeris with Lahiri Ayanamsa.

    Lahiri Ayanamsa is the official standard adopted by the Indian
    Astronomical Ephemeris (published by the Positional Astronomy Centre,
    Government of India). It is based on the precession of the equinoxes
    with the initial point fixed such that the star Spica (Chitra) is at
    0° Libra in the sidereal zodiac.

    This function MUST be called before any calculation.
    """
    swe.set_ephe_path(EPHE_PATH)
    swe.set_sid_mode(swe.SIDM_LAHIRI)


# ---------------------------------------------------------------------------
# Degree / Rashi conversion helpers
# ---------------------------------------------------------------------------

def deg_to_dms(deg):
    """Convert decimal degrees to (degrees, minutes, seconds) tuple."""
    d = int(deg)
    m = int((deg - d) * 60)
    s = (deg - d - m / 60.0) * 3600
    return d, m, round(s, 1)


def format_dms(deg):
    """Format decimal degrees as D°M'S\" string."""
    d, m, s = deg_to_dms(deg)
    return f"{d}°{m:02d}'{s:04.1f}\""


def longitude_to_rashi(longitude):
    """
    Convert a sidereal longitude (0°–360°) to its Rashi (sign).

    Returns
    -------
    dict with:
        'index'     : int 0-11 (0=Aries/Mesha … 11=Pisces/Meena)
        'name'      : English sign name (e.g. "Aries")
        'sanskrit'  : Sanskrit name (e.g. "Mesha")
        'lord'      : Ruling planet of this sign
        'deg'       : Degrees within the sign (0-30)
        'deg_dms'   : Formatted D°M'S" within the sign
        'grid_pos'  : (row, col) position in the South Indian chart
    """
    idx = int(longitude / 30.0) % 12
    deg_in_sign = longitude % 30.0
    return {
        "index":    idx,
        "name":     RASHI_NAMES[idx],
        "sanskrit": RASHI_SANSKRIT[idx],
        "lord":     RASHI_LORDS[idx],
        "deg":      deg_in_sign,
        "deg_dms":  format_dms(deg_in_sign),
        "grid_pos": SOUTH_INDIAN_GRID[idx],
    }


def rashi_to_house(planet_rashi_index, asc_rashi_index):
    """
    Return house number (1-12) for a planet.
    House 1 = the Rashi occupied by the Ascendant (Lagna).
    """
    return ((planet_rashi_index - asc_rashi_index) % 12) + 1


# ---------------------------------------------------------------------------
# Julian Day conversion
# ---------------------------------------------------------------------------

def datetime_to_jd(year, month, day, hour, minute, second, utc_offset):
    """
    Convert a local date/time + UTC offset to Julian Day (UT).

    Parameters
    ----------
    year, month, day : int
    hour, minute, second : int
        Local time components.
    utc_offset : float
        Hours ahead of UTC (e.g. +5.5 for IST).
    """
    decimal_hour_ut = hour + minute / 60.0 + second / 3600.0 - utc_offset
    return swe.julday(year, month, day, decimal_hour_ut)


# ---------------------------------------------------------------------------
# Core sidereal calculation — Sun, Moon, Lagna
# ---------------------------------------------------------------------------

def get_sidereal_positions(jd, latitude, longitude):
    """
    Compute the sidereal positions of the **Sun**, **Moon**, and
    **Ascendant (Lagna)** for a given Julian Day and geographic location,
    using Lahiri Ayanamsa.

    This is the minimal function required for Rashi chart placement.
    ``init_swe()`` must have been called first so that
    ``swe.SIDM_LAHIRI`` is active.

    Parameters
    ----------
    jd : float
        Julian Day number in Universal Time.
    latitude : float
        Geographic latitude (north positive).
    longitude : float
        Geographic longitude (east positive).

    Returns
    -------
    dict with keys:
        'ayanamsa'  : Lahiri Ayanamsa value (degrees) for this JD
        'sun'       : dict  – sidereal longitude, Rashi info, speed
        'moon'      : dict  – sidereal longitude, Rashi info, speed
        'ascendant' : dict  – sidereal longitude, Rashi info
    """
    # --- Ayanamsa ---------------------------------------------------------
    ayanamsa = swe.get_ayanamsa_ut(jd)

    # --- Flags: Swiss Ephemeris + Sidereal (Lahiri) + Speed ---------------
    calc_flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

    # --- Sun --------------------------------------------------------------
    sun_pos, _ = swe.calc_ut(jd, swe.SUN, calc_flags)
    sun_lon = sun_pos[0]
    sun_rashi = longitude_to_rashi(sun_lon)

    # --- Moon -------------------------------------------------------------
    moon_pos, _ = swe.calc_ut(jd, swe.MOON, calc_flags)
    moon_lon = moon_pos[0]
    moon_rashi = longitude_to_rashi(moon_lon)

    # --- Ascendant (Lagna) ------------------------------------------------
    # swe.houses_ex with FLG_SIDEREAL returns sidereal cusps/angles.
    # ascmc[0] = Ascendant, ascmc[1] = MC.
    _, ascmc = swe.houses_ex(
        jd, latitude, longitude,
        b'P',  # house system (Placidus); only ascmc[0] is used here
        flags=swe.FLG_SIDEREAL,
    )
    asc_lon = ascmc[0]
    asc_rashi = longitude_to_rashi(asc_lon)

    return {
        "ayanamsa": ayanamsa,
        "sun": {
            "longitude": sun_lon,
            "speed": sun_pos[3],
            "rashi": sun_rashi,
        },
        "moon": {
            "longitude": moon_lon,
            "speed": moon_pos[3],
            "rashi": moon_rashi,
        },
        "ascendant": {
            "longitude": asc_lon,
            "rashi": asc_rashi,
        },
    }


# ---------------------------------------------------------------------------
# Full planetary calculation (all 9 grahas + Lagna)
# ---------------------------------------------------------------------------

def calculate_positions(year, month, day, hour, minute, second,
                        utc_offset, latitude, longitude):
    """
    Calculate sidereal positions of all nine Vedic planets and the
    Ascendant, using Lahiri Ayanamsa via Swiss Ephemeris.

    Every ``swe.calc_ut`` call uses ``swe.FLG_SIDEREAL`` so all
    longitudes are already in the sidereal (Lahiri) frame — no manual
    ayanamsa subtraction is needed.

    Parameters
    ----------
    year, month, day : int
    hour, minute, second : int
        Local birth time.
    utc_offset : float
        Hours ahead of UTC (e.g. 5.5 for IST).
    latitude, longitude : float
        Birth coordinates (north/east positive).

    Returns
    -------
    dict with:
        'jd'        – Julian Day (UT)
        'ayanamsa'  – Lahiri Ayanamsa value
        'ascendant' – Lagna info dict
        'planets'   – list of 9 planet info dicts
    """
    # Ensure Lahiri Ayanamsa is active
    init_swe()

    jd = datetime_to_jd(year, month, day, hour, minute, second, utc_offset)
    ayanamsa = swe.get_ayanamsa_ut(jd)

    # ---- Ascendant (Lagna) -----------------------------------------------
    _, ascmc = swe.houses_ex(
        jd, latitude, longitude,
        b'P',
        flags=swe.FLG_SIDEREAL,
    )
    asc_lon = ascmc[0]
    asc_rashi = longitude_to_rashi(asc_lon)

    result = {
        "jd": jd,
        "ayanamsa": ayanamsa,
        "ascendant": {
            "longitude": asc_lon,
            "sign": asc_rashi["name"],
            "sign_index": asc_rashi["index"],
            "sign_deg": asc_rashi["deg"],
            "rashi": asc_rashi,
        },
        "planets": [],
    }

    asc_idx = asc_rashi["index"]

    # ---- Seven visible planets -------------------------------------------
    calc_flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

    for swe_id, name, symbol, _ in PLANETS:
        pos, _ = swe.calc_ut(jd, swe_id, calc_flags)
        lon = pos[0]
        speed = pos[3]
        rashi = longitude_to_rashi(lon)

        result["planets"].append({
            "name": name,
            "symbol": symbol,
            "longitude": lon,
            "sign": rashi["name"],
            "sign_index": rashi["index"],
            "sign_deg": rashi["deg"],
            "rashi": rashi,
            "house": rashi_to_house(rashi["index"], asc_idx),
            "retrograde": speed < 0,
            "speed": speed,
        })

    # ---- Rahu (Mean Node) ------------------------------------------------
    pos, _ = swe.calc_ut(jd, RAHU_ID, calc_flags)
    rahu_lon = pos[0]
    rahu_rashi = longitude_to_rashi(rahu_lon)

    result["planets"].append({
        "name": "Rahu",
        "symbol": "Ra",
        "longitude": rahu_lon,
        "sign": rahu_rashi["name"],
        "sign_index": rahu_rashi["index"],
        "sign_deg": rahu_rashi["deg"],
        "rashi": rahu_rashi,
        "house": rashi_to_house(rahu_rashi["index"], asc_idx),
        "retrograde": True,
        "speed": pos[3],
    })

    # ---- Ketu (180° opposite Rahu) ---------------------------------------
    ketu_lon = (rahu_lon + 180.0) % 360.0
    ketu_rashi = longitude_to_rashi(ketu_lon)

    result["planets"].append({
        "name": "Ketu",
        "symbol": "Ke",
        "longitude": ketu_lon,
        "sign": ketu_rashi["name"],
        "sign_index": ketu_rashi["index"],
        "sign_deg": ketu_rashi["deg"],
        "rashi": ketu_rashi,
        "house": rashi_to_house(ketu_rashi["index"], asc_idx),
        "retrograde": True,
        "speed": -abs(pos[3]),
    })

    return result


# ---------------------------------------------------------------------------
# South Indian chart rendering
# ---------------------------------------------------------------------------

def generate_south_chart(positions, person_name="Native", output_dir=None,
                         filename="birth_chart"):
    """
    Render a South Indian style Rashi chart as SVG via jyotichart.

    In the South Indian format the 12 sign boxes are **fixed** — Pisces
    is always top-left, Aries top-second, etc.  The Ascendant sign is
    marked, and planets are placed into their respective Rashi boxes.

    Parameters
    ----------
    positions : dict
        Output from ``calculate_positions()``.
    person_name : str
    output_dir : str or None
        Defaults to ``./output``.
    filename : str
        Without ``.svg`` extension.

    Returns
    -------
    str – path to generated SVG, or None on error.
    """
    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    chart = jyotichart.SouthChart(
        chartname="Rasi",
        personname=person_name,
        IsFullChart=True,
    )

    asc_sign = positions["ascendant"]["sign"]
    asc_idx = positions["ascendant"]["sign_index"]
    # jyotichart may use "Saggitarius" internally; try correct first, then fallback
    res = chart.set_ascendantsign(asc_sign)
    if res != "Success" and asc_sign == "Sagittarius":
        res = chart.set_ascendantsign("Saggitarius")
    if res != "Success":
        print(f"Error setting ascendant: {res}")
        return None

    for planet in positions["planets"]:
        house_num = rashi_to_house(planet["sign_index"], asc_idx)
        jc_planet = JYOTICHART_PLANET_MAP[planet["name"]]

        # Short 2-letter label to avoid overlap in crowded houses
        label = planet["name"][:2]

        res = chart.add_planet(
            planet=jc_planet,
            symbol=label,
            housenum=house_num,
            retrograde=planet["retrograde"],
        )
        if res != "Success":
            print(f"Error adding {planet['name']}: {res}")

    res = chart.draw(location=output_dir, filename=filename)
    if res != "Success":
        print(f"Error drawing chart: {res}")
        return None

    svg_path = os.path.join(output_dir, f"{filename}.svg")
    print(f"\nSouth Indian chart saved to: {svg_path}")
    return svg_path


# ---------------------------------------------------------------------------
# Console display
# ---------------------------------------------------------------------------

def print_positions(positions):
    """Print a formatted table of planetary positions to the console."""
    print("=" * 78)
    print("  VEDIC BIRTH CHART — Lahiri Ayanamsa (Indian Astronomical Ephemeris)")
    print("=" * 78)
    print(f"  Julian Day : {positions['jd']:.6f}")
    print(f"  Ayanamsa   : {format_dms(positions['ayanamsa'])}")
    print("-" * 78)

    asc = positions["ascendant"]
    r = asc["rashi"]
    print(f"  {'Ascendant':<10} │ {r['name']:<14} ({r['sanskrit']:<10}) │ "
          f"{r['deg_dms']:<14} │ Lord: {r['lord']}")
    print("-" * 78)
    print(f"  {'Planet':<10} │ {'Rashi':<14} {'(Sanskrit)':<12} │ "
          f"{'Degrees':<14} │ {'House':>5}  {'R':>3}")
    print("-" * 78)

    for p in positions["planets"]:
        r = p["rashi"]
        retro = "(R)" if p["retrograde"] else ""
        print(f"  {p['name']:<10} │ {r['name']:<14} ({r['sanskrit']:<10}) │ "
              f"{r['deg_dms']:<14} │ {p['house']:>5}  {retro:>3}")

    print("=" * 78)

    # South Indian grid summary
    print("\n  South Indian Chart Grid (fixed-sign layout):")
    print("  ┌────────────┬────────────┬────────────┬────────────┐")
    grid = {}
    for p in positions["planets"]:
        row, col = SOUTH_INDIAN_GRID[p["sign_index"]]
        grid.setdefault((row, col), []).append(p["symbol"])

    asc_grid = SOUTH_INDIAN_GRID[asc["sign_index"]]

    for row in range(4):
        cells = []
        for col in range(4):
            if row in (1, 2) and col in (1, 2):
                cells.append("          ")
                continue
            idx = [k for k, v in SOUTH_INDIAN_GRID.items()
                   if v == (row, col)][0]
            planets_here = grid.get((row, col), [])
            marker = "*" if (row, col) == asc_grid else " "
            abbr = RASHI_SANSKRIT[idx][:3]
            body = f"{abbr}{marker}" + " ".join(planets_here)
            cells.append(f"{body:<10}")
        print(f"  │ {'│ '.join(cells)}│")
        if row < 3:
            if row == 0 or row == 2:
                print("  ├────────────┼────────────┼"
                      "────────────┼────────────┤")
            else:
                print("  │            ├────────────┼"
                      "────────────┤            │")
    print("  └────────────┴────────────┴────────────┴────────────┘")
    print("  (* = Ascendant sign)\n")


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------

def get_birth_details():
    """Prompt the user for birth details."""
    print("\n" + "=" * 50)
    print("  VEDIC ASTROLOGY — Birth Chart Generator")
    print("  (Lahiri Ayanamsa | South Indian Chart)")
    print("=" * 50 + "\n")

    name = input("  Name of the person   : ").strip() or "Native"

    print("\n  --- Date of Birth ---")
    year  = int(input("  Year  (e.g. 1990)    : "))
    month = int(input("  Month (1-12)         : "))
    day   = int(input("  Day   (1-31)         : "))

    print("\n  --- Time of Birth (local time) ---")
    hour   = int(input("  Hour   (0-23)        : "))
    minute = int(input("  Minute (0-59)        : "))
    second = int(input("  Second (0-59)        : ") or "0")

    print("\n  --- UTC Offset ---")
    utc_offset = float(input("  UTC offset (e.g. 5.5 for IST) : "))

    print("\n  --- Place of Birth (coordinates) ---")
    latitude  = float(input("  Latitude  (N+, e.g. 13.0827)  : "))
    longitude = float(input("  Longitude (E+, e.g. 80.2707)  : "))

    return {
        "name": name,
        "year": year, "month": month, "day": day,
        "hour": hour, "minute": minute, "second": second,
        "utc_offset": utc_offset,
        "latitude": latitude, "longitude": longitude,
    }


def main():
    """Gather input, calculate, display, and render chart."""
    birth = get_birth_details()

    print("\nCalculating sidereal positions (Lahiri Ayanamsa)...\n")

    # Full calculation — all 9 planets + Lagna
    positions = calculate_positions(
        year=birth["year"], month=birth["month"], day=birth["day"],
        hour=birth["hour"], minute=birth["minute"], second=birth["second"],
        utc_offset=birth["utc_offset"],
        latitude=birth["latitude"], longitude=birth["longitude"],
    )

    # Also demonstrate the focused Sun/Moon/Lagna function
    jd = positions["jd"]
    core = get_sidereal_positions(jd, birth["latitude"], birth["longitude"])
    print(f"  Quick check — Sun  Rashi : {core['sun']['rashi']['sanskrit']}")
    print(f"  Quick check — Moon Rashi : {core['moon']['rashi']['sanskrit']}")
    print(f"  Quick check — Lagna      : {core['ascendant']['rashi']['sanskrit']}")
    print()

    print_positions(positions)

    generate_south_chart(positions, person_name=birth["name"])

    print("Done.")


if __name__ == "__main__":
    main()
