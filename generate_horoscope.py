#!/usr/bin/env python3
"""
Generate a complete standalone HTML horoscope report.

Birth: 11 Sep 2009, 1:17 AM, Dubai (25.2048 N, 55.2708 E, UTC+4)
Includes: D1 (Rashi), D9 (Navamsha), D10 (Dashamsha), full Dasha, current Dasha.
"""

import json
import os
from datetime import datetime

from chart_gen import (
    calculate_positions, generate_south_chart, format_dms,
    init_swe, RASHI_NAMES, RASHI_SANSKRIT, RASHI_LORDS,
    SOUTH_INDIAN_GRID, JYOTICHART_PLANET_MAP, deg_to_dms,
    longitude_to_rashi, rashi_to_house
)
from vims_engine import (
    compute_moon_longitude, calc_nakshatra, get_full_dasha_report,
    get_dasha_timeline, find_active_periods, get_antardashas,
    get_pratyantardashas, _years_to_ymd
)
import jyotichart

# ── Birth Data ────────────────────────────────────────────────────────────
BIRTH = {
    "name": "Native",
    "year": 2009, "month": 9, "day": 11,
    "hour": 1, "minute": 17, "second": 0,
    "utc_offset": 4.0,
    "latitude": 25.2048, "longitude_geo": 55.2708,
    "city": "Dubai", "country": "United Arab Emirates",
}

# ── Compute D1 positions ─────────────────────────────────────────────────
positions = calculate_positions(
    BIRTH["year"], BIRTH["month"], BIRTH["day"],
    BIRTH["hour"], BIRTH["minute"], BIRTH["second"],
    BIRTH["utc_offset"], BIRTH["latitude"], BIRTH["longitude_geo"],
)

asc_idx = positions["ascendant"]["sign_index"]

# ── Compute D9 (Navamsha) ────────────────────────────────────────────────
def navamsha_sign_index(sidereal_longitude):
    """Navamsha: divide each sign into 9 parts of 3°20'. The navamsha
    sign starts from Aries for fire signs, Cancer for earth signs,
    Libra for air signs, Capricorn for water signs."""
    sign_idx = int(sidereal_longitude / 30) % 12
    deg_in_sign = sidereal_longitude % 30
    navamsha_num = int(deg_in_sign / (30 / 9))  # 0-8 within sign

    fire_signs = [0, 4, 8]     # Aries, Leo, Sagittarius
    earth_signs = [1, 5, 9]    # Taurus, Virgo, Capricorn
    air_signs = [2, 6, 10]     # Gemini, Libra, Aquarius
    water_signs = [3, 7, 11]   # Cancer, Scorpio, Pisces

    if sign_idx in fire_signs:
        start = 0   # Aries
    elif sign_idx in earth_signs:
        start = 3   # Cancer
    elif sign_idx in air_signs:
        start = 6   # Libra
    else:
        start = 9   # Capricorn

    return (start + navamsha_num) % 12


def dashamsha_sign_index(sidereal_longitude):
    """Dashamsha (D10): divide each sign into 10 parts of 3° each.
    For odd signs, count from the sign itself.
    For even signs, count from the 9th sign from it."""
    sign_idx = int(sidereal_longitude / 30) % 12
    deg_in_sign = sidereal_longitude % 30
    dashamsha_num = int(deg_in_sign / 3)  # 0-9 within sign
    if dashamsha_num > 9:
        dashamsha_num = 9

    if (sign_idx + 1) % 2 == 1:  # odd sign (1-indexed)
        start = sign_idx
    else:  # even sign
        start = (sign_idx + 8) % 12  # 9th from sign (0-indexed: +8)

    return (start + dashamsha_num) % 12


# Build D9 positions
d9_planets = []
for p in positions["planets"]:
    d9_sign = navamsha_sign_index(p["longitude"])
    d9_planets.append({
        "name": p["name"],
        "symbol": p["symbol"],
        "d9_sign_index": d9_sign,
        "d9_sign": RASHI_NAMES[d9_sign],
        "d9_sanskrit": RASHI_SANSKRIT[d9_sign],
        "d9_lord": RASHI_LORDS[d9_sign],
        "retrograde": p["retrograde"],
    })

d9_asc_sign = navamsha_sign_index(positions["ascendant"]["longitude"])

# Build D10 positions
d10_planets = []
for p in positions["planets"]:
    d10_sign = dashamsha_sign_index(p["longitude"])
    d10_planets.append({
        "name": p["name"],
        "symbol": p["symbol"],
        "d10_sign_index": d10_sign,
        "d10_sign": RASHI_NAMES[d10_sign],
        "d10_sanskrit": RASHI_SANSKRIT[d10_sign],
        "d10_lord": RASHI_LORDS[d10_sign],
        "retrograde": p["retrograde"],
    })

d10_asc_sign = dashamsha_sign_index(positions["ascendant"]["longitude"])

# ── Generate SVG charts ──────────────────────────────────────────────────
output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(output_dir, exist_ok=True)

