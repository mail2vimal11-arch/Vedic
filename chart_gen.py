#!/usr/bin/env python3
"""
Vedic Astrology Chart Generator
================================
Calculates planetary positions using Swiss Ephemeris with Lahiri Ayanamsa
and renders a South Indian style birth chart using jyotichart.

Usage:
    python chart_gen.py

Requires:
    - pyswisseph (Swiss Ephemeris Python bindings)
    - jyotichart (South Indian chart renderer)
    - Ephemeris files (.se1) in the ./ephe directory
"""

import os
import sys
import math
from datetime import datetime

import swisseph as swe
import jyotichart


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EPHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")

# Zodiac signs in order (0-11)
SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Saggitarius", "Capricorn", "Aquarius", "Pisces"
]

# Swiss Ephemeris planet IDs and their display info
PLANETS = [
    (swe.SUN,     "Sun",     "Su", jyotichart.SUN),
    (swe.MOON,    "Moon",    "Mo", jyotichart.MOON),
    (swe.MARS,    "Mars",    "Ma", jyotichart.MARS),
    (swe.MERCURY, "Mercury", "Me", jyotichart.MERCURY),
    (swe.JUPITER, "Jupiter", "Ju", jyotichart.JUPITER),
    (swe.VENUS,   "Venus",   "Ve", jyotichart.VENUS),
    (swe.SATURN,  "Saturn",  "Sa", jyotichart.SATURN),
]

# Mean node for Rahu; Ketu is 180 degrees opposite
RAHU_ID = swe.MEAN_NODE


# ---------------------------------------------------------------------------
# Helper functions
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


def sign_index(longitude):
    """Return 0-based sign index (0=Aries .. 11=Pisces) from longitude."""
    return int(longitude / 30.0) % 12


def sign_name(longitude):
    """Return the zodiac sign name for a given sidereal longitude."""
    return SIGNS[sign_index(longitude)]


def sign_degrees(longitude):
    """Return degrees within the sign (0-30) for a given longitude."""
    return longitude % 30.0


def datetime_to_jd(year, month, day, hour, minute, second, utc_offset):
    """
    Convert date/time with UTC offset to Julian Day Number.

    Parameters
    ----------
    year, month, day : int
    hour, minute, second : int
    utc_offset : float
        Hours ahead of UTC (e.g. +5.5 for IST).
    """
    # Convert local time to UTC
    decimal_hour = hour + minute / 60.0 + second / 3600.0 - utc_offset
    jd = swe.julday(year, month, day, decimal_hour)
    return jd


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def calculate_positions(year, month, day, hour, minute, second,
                        utc_offset, latitude, longitude):
    """
    Calculate sidereal planetary positions and ascendant using
    Lahiri Ayanamsa via Swiss Ephemeris.

    Parameters
    ----------
    year, month, day : int
        Date of birth.
    hour, minute, second : int
        Time of birth (local time).
    utc_offset : float
        UTC offset in hours (e.g. 5.5 for IST).
    latitude : float
        Birth latitude in decimal degrees (north positive).
    longitude : float
        Birth longitude in decimal degrees (east positive).

    Returns
    -------
    dict with keys:
        'jd'        : Julian Day
        'ayanamsa'  : Lahiri Ayanamsa value used
        'ascendant' : dict with 'longitude', 'sign', 'sign_deg'
        'planets'   : list of dicts with planet info
    """
    # Set ephemeris path
    swe.set_ephe_path(EPHE_PATH)

    # Set Lahiri Ayanamsa (Indian standard, officially adopted by
    # the Indian Astronomical Ephemeris)
    swe.set_sid_mode(swe.SIDM_LAHIRI)

    # Compute Julian Day in UT
    jd = datetime_to_jd(year, month, day, hour, minute, second, utc_offset)

    # Get Ayanamsa value for this date
    ayanamsa = swe.get_ayanamsa_ut(jd)

    # Calculate Ascendant (Lagna)
    # swe.houses_ex returns (cusps, ascmc) — ascmc[0] is the Ascendant
    cusps, ascmc = swe.houses_ex(jd, latitude, longitude,
                                  b'P',  # Placidus (used only for cusp calc)
                                  flags=swe.FLG_SIDEREAL)
    asc_longitude = ascmc[0]  # Sidereal ascendant

    result = {
        'jd': jd,
        'ayanamsa': ayanamsa,
        'ascendant': {
            'longitude': asc_longitude,
            'sign': sign_name(asc_longitude),
            'sign_index': sign_index(asc_longitude),
            'sign_deg': sign_degrees(asc_longitude),
        },
        'planets': [],
    }

    # Calculate each planet
    for swe_id, name, symbol, _ in PLANETS:
        flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
        pos, ret = swe.calc_ut(jd, swe_id, flags)
        lon = pos[0]      # sidereal longitude
        speed = pos[3]    # daily speed — negative means retrograde

        result['planets'].append({
            'name': name,
            'symbol': symbol,
            'longitude': lon,
            'sign': sign_name(lon),
            'sign_index': sign_index(lon),
            'sign_deg': sign_degrees(lon),
            'retrograde': speed < 0,
            'speed': speed,
        })

    # Rahu (Mean Node)
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    pos, ret = swe.calc_ut(jd, RAHU_ID, flags)
    rahu_lon = pos[0]

    result['planets'].append({
        'name': 'Rahu',
        'symbol': 'Ra',
        'longitude': rahu_lon,
        'sign': sign_name(rahu_lon),
        'sign_index': sign_index(rahu_lon),
        'sign_deg': sign_degrees(rahu_lon),
        'retrograde': True,  # Rahu is always retrograde
        'speed': pos[3],
    })

    # Ketu (180° opposite Rahu)
    ketu_lon = (rahu_lon + 180.0) % 360.0

    result['planets'].append({
        'name': 'Ketu',
        'symbol': 'Ke',
        'longitude': ketu_lon,
        'sign': sign_name(ketu_lon),
        'sign_index': sign_index(ketu_lon),
        'sign_deg': sign_degrees(ketu_lon),
        'retrograde': True,  # Ketu is always retrograde
        'speed': -abs(pos[3]),
    })

    return result