def read_svg(path):
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            raw = f.read()
        for enc in ("utf-8-sig", "utf-16", "utf-16-le", "latin-1"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
    return ""

# D1 Rashi chart
d1_svg_path = generate_south_chart(positions, person_name="Native",
                                    output_dir=output_dir, filename="d1_rashi")
d1_svg = read_svg(d1_svg_path)

# D9 Navamsha chart via jyotichart
def generate_divisional_chart(planet_data, asc_sign_index, chart_name,
                               person_name, output_dir, filename):
    chart = jyotichart.SouthChart(
        chartname=chart_name,
        personname=person_name,
        IsFullChart=True,
    )
    asc_sign = RASHI_NAMES[asc_sign_index]
    res = chart.set_ascendantsign(asc_sign)
    if res != "Success":
        print(f"Error setting ascendant for {chart_name}: {res}")
        return None

    for p in planet_data:
        if "d9_sign_index" in p:
            p_sign_idx = p["d9_sign_index"]
        elif "d10_sign_index" in p:
            p_sign_idx = p["d10_sign_index"]
        else:
            continue

        house_num = ((p_sign_idx - asc_sign_index) % 12) + 1
        jc_planet = JYOTICHART_PLANET_MAP[p["name"]]
        label = f"{p['symbol']}"

        # Delete the pre-added planet first, then re-add with correct house
        chart.delete_planet(planet=jc_planet)
        res = chart.add_planet(
            planet=jc_planet,
            symbol=label,
            housenum=house_num,
            retrograde=p["retrograde"],
        )
        if res != "Success":
            print(f"Error adding {p['name']} to {chart_name}: {res}")

    res = chart.draw(location=output_dir, filename=filename)
    if res != "Success":
        print(f"Error drawing {chart_name}: {res}")
        return None
    return os.path.join(output_dir, f"{filename}.svg")

d9_svg_path = generate_divisional_chart(
    d9_planets, d9_asc_sign, "Navamsha", "Native", output_dir, "d9_navamsha"
)
d9_svg = read_svg(d9_svg_path)

d10_svg_path = generate_divisional_chart(
    d10_planets, d10_asc_sign, "Dashamsha", "Native", output_dir, "d10_dashamsha"
)
d10_svg = read_svg(d10_svg_path)

# ── Moon longitude & Dasha ───────────────────────────────────────────────
moon_lon = compute_moon_longitude(
    BIRTH["year"], BIRTH["month"], BIRTH["day"],
    BIRTH["hour"], BIRTH["minute"], BIRTH["second"],
    BIRTH["utc_offset"],
)
nakshatra = calc_nakshatra(moon_lon)
birth_dt = datetime(BIRTH["year"], BIRTH["month"], BIRTH["day"],
                    BIRTH["hour"], BIRTH["minute"], BIRTH["second"])
dasha_report = get_full_dasha_report(birth_dt, moon_lon)
timeline = get_dasha_timeline(moon_lon, birth_dt)
now = datetime(2026, 2, 15)
active = find_active_periods(timeline, now)

# ── Build JSON data blob for the HTML ────────────────────────────────────
planets_json = []
for p in positions["planets"]:
    planets_json.append({
        "name": p["name"],
        "symbol": p["symbol"],
        "sign": p["rashi"]["name"],
        "sign_sanskrit": p["rashi"]["sanskrit"],
        "degrees": format_dms(p["sign_deg"]),
        "longitude": round(p["longitude"], 4),
        "house": p["house"],
        "retrograde": p["retrograde"],
        "lord": p["rashi"]["lord"],
    })

d9_json = []
for p in d9_planets:
    d9_json.append({
        "name": p["name"],
        "symbol": p["symbol"],
        "sign": p["d9_sign"],
        "sign_sanskrit": p["d9_sanskrit"],
        "lord": p["d9_lord"],
        "house": ((p["d9_sign_index"] - d9_asc_sign) % 12) + 1,
        "retrograde": p["retrograde"],
    })

d10_json = []
for p in d10_planets:
    d10_json.append({
        "name": p["name"],
        "symbol": p["symbol"],
        "sign": p["d10_sign"],
        "sign_sanskrit": p["d10_sanskrit"],
        "lord": p["d10_lord"],
        "house": ((p["d10_sign_index"] - d10_asc_sign) % 12) + 1,
        "retrograde": p["retrograde"],
    })

asc = positions["ascendant"]
current_dasha = None
if active:
    current_dasha = {
        "maha": active["maha"]["dasha_lord"],
        "maha_start": active["maha"]["start_date"].strftime("%d-%b-%Y"),
        "maha_end": active["maha"]["end_date"].strftime("%d-%b-%Y"),
        "antar": active["antar"]["antar_lord"],
        "antar_start": active["antar"]["start_date"].strftime("%d-%b-%Y"),
        "antar_end": active["antar"]["end_date"].strftime("%d-%b-%Y"),
    }
    if active.get("pratyantar"):
        current_dasha["pratyantar"] = active["pratyantar"]["pratyantar_lord"]
        current_dasha["pratyantar_start"] = active["pratyantar"]["start_date"].strftime("%d-%b-%Y")
        current_dasha["pratyantar_end"] = active["pratyantar"]["end_date"].strftime("%d-%b-%Y")

chart_data = {
    "birth_details": {
        "name": BIRTH["name"],
        "date": f"{BIRTH['day']:02d}-{BIRTH['month']:02d}-{BIRTH['year']}",
        "time": f"{BIRTH['hour']:02d}:{BIRTH['minute']:02d}:{BIRTH['second']:02d}",
        "city": BIRTH["city"],
        "country": BIRTH["country"],
        "latitude": BIRTH["latitude"],
        "longitude": BIRTH["longitude_geo"],
        "utc_offset": BIRTH["utc_offset"],
    },
    "chart": {
        "julian_day": round(positions["jd"], 6),
        "ayanamsa": format_dms(positions["ayanamsa"]),
        "ayanamsa_deg": round(positions["ayanamsa"], 6),
        "ascendant": {
            "sign": asc["rashi"]["name"],
            "sign_sanskrit": asc["rashi"]["sanskrit"],
            "degrees": format_dms(asc["sign_deg"]),
            "lord": asc["rashi"]["lord"],
            "longitude": round(asc["longitude"], 4),
        },
        "planets": planets_json,
    },
    "d9": {
        "ascendant": {
            "sign": RASHI_NAMES[d9_asc_sign],
            "sign_sanskrit": RASHI_SANSKRIT[d9_asc_sign],
            "lord": RASHI_LORDS[d9_asc_sign],
        },
        "planets": d9_json,
    },
    "d10": {
        "ascendant": {
            "sign": RASHI_NAMES[d10_asc_sign],
            "sign_sanskrit": RASHI_SANSKRIT[d10_asc_sign],
            "lord": RASHI_LORDS[d10_asc_sign],
        },
        "planets": d10_json,
    },
    "nakshatra": {
        "name": nakshatra["name"],
        "number": nakshatra["number"],
        "pada": nakshatra["pada"],
        "lord": nakshatra["lord"],
    },
    "moon_longitude": round(moon_lon, 4),
    "dasha_report": dasha_report,
    "current_dasha": current_dasha,
}

# ── Escape SVGs for safe embedding ───────────────────────────────────────
import html as html_mod

# ── Write standalone HTML ────────────────────────────────────────────────
html_output = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vedic Horoscope — 11 Sep 2009, 1:17 AM, Dubai</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#9790;</text></svg>">
    <style>
:root {{
    --color-bg: #faf8f4; --color-surface: #ffffff; --color-border: #e8e2d8; --color-border-lt: #f0ebe3;
    --color-text: #2d2a26; --color-text-2: #5c5650; --color-text-3: #8a8279;
    --color-saffron: #e8761c; --color-saffron-dk: #c4600f; --color-saffron-lt: #fdf0e3;
    --color-maroon: #7a1f2e; --color-maroon-lt: #f5e6e9;
    --color-gold: #b8860b; --color-gold-lt: #fef9e7; --color-temple: #8b4513;
    --color-success: #2d7d46; --color-error: #c0392b;
    --font-display: Georgia, serif; --font-body: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --radius: 8px; --radius-lg: 12px;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.06); --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
    --max-width: 1100px;
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ font-size: 16px; scroll-behavior: smooth; -webkit-font-smoothing: antialiased; }}
body {{ font-family: var(--font-body); color: var(--color-text); background: var(--color-bg); line-height: 1.6; min-height: 100vh; display: flex; flex-direction: column; }}
.container {{ max-width: var(--max-width); margin: 0 auto; padding: 0 24px; width: 100%; }}
.site-header {{ background: linear-gradient(135deg, var(--color-maroon) 0%, var(--color-temple) 100%); color: #fff; position: sticky; top: 0; z-index: 100; box-shadow: var(--shadow-md); }}
.header-inner {{ display: flex; align-items: center; justify-content: space-between; height: 64px; }}
.brand {{ display: flex; align-items: center; gap: 12px; }}
.brand-icon {{ font-size: 2rem; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3)); }}
.brand-name {{ font-family: var(--font-display); font-size: 1.5rem; font-weight: 600; }}
.brand-tagline {{ font-size: 0.72rem; opacity: 0.85; letter-spacing: 0.05em; text-transform: uppercase; }}
.header-actions {{ display: flex; gap: 8px; }}
.badge {{ font-size: 0.68rem; padding: 3px 10px; border-radius: 20px; background: rgba(255,255,255,0.18); color: rgba(255,255,255,0.9); }}
.card {{ background: var(--color-surface); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); border: 1px solid var(--color-border); margin-bottom: 24px; overflow: hidden; }}
.card-header {{ padding: 24px 28px 8px; display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
.card-header h2 {{ font-family: var(--font-display); font-size: 1.35rem; font-weight: 600; color: var(--color-maroon); }}
.card-subtitle {{ font-size: 0.85rem; color: var(--color-text-3); }}
.summary-card {{ background: linear-gradient(135deg, var(--color-maroon) 0%, var(--color-temple) 100%); color: #fff; border: none; margin-top: 24px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; }}
.summary-item {{ padding: 18px 24px; border-right: 1px solid rgba(255,255,255,0.12); border-bottom: 1px solid rgba(255,255,255,0.12); }}
.summary-item:nth-child(3n) {{ border-right: none; }}
.summary-item:nth-child(n+7) {{ border-bottom: none; }}
.summary-label {{ display: block; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.7; margin-bottom: 4px; }}
.summary-value {{ display: block; font-family: var(--font-display); font-size: 1.05rem; font-weight: 500; }}
.tabs {{ display: flex; gap: 2px; background: var(--color-border-lt); border-radius: var(--radius-lg) var(--radius-lg) 0 0; padding: 4px 4px 0; overflow-x: auto; flex-wrap: wrap; }}
.tab {{ flex: 1; padding: 12px 16px; background: transparent; border: none; font-family: var(--font-body); font-size: 0.85rem; font-weight: 500; color: var(--color-text-3); cursor: pointer; border-radius: var(--radius) var(--radius) 0 0; transition: all 0.2s; white-space: nowrap; min-width: fit-content; }}
.tab:hover {{ color: var(--color-text); background: rgba(255,255,255,0.5); }}
.tab.active {{ background: var(--color-surface); color: var(--color-saffron-dk); box-shadow: 0 -2px 0 var(--color-saffron) inset; }}
.tab-panel {{ display: none; }} .tab-panel.active {{ display: block; }}
.tab-panel > .card {{ border-radius: 0 0 var(--radius-lg) var(--radius-lg); margin-top: 0; border-top: none; }}
.chart-container {{ display: flex; justify-content: center; padding: 24px; background: var(--color-bg); min-height: 300px; }}
.chart-container svg {{ max-width: 100%; height: auto; max-height: 520px; }}
.chart-meta {{ display: flex; justify-content: center; gap: 32px; padding: 12px 24px; font-size: 0.78rem; color: var(--color-text-3); border-top: 1px solid var(--color-border-lt); }}
.table-wrap {{ overflow-x: auto; padding: 0 4px 16px; }}
.data-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
.data-table th {{ background: var(--color-saffron-lt); color: var(--color-temple); font-weight: 600; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 14px; text-align: left; border-bottom: 2px solid var(--color-border); }}
.data-table td {{ padding: 10px 14px; border-bottom: 1px solid var(--color-border-lt); vertical-align: middle; }}
.data-table tbody tr:hover {{ background: var(--color-gold-lt); }}
.data-table tbody tr.row-highlight {{ background: var(--color-saffron-lt); font-weight: 500; }}
.data-table-sm td, .data-table-sm th {{ padding: 7px 12px; font-size: 0.82rem; }}
.tag-retro {{ display: inline-block; font-size: 0.7rem; padding: 2px 7px; background: var(--color-maroon-lt); color: var(--color-maroon); border-radius: 10px; font-weight: 600; }}
.tag-direct {{ display: inline-block; font-size: 0.7rem; padding: 2px 7px; background: #e8f5e9; color: var(--color-success); border-radius: 10px; font-weight: 500; }}
.tag-birth {{ font-size: 0.68rem; padding: 2px 8px; background: var(--color-gold-lt); color: var(--color-gold); border-radius: 10px; font-weight: 600; }}
.dasha-timeline {{ display: flex; width: 100%; height: 44px; border-radius: var(--radius); overflow: hidden; margin: 16px 0 24px; box-shadow: var(--shadow-sm); }}
.dasha-bar {{ display: flex; align-items: center; justify-content: center; font-size: 0.68rem; font-weight: 600; color: #fff; cursor: pointer; transition: opacity 0.2s; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 4px; }}
.dasha-bar:hover {{ opacity: 0.85; }} .dasha-bar.active-bar {{ box-shadow: inset 0 0 0 2px rgba(255,255,255,0.6); }}
.dasha-ketu {{ background: #607d8b; }} .dasha-venus {{ background: #e91e63; }} .dasha-sun {{ background: #ff9800; }}
.dasha-moon {{ background: #9c27b0; }} .dasha-mars {{ background: #f44336; }} .dasha-rahu {{ background: #3f51b5; }}
.dasha-jupiter {{ background: #ffc107; color: #333; }} .dasha-saturn {{ background: #455a64; }} .dasha-mercury {{ background: #4caf50; }}
.info-box {{ background: var(--color-gold-lt); border: 1px solid #f0e1a1; border-radius: var(--radius); padding: 16px 20px; margin: 16px 20px; }}
.info-box h3 {{ font-family: var(--font-display); font-size: 1rem; color: var(--color-gold); margin-bottom: 8px; }}
.info-box p {{ font-size: 0.85rem; color: var(--color-text-2); margin-bottom: 4px; }}
.section-title {{ font-family: var(--font-display); font-size: 1.1rem; color: var(--color-maroon); padding: 20px 20px 8px; }}
.current-dasha-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; padding: 20px 24px 28px; }}
.dasha-card {{ border-radius: var(--radius); padding: 20px; text-align: center; }}
.dasha-card-maha {{ background: linear-gradient(135deg, var(--color-maroon), var(--color-temple)); color: #fff; }}
.dasha-card-antar {{ background: linear-gradient(135deg, var(--color-saffron), var(--color-saffron-dk)); color: #fff; }}
.dasha-card-pratyantar {{ background: var(--color-gold-lt); border: 1px solid #f0e1a1; color: var(--color-text); }}
.dasha-card-level {{ font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em; opacity: 0.8; margin-bottom: 6px; }}
.dasha-card-lord {{ font-family: var(--font-display); font-size: 1.6rem; font-weight: 600; margin-bottom: 8px; }}
.dasha-card-dates {{ font-size: 0.78rem; opacity: 0.85; }}
.btn {{ display: inline-flex; align-items: center; gap: 6px; padding: 10px 20px; border-radius: var(--radius); font-family: var(--font-body); font-size: 0.88rem; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 0.2s; white-space: nowrap; }}
.btn-outline {{ background: transparent; color: var(--color-text-2); border-color: var(--color-border); }}
.btn-outline:hover {{ background: var(--color-saffron-lt); color: var(--color-saffron-dk); border-color: var(--color-saffron); }}
.btn-primary {{ background: linear-gradient(135deg, var(--color-saffron), var(--color-saffron-dk)); color: #fff; box-shadow: 0 2px 6px rgba(232,118,28,0.3); }}
.btn-primary:hover {{ box-shadow: 0 4px 12px rgba(232,118,28,0.4); transform: translateY(-1px); }}
.btn-sm {{ padding: 6px 12px; font-size: 0.78rem; }}
.btn-expand {{ background: none; border: none; color: var(--color-saffron); cursor: pointer; font-size: 0.82rem; font-weight: 500; padding: 4px 8px; border-radius: 4px; }}
.btn-expand:hover {{ background: var(--color-saffron-lt); }}
.site-footer {{ margin-top: auto; background: var(--color-text); color: rgba(255,255,255,0.6); padding: 20px 0; text-align: center; font-size: 0.78rem; }}
.footer-tech {{ margin-top: 4px; font-size: 0.7rem; opacity: 0.5; }}
.interpretation {{ padding: 20px 28px; }}
.interpretation h3 {{ font-family: var(--font-display); color: var(--color-maroon); margin: 16px 0 8px; font-size: 1.05rem; }}
.interpretation p {{ font-size: 0.88rem; color: var(--color-text-2); margin-bottom: 8px; line-height: 1.7; }}
.interpretation ul {{ margin: 8px 0 16px 20px; font-size: 0.88rem; color: var(--color-text-2); }}
.interpretation li {{ margin-bottom: 6px; line-height: 1.6; }}
.download-bar {{ display: flex; gap: 10px; justify-content: center; padding: 16px; flex-wrap: wrap; }}
@media print {{
    .site-header, .site-footer, .tabs, .download-bar, .btn-expand, .card-actions {{ display: none !important; }}
    .tab-panel {{ display: block !important; page-break-inside: avoid; }}
    .card {{ box-shadow: none; border: 1px solid #ccc; break-inside: avoid; }}
    .summary-card {{ color: #000; background: #f5f5f5 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ background: #fff; }}
    .chart-container svg {{ max-height: 400px; }}
}}
@media (max-width: 768px) {{
    .container {{ padding: 0 16px; }}
    .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .summary-item:nth-child(3n) {{ border-right: 1px solid rgba(255,255,255,0.12); }}
    .summary-item:nth-child(2n) {{ border-right: none; }}
    .tabs {{ gap: 0; }}
    .tab {{ padding: 10px 10px; font-size: 0.75rem; }}
    .current-dasha-grid {{ grid-template-columns: 1fr; }}
}}
    </style>
</head>
<body>

<header class="site-header">
    <div class="container header-inner">
        <div class="brand">
            <span class="brand-icon">&#9790;</span>
            <div>
                <h1 class="brand-name">Jyotish</h1>
                <p class="brand-tagline">Complete Vedic Horoscope Report</p>
            </div>
        </div>
        <nav class="header-actions">
            <span class="badge">Lahiri Ayanamsa</span>
            <span class="badge">Swiss Ephemeris</span>
        </nav>
    </div>
</header>

<main class="container">

    <!-- Download Bar -->
    <div class="download-bar" style="margin-top:24px;">
        <button class="btn btn-primary" onclick="window.print()">&#128424; Print / Save as PDF</button>
        <button class="btn btn-outline" onclick="downloadHTML()">&#11015; Download HTML</button>
    </div>

    <!-- Birth Summary -->
    <div class="card summary-card">
        <div class="summary-grid">
            <div class="summary-item">
                <span class="summary-label">Date &amp; Time</span>
                <span class="summary-value">11 Sep 2009, 01:17 AM</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Place</span>
                <span class="summary-value">Dubai, UAE</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Coordinates</span>
                <span class="summary-value">25.2048&deg;N, 55.2708&deg;E (UTC+4)</span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Lagna (Ascendant)</span>
                <span class="summary-value" id="summaryLagna"></span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Moon Sign (Rashi)</span>
                <span class="summary-value" id="summaryMoonSign"></span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Nakshatra</span>
                <span class="summary-value" id="summaryNakshatra"></span>
            </div>
            <div class="summary-item">
                <span class="summary-label">Ayanamsa (Lahiri)</span>
                <span class="summary-value" id="summaryAyanamsa"></span>
            </div>
            <div class="summary-item">
                <span class="summary-label">D9 Navamsha Lagna</span>
                <span class="summary-value" id="summaryD9Lagna"></span>
            </div>
            <div class="summary-item">
                <span class="summary-label">D10 Dashamsha Lagna</span>
                <span class="summary-value" id="summaryD10Lagna"></span>
            </div>
        </div>
    </div>

    <!-- Tabs -->
    <div class="tabs">
        <button class="tab active" data-tab="chartTab">D1 Rashi</button>
        <button class="tab" data-tab="d9Tab">D9 Navamsha</button>
        <button class="tab" data-tab="d10Tab">D10 Dashamsha</button>
        <button class="tab" data-tab="planetsTab">Planets</button>
        <button class="tab" data-tab="dashaTab">Dasha Timeline</button>
        <button class="tab" data-tab="currentTab">Current Dasha</button>
        <button class="tab" data-tab="interpretTab">Interpretation</button>
    </div>

    <!-- Tab: D1 Rashi Chart -->
    <div id="chartTab" class="tab-panel active">
        <div class="card">
            <div class="card-header">
                <h2>D1 &mdash; Rashi Chart (South Indian)</h2>
                <div class="card-actions">
                    <button class="btn btn-sm btn-outline" onclick="downloadSVG('d1')">&#11015; SVG</button>
                </div>
            </div>
            <div id="d1Container" class="chart-container"></div>
            <div class="chart-meta">
                <span>Ayanamsa: <strong id="chartAyanamsa"></strong> (Lahiri)</span>
                <span>Julian Day: <strong id="chartJD"></strong></span>
            </div>
        </div>
    </div>

    <!-- Tab: D9 Navamsha -->
    <div id="d9Tab" class="tab-panel">
        <div class="card">
            <div class="card-header">
                <h2>D9 &mdash; Navamsha Chart</h2>
                <p class="card-subtitle">Spouse, dharma, spiritual fortune &mdash; the soul chart</p>
            </div>
            <div id="d9Container" class="chart-container"></div>
            <div class="table-wrap" style="padding-top:8px;">
                <table class="data-table data-table-sm">
                    <thead><tr><th>Planet</th><th>D9 Sign</th><th>Sanskrit</th><th>House</th><th>Lord</th><th>Status</th></tr></thead>
                    <tbody id="d9TableBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Tab: D10 Dashamsha -->
    <div id="d10Tab" class="tab-panel">
        <div class="card">
            <div class="card-header">
                <h2>D10 &mdash; Dashamsha Chart</h2>
                <p class="card-subtitle">Career, profession, public standing &mdash; the karma chart</p>
            </div>
            <div id="d10Container" class="chart-container"></div>
            <div class="table-wrap" style="padding-top:8px;">
                <table class="data-table data-table-sm">
                    <thead><tr><th>Planet</th><th>D10 Sign</th><th>Sanskrit</th><th>House</th><th>Lord</th><th>Status</th></tr></thead>
                    <tbody id="d10TableBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Tab: Planetary Positions -->
    <div id="planetsTab" class="tab-panel">
        <div class="card">
            <div class="card-header">
                <h2>Planetary Positions (D1)</h2>
                <p class="card-subtitle">Sidereal longitudes &mdash; Lahiri Ayanamsa</p>
            </div>
            <div class="table-wrap">
                <table class="data-table">
                    <thead><tr><th>Planet</th><th>Rashi</th><th>Sanskrit</th><th>Degrees</th><th>House</th><th>Lord</th><th>Status</th></tr></thead>
                    <tbody id="planetsTableBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Tab: Dasha Timeline -->
    <div id="dashaTab" class="tab-panel">
        <div class="card">
            <div class="card-header">
                <h2>Vimshottari Maha Dasha Timeline</h2>
                <p class="card-subtitle">120-year cycle based on Moon Nakshatra at birth</p>
            </div>
            <div id="dashaBalanceBox" class="info-box">
                <h3>Dasha Balance at Birth</h3>
                <div id="dashaBalanceContent"></div>
            </div>
            <div id="dashaTimeline" class="dasha-timeline" style="margin:16px 20px 24px;"></div>
            <div class="table-wrap">
                <table class="data-table">
                    <thead><tr><th>#</th><th>Dasha Lord</th><th>Start Date</th><th>End Date</th><th>Duration</th><th></th></tr></thead>
                    <tbody id="dashaTableBody"></tbody>
                </table>
            </div>
            <div id="antardashaSection" style="display:none;">
                <h3 id="antardashaTitle" class="section-title"></h3>
                <div class="table-wrap">
                    <table class="data-table data-table-sm">
                        <thead><tr><th>#</th><th>Antardasha Lord</th><th>Start</th><th>End</th><th>Duration</th></tr></thead>
                        <tbody id="antardashaTableBody"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Tab: Current Dasha -->
    <div id="currentTab" class="tab-panel">
        <div class="card">
            <div class="card-header">
                <h2>Currently Running Dasha</h2>
                <p class="card-subtitle">As of 15 Feb 2026</p>
            </div>
            <div id="currentDashaContent" class="current-dasha-grid"></div>
        </div>
    </div>

    <!-- Tab: Interpretation -->
    <div id="interpretTab" class="tab-panel">
        <div class="card">
            <div class="card-header">
                <h2>Chart Interpretation &amp; Key Yogas</h2>
                <p class="card-subtitle">Vedic astrology analysis based on planetary placements</p>
            </div>
            <div class="interpretation" id="interpretContent"></div>
        </div>
    </div>

</main>

<footer class="site-footer">
    <div class="container">
        <p>&copy; 2026 Jyotish &mdash; Vedic Astrology Calculator</p>
        <p class="footer-tech">Swiss Ephemeris &middot; Lahiri Ayanamsa &middot; Vimshottari Dasha</p>
    </div>
</footer>

<script>
// ── Embedded chart data ──────────────────────────────────────────────────
const DATA = {json.dumps(chart_data, indent=2)};

const D1_SVG = {json.dumps(d1_svg)};
const D9_SVG = {json.dumps(d9_svg)};
const D10_SVG = {json.dumps(d10_svg)};

const $=s=>document.querySelector(s);
const $$=s=>document.querySelectorAll(s);

document.addEventListener("DOMContentLoaded", ()=>{{
    renderSummary();
    renderCharts();
    renderPlanets();
    renderD9Table();
    renderD10Table();
    renderDasha();
    renderCurrentDasha();
    renderInterpretation();
    bindTabs();
}});

function renderSummary(){{
    const c=DATA.chart, n=DATA.nakshatra;
    $("#summaryLagna").textContent=`${{c.ascendant.sign}} (${{c.ascendant.sign_sanskrit}}) ${{c.ascendant.degrees}} — Lord: ${{c.ascendant.lord}}`;
    const moon=c.planets.find(p=>p.name==="Moon");
    if(moon) $("#summaryMoonSign").textContent=`${{moon.sign}} (${{moon.sign_sanskrit}})`;
    $("#summaryNakshatra").textContent=`${{n.name}} #${{n.number}}, Pada ${{n.pada}} — Lord: ${{n.lord}}`;
    $("#summaryAyanamsa").textContent=c.ayanamsa;
    const d9=DATA.d9;
    $("#summaryD9Lagna").textContent=`${{d9.ascendant.sign}} (${{d9.ascendant.sign_sanskrit}})`;
    const d10=DATA.d10;
    $("#summaryD10Lagna").textContent=`${{d10.ascendant.sign}} (${{d10.ascendant.sign_sanskrit}})`;
}}

function renderCharts(){{
    $("#d1Container").innerHTML=D1_SVG||'<p style="color:#999;padding:40px">D1 chart not available</p>';
    $("#d9Container").innerHTML=D9_SVG||'<p style="color:#999;padding:40px">D9 chart not available</p>';
    $("#d10Container").innerHTML=D10_SVG||'<p style="color:#999;padding:40px">D10 chart not available</p>';
    $("#chartAyanamsa").textContent=DATA.chart.ayanamsa;
    $("#chartJD").textContent=DATA.chart.julian_day;
}}

function renderPlanets(){{
    const tbody=$("#planetsTableBody"); tbody.innerHTML="";
    const asc=DATA.chart.ascendant;
    const ascRow=document.createElement("tr"); ascRow.classList.add("row-highlight");
    ascRow.innerHTML=`<td><strong>Ascendant</strong></td><td>${{asc.sign}}</td><td>${{asc.sign_sanskrit}}</td><td>${{asc.degrees}}</td><td>1</td><td>${{asc.lord}}</td><td>—</td>`;
    tbody.appendChild(ascRow);
    DATA.chart.planets.forEach(p=>{{
        const tr=document.createElement("tr");
        const st=p.retrograde?'<span class="tag-retro">R</span>':'<span class="tag-direct">D</span>';
        tr.innerHTML=`<td><strong>${{p.name}}</strong></td><td>${{p.sign}}</td><td>${{p.sign_sanskrit}}</td><td>${{p.degrees}}</td><td>${{p.house}}</td><td>${{p.lord}}</td><td>${{st}}</td>`;
        tbody.appendChild(tr);
    }});
}}

function renderDivisionalTable(planets, tbodyId){{
    const tbody=$(tbodyId); tbody.innerHTML="";
    planets.forEach(p=>{{
        const tr=document.createElement("tr");
        const st=p.retrograde?'<span class="tag-retro">R</span>':'<span class="tag-direct">D</span>';
        tr.innerHTML=`<td><strong>${{p.name}}</strong></td><td>${{p.sign}}</td><td>${{p.sign_sanskrit}}</td><td>${{p.house}}</td><td>${{p.lord}}</td><td>${{st}}</td>`;
        tbody.appendChild(tr);
    }});
}}
function renderD9Table(){{ renderDivisionalTable(DATA.d9.planets, "#d9TableBody"); }}
function renderD10Table(){{ renderDivisionalTable(DATA.d10.planets, "#d10TableBody"); }}

function formatDate(s){{
    if(!s) return "—";
    const parts=s.split(" ")[0].split("-");
    const months=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return `${{parseInt(parts[2])}}-${{months[parseInt(parts[1])-1]}}-${{parts[0]}}`;
}}

function renderDasha(){{
    const report=DATA.dasha_report; if(!report) return;
    const bal=report.dasha_balance, nak=report.nakshatra;
    $("#dashaBalanceContent").innerHTML=`<p><strong>Birth Nakshatra:</strong> ${{nak.name}} (#${{nak.number}}, Pada ${{nak.pada}})</p><p><strong>Nakshatra Lord:</strong> ${{nak.lord}}</p><p><strong>Starting Dasha:</strong> ${{bal.lord}} — Balance: ${{bal.balance_ymd.years}}y ${{bal.balance_ymd.months}}m ${{bal.balance_ymd.days}}d</p>`;
    const tl=$("#dashaTimeline"); tl.innerHTML="";
    const total=report.maha_dashas.reduce((s,d)=>s+d.duration_years,0);
    const activeMaha=DATA.current_dasha?DATA.current_dasha.maha:null;
    report.maha_dashas.forEach(md=>{{
        const pct=(md.duration_years/total)*100;
        const bar=document.createElement("div");
        bar.className=`dasha-bar dasha-${{md.maha_dasha_lord.toLowerCase()}}`;
        if(md.maha_dasha_lord===activeMaha) bar.classList.add("active-bar");
        bar.style.width=`${{pct}}%`;
        bar.textContent=md.maha_dasha_lord.substring(0,3);
        bar.title=`${{md.maha_dasha_lord}}: ${{formatDate(md.start_date)}} to ${{formatDate(md.end_date)}}`;
        bar.addEventListener("click",()=>showAntardashas(md));
        tl.appendChild(bar);
    }});
    const tbody=$("#dashaTableBody"); tbody.innerHTML="";
    report.maha_dashas.forEach((md,i)=>{{
        const tr=document.createElement("tr");
        if(md.maha_dasha_lord===activeMaha) tr.classList.add("row-highlight");
        const birthTag=md.is_birth_dasha?' <span class="tag-birth">Birth</span>':"";
        const dur=`${{md.duration_ymd.years}}y ${{md.duration_ymd.months}}m ${{md.duration_ymd.days}}d`;
        tr.innerHTML=`<td>${{i+1}}</td><td><strong>${{md.maha_dasha_lord}}</strong>${{birthTag}}</td><td>${{formatDate(md.start_date)}}</td><td>${{formatDate(md.end_date)}}</td><td>${{dur}}</td><td><button class="btn-expand" data-idx="${{i}}">View Bhukti &#9660;</button></td>`;
        tbody.appendChild(tr);
    }});
    $$(".btn-expand").forEach(btn=>{{
        btn.addEventListener("click",()=>showAntardashas(report.maha_dashas[parseInt(btn.dataset.idx)]));
    }});
}}

function showAntardashas(md){{
    const sec=$("#antardashaSection"); sec.style.display="block";
    $("#antardashaTitle").textContent=`Antardashas within ${{md.maha_dasha_lord}} Maha Dasha`;
    const tbody=$("#antardashaTableBody"); tbody.innerHTML="";
    md.antardashas.forEach((ad,i)=>{{
        const tr=document.createElement("tr");
        const dur=`${{ad.duration_ymd.years}}y ${{ad.duration_ymd.months}}m ${{ad.duration_ymd.days}}d`;
        tr.innerHTML=`<td>${{i+1}}</td><td><strong>${{ad.antar_dasha_lord}}</strong></td><td>${{formatDate(ad.start_date)}}</td><td>${{formatDate(ad.end_date)}}</td><td>${{dur}}</td>`;
        tbody.appendChild(tr);
    }});
    sec.scrollIntoView({{behavior:"smooth",block:"nearest"}});
}}

function renderCurrentDasha(){{
    const cd=DATA.current_dasha, el=$("#currentDashaContent");
    if(!cd){{ el.innerHTML='<p style="padding:20px;color:#999;">Not available</p>'; return; }}
    let html=`<div class="dasha-card dasha-card-maha"><div class="dasha-card-level">Maha Dasha</div><div class="dasha-card-lord">${{cd.maha}}</div><div class="dasha-card-dates">${{cd.maha_start}} — ${{cd.maha_end}}</div></div><div class="dasha-card dasha-card-antar"><div class="dasha-card-level">Antardasha (Bhukti)</div><div class="dasha-card-lord">${{cd.antar}}</div><div class="dasha-card-dates">${{cd.antar_start}} — ${{cd.antar_end}}</div></div>`;
    if(cd.pratyantar) html+=`<div class="dasha-card dasha-card-pratyantar"><div class="dasha-card-level">Pratyantardasha</div><div class="dasha-card-lord">${{cd.pratyantar}}</div><div class="dasha-card-dates">${{cd.pratyantar_start}} — ${{cd.pratyantar_end}}</div></div>`;
    el.innerHTML=html;
}}

function renderInterpretation(){{
    const c=DATA.chart, cd=DATA.current_dasha, n=DATA.nakshatra;
    const planets=c.planets;
    const sun=planets.find(p=>p.name==="Sun");
    const moon=planets.find(p=>p.name==="Moon");
    const mars=planets.find(p=>p.name==="Mars");
    const merc=planets.find(p=>p.name==="Mercury");
    const jup=planets.find(p=>p.name==="Jupiter");
    const ven=planets.find(p=>p.name==="Venus");
    const sat=planets.find(p=>p.name==="Saturn");
    const rahu=planets.find(p=>p.name==="Rahu");
    const ketu=planets.find(p=>p.name==="Ketu");

    let html=`
    <h3>Lagna Analysis &mdash; ${{c.ascendant.sign}} (${{c.ascendant.sign_sanskrit}}) Ascendant</h3>
    <p>The native has <strong>Gemini (Mithuna) Lagna</strong>, ruled by Mercury. Gemini ascendants are characterised by intellectual curiosity, communication skills, adaptability, and a quick-learning nature. Mercury as Lagna lord makes education and analytical thinking central to the personality.</p>

    <h3>Key Planetary Placements</h3>
    <ul>
        <li><strong>Mars in 1st House (Gemini)</strong> &mdash; Mars in the Lagna gives strong physical vitality, courage, competitive spirit, and a dynamic personality. This is a Manglik placement. The native is action-oriented and assertive.</li>
        <li><strong>Sun in 3rd House (Leo, own sign)</strong> &mdash; Sun in its own sign Leo in the 3rd house is excellent. It gives confident self-expression, courage in communication, strong willpower, leadership among siblings, and success through personal efforts. The 3rd house Sun makes the native bold and enterprising.</li>
        <li><strong>Mercury Retrograde in 4th House (Virgo, own sign)</strong> &mdash; Mercury in its own sign Virgo, albeit retrograde, gives a powerful but introspective intellect. The 4th house placement indicates academic excellence, comfort through knowledge, and a strong analytical mind. Retrograde Mercury suggests deep thinking and revisiting ideas before conclusion.</li>
        <li><strong>Saturn in 4th House (Virgo)</strong> &mdash; Saturn in the 4th house can bring delayed domestic happiness but gives discipline, structure, and persistence in education. Combined with Mercury, it creates a serious student with methodical study habits.</li>
        <li><strong>Venus in 2nd House (Cancer)</strong> &mdash; Venus in the 2nd house brings sweetness in speech, love for family wealth, and appreciation of art and beauty. In Cancer, Venus is nurturing and emotionally expressive.</li>
        <li><strong>Ketu in 2nd House (Cancer)</strong> &mdash; Ketu with Venus in the 2nd house adds a spiritual dimension to family values and speech. It may create an unconventional approach to wealth.</li>
        <li><strong>Moon in 12th House (Taurus)</strong> &mdash; Moon in Taurus is very comfortable (Moon is exalted in Taurus). However, the 12th house placement inclines toward a rich inner life, vivid dreams, spiritual leanings, and potential for foreign connections. The exalted Moon mitigates 12th house difficulties significantly.</li>
        <li><strong>Jupiter Retrograde in 8th House (Capricorn, debilitated)</strong> &mdash; Jupiter in Capricorn is debilitated and in the 8th house of transformation. This calls for developing wisdom through challenges. Retrograde Jupiter suggests re-evaluation of beliefs and deep research ability. The debilitation may be cancelled (Neecha Bhanga) if Saturn is well-placed.</li>
        <li><strong>Rahu in 8th House (Capricorn)</strong> &mdash; Rahu in the 8th house intensifies interest in mysteries, occult sciences, and deep research. Combined with Jupiter, it can give sudden insights and unconventional wisdom.</li>
    </ul>

    <h3>Notable Yogas</h3>
    <ul>
        <li><strong>Budhaditya Yoga potential</strong> &mdash; Sun in Leo (3rd) and Mercury in Virgo (4th) are in adjacent signs. While not in the same house, Mercury ruling the Lagna and Sun ruling the 3rd create a strong communication axis.</li>
        <li><strong>Neecha Bhanga Raja Yoga</strong> &mdash; Jupiter is debilitated in Capricorn, but Saturn (lord of Capricorn) is in a Kendra from Moon, potentially cancelling the debilitation and converting it into a Raja Yoga for rise after struggle.</li>
        <li><strong>Ruchaka Yoga potential</strong> &mdash; Mars in a Kendra (1st house) gives strong Ruchaka Yoga qualities: courage, physical strength, leadership ability, and a commanding presence.</li>
        <li><strong>Gajakesari Yoga consideration</strong> &mdash; Moon in Taurus (exalted) and Jupiter in a Kendra from Moon (7th from Moon) creates a form of Gajakesari Yoga, giving wisdom, good reputation, and lasting success despite challenges.</li>
    </ul>

    <h3>Moon Sign &amp; Nakshatra</h3>
    <p><strong>Moon in Taurus (Vrishabha)</strong> &mdash; The Moon sign indicates an emotionally stable, loyal, comfort-seeking, and patient inner nature. Taurus Moon natives value security and have strong aesthetic sensibility.</p>
    <p><strong>Krittika Nakshatra, Pada 4</strong> &mdash; Krittika is ruled by the Sun and is associated with sharpness, purification, and the ability to cut through illusion. Pada 4 falls in the Pisces navamsha, adding spiritual depth and compassion. The fire of Krittika combined with earthy Taurus creates a determined and dignified character.</p>

    <h3>D9 Navamsha Highlights</h3>
    <p>The Navamsha (D9) chart reveals the deeper soul purpose, dharma, and marriage potential. The D9 Lagna is <strong>${{DATA.d9.ascendant.sign}} (${{DATA.d9.ascendant.sign_sanskrit}})</strong>, indicating the inner spiritual orientation and the qualities that will manifest more strongly in the second half of life.</p>

    <h3>D10 Dashamsha Highlights</h3>
    <p>The Dashamsha (D10) chart governs career and professional life. The D10 Lagna is <strong>${{DATA.d10.ascendant.sign}} (${{DATA.d10.ascendant.sign_sanskrit}})</strong>. This chart should be studied as the native grows into professional life to understand career direction, achievements, and public standing.</p>

    <h3>Current Dasha Period (15 Feb 2026)</h3>`;
    if(cd){{
        html+=`<p>Currently running <strong>${{cd.maha}} Maha Dasha / ${{cd.antar}} Antardasha</strong>`;
        if(cd.pratyantar) html+=` / ${{cd.pratyantar}} Pratyantardasha`;
        html+=`.</p>`;
        html+=`<p><strong>Mars Maha Dasha (Mar 2020 — Mar 2027)</strong> activates the energy of Mars in the 1st house. This period brings physical activity, competitive spirit, initiatives, and courage. Mars being the Lagna planet in the chart gives this Dasha special significance for self-development and taking bold action.</p>`;
        html+=`<p><strong>Venus Antardasha (Feb 2025 — Apr 2026)</strong> within Mars Dasha brings a blend of Mars' drive with Venus' refinement. This period favours creative pursuits, artistic interests, social connections, and developing aesthetic sensibilities. Venus in the 2nd house makes this period good for developing speech, accumulating resources, and family harmony.</p>`;
    }}
    html+=`

    <h3>Life Themes Summary</h3>
    <ul>
        <li><strong>Education &amp; Intellect:</strong> Very strong — Mercury in own sign (Virgo, 4th house) + Saturn's discipline. Academic excellence is highly indicated, especially in analytical, scientific, or technical subjects.</li>
        <li><strong>Communication:</strong> Outstanding — Gemini Lagna + Sun in Leo (3rd) + Mars energy. Natural ability in writing, speaking, and media.</li>
        <li><strong>Career direction:</strong> Likely in fields requiring analytical thinking, research, technology, communication, or management. The D10 chart should be monitored as the native matures.</li>
        <li><strong>Spiritual inclination:</strong> Moon in 12th (exalted) + Ketu in 2nd + Jupiter in 8th suggest deep spiritual potential that will manifest with age.</li>
        <li><strong>Health:</strong> Mars in Lagna gives robust constitution. Attention to digestive health (Saturn in 4th) and emotional well-being (Moon in 12th) is advisable.</li>
    </ul>
    `;
    $("#interpretContent").innerHTML=html;
}}

function bindTabs(){{
    $$(".tab").forEach(tab=>{{
        tab.addEventListener("click",()=>{{
            $$(".tab").forEach(t=>t.classList.remove("active"));
            $$(".tab-panel").forEach(p=>p.classList.remove("active"));
            tab.classList.add("active");
            const panel=$("#"+tab.dataset.tab);
            if(panel) panel.classList.add("active");
        }});
    }});
}}

function downloadSVG(chart){{
    let svg;
    if(chart==='d1') svg=document.querySelector("#d1Container svg");
    else if(chart==='d9') svg=document.querySelector("#d9Container svg");
    else svg=document.querySelector("#d10Container svg");
    if(!svg){{ alert("Chart not available"); return; }}
    const data=new XMLSerializer().serializeToString(svg);
    const blob=new Blob([data],{{type:"image/svg+xml"}});
    const url=URL.createObjectURL(blob);
    const a=document.createElement("a"); a.href=url; a.download=`vedic_${{chart}}_chart.svg`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
}}

function downloadHTML(){{
    const html=document.documentElement.outerHTML;
    const blob=new Blob([html],{{type:"text/html"}});
    const url=URL.createObjectURL(blob);
    const a=document.createElement("a"); a.href=url; a.download="vedic_horoscope_11Sep2009_Dubai.html";
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
}}
</script>
</body>
</html>'''

output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "horoscope_11Sep2009_Dubai.html")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(html_output)

print(f"\nHoroscope HTML generated: {output_path}")
print(f"D1 SVG: {d1_svg_path}")
print(f"D9 SVG: {d9_svg_path}")
print(f"D10 SVG: {d10_svg_path}")
print(f"\nBirth Nakshatra: {nakshatra['name']} #{nakshatra['number']}, Pada {nakshatra['pada']}")
print(f"Moon longitude: {moon_lon:.4f}")
print(f"Current Dasha: {current_dasha}")