# ---------------------------------------------------------------------------
# Chart rendering
# ---------------------------------------------------------------------------

def get_house_number(planet_sign_index, asc_sign_index):
    """
    Return house number (1-12) for a planet given its sign index
    and the ascendant sign index. House 1 = ascendant sign.
    """
    return ((planet_sign_index - asc_sign_index) % 12) + 1


# Map planet names to jyotichart planet constants
JYOTICHART_PLANET_MAP = {
    'Sun':     jyotichart.SUN,
    'Moon':    jyotichart.MOON,
    'Mars':    jyotichart.MARS,
    'Mercury': jyotichart.MERCURY,
    'Jupiter': jyotichart.JUPITER,
    'Venus':   jyotichart.VENUS,
    'Saturn':  jyotichart.SATURN,
    'Rahu':    jyotichart.RAHU,
    'Ketu':    jyotichart.KETU,
}


def generate_south_chart(positions, person_name="Native", output_dir=None,
                         filename="birth_chart"):
    """
    Generate a South Indian style birth chart SVG using jyotichart.

    Parameters
    ----------
    positions : dict
        Output from calculate_positions().
    person_name : str
        Name of the person.
    output_dir : str or None
        Directory to save the SVG. Defaults to ./output.
    filename : str
        Output filename (without .svg extension).

    Returns
    -------
    str : Path to the generated SVG file.
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "output")
    os.makedirs(output_dir, exist_ok=True)

    # Create chart
    chart = jyotichart.SouthChart(
        chartname="Rasi",
        personname=person_name,
        IsFullChart=True,
    )

    # Set ascendant sign
    asc_sign = positions['ascendant']['sign']
    asc_sign_idx = positions['ascendant']['sign_index']
    result = chart.set_ascendantsign(asc_sign)
    if result != "Success":
        print(f"Error setting ascendant: {result}")
        return None

    # Add each planet
    for planet in positions['planets']:
        house_num = get_house_number(planet['sign_index'], asc_sign_idx)
        jc_planet = JYOTICHART_PLANET_MAP[planet['name']]

        # Display symbol with degrees inside the sign
        d, m, _ = deg_to_dms(planet['sign_deg'])
        label = f"{planet['symbol']} {d}:{m:02d}"

        result = chart.add_planet(
            planet=jc_planet,
            symbol=label,
            housenum=house_num,
            retrograde=planet['retrograde'],
        )
        if result != "Success":
            print(f"Error adding {planet['name']}: {result}")

    # Draw chart
    result = chart.draw(location=output_dir, filename=filename)
    if result != "Success":
        print(f"Error drawing chart: {result}")
        return None

    svg_path = os.path.join(output_dir, f"{filename}.svg")
    print(f"\nSouth Indian chart saved to: {svg_path}")
    return svg_path


# ---------------------------------------------------------------------------
# Console display
# ---------------------------------------------------------------------------

def print_positions(positions):
    """Print a formatted table of planetary positions to the console."""
    print("=" * 70)
    print("  VEDIC BIRTH CHART — Lahiri Ayanamsa (Indian Astronomical Ephemeris)")
    print("=" * 70)
    print(f"  Julian Day   : {positions['jd']:.6f}")
    print(f"  Ayanamsa     : {format_dms(positions['ayanamsa'])}")
    print("-" * 70)

    asc = positions['ascendant']
    print(f"  {'Ascendant (Lagna)':<18} {asc['sign']:<14} "
          f"{format_dms(asc['sign_deg'])}")
    print("-" * 70)
    print(f"  {'Planet':<18} {'Sign':<14} {'Degrees':<14} {'Retro'}")
    print("-" * 70)

    for p in positions['planets']:
        retro = "(R)" if p['retrograde'] else ""
        print(f"  {p['name']:<18} {p['sign']:<14} "
              f"{format_dms(p['sign_deg']):<14} {retro}")

    print("=" * 70)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_birth_details():
    """Prompt the user for birth details interactively."""
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
    latitude  = float(input("  Latitude  (N positive, e.g. 13.0827)  : "))
    longitude = float(input("  Longitude (E positive, e.g. 80.2707)  : "))

    return {
        'name': name,
        'year': year, 'month': month, 'day': day,
        'hour': hour, 'minute': minute, 'second': second,
        'utc_offset': utc_offset,
        'latitude': latitude, 'longitude': longitude,
    }


def main():
    """Main function — gather input, calculate, display, and render chart."""
    birth = get_birth_details()

    print("\nCalculating planetary positions...")

    positions = calculate_positions(
        year=birth['year'],
        month=birth['month'],
        day=birth['day'],
        hour=birth['hour'],
        minute=birth['minute'],
        second=birth['second'],
        utc_offset=birth['utc_offset'],
        latitude=birth['latitude'],
        longitude=birth['longitude'],
    )

    # Print positions to console
    print_positions(positions)

    # Generate South Indian chart SVG
    generate_south_chart(
        positions=positions,
        person_name=birth['name'],
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
