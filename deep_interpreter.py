"""
Classical Parashari Jyotish Deep Consultation Engine
=====================================================
Role: Classical Parashari Jyotish Analyst — generates a complete life consultation
strictly following the doctrinal framework of Brihat Parashara Hora Shastra.

Interpretive Principles (from BPHS Doctrine):
  - Synthesise results ONLY through classical Parashari logic
  - Graha nature, Rāśi placement, Bhava outcomes, Yogas, Strength, Dasha unfolding
  - No modern or pop-astrology interpretations
  - Deterministic but advisory tone — classical register throughout

Style Requirements:
  - Classical tone — no casual language
  - Deterministic but advisory; no generic personality descriptions
  - Output: complete Parashari life consultation, not a personality reading

Objective: Deliver a consultation reflecting structure of destiny, karmic unfolding,
timing of experience, means of alignment, career, marriage, and spiritual direction.

Cross-referenced sources:
  - Brihat Parasara Hora Shastra (Girish Chand Sharma & Maharishi Parashara eds.)
  - lord_effects.json  — BPHS slokas for lord-in-house placements
  - house_chapters.json — BPHS chapter summaries for each house
  - interpretations.py  — classical planet-in-house text layer
  - bphs_engine.py      — existing BPHS sloka engine
"""

import os
import json
import math
import logging
import tempfile
from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Any

logger = logging.getLogger("vedic.deep")

# ── Chart generation imports ─────────────────────────────────────────────────
try:
    import swisseph as swe
    import jyotichart
    from chart_gen import (
        RASHI_NAMES, RASHI_SANSKRIT, RASHI_LORDS,
        JYOTICHART_PLANET_MAP, deg_to_dms, rashi_to_house,
        generate_south_chart, EPHE_PATH,
    )
    HAS_CHART_GEN = True
except ImportError as e:
    HAS_CHART_GEN = False
    logger.warning(f"Chart generation imports unavailable: {e}")

# ── B.V. Raman Rule Engine Integration ───────────────────────────────────────
try:
    import bv_raman_rules
    HAS_RAMAN_RULES = True
except ImportError:
    HAS_RAMAN_RULES = False
    logger.warning("bv_raman_rules module not found — falling back to basic yoga detection")

# ── AI Interpretation Layer ──────────────────────────────────────────────────
try:
    import ai_interpreter
    HAS_AI_LAYER = True
except ImportError:
    HAS_AI_LAYER = False
    logger.info("ai_interpreter module not found — AI narrative layer disabled")

# ── Chart Helpers — D1, D9, Transit SVG generation ───────────────────────────

def _read_svg(path: str) -> str:
    """Read an SVG file and return its content as a string."""
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            raw = f.read()
        for enc in ("utf-8-sig", "utf-16", "utf-16-le", "latin-1"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
    return ""


def _navamsha_sign_index(sidereal_longitude: float) -> int:
    """Compute Navamsha (D9) sign index from sidereal longitude."""
    sign_idx = int(sidereal_longitude / 30) % 12
    deg_in_sign = sidereal_longitude % 30
    navamsha_num = int(deg_in_sign / (30 / 9))
    fire_signs = [0, 4, 8]
    earth_signs = [1, 5, 9]
    air_signs = [2, 6, 10]
    if sign_idx in fire_signs:
        start = 0
    elif sign_idx in earth_signs:
        start = 3
    elif sign_idx in air_signs:
        start = 6
    else:
        start = 9
    return (start + navamsha_num) % 12


def _dasamsa_sign_index(sidereal_longitude: float) -> int:
    """Compute Dasamsa (D10) sign index from sidereal longitude.
    Each sign is divided into 10 equal parts of 3° each.
    For odd signs: count starts from the sign itself.
    For even signs: count starts from the 9th sign from it."""
    sign_idx = int(sidereal_longitude / 30) % 12
    deg_in_sign = sidereal_longitude % 30
    dasamsa_num = int(deg_in_sign / 3)  # 0-9 (each pada = 3°)
    # Odd signs (0-indexed: Aries=0 is odd sign #1): start from sign itself
    # Even signs (Taurus=1 is even sign #2): start from 9th sign
    if sign_idx % 2 == 0:  # Odd signs (Aries, Gemini, Leo, etc.)
        start = sign_idx
    else:  # Even signs (Taurus, Cancer, Virgo, etc.)
        start = (sign_idx + 9) % 12
    return (start + dasamsa_num) % 12


def _build_position_table(planet_data: list, asc_sign_index: int,
                          color: str = "var(--gold)") -> str:
    """Build an HTML position table for a chart's planet data."""
    rows = ""
    for p in planet_data:
        sign_idx = p.get("sign_index", p.get("d9_sign_index", 0))
        house_num = rashi_to_house(sign_idx, asc_sign_index)
        sign_name = SIGN_NAMES[sign_idx] if sign_idx < 12 else "?"
        deg = p.get("sign_deg", 0)
        retro = p.get("retrograde", False)
        r_mark = " (R)" if retro else ""
        deg_str = f"{deg:.1f}°{r_mark}" if deg else r_mark.strip()
        rows += (
            f"<tr><td style='color:{color};font-weight:600;'>{p['name']}</td>"
            f"<td>{sign_name} {deg_str}</td>"
            f"<td>House {house_num}</td></tr>\n"
        )
    return f"""<table style="width:100%;border-collapse:collapse;font-size:0.92em;">
      <thead><tr style="border-bottom:2px solid rgba(201,168,76,.4);">
        <th style="text-align:left;padding:6px;color:{color};">Planet</th>
        <th style="text-align:left;padding:6px;color:{color};">Position</th>
        <th style="text-align:left;padding:6px;color:{color};">House</th>
      </tr></thead><tbody>{rows}</tbody></table>"""


def _generate_chart_svg(planet_data: list, asc_sign_index: int,
                        chart_name: str, person_name: str) -> str:
    """Generate a South Indian chart SVG string using jyotichart.
    Returns inline SVG content or empty string on failure."""
    if not HAS_CHART_GEN:
        return ""
    try:
        chart = jyotichart.SouthChart(
            chartname=chart_name,
            personname=person_name,
            IsFullChart=True,
        )
        asc_sign = RASHI_NAMES[asc_sign_index]
        res = chart.set_ascendantsign(asc_sign)
        if res != "Success" and asc_sign == "Sagittarius":
            chart.set_ascendantsign("Saggitarius")  # jyotichart fallback

        for p in planet_data:
            sign_idx = p.get("sign_index", p.get("d9_sign_index", 0))
            house_num = rashi_to_house(sign_idx, asc_sign_index)
            jc_planet = JYOTICHART_PLANET_MAP.get(p["name"])
            if not jc_planet:
                continue
            # Short label to avoid overlap; full details in the position table
            abbr = p["name"][:2]
            label = abbr
            retro = p.get("retrograde", False)
            # Delete any pre-existing planet first (IsFullChart may pre-populate)
            chart.delete_planet(planet=jc_planet)
            chart.add_planet(planet=jc_planet, symbol=label,
                           housenum=house_num, retrograde=retro)

        with tempfile.TemporaryDirectory() as tmpdir:
            chart.draw(location=tmpdir, filename=chart_name)
            svg_path = os.path.join(tmpdir, f"{chart_name}.svg")
            return _read_svg(svg_path)
    except Exception as e:
        logger.warning(f"Chart generation failed for {chart_name}: {e}")
        return ""


def _generate_d1_d9_d10_html(positions: dict, name: str) -> str:
    """Generate D1 (Rashi), D9 (Navamsha), and D10 (Dasamsa) charts
    stacked vertically, each with a position table alongside."""
    if not HAS_CHART_GEN:
        return ""

    asc_idx = positions.get("ascendant", {}).get("sign_index", 0)
    asc_lon = positions.get("ascendant", {}).get("longitude", 0)
    planets = positions.get("planets", [])
    lagna_name = SIGN_NAMES[asc_idx] if asc_idx < 12 else "Aries"

    # ── D1 Rashi ─────────────────────────────────────────────────
    d1_svg = _generate_chart_svg(planets, asc_idx, "D1_Rashi", name)
    d1_table = _build_position_table(planets, asc_idx, color="var(--gold)")

    # ── D9 Navamsha ──────────────────────────────────────────────
    d9_planets = []
    for p in planets:
        d9_sign = _navamsha_sign_index(p["longitude"])
        d9_planets.append({
            "name": p["name"],
            "sign_index": d9_sign,
            "sign_deg": p["longitude"] % (30 / 9) * 9,
            "retrograde": p["retrograde"],
        })
    d9_asc = _navamsha_sign_index(asc_lon)
    d9_svg = _generate_chart_svg(d9_planets, d9_asc, "D9_Navamsha", name)
    d9_table = _build_position_table(d9_planets, d9_asc, color="#B07DC9")

    # ── D10 Dasamsa ──────────────────────────────────────────────
    d10_planets = []
    for p in planets:
        d10_sign = _dasamsa_sign_index(p["longitude"])
        d10_planets.append({
            "name": p["name"],
            "sign_index": d10_sign,
            "sign_deg": p["longitude"] % 3 * 10,  # approx degree in D10 sign
            "retrograde": p["retrograde"],
        })
    d10_asc = _dasamsa_sign_index(asc_lon)
    d10_svg = _generate_chart_svg(d10_planets, d10_asc, "D10_Dasamsa", name)
    d10_table = _build_position_table(d10_planets, d10_asc, color="#2E86AB")

    if not d1_svg and not d9_svg and not d10_svg:
        return ""

    def _chart_block(title, subtitle, svg, table, tag_color, border_color):
        return f"""
    <div style="margin-bottom:36px;">
      <div style="font-weight:700; color:{tag_color}; margin-bottom:12px; font-size:1.15em;
           border-bottom:2px solid {border_color}; padding-bottom:6px;">
        {title}
        <span style="font-size:0.75em; color:rgba(250,246,238,.5); margin-left:8px;">{subtitle}</span>
      </div>
      <div style="display:flex; gap:20px; flex-wrap:wrap; align-items:flex-start;">
        <div style="flex:1 1 340px; min-width:280px; max-width:500px;">
          <div style="background:#0d0d0d; border:1px solid {border_color}; border-radius:8px;
               padding:10px; overflow:hidden;">
            <div style="width:100%; max-width:100%;" class="chart-wrap">{svg}</div>
          </div>
        </div>
        <div style="flex:1 1 300px; min-width:250px;">
          <div style="font-weight:600; color:{tag_color}; margin-bottom:8px; font-size:0.95em;">
            Planetary Positions</div>
          {table}
        </div>
      </div>
    </div>"""

    d1_block = _chart_block(
        "D1 — Rashi (Birth Chart)", "Foundation of all predictions",
        d1_svg, d1_table, "var(--gold)", "rgba(201,168,76,.3)")
    d9_block = _chart_block(
        "D9 — Navamsha (Destiny Chart)", "Soul strength · Marriage · Inner dignity",
        d9_svg, d9_table, "#B07DC9", "rgba(176,125,201,.3)")
    d10_block = _chart_block(
        "D10 — Dasamsa (Career Chart)", "Professional destiny · Status · Karma in action",
        d10_svg, d10_table, "#2E86AB", "rgba(46,134,171,.3)")

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">BIRTH CHARTS</span>
    <div>
      <div class="sec-title">Divisional Charts &mdash; D1, D9 &amp; D10</div>
      <span class="sec-skt">&#2352;&#2366;&#2358;&#2367; &#2330;&#2325;&#2381;&#2352;
        &middot; &#2344;&#2357;&#2366;&#2306;&#2358; &middot; &#2342;&#2358;&#2366;&#2306;&#2358;</span>
    </div>
    <div class="sec-line"></div>
  </div>
  {d1_block}
  {d9_block}
  {d10_block}
  <div class="callout" style="background:rgba(201,168,76,.05);border-color:rgba(201,168,76,.3);">
    <strong style="color:var(--gold);">Reading Guide:</strong>
    The <strong>D1 (Rashi)</strong> chart is the foundation — all predictions begin here.
    The <strong>D9 (Navamsha)</strong> reveals your soul's deeper destiny, marriage, and the true
    strength of each planet. A planet strong in both D1 and D9 delivers its full promise.
    The <strong>D10 (Dasamsa)</strong> is the career chart — it shows your professional karma,
    status in society, and which planets drive your public achievements. A planet strong in
    D1 and D10 together indicates exceptional professional success in that domain.
  </div>
</div>"""


def _generate_transit_chart_html(positions: dict, name: str) -> str:
    """Generate a current transit chart showing today's planetary positions
    in South Indian format, with interpretation of transits from natal Lagna."""
    if not HAS_CHART_GEN:
        return ""
    try:
        swe.set_ephe_path(EPHE_PATH)
        swe.set_sid_mode(swe.SIDM_LAHIRI)

        now = datetime.now(timezone.utc)
        jd = swe.julday(now.year, now.month, now.day,
                        now.hour + now.minute / 60.0 + now.second / 3600.0)
        flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

        planet_ids = {
            "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS,
            "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER,
            "Venus": swe.VENUS, "Saturn": swe.SATURN,
        }
        symbols = {"Sun": "☉", "Moon": "☾", "Mars": "♂", "Mercury": "☿",
                   "Jupiter": "♃", "Venus": "♀", "Saturn": "♄"}

        transit_planets = []
        transit_info_lines = []
        natal_asc_idx = positions.get("ascendant", {}).get("sign_index", 0)
        natal_lagna = RASHI_NAMES[natal_asc_idx]

        for pname, pid in planet_ids.items():
            pos, _ = swe.calc_ut(jd, pid, flags)
            lon = pos[0]
            sign_idx = int(lon / 30) % 12
            deg_in_sign = lon - sign_idx * 30
            retro = pos[3] < 0
            transit_planets.append({
                "name": pname,
                "symbol": symbols.get(pname, "?"),
                "sign_index": sign_idx,
                "sign_deg": deg_in_sign,
                "retrograde": retro,
            })
            house_from_lagna = ((sign_idx - natal_asc_idx) % 12) + 1
            sign_name = RASHI_NAMES[sign_idx]
            r_mark = " (R)" if retro else ""
            transit_info_lines.append(
                f"<tr><td style='color:var(--gold);font-weight:600;'>{pname}</td>"
                f"<td>{sign_name} {deg_in_sign:.1f}°{r_mark}</td>"
                f"<td>House {house_from_lagna} from {natal_lagna}</td></tr>"
            )

        # Rahu/Ketu
        rahu_pos, _ = swe.calc_ut(jd, swe.MEAN_NODE, flags)
        rahu_lon = rahu_pos[0]
        rahu_sign_idx = int(rahu_lon / 30) % 12
        rahu_deg = rahu_lon - rahu_sign_idx * 30
        ketu_lon = (rahu_lon + 180) % 360
        ketu_sign_idx = int(ketu_lon / 30) % 12
        ketu_deg = ketu_lon - ketu_sign_idx * 30

        transit_planets.append({"name": "Rahu", "symbol": "☊", "sign_index": rahu_sign_idx,
                                "sign_deg": rahu_deg, "retrograde": True})
        transit_planets.append({"name": "Ketu", "symbol": "☋", "sign_index": ketu_sign_idx,
                                "sign_deg": ketu_deg, "retrograde": True})

        rahu_house = ((rahu_sign_idx - natal_asc_idx) % 12) + 1
        ketu_house = ((ketu_sign_idx - natal_asc_idx) % 12) + 1
        transit_info_lines.append(
            f"<tr><td style='color:var(--gold);font-weight:600;'>Rahu</td>"
            f"<td>{RASHI_NAMES[rahu_sign_idx]} {rahu_deg:.1f}° (R)</td>"
            f"<td>House {rahu_house} from {natal_lagna}</td></tr>")
        transit_info_lines.append(
            f"<tr><td style='color:var(--gold);font-weight:600;'>Ketu</td>"
            f"<td>{RASHI_NAMES[ketu_sign_idx]} {ketu_deg:.1f}° (R)</td>"
            f"<td>House {ketu_house} from {natal_lagna}</td></tr>")

        # Generate transit chart SVG
        transit_svg = _generate_chart_svg(transit_planets, natal_asc_idx,
                                          "Gochara_Transit", name)

        date_str = now.strftime("%d %B %Y")
        info_rows = "\n".join(transit_info_lines)

        return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag" style="background:linear-gradient(135deg,#2E86AB,#1a5276);
          color:#fff;">CURRENT TRANSITS</span>
    <div>
      <div class="sec-title">Gochara — Live Transit Positions</div>
      <span class="sec-skt">&#2327;&#2379;&#2330;&#2352; &#2347;&#2354;
        &middot; as of {date_str}</span>
    </div>
    <div class="sec-line"></div>
  </div>
  <div style="display:flex; gap:16px; justify-content:center; flex-wrap:wrap; margin:16px 0; max-width:100%; overflow:hidden;">
    <div style="flex:1 1 45%; min-width:240px; max-width:48%; text-align:center;">
      <div style="font-weight:700; color:#2E86AB; margin-bottom:8px; font-size:1.05em;">
        Transit Chart — {date_str}</div>
      <div style="background:#0d0d0d; border:1px solid rgba(46,134,171,.3); border-radius:8px; padding:8px; overflow:hidden;">
        <div style="width:100%; max-width:100%;" class="chart-wrap">{transit_svg}</div>
      </div>
    </div>
    <div style="flex:1 1 45%; min-width:240px; max-width:50%;">
      <div style="font-weight:700; color:#2E86AB; margin-bottom:8px; font-size:1.05em;">
        Transit Positions from {natal_lagna} Lagna</div>
      <table style="width:100%;border-collapse:collapse;font-size:0.92em;">
        <thead>
          <tr style="border-bottom:2px solid rgba(46,134,171,.4);">
            <th style="text-align:left;padding:6px;color:#2E86AB;">Planet</th>
            <th style="text-align:left;padding:6px;color:#2E86AB;">Position</th>
            <th style="text-align:left;padding:6px;color:#2E86AB;">Transit House</th>
          </tr>
        </thead>
        <tbody>
          {info_rows}
        </tbody>
      </table>
    </div>
  </div>
</div>"""

    except Exception as e:
        logger.warning(f"Transit chart generation failed: {e}")
        return ""


# ── Parashari Engine Identity ─────────────────────────────────────────────────
# This constant encodes the role, style, and objective that govern all
# text generation in this engine.  Every narrative, verdict, and synthesis
# produced here must comply with these principles.
PARASHARI_ROLE = {
    "role": "Classical Parashari Jyotish Analyst AI",
    "doctrine": "Brihat Parashara Hora Shastra",
    "interpretive_framework": [
        "Graha nature (natural & functional benefic/malefic)",
        "Rāśi placement and dignity",
        "Bhava outcomes via lordship and occupation",
        "Yoga identification from classical lists",
        "Vimshottari Dasha timing",
        "Ashtakavarga strength zones",
        "Remedial structure (Ratna, Mantra, Dana, Kriya)",
    ],
    "style": {
        "tone": "Classical — deterministic but advisory",
        "language": "No casual phrasing; no generic personality descriptions",
        "output_type": "Complete Parashari life consultation",
        "forbidden": "Modern/pop-astrology interpretations",
    },
    "objective": [
        "Structure of destiny and karmic unfolding",
        "Timing of experience through Dasha periods",
        "Means of alignment through Upaya",
        "Career, marriage, family, and spiritual direction",
    ],
}

# ── Sign / Planet constants ───────────────────────────────────────────────────

SIGN_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]
SIGN_SANSKRIT = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena"
]
SIGN_LORDS = {
    "Aries": "Mars",   "Taurus": "Venus",  "Gemini": "Mercury",
    "Cancer": "Moon",  "Leo": "Sun",        "Virgo": "Mercury",
    "Libra": "Venus",  "Scorpio": "Mars",   "Sagittarius": "Jupiter",
    "Saggitarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter"
}

# Planets' exaltation signs and degrees
EXALTATION = {
    "Sun":     ("Aries", 10),
    "Moon":    ("Taurus", 3),
    "Mars":    ("Capricorn", 28),
    "Mercury": ("Virgo", 15),
    "Jupiter": ("Cancer", 5),
    "Venus":   ("Pisces", 27),
    "Saturn":  ("Libra", 20),
}
DEBILITATION = {
    "Sun":     "Libra",
    "Moon":    "Scorpio",
    "Mars":    "Cancer",
    "Mercury": "Pisces",
    "Jupiter": "Capricorn",
    "Venus":   "Virgo",
    "Saturn":  "Aries",
}
OWN_SIGNS = {
    "Sun":     ["Leo"],
    "Moon":    ["Cancer"],
    "Mars":    ["Aries", "Scorpio"],
    "Mercury": ["Gemini", "Virgo"],
    "Jupiter": ["Sagittarius", "Pisces", "Saggitarius"],
    "Venus":   ["Taurus", "Libra"],
    "Saturn":  ["Capricorn", "Aquarius"],
}
FRIENDLY = {
    "Sun":     ["Moon", "Mars", "Jupiter"],
    "Moon":    ["Sun", "Mercury"],
    "Mars":    ["Sun", "Moon", "Jupiter"],
    "Mercury": ["Sun", "Venus"],
    "Jupiter": ["Sun", "Moon", "Mars"],
    "Venus":   ["Mercury", "Saturn"],
    "Saturn":  ["Mercury", "Venus"],
}
ENEMY = {
    "Sun":     ["Saturn", "Venus"],
    "Moon":    ["Saturn"],
    "Mars":    ["Mercury"],
    "Mercury": ["Moon"],
    "Jupiter": ["Mercury", "Venus"],
    "Venus":   ["Sun", "Moon"],
    "Saturn":  ["Sun", "Moon", "Mars"],
}

NAKSHATRA_LORDS = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"
]
NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purvaphalguni", "Uttaraphalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purvashadha", "Uttarashadha", "Shravana", "Dhanishtha", "Shatabhisha",
    "Purvabhadrapada", "Uttarabhadrapada", "Revati"
]
DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17
}
DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]

PANCHA_MAHAPURUSHA = {
    "Mars":    "Ruchaka",
    "Mercury": "Bhadra",
    "Jupiter": "Hamsa",
    "Venus":   "Malavya",
    "Saturn":  "Shasha",
}
KENDRA_HOUSES = {1, 4, 7, 10}
TRIKONA_HOUSES = {1, 5, 9}
DUSTHANA_HOUSES = {6, 8, 12}
UPACHAYA_HOUSES = {3, 6, 10, 11}


# ── Load JSON knowledge bases ─────────────────────────────────────────────────

def _load_json(filename: str) -> dict:
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

_LORD_EFFECTS: dict = {}
_HOUSE_CHAPTERS: dict = {}


def _ensure_loaded():
    global _LORD_EFFECTS, _HOUSE_CHAPTERS
    if not _LORD_EFFECTS:
        _LORD_EFFECTS = _load_json("lord_effects.json")
    if not _HOUSE_CHAPTERS:
        _HOUSE_CHAPTERS = _load_json("house_chapters.json")


# ── Dignity helpers ───────────────────────────────────────────────────────────

def get_dignity(planet: str, sign: str) -> str:
    """Return the dignity of a planet in a given sign."""
    if planet in ("Rahu", "Ketu", "Uranus", "Neptune", "Pluto"):
        return "Neutral"
    ex_sign, _ = EXALTATION.get(planet, (None, None))
    if ex_sign and sign in (ex_sign, ex_sign.replace("Saggitarius", "Sagittarius")):
        return "Exalted"
    if sign in DEBILITATION.get(planet, ""):
        return "Debilitated"
    own = OWN_SIGNS.get(planet, [])
    if sign in own or sign.replace("Saggitarius", "Sagittarius") in own:
        return "Own Sign"
    lord = SIGN_LORDS.get(sign, "")
    if lord in FRIENDLY.get(planet, []):
        return "Friendly"
    if lord in ENEMY.get(planet, []):
        return "Enemy Sign"
    return "Neutral"


def get_nakshatra(longitude: float) -> dict:
    """Return nakshatra details from a sidereal longitude."""
    idx = int(longitude / (360 / 27)) % 27
    pada = int((longitude % (360 / 27)) / (360 / 27 / 4)) + 1
    return {
        "name": NAKSHATRA_NAMES[idx],
        "lord": NAKSHATRA_LORDS[idx],
        "pada": pada,
        "index": idx,
    }


# ── House lord mapping ────────────────────────────────────────────────────────

def build_house_lord_map(lagna_sign_idx: int) -> Dict[int, str]:
    """Build {house_number: lord_planet} for all 12 houses."""
    result = {}
    for h in range(1, 13):
        sign_idx = (lagna_sign_idx + h - 1) % 12
        sign_name = SIGN_NAMES[sign_idx]
        # handle jyotichart's Saggitarius spelling
        result[h] = SIGN_LORDS.get(sign_name, SIGN_LORDS.get("Sagittarius", "Jupiter"))
    return result


def planet_house(planet_sign_idx: int, lagna_sign_idx: int) -> int:
    """Return the house number (1-12) for a planet given lagna."""
    return ((planet_sign_idx - lagna_sign_idx) % 12) + 1


# ── Yoga detection ────────────────────────────────────────────────────────────

def detect_yogas(positions: dict, lagna_sign_idx: int, house_lord_map: Dict[int, str]) -> List[dict]:
    """Detect major yogas from the chart positions."""
    yogas = []
    planets = {p["name"]: p for p in positions.get("planets", [])}

    def sign_idx(p_name):
        if p_name in planets:
            return planets[p_name]["rashi"].get("index",
                SIGN_NAMES.index(planets[p_name]["rashi"]["name"]) if planets[p_name]["rashi"]["name"] in SIGN_NAMES else 0)
        return None

    def house_of(p_name):
        si = sign_idx(p_name)
        if si is not None:
            return planet_house(si, lagna_sign_idx)
        return None

    # ── Pancha Mahapurusha ──────────────────────────────────────────────────
    for planet, yoga_name in PANCHA_MAHAPURUSHA.items():
        if planet not in planets:
            continue
        p = planets[planet]
        dignity = get_dignity(planet, p["rashi"]["name"])
        h = house_of(planet)
        if dignity in ("Exalted", "Own Sign") and h in KENDRA_HOUSES:
            yogas.append({
                "name": yoga_name + " Yoga",
                "category": "Pancha Mahapurusha",
                "planet": planet,
                "house": h,
                "dignity": dignity,
                "description": (
                    f"{planet} in {dignity} in the {h}th house (Kendra) forms {yoga_name} Yoga — "
                    f"one of the five supreme Pancha Mahapurusha Yogas of Vedic astrology."
                ),
                "strength": "Very Strong",
            })

    # ── Gajakesari Yoga ────────────────────────────────────────────────────
    if "Jupiter" in planets and "Moon" in planets:
        jup_h = house_of("Jupiter")
        moon_h = house_of("Moon")
        if jup_h and moon_h:
            diff = abs(jup_h - moon_h)
            kendra_diff = diff in (0, 3, 6, 9)
            if kendra_diff:
                yogas.append({
                    "name": "Gajakesari Yoga",
                    "category": "Fortune Yoga",
                    "planet": "Jupiter + Moon",
                    "house": f"{jup_h} & {moon_h}",
                    "dignity": get_dignity("Jupiter", planets["Jupiter"]["rashi"]["name"]),
                    "description": (
                        "Jupiter and Moon are in mutual Kendra — the celebrated Gajakesari Yoga. "
                        "Grants intelligence, eloquence, lasting fame, and the ability to overcome obstacles."
                    ),
                    "strength": "Strong" if get_dignity("Jupiter", planets["Jupiter"]["rashi"]["name"]) == "Exalted" else "Moderate",
                })

    # ── Yoga Karaka ────────────────────────────────────────────────────────
    # Find planet ruling both a Kendra and a Trikona
    kendra_lords = {house_lord_map[h] for h in KENDRA_HOUSES if h != 1}
    trikona_lords = {house_lord_map[h] for h in TRIKONA_HOUSES if h != 1}
    yoga_karakas = kendra_lords & trikona_lords
    for yk in yoga_karakas:
        if yk in planets:
            yogas.append({
                "name": f"Yoga Karaka ({yk})",
                "category": "Raja Yoga",
                "planet": yk,
                "house": house_of(yk),
                "dignity": get_dignity(yk, planets[yk]["rashi"]["name"]),
                "description": (
                    f"{yk} rules both a Kendra and a Trikona for this Lagna — making it the supreme Yoga Karaka. "
                    "All house significations of this planet are highly auspicious."
                ),
                "strength": "Very Strong",
            })

    # ── Dharma-Karmadhipati ────────────────────────────────────────────────
    lord_9 = house_lord_map.get(9)
    lord_10 = house_lord_map.get(10)
    if lord_9 and lord_10 and lord_9 != lord_10:
        h9 = house_of(lord_9)
        h10 = house_of(lord_10)
        # Check if they're conjunct or in mutual Kendra
        if h9 and h10 and (h9 == h10 or abs(h9 - h10) in (0, 3, 6, 9)):
            yogas.append({
                "name": "Dharma-Karmadhipati Yoga",
                "category": "Raja Yoga",
                "planet": f"{lord_9} + {lord_10}",
                "house": f"{h9} & {h10}",
                "dignity": "",
                "description": (
                    f"9th lord ({lord_9}) and 10th lord ({lord_10}) are in mutual connection — "
                    "Dharma-Karmadhipati Yoga. Grants career authority aligned with dharma and destiny."
                ),
                "strength": "Strong",
            })

    # ── Viparita Raja Yoga ─────────────────────────────────────────────────
    for dusthana in [6, 8, 12]:
        lord = house_lord_map.get(dusthana)
        if lord and lord in planets:
            h = house_of(lord)
            if h in DUSTHANA_HOUSES:
                yogas.append({
                    "name": f"Viparita Raja Yoga (H{dusthana})",
                    "category": "Viparita Yoga",
                    "planet": lord,
                    "house": h,
                    "dignity": get_dignity(lord, planets[lord]["rashi"]["name"]),
                    "description": (
                        f"{lord} (lord of {dusthana}th house) placed in the {h}th Dusthana — "
                        "Viparita Raja Yoga. Enemies and obstacles become self-defeating; the native rises through adversity."
                    ),
                    "strength": "Moderate",
                })

    # ── Dhana (Wealth) Yogas ───────────────────────────────────────────────
    lord_2 = house_lord_map.get(2)
    lord_11 = house_lord_map.get(11)
    if lord_2 and lord_11 and lord_2 in planets and lord_11 in planets:
        h2 = house_of(lord_2)
        h11 = house_of(lord_11)
        if h2 and h11 and (h2 in KENDRA_HOUSES | TRIKONA_HOUSES or h11 in KENDRA_HOUSES | TRIKONA_HOUSES):
            yogas.append({
                "name": "Dhana Yoga",
                "category": "Wealth Yoga",
                "planet": f"{lord_2} + {lord_11}",
                "house": f"{h2} & {h11}",
                "dignity": "",
                "description": (
                    f"2nd lord ({lord_2}) and 11th lord ({lord_11}) are strong — "
                    "Dhana Yoga indicating substantial wealth accumulation."
                ),
                "strength": "Moderate",
            })

    return yogas


# ── Dasha calculation ─────────────────────────────────────────────────────────

def calculate_dasha_timeline(birth_dt: datetime, moon_longitude: float) -> List[dict]:
    """Return list of all Mahadashas with start/end dates."""
    nak_idx = int(moon_longitude / (360 / 27)) % 27
    nak_lord = NAKSHATRA_LORDS[nak_idx]
    elapsed_fraction = (moon_longitude % (360 / 27)) / (360 / 27)

    start_idx = DASHA_ORDER.index(nak_lord)
    remaining_years = DASHA_YEARS[nak_lord] * (1 - elapsed_fraction)

    timeline = []
    current_date = birth_dt
    for i in range(len(DASHA_ORDER)):
        planet = DASHA_ORDER[(start_idx + i) % len(DASHA_ORDER)]
        years = remaining_years if i == 0 else DASHA_YEARS[planet]
        days = int(years * 365.25)
        end_date = datetime(
            current_date.year + int(years),
            current_date.month,
            min(current_date.day, 28)
        )
        timeline.append({
            "planet": planet,
            "years": DASHA_YEARS[planet],
            "start": current_date,
            "end": end_date,
        })
        current_date = end_date
        remaining_years = 0  # Only first period is partial

    return timeline


def get_current_dasha(timeline: List[dict]) -> Optional[dict]:
    """Return the currently active Mahadasha."""
    now = datetime.now()
    for period in timeline:
        if period["start"] <= now <= period["end"]:
            return period
    return None


# ── Core interpretation builder ───────────────────────────────────────────────

def _lord_effect_text(lord_house: int, placed_house: int) -> str:
    """Fetch BPHS lord-in-house sloka text from lord_effects.json."""
    _ensure_loaded()
    house_data = _LORD_EFFECTS.get(str(lord_house), {})
    return house_data.get(str(placed_house), "")


def _house_summary_text(house_num: int) -> str:
    """Fetch BPHS house chapter summary from house_chapters.json."""
    _ensure_loaded()
    return _HOUSE_CHAPTERS.get(str(house_num - 1), "")


def build_planet_map(positions: dict) -> Dict[str, dict]:
    """Index planets by name for quick lookup."""
    return {p["name"]: p for p in positions.get("planets", [])}


def generate_house_interpretations(
    positions: dict,
    lagna_sign_idx: int,
    house_lord_map: Dict[int, str],
    planet_map: Dict[str, dict],
) -> List[dict]:
    """
    Generate deep interpretation for all 12 houses.
    Cross-references lord_effects.json, house_chapters.json, and planetary dignities.
    """
    _ensure_loaded()
    results = []

    # Build reverse map: sign_idx → list of planets there
    sign_planet_map: Dict[int, List[str]] = {}
    for name, p in planet_map.items():
        si = p["rashi"].get("index")
        if si is None:
            try:
                si = SIGN_NAMES.index(p["rashi"]["name"])
            except ValueError:
                si = 0
        sign_planet_map.setdefault(si, []).append(name)

    for house_num in range(1, 13):
        sign_idx = (lagna_sign_idx + house_num - 1) % 12
        sign_name = SIGN_NAMES[sign_idx]
        sign_skt = SIGN_SANSKRIT[sign_idx]
        lord = house_lord_map[house_num]

        # Planets in this house
        occupants = sign_planet_map.get(sign_idx, [])

        # Where is the lord?
        lord_sign_idx = None
        lord_house = house_num  # default
        if lord in planet_map:
            try:
                lord_sign_idx = SIGN_NAMES.index(planet_map[lord]["rashi"]["name"])
            except ValueError:
                lord_sign_idx = 0
            lord_house = planet_house(lord_sign_idx, lagna_sign_idx)

        # Lord dignity
        lord_dignity = "Unknown"
        if lord in planet_map:
            lord_dignity = get_dignity(lord, planet_map[lord]["rashi"]["name"])

        # BPHS sloka: lord of this house in lord_house
        bphs_sloka = _lord_effect_text(house_num, lord_house)

        # Occupant dignities and notes
        occupant_details = []
        for p_name in occupants:
            if p_name in planet_map:
                pdata = planet_map[p_name]
                dignity = get_dignity(p_name, sign_name)
                nak = get_nakshatra(pdata.get("longitude", 0))
                occupant_details.append({
                    "planet": p_name,
                    "dignity": dignity,
                    "retrograde": pdata.get("retrograde", False),
                    "nakshatra": nak["name"],
                    "nakshatra_lord": nak["lord"],
                    "nakshatra_pada": nak["pada"],
                    "degrees": round(pdata.get("sign_deg", pdata.get("longitude", 0)) % 30, 2),
                })

        # House classification
        classification = []
        if house_num in KENDRA_HOUSES:
            classification.append("Kendra (Angular)")
        if house_num in TRIKONA_HOUSES:
            classification.append("Trikona (Trine)")
        if house_num in DUSTHANA_HOUSES:
            classification.append("Dusthana (Difficult)")
        if house_num in UPACHAYA_HOUSES:
            classification.append("Upachaya (Growth)")
        if not classification:
            classification.append("Neutral")

        results.append({
            "house": house_num,
            "sign": sign_name,
            "sign_sanskrit": sign_skt,
            "lord": lord,
            "lord_house": lord_house,
            "lord_dignity": lord_dignity,
            "lord_sign": planet_map[lord]["rashi"]["name"] if lord in planet_map else sign_name,
            "occupants": occupants,
            "occupant_details": occupant_details,
            "classification": classification,
            "bphs_sloka": bphs_sloka,
            "bphs_house_summary": _house_summary_text(house_num),
        })

    return results


# ── Ashtakvarga scoring ───────────────────────────────────────────────────────

def classify_bindu(score: int) -> str:
    if score >= 30:
        return "Strong"
    elif score >= 25:
        return "Average"
    else:
        return "Weak"


# ── HTML Report Generator ─────────────────────────────────────────────────────

def _planet_colour(name: str) -> str:
    colours = {
        "Sun": "#FF6B00", "Moon": "#9090FF", "Mars": "#FF4444",
        "Mercury": "#00CC77", "Jupiter": "#FFD700", "Venus": "#FF69B4",
        "Saturn": "#8877DD", "Rahu": "#AAAAAA", "Ketu": "#CC8844",
    }
    return colours.get(name, "#C9A84C")


def _dignity_colour(dignity: str) -> str:
    return {
        "Exalted":     "#00E676",
        "Own Sign":    "#69F0AE",
        "Friendly":    "#FFD700",
        "Neutral":     "rgba(250,246,238,0.7)",
        "Enemy Sign":  "#FF7043",
        "Debilitated": "#FF1744",
        "Unknown":     "rgba(250,246,238,0.5)",
    }.get(dignity, "rgba(250,246,238,0.7)")


HOUSE_TITLES = {
    1:  "Tanu Bhava — Self & Body",
    2:  "Dhana Bhava — Wealth & Speech",
    3:  "Sahaj Bhava — Courage & Siblings",
    4:  "Bandhu Bhava — Home & Mother",
    5:  "Putra Bhava — Intelligence & Children",
    6:  "Ari Bhava — Enemies & Health",
    7:  "Yuvati Bhava — Marriage & Partnership",
    8:  "Randhra Bhava — Longevity & Transformation",
    9:  "Dharma Bhava — Fortune & Dharma",
    10: "Karma Bhava — Career & Status",
    11: "Labha Bhava — Gains & Income",
    12: "Vyaya Bhava — Losses & Liberation",
}


def generate_consultation_html(
    birth: dict,
    positions: dict,
    moon_longitude: float,
    nakshatra_info: dict,
    dasha_report: str,
    current_dasha: Optional[dict],
    ashtakvarga: Optional[dict] = None,
    extended_data: Optional[dict] = None,
    ai_narratives: Optional[Dict[str, str]] = None,
) -> str:
    """
    Generate a full, standalone consultation-quality HTML report.
    All interpretations are dynamically computed from the birth chart.
    """
    name = birth.get("name", "Native")
    dob = f"{birth.get('day', ''):02d} {_month_name(birth.get('month', 1))} {birth.get('year', '')}"
    tob = f"{birth.get('hour', 0):02d}:{birth.get('minute', 0):02d}"
    city = birth.get("city", "")
    country = birth.get("country", "")

    # Core chart data
    asc = positions.get("ascendant", {})
    lagna_sign = asc.get("rashi", {}).get("name", "Aquarius")
    lagna_skt = asc.get("rashi", {}).get("sanskrit", "Kumbha")
    try:
        lagna_sign_idx = SIGN_NAMES.index(lagna_sign)
    except ValueError:
        lagna_sign_idx = 0
    lagna_lord = SIGN_LORDS.get(lagna_sign, "Saturn")
    lagna_deg = round(asc.get("sign_deg", asc.get("longitude", 0)) % 30, 2)

    planet_map = build_planet_map(positions)
    house_lord_map = build_house_lord_map(lagna_sign_idx)

    # Birth datetime for dasha
    try:
        birth_dt = datetime(
            int(birth.get("year", 2000)), int(birth.get("month", 1)),
            int(birth.get("day", 1)), int(birth.get("hour", 0)),
            int(birth.get("minute", 0)), int(birth.get("second", 0))
        )
    except Exception:
        birth_dt = datetime(2000, 1, 1)

    dasha_timeline = calculate_dasha_timeline(birth_dt, moon_longitude)
    active_dasha = get_current_dasha(dasha_timeline)

    # Yogas — use B.V. Raman rule engine if available, else fall back
    if HAS_RAMAN_RULES:
        raman_yogas = bv_raman_rules.detect_all_yogas(positions)
        # Convert to format expected by rendering functions
        yogas = []
        for ry in raman_yogas:
            yogas.append({
                "name": ry["name"],
                "category": ry["category"],
                "planet": ", ".join(ry.get("planets", [])),
                "house": ", ".join(str(h) for h in ry.get("houses", [])) if ry.get("houses") else "",
                "dignity": "",
                "description": ry.get("description", ""),
                "strength": ry.get("strength", "Moderate"),
                "classical_result": ry.get("classical_result", ""),
                "source": ry.get("source", ""),
            })
    else:
        yogas = detect_yogas(positions, lagna_sign_idx, house_lord_map)

    # B.V. Raman chart analysis (planet effects + dasha readings)
    raman_analysis = None
    if HAS_RAMAN_RULES:
        try:
            raman_analysis = bv_raman_rules.analyze_chart(positions, birth_dt, moon_longitude)
        except Exception as e:
            logger.warning(f"B.V. Raman analysis error: {e}")

    # House interpretations
    house_interps = generate_house_interpretations(
        positions, lagna_sign_idx, house_lord_map, planet_map
    )

    # Nakshatra rising (for lagna)
    lagna_lon = asc.get("longitude", 0)
    lagna_nak = get_nakshatra(lagna_lon)

    # Moon nakshatra
    moon_nak = nakshatra_info if nakshatra_info else get_nakshatra(moon_longitude)

    # Extended data from parashari_engine
    ext = extended_data or {}

    # ── HTML Assembly — Full 20-Section Parashari Sequence ───────────────────
    # Follows Brihat Parashara Hora Shastra doctrinal order
    # as specified in Astro_prompt.docx

    html_parts = [_html_head(name)]
    html_parts.append(_html_cover(name, dob, tob, city, country,
                                   lagna_sign, lagna_skt, lagna_lord,
                                   lagna_nak, moon_nak, yogas, active_dasha))
    html_parts.append('<div class="page">')

    # D1 (Rashi) + D9 (Navamsha) + D10 (Dasamsa) charts stacked vertically
    charts_html = _generate_d1_d9_d10_html(positions, name)
    if charts_html:
        html_parts.append(charts_html)

    # Sec 1-3: Cosmic Context + Lagna + Elemental/Guna Profile
    html_parts.append(_html_cosmic_context(
        lagna_sign, lagna_lord, lagna_nak, planet_map, lagna_sign_idx, house_lord_map))

    # Sec 4: Special Lagnas (Hora, Ghati, Bhava, Varnada)
    if ext.get("special_lagnas"):
        html_parts.append(_html_special_lagnas(ext["special_lagnas"]))

    # Sec 2 (table): Planetary Positions
    html_parts.append(_html_planet_table(positions, lagna_sign_idx, house_lord_map))

    # Sec 14: Avasthas (immediately after planet table)
    if ext.get("avasthas"):
        html_parts.append(_html_avasthas(ext["avasthas"]))

    # Sec 9: Shadbala & Isht/Kasht
    if ext.get("shadbala"):
        html_parts.append(_html_shadbala(ext["shadbala"]))

    # Sec 11: Chara Karakas (Atmakaraka → Darakaraka)
    if ext.get("karakas"):
        html_parts.append(_html_karakas(ext["karakas"]))

    # Astrologer's First Impression callout
    html_parts.append(_html_first_impression(
        positions, lagna_sign, lagna_lord, planet_map, yogas,
        active_dasha, lagna_sign_idx, house_lord_map))

    # Sec 12: Yoga Detection
    html_parts.append(_html_yogas_section(yogas))

    # Sec 8: Drishti Analysis (Graha + Rashi aspects)
    if ext.get("drishti"):
        html_parts.append(_html_drishti(ext["drishti"], planet_map, lagna_sign_idx))

    # Sec 10: Aragala (Intervention / Obstruction)
    if ext.get("aragala"):
        html_parts.append(_html_aragala(ext["aragala"]))

    # Compute D9/D10 planet-to-house mappings for Bhava Vishleshan
    d9_house_map = {}   # planet_name → {sign, house, dignity}
    d10_house_map = {}
    asc_lon = asc.get("longitude", 0)
    d9_asc_idx = _navamsha_sign_index(asc_lon)
    d10_asc_idx = _dasamsa_sign_index(asc_lon)
    for pname, pdata in planet_map.items():
        p_lon = pdata.get("longitude", 0)
        # D9
        d9_si = _navamsha_sign_index(p_lon)
        d9_house_map[pname] = {
            "sign": SIGN_NAMES[d9_si], "house": rashi_to_house(d9_si, d9_asc_idx),
            "dignity": get_dignity(pname, SIGN_NAMES[d9_si]),
        }
        # D10
        d10_si = _dasamsa_sign_index(p_lon)
        d10_house_map[pname] = {
            "sign": SIGN_NAMES[d10_si], "house": rashi_to_house(d10_si, d10_asc_idx),
            "dignity": get_dignity(pname, SIGN_NAMES[d10_si]),
        }

    # Sec 6-7: Bhava Vishleshan — All 12 Houses + D9/D10 context
    html_parts.append(_html_houses_section(
        house_interps, raman_analysis, d9_house_map, d10_house_map))

    # Sec 5: Shodasha Varga (Divisional Charts)
    if ext.get("vargas"):
        html_parts.append(_html_vargas(ext["vargas"]))

    # Sec 13: Longevity & Maraka
    if ext.get("longevity_maraka"):
        html_parts.append(_html_longevity_maraka(ext["longevity_maraka"]))

    # Sec 15: Vimshottari Dasha
    html_parts.append(_html_dasha_section(dasha_timeline, active_dasha, birth_dt, raman_analysis))

    # Sec 6 (cont): Nakshatra Analysis
    html_parts.append(_html_nakshatra_section(lagna_nak, moon_nak, planet_map))

    # Sec 16: Ashtakvarga
    if ashtakvarga:
        html_parts.append(_html_ashtakvarga(ashtakvarga))

    # Sec 18: Karmic Indications
    html_parts.append(_html_karmic(planet_map, lagna_sign_idx, house_lord_map))

    # ── Current Transit Chart (Gochara) ──────────────────────────────────
    transit_html = _generate_transit_chart_html(positions, name)
    if transit_html:
        html_parts.append(transit_html)

    # ── AI Consultation Narrative (powered by Claude) ─────────────────────
    if ai_narratives and HAS_AI_LAYER and any(ai_narratives.values()):
        html_parts.append(ai_interpreter.render_ai_narrative_html(ai_narratives))

    # Sec 19: Life Outcome Synthesis
    html_parts.append(_html_synthesis(
        lagna_sign, lagna_lord, planet_map, yogas, active_dasha,
        house_lord_map, lagna_sign_idx))

    # Sec 20: Remedies
    html_parts.append(_html_remedies(lagna_lord, house_lord_map, planet_map, yogas))

    html_parts.append(_html_footer(name))
    html_parts.append('</div>')
    html_parts.append('</body></html>')

    return "\n".join(html_parts)


# ── HTML sub-builders ─────────────────────────────────────────────────────────

CSS = """
<style>
:root {
  --gold:#C9A84C; --gold-light:#E8C96A; --gold-pale:#F5E6B8;
  --deep-navy:#0A0E1A; --navy:#0F1628; --navy-mid:#16213E; --navy-light:#1E2D5A;
  --cream:#FAF6EE; --text-dark:#1A1209;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--deep-navy); color:var(--cream);
       font-family:Georgia,'Times New Roman',serif; font-size:15px; line-height:1.85; }
.cover { min-height:600px; background:radial-gradient(ellipse at 30% 20%,#1a0a2e,#0A0E1A 50%,#0F0A00);
         display:flex; flex-direction:column; align-items:center; justify-content:center;
         padding:60px 40px; border-bottom:3px solid var(--gold); text-align:center; }
.cover-om { font-size:56px; color:var(--gold); margin-bottom:12px; }
.cover-sup { font-family:Georgia,serif; font-size:10px; letter-spacing:5px;
             color:var(--gold); text-transform:uppercase; margin-bottom:20px; opacity:.8; }
.cover-title { font-size:38px; font-weight:700; color:var(--gold-light);
               letter-spacing:2px; margin-bottom:6px; }
.cover-name  { font-size:52px; font-weight:900; color:#fff;
               letter-spacing:4px; margin:14px 0; }
.cover-div { width:180px; height:2px; margin:20px auto;
             background:linear-gradient(90deg,transparent,var(--gold),transparent); }
.cover-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:20px;
              margin:28px 0; padding:24px; border:1px solid rgba(201,168,76,.3);
              background:rgba(0,0,0,.4); border-radius:4px; max-width:700px; width:100%; }
.cg-label { font-size:9px; letter-spacing:3px; color:var(--gold);
            text-transform:uppercase; display:block; margin-bottom:3px; }
.cg-val { font-size:14px; color:var(--cream); }
.cover-badges { display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin:18px 0; }
.badge { padding:5px 14px; border:1px solid var(--gold); border-radius:2px;
         font-size:10px; letter-spacing:2px; color:var(--gold);
         background:rgba(201,168,76,.08); }
.page { max-width:1080px; margin:0 auto; padding:0 36px; }
.chart-wrap svg { width:100%; height:auto; max-width:100%; display:block; }
.section { padding:50px 0 36px; border-bottom:1px solid rgba(201,168,76,.15); }
.sec-hd { display:flex; align-items:center; gap:16px; margin-bottom:30px; }
.sec-tag { font-size:10px; letter-spacing:3px; color:var(--gold); opacity:.7; min-width:80px; }
.sec-title { font-size:24px; font-weight:700; color:var(--gold-light); }
.sec-skt { font-size:12px; color:rgba(201,168,76,.6); display:block; margin-top:2px; }
.sec-line { flex:1; height:1px; background:linear-gradient(90deg,var(--gold),transparent); opacity:.4; }
.house-block { background:linear-gradient(135deg,rgba(30,45,90,.6),rgba(15,22,40,.85));
               border:1px solid rgba(201,168,76,.2); border-left:3px solid var(--gold);
               border-radius:4px; padding:24px 28px; margin-bottom:22px; }
.house-hd { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:12px; }
.house-num { font-size:10px; letter-spacing:3px; color:var(--gold); opacity:.7; }
.house-name { font-size:18px; font-weight:700; color:var(--gold-light); }
.house-sign { font-size:12px; color:rgba(255,255,255,.6); padding:2px 8px;
              border:1px solid rgba(201,168,76,.3); border-radius:2px; }
.planet-tags { display:flex; gap:6px; flex-wrap:wrap; margin:10px 0; }
.ptag { padding:3px 10px; border-radius:10px; font-size:11px; font-weight:600;
        border:1px solid currentColor; }
.sloka { background:rgba(201,168,76,.08); border-left:2px solid var(--gold);
         padding:9px 14px; margin:12px 0; font-style:italic;
         color:var(--gold-pale); font-size:13.5px; border-radius:0 4px 4px 0; }
.sloka cite { display:block; margin-top:3px; font-size:11px; opacity:.65;
              font-style:normal; letter-spacing:1px; }
.verdict { margin-top:14px; padding:10px 16px;
           background:rgba(201,168,76,.1); border:1px solid rgba(201,168,76,.25);
           border-radius:4px; font-size:14px; }
.vl { font-size:9px; letter-spacing:3px; color:var(--gold);
      display:block; margin-bottom:3px; text-transform:uppercase; }
.planet-table { width:100%; border-collapse:collapse; margin:24px 0; font-size:13.5px; }
.planet-table th { background:rgba(201,168,76,.15); color:var(--gold); font-size:9px;
                   letter-spacing:2px; padding:10px 14px; text-align:left;
                   border-bottom:1px solid rgba(201,168,76,.3); }
.planet-table td { padding:9px 14px; border-bottom:1px solid rgba(255,255,255,.06);
                   color:rgba(250,246,238,.85); }
.planet-table tr:hover td { background:rgba(201,168,76,.05); }
.yoga-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; margin:24px 0; }
.yoga-card { background:linear-gradient(135deg,rgba(30,45,90,.7),rgba(15,22,40,.9));
             border:1px solid rgba(201,168,76,.3); border-radius:6px; padding:22px; }
.yoga-card.pancha { border-color:rgba(255,215,0,.5);
                    background:linear-gradient(135deg,rgba(40,30,5,.85),rgba(15,10,0,.92)); }
.yname { font-size:16px; font-weight:700; color:var(--gold-light); margin-bottom:3px; }
.ytype { font-size:9px; letter-spacing:3px; color:rgba(201,168,76,.6);
         text-transform:uppercase; margin-bottom:10px; }
.yform { font-size:11px; color:var(--gold); background:rgba(201,168,76,.1);
         padding:3px 9px; border-radius:2px; margin-bottom:10px;
         display:inline-block; }
.ytext { font-size:13.5px; color:rgba(250,246,238,.85); line-height:1.7; }
.dasha-row { display:flex; align-items:stretch; margin-bottom:7px;
             border:1px solid rgba(201,168,76,.15); border-radius:4px; overflow:hidden; }
.dasha-row.current { border-color:var(--gold); box-shadow:0 0 16px rgba(201,168,76,.2); }
.dp-col { width:110px; flex:0 0 110px; background:rgba(201,168,76,.1);
          display:flex; flex-direction:column; align-items:center;
          justify-content:center; padding:10px;
          border-right:1px solid rgba(201,168,76,.2); }
.dp-name { font-size:14px; font-weight:700; color:var(--gold-light); }
.dp-yr   { font-size:10px; color:rgba(201,168,76,.65); }
.dd-col  { padding:10px 14px; flex:1; }
.dd-range { font-size:11px; color:rgba(201,168,76,.65); margin-bottom:4px; }
.dd-text  { font-size:13.5px; color:rgba(250,246,238,.85); line-height:1.6; }
.cur-badge { background:var(--gold); color:var(--deep-navy); font-size:8px;
             letter-spacing:2px; padding:2px 7px; border-radius:2px;
             display:inline-block; margin-left:6px; font-weight:700; }
.callout { background:rgba(201,168,76,.08); border:1px solid rgba(201,168,76,.35);
           border-left:3px solid var(--gold); padding:12px 16px;
           margin:14px 0; font-size:14px; border-radius:0 4px 4px 0; }
.callout.pos { background:rgba(0,200,100,.07); border-color:rgba(0,200,100,.3);
               border-left-color:#00C864; }
.summary-banner { background:linear-gradient(135deg,rgba(40,20,5,.9),rgba(10,14,26,.95));
                  border:1px solid var(--gold); border-radius:6px;
                  padding:28px 32px; margin:28px 0; text-align:center; }
.summary-banner h3 { font-size:20px; color:var(--gold-light); margin-bottom:12px; }
.summary-banner p  { font-size:15px; color:rgba(250,246,238,.9);
                     line-height:1.85; max-width:760px; margin:0 auto; }
.info-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:20px 0; }
.ic { background:rgba(30,45,90,.5); border:1px solid rgba(201,168,76,.2);
      border-radius:4px; padding:12px 14px; }
.ic-l { font-size:9px; color:var(--gold); letter-spacing:2px;
         text-transform:uppercase; display:block; margin-bottom:3px; }
.ic-v { font-size:14px; color:var(--cream); }
.remedy-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:20px 0; }
.rc { background:rgba(15,22,40,.85); border:1px solid rgba(201,168,76,.2);
      border-radius:6px; padding:18px; }
.ri { font-size:22px; margin-bottom:8px; }
.rt { font-size:13px; font-weight:700; color:var(--gold); margin-bottom:6px; }
.rb { font-size:12.5px; color:rgba(250,246,238,.8); line-height:1.6; }
.footer { text-align:center; padding:36px; border-top:1px solid rgba(201,168,76,.2);
          color:rgba(201,168,76,.4); font-size:10px; letter-spacing:2px; }
.nak-grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin:22px 0; }
.nak-card { background:linear-gradient(135deg,rgba(30,45,90,.6),rgba(15,22,40,.9));
            border:1px solid rgba(201,168,76,.25); border-radius:6px; padding:22px; }
.nak-title { font-size:17px; font-weight:700; color:var(--gold-light); margin-bottom:3px; }
.nak-sub { font-size:11px; color:rgba(201,168,76,.6); letter-spacing:1px; margin-bottom:12px; }
.nak-text { font-size:13.5px; color:rgba(250,246,238,.85); line-height:1.75; }

/* ── AI CONSULTATION NARRATIVE ── */
.ai-consultation { border:1px solid rgba(201,168,76,.25); border-radius:8px; padding:0; margin-top:32px; }
.ai-section { margin:24px 0; padding:0 20px; }
.ai-section-hd { margin-bottom:16px; padding-bottom:10px; border-bottom:1px solid rgba(201,168,76,.15); }
.ai-section-title { font-size:17px; font-weight:600; color:var(--gold); letter-spacing:0.5px; }
.ai-section-skt { font-size:11px; color:rgba(201,168,76,.5); font-style:italic; margin-top:2px; }
.ai-section-sub { font-size:12px; color:rgba(250,246,238,.45); margin-top:3px; }
.ai-narrative { font-size:14px; line-height:1.75; color:rgba(250,246,238,.82); }
.ai-narrative p { margin:0 0 14px 0; text-indent:1.5em; }
.ai-narrative p:first-child { text-indent:0; }
.ai-narrative p:first-child::first-letter { font-size:2em; float:left; line-height:1; margin-right:6px; color:var(--gold); font-weight:700; }
.ai-narrative strong { color:var(--gold); }

@media print { body { background:white; color:#111; } }
</style>
"""


def _html_head(name: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Vedic Consultation — {name}</title>
{CSS}
</head>
<body>"""


def _html_cover(name, dob, tob, city, country,
                lagna_sign, lagna_skt, lagna_lord,
                lagna_nak, moon_nak, yogas, active_dasha) -> str:
    city_str = f"{city}, {country}" if city else country
    yoga_badges = "".join(
        f'<span class="badge">{y["name"]}</span>'
        for y in yogas[:6]
    )
    active_str = ""
    if active_dasha:
        active_str = f"{active_dasha['planet']} Mahadasha"

    return f"""
<div class="cover">
  <div class="cover-om">&#2384;</div>
  <div class="cover-sup">Classical Parashari Jyotish Analyst &middot; Brihat Parashara Hora Shastra</div>
  <div class="cover-title">Jyotish Kundali Vishleshan</div>
  <div class="cover-name">{name.upper()}</div>
  <div class="cover-div"></div>
  <div class="cover-grid">
    <div><span class="cg-label">Date of Birth</span><span class="cg-val">{dob}</span></div>
    <div><span class="cg-label">Time of Birth</span><span class="cg-val">{tob} (Local)</span></div>
    <div><span class="cg-label">Place</span><span class="cg-val">{city_str}</span></div>
    <div><span class="cg-label">Lagna</span><span class="cg-val">{lagna_sign} ({lagna_skt})</span></div>
    <div><span class="cg-label">Lagna Lord</span><span class="cg-val">{lagna_lord}</span></div>
    <div><span class="cg-label">Rising Nakshatra</span>
         <span class="cg-val">{lagna_nak.get("name","")}, Pada {lagna_nak.get("pada","")}</span></div>
    <div><span class="cg-label">Moon Sign</span>
         <span class="cg-val">{moon_nak.get("sign", moon_nak.get("name",""))}</span></div>
    <div><span class="cg-label">Moon Nakshatra</span>
         <span class="cg-val">{moon_nak.get("name","")}, Pada {moon_nak.get("pada","")}</span></div>
    <div><span class="cg-label">Current Dasha</span>
         <span class="cg-val">{active_str}</span></div>
  </div>
  <div class="cover-badges">{yoga_badges}</div>
  <div style="font-size:11px;color:rgba(201,168,76,.45);letter-spacing:2px;margin-top:16px;">
    Classical Parashari Doctrine &middot; Lahiri Ayanamsa &middot; Generated {datetime.now().strftime("%B %Y")}
  </div>
</div>"""


def _html_planet_table(positions: dict, lagna_sign_idx: int, house_lord_map: Dict[int, str]) -> str:
    rows = ""
    asc = positions.get("ascendant", {})
    asc_sign = asc.get("rashi", {}).get("name", "")
    asc_deg = round(asc.get("sign_deg", asc.get("longitude", 0)) % 30, 2)

    rows += f"""<tr>
      <td><strong style="color:var(--gold)">ASC</strong></td>
      <td>{asc_sign}</td><td>{asc_deg}°</td>
      <td>{asc.get("rashi",{}).get("sanskrit","")}</td>
      <td>1st</td><td>—</td><td>—</td><td>—</td>
    </tr>"""

    for p in positions.get("planets", []):
        name = p["name"]
        if name in ("Uranus", "Neptune", "Pluto"):
            continue
        sign = p["rashi"]["name"]
        try:
            si = SIGN_NAMES.index(sign)
        except ValueError:
            si = 0
        house = planet_house(si, lagna_sign_idx)
        dignity = get_dignity(name, sign)
        retro = " (R)" if p.get("retrograde") else ""
        deg = round(p.get("sign_deg", p.get("longitude", 0)) % 30, 2)
        nak = get_nakshatra(p.get("longitude", 0))
        dc = _dignity_colour(dignity)
        pc = _planet_colour(name)
        rows += f"""<tr>
          <td><strong style="color:{pc}">{name}</strong>{retro}</td>
          <td>{sign}</td><td>{deg}°</td>
          <td>{nak["name"]} / Pd.{nak["pada"]}</td>
          <td>{house}th</td>
          <td>{house_lord_map.get(house, "")}</td>
          <td style="color:{dc};font-weight:600;">{dignity}</td>
          <td>{p["rashi"].get("sanskrit","")}</td>
        </tr>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">OVERVIEW</span>
    <div><div class="sec-title">Graha Sthiti &mdash; Planetary Positions</div>
         <span class="sec-skt">&#2327;&#2381;&#2352;&#2361; &#2360;&#2381;&#2341;&#2367;&#2340;&#2367;</span></div>
    <div class="sec-line"></div>
  </div>
  <table class="planet-table">
    <thead><tr>
      <th>Planet</th><th>Sign</th><th>Degree</th><th>Nakshatra / Pada</th>
      <th>House</th><th>House Lord</th><th>Dignity</th><th>Sanskrit</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def _html_yogas_section(yogas: List[dict]) -> str:
    if not yogas:
        return ""
    cards = ""
    for y in yogas:
        cat = y.get("category", "Yoga")
        if cat == "Pancha Mahapurusha":
            cls = "yoga-card pancha"
        elif "Raja" in cat:
            cls = "yoga-card raja"
        elif "Adverse" in cat or y.get("strength") == "Adverse":
            cls = "yoga-card adverse"
        else:
            cls = "yoga-card"
        strength_color = {
            "Very Strong": "#FFD700", "Strong": "#69F0AE",
            "Moderate": "var(--gold)", "Adverse": "#FF6B6B",
            "Background": "rgba(250,246,238,.5)"
        }.get(y.get("strength", ""), "var(--gold)")

        # Classical result text from B.V. Raman
        classical = y.get("classical_result", "")
        classical_block = ""
        if classical:
            classical_block = f"""
            <div style="font-size:11px;color:rgba(250,246,238,.7);margin-top:6px;
                 padding-top:6px;border-top:1px solid rgba(201,168,76,.15);
                 font-style:italic;">
              <strong style="color:var(--gold);font-style:normal;">Classical Result:</strong> {classical}
            </div>"""

        source = y.get("source", "")
        source_block = ""
        if source:
            source_block = f'<div style="font-size:9px;color:rgba(201,168,76,.35);margin-top:4px;">{source}</div>'

        cards += f"""
      <div class="{cls}">
        <div class="yname">{y["name"]}</div>
        <div class="ytype">{cat}</div>
        <div class="yform">{y.get("planet","")} &middot; House {y.get("house","")}</div>
        <div style="font-size:11px;color:{strength_color};margin-bottom:8px;">
          Strength: {y.get("strength","")}</div>
        <div class="ytext">{y.get("description","")}</div>
        {classical_block}
        {source_block}
      </div>"""

    # Categorize yogas for summary
    raja_count = sum(1 for y in yogas if "Raja" in y.get("category", ""))
    dhana_count = sum(1 for y in yogas if "Wealth" in y.get("category", "") or "Dhana" in y.get("name", ""))
    pancha_count = sum(1 for y in yogas if y.get("category") == "Pancha Mahapurusha")
    lunar_count = sum(1 for y in yogas if "Lunar" in y.get("category", ""))
    adverse_count = sum(1 for y in yogas if y.get("strength") == "Adverse" or "Adverse" in y.get("category", ""))

    summary_parts = []
    if pancha_count:
        summary_parts.append(f"{pancha_count} Pancha Mahapurusha")
    if raja_count:
        summary_parts.append(f"{raja_count} Raja Yoga(s)")
    if dhana_count:
        summary_parts.append(f"{dhana_count} Dhana/Wealth Yoga(s)")
    if lunar_count:
        summary_parts.append(f"{lunar_count} Lunar Yoga(s)")
    if adverse_count:
        summary_parts.append(f"{adverse_count} adverse combination(s)")

    summary_text = ", ".join(summary_parts) if summary_parts else "various planetary combinations"

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">YOGAS</span>
    <div><div class="sec-title">Graha Yogas &mdash; Planetary Power Combinations</div>
         <span class="sec-skt">Pancha Mahapurusha &middot; Raja Yoga &middot; Dhana Yoga &middot; Lunar Yoga</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Yoga Summary:</strong>
    {len(yogas)} significant yoga(s) detected in this chart &mdash; {summary_text}.
    These represent the chart's primary power concentrations and karmic signatures
    as defined by B.V. Raman's classical methodology.
  </div>
  <div class="yoga-grid">{cards}</div>
</div>"""


def _html_houses_section(house_interps: List[dict], raman_analysis: dict = None,
                         d9_house_map: dict = None, d10_house_map: dict = None) -> str:
    d9_house_map = d9_house_map or {}
    d10_house_map = d10_house_map or {}
    blocks = ""
    for h in house_interps:
        occ_tags = "".join(
            f'<span class="ptag" style="color:{_planet_colour(od["planet"])};'
            f'background:rgba(0,0,0,.2);">'
            f'{od["planet"]}{"(R)" if od.get("retrograde") else ""} '
            f'<small style="opacity:.7;">{od["dignity"]}</small></span>'
            for od in h["occupant_details"]
        )
        sloka_block = ""
        if h.get("bphs_sloka"):
            sloka_block = f"""
            <div class="sloka">"{h["bphs_sloka"]}"
              <cite>— BPHS, Lord of {h["house"]}th in {h["lord_house"]}th Bhava</cite>
            </div>"""

        # B.V. Raman's planet-in-house effects for each occupant
        raman_effects_block = ""
        if raman_analysis and h["occupant_details"]:
            pe = raman_analysis.get("planet_effects", {})
            for od in h["occupant_details"]:
                pname = od["planet"]
                if pname in pe:
                    peff = pe[pname]
                    interp_text = peff.get("interpretation", "")
                    if interp_text:
                        raman_effects_block += f"""
              <div style="margin:8px 0;padding:8px 12px;border-left:2px solid {_planet_colour(pname)};
                   background:rgba(0,0,0,.15);border-radius:0 4px 4px 0;">
                <div style="font-size:11px;color:{_planet_colour(pname)};font-weight:600;margin-bottom:4px;">
                  {pname} in House {h["house"]} ({od["dignity"]})</div>
                <div style="font-size:12px;color:rgba(250,246,238,.75);line-height:1.5;">
                  {interp_text}</div>
                <div style="font-size:9px;color:rgba(201,168,76,.3);margin-top:3px;">
                  — B.V. Raman, How to Judge a Horoscope</div>
              </div>"""

        # ── D9 / D10 sub-blocks for each occupant ────────────────────
        divisional_block = ""
        if h["occupant_details"] and (d9_house_map or d10_house_map):
            div_rows = ""
            for od in h["occupant_details"]:
                pname = od["planet"]
                d9 = d9_house_map.get(pname, {})
                d10 = d10_house_map.get(pname, {})
                d9_text = f'{d9.get("sign","?")} (H{d9.get("house","?")}) — <span style="color:{_dignity_colour(d9.get("dignity","Neutral"))}">{d9.get("dignity","?")}</span>' if d9 else "—"
                d10_text = f'{d10.get("sign","?")} (H{d10.get("house","?")}) — <span style="color:{_dignity_colour(d10.get("dignity","Neutral"))}">{d10.get("dignity","?")}</span>' if d10 else "—"
                div_rows += f"""<tr>
                  <td style="padding:4px 8px;color:{_planet_colour(pname)};font-weight:600;">{pname}</td>
                  <td style="padding:4px 8px;color:#B07DC9;">{d9_text}</td>
                  <td style="padding:4px 8px;color:#2E86AB;">{d10_text}</td></tr>"""
            divisional_block = f"""
            <div style="margin:12px 0;padding:10px 14px;background:rgba(0,0,0,.2);
                 border:1px solid rgba(201,168,76,.15);border-radius:4px;">
              <div style="font-size:11px;letter-spacing:2px;color:var(--gold);opacity:.7;margin-bottom:6px;">
                DIVISIONAL CHART POSITIONS</div>
              <table style="width:100%;border-collapse:collapse;font-size:12px;">
                <thead><tr style="border-bottom:1px solid rgba(201,168,76,.2);">
                  <th style="text-align:left;padding:4px 8px;color:var(--gold);font-size:10px;">Planet</th>
                  <th style="text-align:left;padding:4px 8px;color:#B07DC9;font-size:10px;">D9 (Navamsha)</th>
                  <th style="text-align:left;padding:4px 8px;color:#2E86AB;font-size:10px;">D10 (Dasamsa)</th>
                </tr></thead><tbody>{div_rows}</tbody></table>
            </div>"""

        blocks += f"""
      <div class="house-block">
        <div class="house-hd">
          <span class="house-num">HOUSE {h["house"]}</span>
          <span class="house-name">{HOUSE_TITLES.get(h["house"],"")}</span>
          <span class="house-sign">{h["sign"]} ({h["sign_sanskrit"]})</span>
          <span style="font-size:12px;color:var(--gold);opacity:.8;">
            Lord: {h["lord"]} in H{h["lord_house"]}
            <span style="color:{_dignity_colour(h["lord_dignity"])};">({h["lord_dignity"]})</span>
          </span>
        </div>
        <div class="planet-tags">{occ_tags if occ_tags else
            '<span style="font-size:12px;color:rgba(250,246,238,.4);font-style:italic;">No planets</span>'}</div>
        <div style="font-size:12px;color:rgba(201,168,76,.6);margin-bottom:10px;">
          {" &middot; ".join(h["classification"])}
        </div>
        {sloka_block}
        <div class="verdict">
          <span class="vl">BPHS Analysis</span>
          Lord <strong>{h["lord"]}</strong> ({h["lord_dignity"]}) is in the
          <strong>{h["lord_house"]}th house</strong> ({h["lord_sign"]}).
          {_lord_verdict(h["lord"], h["house"], h["lord_house"], h["lord_dignity"])}
        </div>
        {raman_effects_block}
        {divisional_block}
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">HOUSES</span>
    <div><div class="sec-title">Bhava Vishleshan &mdash; All 12 Houses</div>
         <span class="sec-skt">&#2349;&#2366;&#2357; &#2357;&#2367;&#2358;&#2381;&#2354;&#2375;&#2359;&#2339;
         &middot; D1 &middot; D9 &middot; D10</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout" style="background:rgba(201,168,76,.05);border-color:rgba(201,168,76,.3);">
    <strong style="color:var(--gold);">Comprehensive Analysis:</strong>
    Each house below shows the D1 (Rashi) placement as the primary analysis, with
    D9 (Navamsha) and D10 (Dasamsa) positions for every occupying planet. This
    three-chart cross-reference reveals the full depth of each planet's karma —
    its birth promise (D1), soul strength (D9), and professional expression (D10).
  </div>
  {blocks}
</div>"""


def _parashari_combination(own_house: int, placed_house: int) -> str:
    """Return a Parashari doctrine note for a specific lord-in-house combination."""
    combos = {
        (1, 1): "The Lagna lord in the Lagna itself grants a strong self-directed nature — physical vitality is preserved and the personality commands respect.",
        (1, 4): "Lagna lord in the 4th bestows domestic happiness, property, and maternal blessings; the native finds identity through hearth and homeland.",
        (1, 5): "Lagna lord in the 5th: intellect and progeny illuminate the life path; creative self-expression and spiritual inclination are both heightened.",
        (1, 7): "Lagna lord in the 7th: partnerships become the mirror of the self — marriage and alliance are primary karmic theatres for this native.",
        (1, 9): "Lagna lord in the 9th produces a dharmic life orientation; fortune, father, and divine grace flow readily toward the native.",
        (1, 10): "Lagna lord in the 10th: the self merges with career — public authority and professional legacy become expressions of personal dharma.",
        (2, 2): "2nd lord in own house: wealth accumulates through self-effort; speech carries conviction and the family lineage is preserved.",
        (2, 11): "2nd lord in the 11th: income through networks; accumulated wealth and speech serve the fulfilment of long-held desires.",
        (3, 3): "3rd lord in own house: courage is abundant; siblings are supportive and communication thrives; short journeys prove auspicious.",
        (4, 4): "4th lord in own house: strong roots and lasting peace; property, mother, and inner contentment are naturally available.",
        (4, 1): "4th lord in the Lagna: home and mother shape the identity decisively; the native is oriented toward security and continuity.",
        (5, 5): "5th lord in own house: intelligence is acute, progeny is blessed, and past-life merit flows easily into present enjoyment.",
        (5, 9): "5th lord in the 9th: the highest dharmic combination — intelligence aligned with fortune; a life touched by wisdom and pilgrimage.",
        (5, 1): "5th lord in the Lagna: intelligence and creativity pervade the personality; recognition for intellect or progeny follows.",
        (6, 6): "6th lord in own house: enemies are contained; service-based career; health requires consistent disciplined management.",
        (6, 8): "6th lord in the 8th forms Viparita Harsha Yoga — what manifests as adversity ultimately resolves as liberation or unexpected gain.",
        (6, 12): "6th lord in the 12th forms Viparita Yoga — expenditures and losses may transmute into spiritual or material gain.",
        (7, 7): "7th lord in own house: marriage is productive and partnership is a source of sustained strength.",
        (7, 8): "7th lord in the 8th: hidden karmas govern partnerships; the native must navigate transformation through relationship.",
        (8, 8): "8th lord in own house: occult depth, research orientation, and extended longevity; the native is drawn to hidden knowledge.",
        (8, 12): "8th lord in the 12th forms Viparita Sarala Yoga — transformation generates liberation; loss becomes the gateway to mastery.",
        (9, 9): "9th lord in own house: fortune is self-generated; dharma is lived with conviction; the father's influence is deeply positive.",
        (9, 10): "9th lord in the 10th: Dharma-Karmadhipati Yoga — divine fortune activates through the career; a blessed professional life.",
        (9, 1): "9th lord in the Lagna: the personality carries an innate sense of dharma; fortunate circumstances attend personal initiative.",
        (10, 9): "10th lord in the 9th: career is elevated by grace and mentorship; father, guru, or higher dharma governs professional rise.",
        (10, 10): "10th lord in own house: career is powerful and self-driven; authority and public recognition come through direct effort.",
        (11, 11): "11th lord in own house: gains accumulate consistently; the network of allies is wide, loyal, and beneficial.",
        (11, 1): "11th lord in the Lagna: gains come easily and the native is known for enterprise; desires translate readily into achievement.",
        (12, 8): "12th lord in the 8th forms Viparita Yoga — losses and exile become vehicles for occult wisdom and eventual mastery.",
        (12, 12): "12th lord in own house: liberation and foreign lands hold karmic significance; expenditure on worthy causes brings spiritual merit.",
    }
    key = (own_house, placed_house)
    if key in combos:
        return combos[key]
    # Generic Parashari-style fallback
    bhava_names = {
        1:"Tanu",2:"Dhana",3:"Sahaj",4:"Bandhu",5:"Putra",6:"Ari",
        7:"Yuvati",8:"Randhra",9:"Dharma",10:"Karma",11:"Labha",12:"Vyaya"
    }
    own_nm  = bhava_names.get(own_house, f"{own_house}th")
    plcd_nm = bhava_names.get(placed_house, f"{placed_house}th")
    return (f"The {own_nm} Bhava agenda is expressed through the {plcd_nm} arena — "
            f"examine the condition of the {plcd_nm} Bhava, its lord, and its occupants "
            f"to determine the full quality of results.")


def _lord_verdict(planet: str, own_house: int, placed_house: int, dignity: str) -> str:
    """Generate a Parashari-quality verdict for a lord's placement."""
    # House classification
    if placed_house in KENDRA_HOUSES:
        pos = ("a Kendra — the lord operates from a position of full angular strength; "
               "results manifest visibly in the material and social world.")
    elif placed_house in TRIKONA_HOUSES:
        pos = ("a Trikona — placement here is inherently auspicious; dharmic momentum "
               "supports the native in all matters of this house.")
    elif placed_house in DUSTHANA_HOUSES:
        pos = ("a Dusthana (6th, 8th, or 12th) — the lord encounters resistance; "
               "however, lords of difficult houses in difficult houses may form Viparita Yoga, "
               "converting apparent adversity into concealed fortune.")
    else:
        pos = ("a neutral Bhava — outcomes are mixed and depend on planetary association, "
               "aspect, and transit activation.")

    # Dignity note — Parashari framing
    dig_note = {
        "Exalted":
            "Being exalted, the planet delivers the full promise of its significations with maximum grace and minimal obstruction.",
        "Own Sign":
            "In own sign, the planet acts from authority and comfort — its significations are expressed freely and completely.",
        "Friendly":
            "In a friendly sign, the planet receives support; results are broadly positive, though shaped by the sign lord's condition.",
        "Enemy Sign":
            "In an enemy sign, the planet operates under strain; effort and discipline are required before results materialise.",
        "Debilitated":
            "Debilitation reduces the planet's capacity to deliver; examine whether Neecha Bhanga applies through planetary conjunctions or lordship.",
        "Neutral":
            "In a neutral sign, outcomes are moderate — neither flowing freely nor obstructed; association and aspect govern the final quality.",
    }.get(dignity, "")

    combination_note = _parashari_combination(own_house, placed_house)
    return f"Placed in {pos} {dig_note} {combination_note}"


def _html_dasha_section(timeline: List[dict], active: Optional[dict], birth_dt: datetime,
                        raman_analysis: dict = None) -> str:
    rows = ""
    now = datetime.now()
    dasha_readings = raman_analysis.get("dasha_readings", {}) if raman_analysis else {}

    for period in timeline:
        is_current = period["start"] <= now <= period["end"]
        cls = "dasha-row current" if is_current else "dasha-row"
        cur = '<span class="cur-badge">CURRENT</span>' if is_current else ""
        pc = _planet_colour(period["planet"])
        start_str = period["start"].strftime("%b %Y")
        end_str = period["end"].strftime("%b %Y")

        # Use B.V. Raman's dasha reading if available
        brief = _dasha_brief(period["planet"])
        raman_reading = ""
        dr = dasha_readings.get(period["planet"], {})
        if dr.get("strength_reading"):
            strength_level = dr.get("strength_level", "General")
            strength_color = {"Strong": "#69F0AE", "Weak": "#FF6B6B", "Mixed": "var(--gold)"}.get(
                strength_level, "rgba(250,246,238,.6)")
            ctx = dr.get("contextual_note", "")
            raman_reading = f"""
              <div style="margin-top:6px;font-size:11px;color:rgba(250,246,238,.65);line-height:1.5;">
                <span style="color:{strength_color};font-weight:600;">
                  [{strength_level}]</span> {dr["strength_reading"][:300]}
              </div>"""
            if ctx:
                raman_reading += f"""
              <div style="font-size:10px;color:rgba(201,168,76,.4);margin-top:3px;font-style:italic;">
                {ctx}</div>"""

        rows += f"""
      <div class="{cls}">
        <div class="dp-col">
          <div class="dp-name" style="color:{pc};">{period["planet"]}</div>
          <div class="dp-yr">{DASHA_YEARS[period["planet"]]} yrs</div>
        </div>
        <div class="dd-col">
          <div class="dd-range">{start_str} &rarr; {end_str} {cur}</div>
          <div class="dd-text">{brief}</div>
          {raman_reading}
        </div>
      </div>"""

    active_block = ""
    if active:
        active_dr = dasha_readings.get(active["planet"], {})
        active_strength = active_dr.get("strength_reading", _dasha_brief(active["planet"]))
        active_ctx = active_dr.get("contextual_note", "")
        active_block = f"""
      <div class="callout pos" style="margin-top:24px;">
        <strong style="color:#00C864;">Active Mahadasha: {active["planet"]}</strong>
        ({active["start"].strftime("%b %Y")} &ndash; {active["end"].strftime("%b %Y")})<br/>
        {active_strength[:400]}
        {"<br/><em style='font-size:11px;color:rgba(250,246,238,.5);'>" + active_ctx + "</em>" if active_ctx else ""}
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">DASHA</span>
    <div><div class="sec-title">Vimshottari Dasha &mdash; The River of Time</div>
         <span class="sec-skt">&#2357;&#2367;&#2306;&#2358;&#2379;&#2340;&#2381;&#2340;&#2352;&#2368; &#2342;&#2358;&#2366; &middot; 120-Year Planetary Period Sequence</span></div>
    <div class="sec-line"></div>
  </div>
  {active_block}
  <div style="margin-top:20px;">{rows}</div>
</div>"""


def _dasha_brief(planet: str) -> str:
    briefs = {
        "Sun":     "Solar period — authority, career, government connections, paternal themes, identity crystallisation.",
        "Moon":    "Lunar period — emotional depth, home, mother, public recognition, intuition, domestic life.",
        "Mars":    "Mars period — career drive, courage, initiative, leadership, competitive achievement, physical energy.",
        "Mercury": "Mercury period — intellect, communication, writing, analysis, business, siblings, education.",
        "Jupiter": "Jupiter period — wisdom, expansion, spirituality, teaching, higher knowledge, fortune, children.",
        "Venus":   "Venus period — relationships, beauty, creativity, comfort, dharma, property, sensual enjoyment.",
        "Saturn":  "Saturn period — discipline, structure, karmic lessons, endurance, service, delays, ultimate mastery.",
        "Rahu":    "Rahu period — ambition, foreign connections, unconventional paths, rapid expansion, obsession, illusion.",
        "Ketu":    "Ketu period — spirituality, detachment, past-life themes, moksha, sudden changes, occult wisdom.",
    }
    return briefs.get(planet, "")


def _html_nakshatra_section(lagna_nak: dict, moon_nak: dict, planet_map: Dict[str, dict]) -> str:
    nak_data = {
        "Ashwini":       ("Ketu",    "Ashwini Kumars — divine physicians. Swift healing, pioneering spirit, impulsive energy."),
        "Bharani":       ("Venus",   "Yama — lord of death and dharma. Carries the weight of karma, intense creative force."),
        "Krittika":      ("Sun",     "Agni — the fire deity. Sharp, purifying, cutting through illusion with solar precision."),
        "Rohini":        ("Moon",    "Brahma — creator. Fertile, creative, sensual, deeply connected to material beauty."),
        "Mrigashira":    ("Mars",    "Soma — the moon-god. Gentle seeker, eternal wanderer in search of the perfect."),
        "Ardra":         ("Rahu",    "Rudra — the storm god. Transformation through destruction, intense mental activity."),
        "Punarvasu":     ("Jupiter", "Aditi — mother of gods. Return to goodness, restoration, Jupiterian benevolence."),
        "Pushya":        ("Saturn",  "Brihaspati — guru of gods. Nourishment, wisdom, the most auspicious of nakshatras."),
        "Ashlesha":      ("Mercury", "Nagas — serpent wisdom. Deep emotional intelligence, coiling Kundalini energy, psychic power."),
        "Magha":         ("Ketu",    "Pitrs — ancestral spirits. Royal authority, ancestral merit, connection to lineage power."),
        "Purvaphalguni": ("Venus",   "Bhaga — lord of delight. Pleasure, creativity, marital happiness, artistic expression."),
        "Uttaraphalguni":("Sun",     "Aryaman — solar dharma. Steady alliance, social contracts, responsibility in relationships."),
        "Hasta":         ("Moon",    "Savitar — the solar creator. Skillful hands, craftsmanship, wit, healing dexterity."),
        "Chitra":        ("Mars",    "Vishwakarma — divine architect. Aesthetic brilliance, architectural mind, creative fire."),
        "Swati":         ("Rahu",    "Vayu — the wind god. Independence, restlessness, diplomatic flexibility, scattered energy."),
        "Vishakha":      ("Jupiter", "Indra-Agni — dual power. Goal-oriented, jealous of achievement, purposeful ambition."),
        "Anuradha":      ("Saturn",  "Mitra — divine friendship. Deep loyalty, alliance building, Saturnine discipline in love."),
        "Jyeshtha":      ("Mercury", "Indra — king of gods. Seniority, authority, protective power, the elder's wisdom."),
        "Mula":          ("Ketu",    "Nirriti — dissolution goddess. Gets to the root of everything; destructive and regenerative."),
        "Purvashadha":   ("Venus",   "Apas — water goddess. Purification, invincibility, philosophical restlessness, deep pride."),
        "Uttarashadha":  ("Sun",     "Vishwadevas — universal gods. Final victory, righteousness, permanent achievement."),
        "Shravana":      ("Moon",    "Vishnu — the preserver. Listening, learning, wisdom through hearing, connection to cosmic law."),
        "Dhanishtha":    ("Mars",    "Eight Vasus — elemental gods. Wealth, music, martial arts, abundant material success."),
        "Shatabhisha":   ("Rahu",    "Varuna — cosmic law. Healing, occult research, 100 physicians, secretive investigative power."),
        "Purvabhadrapada":("Jupiter","Aja Ekapada — the one-footed goat. Purification through fire, ascetic wisdom, otherworldly."),
        "Uttarabhadrapada":("Saturn","Ahir Budhnya — serpent of the deep. Deep wisdom, kundalini, compassionate sage energy."),
        "Revati":        ("Mercury", "Pushan — nourisher of souls. Completion, abundance, the final journey, nurturing."),
    }

    def nak_card(nak_dict, label):
        nak_name = nak_dict.get("name", "")
        lord = nak_dict.get("lord", "")
        pada = nak_dict.get("pada", "")
        deity_text = nak_data.get(nak_name, (lord, "Ancient nakshatra with deep cosmic significance."))[1]
        return f"""
      <div class="nak-card">
        <div class="nak-title">{nak_name}</div>
        <div class="nak-sub">{label} &middot; Lord: {lord} &middot; Pada {pada}</div>
        <div class="nak-text">{deity_text}</div>
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">NAKSHATRA</span>
    <div><div class="sec-title">Nakshatra Analysis &mdash; Star Constellation Reading</div>
         <span class="sec-skt">&#2344;&#2325;&#2381;&#2359;&#2340;&#2381;&#2352; &#2357;&#2367;&#2358;&#2381;&#2354;&#2375;&#2359;&#2339;</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="nak-grid">
    {nak_card(lagna_nak, "RISING NAKSHATRA")}
    {nak_card(moon_nak, "MOON NAKSHATRA")}
  </div>
</div>"""


def _html_ashtakvarga(av_data: dict) -> str:
    """Render ashtakvarga house scores if provided."""
    cells = ""
    for h in range(1, 13):
        score = av_data.get(str(h), av_data.get(h, 0))
        colour = "#00E676" if score >= 30 else "#FFD700" if score >= 25 else "#FF4444"
        cells += f"""
      <div style="background:rgba(30,45,90,.6);border:1px solid rgba(201,168,76,.3);
                  border-radius:6px;padding:14px;text-align:center;">
        <div style="font-size:9px;color:var(--gold);letter-spacing:2px;margin-bottom:4px;">H{h}</div>
        <div style="font-size:28px;font-weight:700;color:{colour};">{score}</div>
        <div style="font-size:10px;color:rgba(250,246,238,.6);margin-top:3px;">
          {classify_bindu(score)}</div>
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">ASHTAKVARGA</span>
    <div><div class="sec-title">Ashtakvarga &mdash; House Strength Scores</div>
         <span class="sec-skt">Sarva Ashtakvarga Bindu Scores (30+ = Strong, 25-30 = Average, &lt;25 = Weak)</span></div>
    <div class="sec-line"></div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:24px 0;">
    {cells}
  </div>
</div>"""


def _html_remedies(lagna_lord: str, house_lord_map: Dict[int, str],
                   planet_map: Dict[str, dict], yogas: List[dict]) -> str:
    # Determine yoga karaka for lagna
    kendra_lords = {house_lord_map[h] for h in KENDRA_HOUSES if h != 1}
    trikona_lords = {house_lord_map[h] for h in TRIKONA_HOUSES if h != 1}
    yk_set = kendra_lords & trikona_lords
    yoga_karaka = list(yk_set)[0] if yk_set else ""

    gem_recs = {
        "Sun":     ("Ruby (Manikya)", "Gold ring finger, Sunday sunrise"),
        "Moon":    ("Pearl (Moti)", "Silver right-hand little finger, Monday"),
        "Mars":    ("Red Coral (Moonga)", "Gold/copper ring finger, Tuesday"),
        "Mercury": ("Emerald (Panna)", "Gold little finger, Wednesday"),
        "Jupiter": ("Yellow Sapphire (Pukhraj)", "Gold index finger, Thursday"),
        "Venus":   ("White Sapphire or Diamond", "Silver/platinum middle finger, Friday"),
        "Saturn":  ("Blue Sapphire (Neelam) — test first", "Silver middle finger, Saturday"),
    }

    mantra_recs = {
        "Sun":     "Om Suryaya Namaha (108x Sundays)",
        "Moon":    "Om Chandraya Namaha (108x Mondays)",
        "Mars":    "Om Mangalaya Namaha (108x Tuesdays)",
        "Mercury": "Om Budhaya Namaha (108x Wednesdays)",
        "Jupiter": "Om Gurave Namaha (108x Thursdays)",
        "Venus":   "Om Shukraya Namaha (108x Fridays)",
        "Saturn":  "Om Shanicharaya Namaha (108x Saturdays)",
    }

    cards = []

    # Always recommend Lagna lord remedy
    if lagna_lord in gem_recs:
        gem, wear = gem_recs[lagna_lord]
        cards.append(f"""<div class="rc">
      <div class="ri">&#128142;</div>
      <div class="rt">Lagna Lord Gemstone ({lagna_lord})</div>
      <div class="rb">{gem}<br/><em>Wear: {wear}</em></div>
    </div>""")

    # Yoga Karaka gemstone
    if yoga_karaka and yoga_karaka in gem_recs and yoga_karaka != lagna_lord:
        gem, wear = gem_recs[yoga_karaka]
        cards.append(f"""<div class="rc">
      <div class="ri">&#11088;</div>
      <div class="rt">Yoga Karaka Gemstone ({yoga_karaka})</div>
      <div class="rb">{gem} — most auspicious stone for this Lagna<br/><em>Wear: {wear}</em></div>
    </div>""")

    # Mantra for lagna lord
    if lagna_lord in mantra_recs:
        cards.append(f"""<div class="rc">
      <div class="ri">&#129406;</div>
      <div class="rt">Primary Mantra ({lagna_lord})</div>
      <div class="rb">{mantra_recs[lagna_lord]}</div>
    </div>""")

    # Yoga Karaka mantra
    if yoga_karaka and yoga_karaka in mantra_recs and yoga_karaka != lagna_lord:
        cards.append(f"""<div class="rc">
      <div class="ri">&#127774;</div>
      <div class="rt">Yoga Karaka Mantra ({yoga_karaka})</div>
      <div class="rb">{mantra_recs[yoga_karaka]}</div>
    </div>""")

    # Universal recommendations
    cards += [
        """<div class="rc">
      <div class="ri">&#129717;</div>
      <div class="rt">Daily Practice</div>
      <div class="rb">Surya Namaskar at sunrise (12 rounds Sundays). Meditation 20 min at dawn.
        Contact with natural water bodies strengthens cosmic alignment.</div>
    </div>""",
        """<div class="rc">
      <div class="ri">&#127774;</div>
      <div class="rt">Charitable Acts (Dana)</div>
      <div class="rb">Serve the elderly and underprivileged on Saturdays. Donate to education
        or children on Thursdays. Feed cows on Fridays. All dana activates dharmic fortune.</div>
    </div>""",
    ]

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">UPAYAS</span>
    <div><div class="sec-title">Remedies &amp; Planetary Harmonisation</div>
         <span class="sec-skt">&#2313;&#2346;&#2366;&#2351; &middot; Ratna &middot; Mantra &middot; Dana &middot; Kriya</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Upaya Philosophy:</strong>
    Remedies work through correspondence — colour, sound, charity, and gemstone align the native
    with planetary energies. Practised with sincerity, they create meaningful shifts in life experience.
    Always consult a qualified gemologist before wearing any gemstone.
  </div>
  <div class="remedy-grid">{"".join(cards)}</div>
</div>"""


def _html_cosmic_context(lagna_sign: str, lagna_lord: str, lagna_nak: dict,
                         planet_map: Dict[str, dict], lagna_sign_idx: int,
                         house_lord_map: Dict[int, str]) -> str:
    """
    Section 1 — Cosmic Context of Birth (Parashari Doctrine).
    Establishes the nature of the Lagna, dominant Guna, and karmic positioning
    before any detailed house or yoga analysis begins.
    """
    # ── Lagna element and Guna ────────────────────────────────────────────────
    fire_signs  = {"Aries","Leo","Sagittarius"}
    earth_signs = {"Taurus","Virgo","Capricorn"}
    air_signs   = {"Gemini","Libra","Aquarius"}
    water_signs = {"Cancer","Scorpio","Pisces"}

    if lagna_sign in fire_signs:
        element, element_desc = "Fire (Agni)", (
            "Fire Lagnas orient the native toward initiative, authority, and dharmic action. "
            "The life-force is combustive — best expressed through leadership, courage, and decisive will.")
    elif lagna_sign in earth_signs:
        element, element_desc = "Earth (Prithvi)", (
            "Earth Lagnas give a grounded, patient, and acquisitive nature. "
            "The life-force consolidates — prosperity, craft, and material mastery are the natural outlets.")
    elif lagna_sign in air_signs:
        element, element_desc = "Air (Vayu)", (
            "Air Lagnas produce a restless, communicative, and intellectually oriented native. "
            "The life-force circulates — knowledge, discourse, relationship, and social movement define the path.")
    else:
        element, element_desc = "Water (Jala)", (
            "Water Lagnas impart deep emotional intelligence, intuitive perception, and spiritual receptivity. "
            "The life-force is receptive — home, devotion, healing, and inner life are primary theatres.")

    # ── Guna inference from lagna sign ───────────────────────────────────────
    sattva_signs = {"Aries","Leo","Sagittarius","Cancer","Scorpio","Pisces"}
    rajas_signs  = {"Gemini","Libra","Aquarius","Taurus","Virgo","Capricorn"}
    if lagna_sign in sattva_signs:
        guna = "Sattva"
        guna_desc = ("Sattvic orientation predominates — wisdom, dharma, and inner purity are the native's natural "
                     "gravitational field. The soul aspires toward light and righteous conduct.")
    else:
        guna = "Rajas"
        guna_desc = ("Rajasic orientation predominates — ambition, activity, and engagement with the world are "
                     "the native's driving forces. Achievement, acquisition, and social participation define the life arc.")

    # ── Functional benefic/malefic summary for this Lagna ────────────────────
    kendra_lords  = {house_lord_map[h] for h in KENDRA_HOUSES  if h in house_lord_map}
    trikona_lords = {house_lord_map[h] for h in TRIKONA_HOUSES if h in house_lord_map}
    dusthana_lords= {house_lord_map[h] for h in DUSTHANA_HOUSES if h in house_lord_map}
    func_benefics = sorted(kendra_lords | trikona_lords - dusthana_lords)
    yoga_karaka_set = kendra_lords & trikona_lords
    yk_text = ""
    if yoga_karaka_set:
        yk = list(yoga_karaka_set)[0]
        yk_text = (f"<strong>{yk}</strong> holds the coveted position of Yoga Karaka — "
                   f"lord of both a Kendra and a Trikona — and therefore carries the highest "
                   f"capacity to elevate this native's fortune when well-placed and strong.")

    # ── Nakshatra deity statement ─────────────────────────────────────────────
    nak_name = lagna_nak.get("name","")
    nak_lord = lagna_nak.get("lord","")
    nak_pada = lagna_nak.get("pada","")
    nak_deities = {
        "Ashwini":"the divine Ashwini Kumars (celestial physicians)",
        "Bharani":"Yama (lord of dharmic reckoning)",
        "Krittika":"Agni (the purifying fire)",
        "Rohini":"Brahma (the creator)",
        "Mrigashira":"Soma (the wandering moon-god)",
        "Ardra":"Rudra (the storm-force of transformation)",
        "Punarvasu":"Aditi (mother of the gods)",
        "Pushya":"Brihaspati (guru of the immortals)",
        "Ashlesha":"the Nagas (keepers of serpent wisdom)",
        "Magha":"the Pitrs (ancestral spirits)",
        "Purvaphalguni":"Bhaga (lord of conjugal delight)",
        "Uttaraphalguni":"Aryaman (solar dharma and alliance)",
        "Hasta":"Savitar (the solar craftsman)",
        "Chitra":"Vishwakarma (the divine architect)",
        "Swati":"Vayu (the wind-god of independence)",
        "Vishakha":"Indra-Agni (the dual power of purpose and fire)",
        "Anuradha":"Mitra (the lord of divine friendship)",
        "Jyeshtha":"Indra (king of the gods, sovereign authority)",
        "Mula":"Nirriti (the dissolution goddess at the root of all things)",
        "Purvashadha":"Apas (the water deity of philosophical purification)",
        "Uttarashadha":"the Vishwadevas (universal gods of final victory)",
        "Shravana":"Vishnu (the preserver of cosmic order)",
        "Dhanishtha":"the eight Vasus (elemental lords of abundance)",
        "Shatabhisha":"Varuna (cosmic law and healing)",
        "Purvabhadrapada":"Aja Ekapada (the ascetic flame of purification)",
        "Uttarabhadrapada":"Ahir Budhnya (the serpent of the deep — compassionate sage)",
        "Revati":"Pushan (the nourisher who guides souls toward completion)",
    }
    deity = nak_deities.get(nak_name, "a presiding deity of cosmic significance")

    nak_statement = (
        f"The Lagna rises in <strong>{nak_name}</strong> Nakshatra (Pada {nak_pada}), "
        f"presided over by {deity}. Its lord <strong>{nak_lord}</strong> governs the "
        f"quality of the ascending impulse — the native's instinctive approach to life "
        f"carries the vibrational signature of this star."
    )

    yk_block = f"<p>{yk_text}</p>" if yk_text else ""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">COSMIC CONTEXT</span>
    <div>
      <div class="sec-title">Janma Pravesh &mdash; Context of Birth</div>
      <span class="sec-skt">&#2332;&#2344;&#2381;&#2350; &#2346;&#2381;&#2352;&#2357;&#2375;&#2358; &middot; Parashari Graha Svarūpa</span>
    </div>
    <div class="sec-line"></div>
  </div>

  <div class="callout" style="background:rgba(201,168,76,.07);border-color:rgba(201,168,76,.4);border-left-color:var(--gold);">
    <strong style="color:var(--gold);">Analytical Framework:</strong>
    This consultation follows the doctrinal sequence of Brihat Parashara Hora Shastra.
    All judgements are derived through classical Parashari logic — Graha nature,
    Rāśi placement, Bhava lordship, Yoga identification, and Dasha timing.
    No modern interpretive overlays have been applied.
  </div>

  <div class="house-block" style="margin-top:24px;">
    <div class="house-hd">
      <span class="house-name">Lagna: {lagna_sign}</span>
      <span class="house-sign">Element: {element}</span>
      <span style="font-size:12px;color:var(--gold);opacity:.85;">Dominant Guna: {guna}</span>
    </div>
    <div class="house-text">
      <p>{element_desc}</p>
      <p>{guna_desc}</p>
      <p>{nak_statement}</p>
      {yk_block}
    </div>
  </div>
</div>"""


def _html_first_impression(positions: dict, lagna_sign: str, lagna_lord: str,
                            planet_map: Dict[str, dict], yogas: List[dict],
                            active_dasha: Optional[dict], lagna_sign_idx: int,
                            house_lord_map: Dict[int, str]) -> str:
    """
    Astrologer's First Impression — a synthesising callout that appears
    immediately after the planetary table, giving the overall Parashari
    'read' of the chart before detailed house analysis begins.
    """
    # ── Find dominant planets ─────────────────────────────────────────────────
    dignity_rank = {"Exalted": 5, "Own Sign": 4, "Friendly": 3,
                    "Neutral": 2, "Enemy Sign": 1, "Debilitated": 0, "Unknown": 2}
    strongest = sorted(
        [(n, get_dignity(n, p["rashi"]["name"])) for n, p in planet_map.items()
         if n not in ("Rahu","Ketu","Uranus","Neptune","Pluto")],
        key=lambda x: dignity_rank.get(x[1], 2), reverse=True
    )
    top_planet, top_dignity = strongest[0] if strongest else ("Saturn", "Neutral")

    # ── House loading ─────────────────────────────────────────────────────────
    kendra_loaded = sum(
        1 for p in planet_map.values()
        if planet_house(SIGN_NAMES.index(p["rashi"]["name"]) if p["rashi"]["name"] in SIGN_NAMES else 0,
                        lagna_sign_idx) in KENDRA_HOUSES
    )
    yoga_count = len(yogas)
    pancha = sum(1 for y in yogas if y.get("category") == "Pancha Mahapurusha")

    # ── Compose impression ────────────────────────────────────────────────────
    strength_stmt = (
        f"<strong>{top_planet}</strong> stands as the pre-eminent planet in this chart, "
        f"placed in {top_dignity.lower()} — its significations are the primary vehicle "
        f"of fortune and destiny for this native."
    )

    yoga_stmt = ""
    if pancha > 0:
        yoga_stmt = (
            f"The chart carries <strong>{pancha} Pancha Mahapurusha Yoga(s)</strong> "
            f"— a rare configuration that elevates the native above ordinary circumstance "
            f"and points toward exceptional achievement in the Yoga planet's domain."
        )
    elif yoga_count > 0:
        yoga_stmt = (
            f"<strong>{yoga_count} significant Yoga(s)</strong> have been identified. "
            f"These planetary power concentrations must be read in conjunction with "
            f"Dasha timing to determine when their fruits become accessible."
        )

    kendra_stmt = ""
    if kendra_loaded >= 3:
        kendra_stmt = (
            "The angular houses carry a strong planetary load — worldly action, career, "
            "and social engagement are primary life theatres."
        )

    dasha_stmt = ""
    if active_dasha:
        dasha_stmt = (
            f"The native is presently in <strong>{active_dasha['planet']} Mahadasha</strong> "
            f"({active_dasha['start'].strftime('%b %Y')} – {active_dasha['end'].strftime('%b %Y')}). "
            f"All current experience is filtered through {active_dasha['planet']}'s "
            f"functional nature from the {lagna_sign} Lagna."
        )

    parts = [p for p in [strength_stmt, yoga_stmt, kendra_stmt, dasha_stmt] if p]
    body = " ".join(parts)

    return f"""
<div class="callout" style="background:rgba(201,168,76,.07);border:1px solid rgba(201,168,76,.4);
     border-left:3px solid var(--gold);padding:18px 22px;margin:20px 0;border-radius:0 4px 4px 0;">
  <strong style="color:var(--gold);font-size:11px;letter-spacing:2px;display:block;margin-bottom:8px;text-transform:uppercase;">
    Astrologer's First Impression
  </strong>
  <div style="font-size:15px;color:rgba(250,246,238,.92);line-height:1.85;">
    {body}
  </div>
</div>"""


def _html_synthesis(lagna_sign: str, lagna_lord: str, planet_map: Dict[str, dict],
                    yogas: List[dict], active_dasha: Optional[dict],
                    house_lord_map: Dict[int, str], lagna_sign_idx: int) -> str:
    """
    Section 19 — Life Outcome Synthesis (Parashari Doctrine).
    Integrates character, wealth potential, relationships, career, and
    spiritual direction into a final Parashari reading.
    """
    # ── Identify key life indicators ──────────────────────────────────────────
    planet_7  = house_lord_map.get(7, "")   # marriage significator
    planet_10 = house_lord_map.get(10, "")  # career significator
    planet_9  = house_lord_map.get(9, "")   # fortune / dharma
    planet_11 = house_lord_map.get(11, "")  # gains / fulfilment

    dignity_10 = get_dignity(planet_10, planet_map[planet_10]["rashi"]["name"]) if planet_10 in planet_map else "Unknown"
    dignity_7  = get_dignity(planet_7,  planet_map[planet_7]["rashi"]["name"])  if planet_7  in planet_map else "Unknown"
    dignity_9  = get_dignity(planet_9,  planet_map[planet_9]["rashi"]["name"])  if planet_9  in planet_map else "Unknown"

    # ── Yoga Karaka ───────────────────────────────────────────────────────────
    kendra_lords  = {house_lord_map[h] for h in KENDRA_HOUSES  if h in house_lord_map}
    trikona_lords = {house_lord_map[h] for h in TRIKONA_HOUSES if h in house_lord_map}
    yk_set = kendra_lords & trikona_lords
    yk = list(yk_set)[0] if yk_set else ""

    # ── Career block ──────────────────────────────────────────────────────────
    career_quality = {
        "Exalted":     "exceptionally strong career prospects; public recognition and authority are strongly indicated",
        "Own Sign":    "a confident and self-directed career; the native commands respect in professional domains",
        "Friendly":    "a productive and generally supported career trajectory",
        "Neutral":     "a career that progresses through consistent effort without marked obstruction or extraordinary elevation",
        "Enemy Sign":  "a career marked by friction; the native must navigate resistance before professional credibility is established",
        "Debilitated": "career development requires careful remedial support; Dasha periods of the 10th lord must be evaluated carefully",
    }.get(dignity_10, "a career whose quality depends on the Dasha lord's strength at key junctures")

    # ── Relationship block ────────────────────────────────────────────────────
    marriage_quality = {
        "Exalted":     "marriage is a source of great strength and joy; the partner brings refinement and prosperity",
        "Own Sign":    "the 7th lord in own sign supports lasting partnership; the native attracts a capable and committed companion",
        "Friendly":    "relationships are generally harmonious; partnership brings support and mutual growth",
        "Neutral":     "marriage is neither especially challenging nor exceptionally blessed; compatibility determines outcome",
        "Enemy Sign":  "partnership requires conscious cultivation; differences in temperament or values create tension",
        "Debilitated": "the 7th lord is under strain; delay in marriage or difficulty in sustaining partnership is possible without remedial support",
    }.get(dignity_7, "relationships whose quality unfolds through time and the activation of the 7th house by Dasha")

    # ── Fortune block ─────────────────────────────────────────────────────────
    fortune_quality = {
        "Exalted":     "fortune flows abundantly; grace, mentorship, and divine support are available throughout the life",
        "Own Sign":    "fortune is self-sustaining; dharmic choices reliably attract positive outcomes",
        "Friendly":    "fortune is accessible through right action; the 9th house themes are supportive",
        "Neutral":     "fortune is moderate and depends on disciplined effort and adherence to dharma",
        "Enemy Sign":  "fortune requires effort to access; father or guru relationships may be complex",
        "Debilitated": "fortune must be cultivated through sustained dharmic practice; prayer and charity are strongly recommended",
    }.get(dignity_9, "fortune that reveals itself gradually through dharmic engagement")

    # ── Yoga summary ──────────────────────────────────────────────────────────
    pancha = [y for y in yogas if y.get("category") == "Pancha Mahapurusha"]
    pancha_text = ""
    if pancha:
        pancha_names = ", ".join(y["name"] for y in pancha)
        pancha_text = (
            f"The presence of <strong>{pancha_names}</strong> — "
            f"among the supreme Pancha Mahapurusha Yogas — is a profound indication "
            f"of destined excellence in the Yoga planet's domain. "
            f"These Yogas do not guarantee ease; they guarantee that extraordinary potential exists "
            f"and will express itself when the corresponding Mahadasha activates."
        )

    # ── Dasha timing note ─────────────────────────────────────────────────────
    dasha_text = ""
    if active_dasha:
        dasha_text = (
            f"In the current <strong>{active_dasha['planet']} Mahadasha</strong>, "
            f"all Yoga potential, house themes, and life events are being filtered "
            f"through {active_dasha['planet']}'s functional nature from the {lagna_sign} Lagna. "
            f"The quality of this Dasha lord's placement and dignity determines "
            f"whether the native experiences this as a period of ascent, consolidation, or trial."
        )

    yk_text = ""
    if yk:
        yk_text = (
            f"<strong>{yk}</strong> — Yoga Karaka for the {lagna_sign} Lagna — "
            f"deserves special attention in all life planning. Strengthening this planet "
            f"through its gemstone, mantra, and associated charitable acts "
            f"is the single most impactful intervention available to this native."
        )

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">SYNTHESIS</span>
    <div>
      <div class="sec-title">Jyotish Nirnaya &mdash; Life Outcome Synthesis</div>
      <span class="sec-skt">&#2332;&#2381;&#2351;&#2379;&#2340;&#2367;&#2359; &#2344;&#2367;&#2352;&#2381;&#2339;&#2351; &middot; Final Parashari Reading</span>
    </div>
    <div class="sec-line"></div>
  </div>

  <div class="summary-banner">
    <h3>Astrologer's Closing Synthesis</h3>
    <p>
      The {lagna_sign} Lagna orients this native toward
      {"dharmic initiative and self-authority" if lagna_sign in {"Aries","Leo","Sagittarius"} else
       "material consolidation and patient mastery" if lagna_sign in {"Taurus","Virgo","Capricorn"} else
       "intellectual engagement and relational wisdom" if lagna_sign in {"Gemini","Libra","Aquarius"} else
       "emotional intelligence and devotional depth"}.
      The planetary configuration reveals {career_quality}; in relationships,
      {marriage_quality}; and in matters of fortune and dharma, {fortune_quality}.
    </p>
  </div>

  <div class="house-block">
    <div class="house-hd">
      <span class="house-name" style="font-size:15px;">Key Life Indicators</span>
    </div>
    <div class="house-text">
      {"<p>" + pancha_text + "</p>" if pancha_text else ""}
      {"<p>" + dasha_text + "</p>" if dasha_text else ""}
      {"<p>" + yk_text + "</p>" if yk_text else ""}
      <p>
        <strong>Objective of this consultation</strong> — Structure of destiny and karmic unfolding;
        timing of experience through Dasha periods; means of alignment through Upaya.
        Jyotish illuminates tendencies and potentials. Free will, dharmic choices, and sustained
        effort remain the ultimate determinants of how these patterns are lived.
      </p>
    </div>
  </div>
</div>"""


# ── NEW 20-SECTION HTML RENDERERS ────────────────────────────────────────────

def _html_special_lagnas(lagnas: dict) -> str:
    """Section 4 — Special Lagnas (Hora, Ghati, Bhava, Varnada)."""
    cards = ""
    for key in ["hora_lagna", "ghati_lagna", "bhava_lagna", "varnada_lagna"]:
        lg = lagnas.get(key, {})
        if not lg:
            continue
        cards += f"""
      <div class="ic" style="padding:16px;">
        <span class="ic-l">{lg.get('name', key)}</span>
        <span class="ic-v" style="font-size:16px;font-weight:700;">{lg.get('sign','')}</span>
        <div style="font-size:11px;color:rgba(201,168,76,.65);margin-top:2px;">
          Lord: {lg.get('lord','')} &middot; {lg.get('degree',0)}&deg;</div>
        <div style="font-size:12.5px;color:rgba(250,246,238,.8);margin-top:8px;line-height:1.65;">
          {lg.get('interpretation','')}</div>
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">SPECIAL LAGNAS</span>
    <div><div class="sec-title">Vishishta Lagna &mdash; Special Ascendants</div>
         <span class="sec-skt">&#2357;&#2367;&#2358;&#2367;&#2359;&#2381;&#2335; &#2354;&#2327;&#2381;&#2344; &middot; BPHS Chapter 17</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Doctrine:</strong>
    Special Lagnas reveal hidden dimensions — Hora Lagna governs wealth,
    Ghati Lagna governs power, Bhava Lagna confirms the birth Lagna,
    and Varnada Lagna indicates longevity and life-force trajectory.
  </div>
  <div class="info-grid" style="grid-template-columns:repeat(2,1fr);">
    {cards}
  </div>
</div>"""


def _html_avasthas(avasthas: dict) -> str:
    """Section 14 — Baladi Avasthas (Planetary States)."""
    rows = ""
    avastha_colour = {
        "Yuva": "#00E676", "Kumara": "#FFD700", "Bala": "#FF9800",
        "Vriddha": "#FF7043", "Mrita": "#FF1744",
    }
    for p_name in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]:
        av = avasthas.get(p_name)
        if not av:
            continue
        col = avastha_colour.get(av["avastha"], "#FFD700")
        rows += f"""<tr>
          <td style="color:{_planet_colour(p_name)};font-weight:600;">{p_name}</td>
          <td>{av['sign']}</td>
          <td>{av['degree_in_sign']}&deg;</td>
          <td style="color:{col};font-weight:700;">{av['avastha']}</td>
          <td style="color:{col};">{av['delivery']}</td>
          <td style="font-size:12px;">{av['description']}</td>
        </tr>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">AVASTHAS</span>
    <div><div class="sec-title">Baladi Avastha &mdash; Planetary States</div>
         <span class="sec-skt">&#2348;&#2366;&#2354;&#2366;&#2342;&#2367; &#2309;&#2357;&#2360;&#2381;&#2341;&#2366; &middot; BPHS Chapter 45</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Doctrine:</strong>
    A planet's Avastha determines what percentage of its promised results it can deliver.
    Yuva (prime) delivers 100%; Bala/Mrita deliver 0&ndash;25%. This modifies all other readings.
  </div>
  <table class="planet-table">
    <tr><th>PLANET</th><th>SIGN</th><th>DEGREE</th><th>AVASTHA</th><th>DELIVERY</th><th>INTERPRETATION</th></tr>
    {rows}
  </table>
</div>"""


def _html_shadbala(shadbala: dict) -> str:
    """Section 9 — Shadbala & Isht/Kasht strength."""
    rows = ""
    for p_name in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
        sb = shadbala.get(p_name)
        if not sb:
            continue
        cat_col = {"Exceptionally Strong": "#00E676", "Strong": "#69F0AE",
                   "Moderate": "#FFD700", "Weak": "#FF7043", "Very Weak": "#FF1744"
                   }.get(sb["category"], "#FFD700")
        retro = " &#8634;" if sb["retrograde"] else ""
        rows += f"""<tr>
          <td style="color:{_planet_colour(p_name)};font-weight:600;">
            {p_name}{retro} <span style="font-size:10px;color:rgba(255,255,255,.4);">#{sb.get('rank','')}</span></td>
          <td>{sb['sthana_bala']}</td><td>{sb['dig_bala']}</td>
          <td>{sb['naisargika_bala']}</td><td>{sb['chesta_bala']}</td>
          <td style="font-weight:700;">{sb['total']}</td>
          <td style="color:{cat_col};">{sb['category']}</td>
          <td style="color:#69F0AE;">{sb['isht']}</td>
          <td style="color:#FF7043;">{sb['kasht']}</td>
        </tr>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">SHADBALA</span>
    <div><div class="sec-title">Shadbala &mdash; Sixfold Planetary Strength</div>
         <span class="sec-skt">&#2359;&#2337;&#2381;&#2348;&#2354; &middot; Isht &amp; Kasht Phala &middot; BPHS Chapter 27</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Doctrine:</strong>
    Shadbala quantifies a planet's capacity to deliver results. Isht Phala = benefic delivery capacity;
    Kasht Phala = harmful delivery capacity. Higher total = stronger planet in the chart.
  </div>
  <table class="planet-table" style="font-size:12.5px;">
    <tr><th>PLANET</th><th>STHANA</th><th>DIG</th><th>NAISARGIKA</th><th>CHESTA</th>
        <th>TOTAL</th><th>CATEGORY</th><th>ISHT</th><th>KASHT</th></tr>
    {rows}
  </table>
</div>"""


def _html_karakas(karakas: dict) -> str:
    """Section 11 — Chara Karakas (Soul to Spouse significators)."""
    cards = ""
    karaka_icons = {
        "Atmakaraka": "&#9728;", "Amatyakaraka": "&#9878;",
        "Bhratrikaraka": "&#9876;", "Matrikaraka": "&#127968;",
        "Pitrikaraka": "&#128081;", "Putrakaraka": "&#127891;",
        "Gnatikaraka": "&#128101;", "Darakaraka": "&#128141;",
    }
    for kname in ["Atmakaraka", "Amatyakaraka", "Bhratrikaraka", "Matrikaraka",
                  "Pitrikaraka", "Putrakaraka", "Gnatikaraka", "Darakaraka"]:
        k = karakas.get(kname)
        if not k:
            continue
        icon = karaka_icons.get(kname, "&#9733;")
        cards += f"""
      <div class="yoga-card" style="padding:18px;">
        <div style="font-size:18px;margin-bottom:4px;">{icon}</div>
        <div class="yname" style="font-size:14px;">{kname}</div>
        <div class="ytype">{k.get('meaning','')}</div>
        <div class="yform">{k['planet']} in {k['sign']} ({k['degree_in_sign']}&deg;)</div>
        <div class="ytext" style="font-size:12.5px;">{k.get('interpretation','')}</div>
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">KARAKAS</span>
    <div><div class="sec-title">Chara Karaka &mdash; Soul &amp; Destiny Significators</div>
         <span class="sec-skt">&#2330;&#2352; &#2325;&#2366;&#2352;&#2325; &middot; Jaimini Sutra &middot; BPHS Chapter 32</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Doctrine:</strong>
    Chara Karakas rank planets by degree within their sign. The highest-degree planet
    becomes Atmakaraka (soul significator) — the king of the chart whose sign in the
    Navamsha (D9) reveals the deepest karmic lessons.
  </div>
  <div class="yoga-grid" style="grid-template-columns:repeat(2,1fr);">
    {cards}
  </div>
</div>"""


def _html_drishti(drishti: dict, planet_map: Dict[str, dict], lagna_sign_idx: int) -> str:
    """Section 8 — Drishti Analysis (Graha + Rashi aspects)."""
    graha = drishti.get("graha", {})
    houses_aspected = drishti.get("houses_aspected", {})

    # Build per-house aspect summary
    house_rows = ""
    for h in range(1, 13):
        planets = houses_aspected.get(h, [])
        if not planets:
            house_rows += f"""<tr>
              <td style="color:var(--gold);font-weight:600;">H{h}</td>
              <td colspan="2" style="color:rgba(255,255,255,.4);">No aspects received</td>
            </tr>"""
        else:
            p_tags = " ".join(
                f'<span class="ptag" style="color:{_planet_colour(p)};">{p}</span>'
                for p in planets
            )
            ben = sum(1 for p in planets if p in ("Jupiter", "Venus", "Mercury", "Moon"))
            mal = sum(1 for p in planets if p in ("Saturn", "Mars", "Rahu", "Ketu", "Sun"))
            quality = "Benefic influence dominates" if ben > mal else \
                      "Malefic influence dominates" if mal > ben else "Mixed influence"
            house_rows += f"""<tr>
              <td style="color:var(--gold);font-weight:600;">H{h}</td>
              <td><div class="planet-tags">{p_tags}</div></td>
              <td style="font-size:12px;">{quality}</td>
            </tr>"""

    # Special aspects detail
    special_cards = ""
    for p_name in ["Mars", "Jupiter", "Saturn", "Rahu"]:
        if p_name not in graha:
            continue
        aspects = graha[p_name]
        targets = ", ".join(f"H{a['house']} ({a['label']})" for a in aspects)
        special_cards += f"""
      <div class="ic" style="padding:12px;">
        <span class="ic-l">{p_name} ASPECTS</span>
        <span class="ic-v" style="font-size:12px;">{targets}</span>
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">DRISHTI</span>
    <div><div class="sec-title">Drishti Vishleshan &mdash; Aspect Analysis</div>
         <span class="sec-skt">&#2342;&#2371;&#2359;&#2381;&#2335;&#2367; &#2357;&#2367;&#2358;&#2381;&#2354;&#2375;&#2359;&#2339; &middot; Graha &amp; Rashi Drishti</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Doctrine:</strong>
    All planets cast a 7th-house aspect. Mars, Jupiter, Saturn, and the Nodes cast
    additional special aspects. These aspects create the web of planetary influence
    that governs interactions between life areas.
  </div>
  <div class="info-grid" style="grid-template-columns:repeat(2,1fr);margin-bottom:20px;">
    {special_cards}
  </div>
  <table class="planet-table">
    <tr><th>HOUSE</th><th>ASPECTED BY</th><th>NET INFLUENCE</th></tr>
    {house_rows}
  </table>
</div>"""


def _html_aragala(aragala: dict) -> str:
    """Section 10 — Aragala (Intervention / Obstruction)."""
    rows = ""
    verdict_col = {"Supported": "#00E676", "Obstructed": "#FF7043",
                   "Mixed": "#FFD700", "Neutral": "rgba(250,246,238,.5)"}
    for h in range(1, 13):
        ar = aragala.get(h, aragala.get(str(h), {}))
        if not ar:
            continue
        v = ar.get("verdict", "Neutral")
        sup = ", ".join(f"{p[0]} ({p[1]})" for p in ar.get("supporters", []))
        blk = ", ".join(f"{p[0]} ({p[1]})" for p in ar.get("blockers", []))
        rows += f"""<tr>
          <td style="color:var(--gold);font-weight:600;">H{h}</td>
          <td style="font-size:12px;">{sup or '—'}</td>
          <td style="font-size:12px;">{blk or '—'}</td>
          <td style="color:{verdict_col.get(v, '#FFD700')};font-weight:600;">{v}</td>
        </tr>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">ARAGALA</span>
    <div><div class="sec-title">Aragala &mdash; Intervention &amp; Obstruction</div>
         <span class="sec-skt">&#2309;&#2352;&#2381;&#2327;&#2354;&#2366; &middot; BPHS Chapter 31</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Doctrine:</strong>
    Aragala identifies which planets support or block each house's outcomes.
    Planets in the 2nd, 4th, and 11th from a house create intervention (support);
    planets in the 3rd, 10th, and 12th create obstruction.
  </div>
  <table class="planet-table" style="font-size:12.5px;">
    <tr><th>HOUSE</th><th>SUPPORT (ARAGALA)</th><th>OBSTRUCTION (VIRODHA)</th><th>VERDICT</th></tr>
    {rows}
  </table>
</div>"""


def _html_vargas(vargas: dict) -> str:
    """Section 5 — Shodasha Varga (Divisional Charts)."""
    # Key charts to display with descriptions
    chart_info = {
        "D9":  ("Navamsha", "Marriage, inner nature, dharmic strength — the soul chart"),
        "D10": ("Dashamsha", "Career, profession, public action, and social contribution"),
        "D3":  ("Drekkana", "Siblings, courage, and vitality"),
        "D7":  ("Saptamsha", "Children, progeny, and creative legacy"),
        "D12": ("Dwadashamsha", "Parents and ancestral lineage"),
        "D2":  ("Hora", "Wealth polarity — Leo (solar) or Cancer (lunar) accumulation"),
        "D16": ("Shodashamsha", "Vehicles, comforts, and luxury"),
        "D20": ("Vimsamsha", "Spiritual practice and upasana"),
        "D24": ("Chaturvimsamsha", "Education, learning, and academic achievement"),
        "D27": ("Nakshatramsha", "Physical strength and vitality"),
        "D30": ("Trimsamsha", "Misfortune, disease, and hidden challenges"),
    }

    tables = ""
    for chart_key in ["D9", "D10", "D3", "D7", "D12", "D2", "D16", "D20", "D24", "D27", "D30"]:
        chart_data = vargas.get(chart_key, {})
        if not chart_data:
            continue
        cname, cdesc = chart_info.get(chart_key, (chart_key, ""))
        cells = ""
        for body in ["Lagna", "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]:
            sign = chart_data.get(body, "")
            if sign:
                cells += f'<td style="font-size:12px;">{sign}</td>'
            else:
                cells += '<td style="color:rgba(255,255,255,.3);">—</td>'

        tables += f"""
      <div class="house-block" style="padding:16px 20px;margin-bottom:14px;">
        <div class="house-hd" style="margin-bottom:8px;">
          <span class="house-name" style="font-size:15px;">{chart_key} — {cname}</span>
          <span class="house-sign" style="font-size:11px;">{cdesc}</span>
        </div>
        <table class="planet-table" style="font-size:12px;margin:4px 0;">
          <tr><th>LAGNA</th><th>SUN</th><th>MOON</th><th>MARS</th><th>MERC</th>
              <th>JUP</th><th>VEN</th><th>SAT</th><th>RAHU</th><th>KETU</th></tr>
          <tr>{cells}</tr>
        </table>
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">DIVISIONAL CHARTS</span>
    <div><div class="sec-title">Shodasha Varga &mdash; Divisional Chart Analysis</div>
         <span class="sec-skt">&#2359;&#2379;&#2337;&#2358; &#2357;&#2352;&#2381;&#2327; &middot; BPHS Chapters 6&ndash;7</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Doctrine:</strong>
    Divisional charts reveal specific life dimensions. The D9 Navamsha is the soul chart —
    a planet strong in both D1 and D9 delivers its full promise. D10 governs career;
    D7 governs children; D3 governs siblings and courage.
  </div>
  {tables}
</div>"""


def _html_longevity_maraka(data: dict) -> str:
    """Section 13 — Longevity & Maraka Grahas."""
    cat = data.get("longevity_category", "Unknown")
    desc = data.get("longevity_description", "")
    basis = data.get("basis", {})
    marakas = data.get("maraka_grahas", [])

    basis_text = (
        f"Lagna Lord <strong>{basis.get('lagna_lord','')}</strong> in {basis.get('lagna_lord_sign','')}, "
        f"8th Lord <strong>{basis.get('eighth_lord','')}</strong> in {basis.get('eighth_lord_sign','')}, "
        f"Moon in {basis.get('moon_sign','')}"
    )

    maraka_rows = ""
    for m in marakas:
        maraka_rows += f"""<tr>
          <td style="color:{_planet_colour(m['planet'])};font-weight:600;">{m['planet']}</td>
          <td style="font-size:12.5px;">{m['reason']}</td>
          <td style="font-size:12px;color:#FF7043;">{m['danger_period']}</td>
        </tr>"""

    cat_col = "#00E676" if "Long" in cat else "#FFD700" if "Medium" in cat else "#FF7043"

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">LONGEVITY</span>
    <div><div class="sec-title">Ayurdaya &mdash; Longevity &amp; Maraka Analysis</div>
         <span class="sec-skt">&#2310;&#2351;&#2369;&#2352;&#2381;&#2342;&#2366;&#2351; &middot; BPHS Chapter 44</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="summary-banner" style="text-align:left;padding:22px 28px;">
    <h3 style="font-size:18px;">Longevity Assessment:
      <span style="color:{cat_col};">{cat}</span></h3>
    <p style="font-size:14px;text-align:left;">{desc}</p>
    <div style="margin-top:10px;font-size:13px;color:rgba(250,246,238,.7);">
      Basis: {basis_text}</div>
  </div>
  <div style="margin-top:20px;">
    <div class="vl">MARAKA GRAHAS — HEALTH-CRITICAL PERIODS</div>
    <table class="planet-table">
      <tr><th>PLANET</th><th>REASON</th><th>DANGER PERIOD</th></tr>
      {maraka_rows}
    </table>
  </div>
</div>"""


def _html_karmic(planet_map: Dict[str, dict], lagna_sign_idx: int,
                 house_lord_map: Dict[int, str]) -> str:
    """Section 18 — Karmic Indications (Rahu/Ketu axis + 12th house)."""
    # Rahu/Ketu axis
    rahu_house = ketu_house = 0
    rahu_sign = ketu_sign = ""
    if "Rahu" in planet_map:
        r_lon = planet_map["Rahu"].get("longitude", 0.0)
        r_si = int(r_lon / 30) % 12
        rahu_house = ((r_si - lagna_sign_idx) % 12) + 1
        rahu_sign = SIGN_NAMES[r_si]
    if "Ketu" in planet_map:
        k_lon = planet_map["Ketu"].get("longitude", 0.0)
        k_si = int(k_lon / 30) % 12
        ketu_house = ((k_si - lagna_sign_idx) % 12) + 1
        ketu_sign = SIGN_NAMES[k_si]

    rahu_text = ""
    if rahu_house:
        rahu_text = (
            f"<strong>Rahu</strong> in House {rahu_house} ({rahu_sign}) — the north node "
            f"indicates the area of karmic desire and worldly ambition. "
            f"The native is drawn toward the significations of the {rahu_house}th house "
            f"with an insatiable drive. Over-attachment here creates bondage; "
            f"conscious engagement creates extraordinary growth."
        )

    ketu_text = ""
    if ketu_house:
        ketu_text = (
            f"<strong>Ketu</strong> in House {ketu_house} ({ketu_sign}) — the south node "
            f"indicates past-life mastery. The native has already achieved in this domain "
            f"and may feel detached from its worldly rewards. This house area serves as "
            f"a source of spiritual wisdom rather than material accumulation."
        )

    # 12th house — past karma
    lord_12 = house_lord_map.get(12, "")
    lord_12_sign = ""
    lord_12_house = 12
    if lord_12 in planet_map:
        l12_lon = planet_map[lord_12].get("longitude", 0.0)
        l12_si = int(l12_lon / 30) % 12
        lord_12_house = ((l12_si - lagna_sign_idx) % 12) + 1
        lord_12_sign = SIGN_NAMES[l12_si]

    vyaya_text = (
        f"The 12th lord <strong>{lord_12}</strong> placed in House {lord_12_house} "
        f"({'(' + lord_12_sign + ')' if lord_12_sign else ''}) — "
        f"this placement governs past-life karmic residue, losses that serve as lessons, "
        f"and the native's relationship with moksha (liberation). "
        f"{'In a Kendra, the 12th lord redirects loss into visible transformation.' if lord_12_house in {1,4,7,10} else ''}"
        f"{'In a Trikona, losses ultimately feed dharmic growth.' if lord_12_house in {1,5,9} else ''}"
        f"{'In a Dusthana, Viparita Yoga may convert adversity into hidden advantage.' if lord_12_house in {6,8,12} else ''}"
    )

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">KARMA</span>
    <div><div class="sec-title">Karmic Indications &mdash; Past-Life Residue &amp; Soul Direction</div>
         <span class="sec-skt">&#2325;&#2352;&#2381;&#2350; &#2357;&#2367;&#2330;&#2366;&#2352; &middot; Rahu-Ketu Axis &middot; Vyaya Bhava</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Doctrine:</strong>
    The Rahu-Ketu axis reveals the soul's karmic trajectory — where it has been (Ketu)
    and where it is headed (Rahu). The 12th house governs past-life debts,
    spiritual aspiration, and the mechanism of karmic release.
  </div>
  <div class="house-block" style="margin-top:18px;">
    <div class="house-hd"><span class="house-name">Rahu-Ketu Axis</span></div>
    <div class="house-text">
      {'<p>' + rahu_text + '</p>' if rahu_text else ''}
      {'<p>' + ketu_text + '</p>' if ketu_text else ''}
    </div>
  </div>
  <div class="house-block">
    <div class="house-hd"><span class="house-name">Vyaya Bhava (12th House) — Karmic Release</span></div>
    <div class="house-text"><p>{vyaya_text}</p></div>
  </div>
</div>"""


def _html_footer(name: str) -> str:
    return f"""
<div class="footer">
  <div style="font-size:15px;margin-bottom:6px;">&#2384; &#2344;&#2350;&#2379; &#2349;&#2327;&#2357;&#2340;&#2375; &#2357;&#2366;&#2360;&#2369;&#2342;&#2375;&#2357;&#2366;&#2351;</div>
  {name} &middot; Vedic Consultation &middot; Generated {datetime.now().strftime("%B %Y")}<br/>
  Cross-referenced: BPHS (Girish Chand Sharma &amp; Maharishi Parashara editions)
  &middot; lord_effects.json &middot; house_chapters.json<br/><br/>
  <em>Jyotish illuminates tendencies and potentials. Free will, effort, and dharmic choices
  remain the ultimate determinants of life's expression.</em>
</div>"""


def _month_name(m: int) -> str:
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    try:
        return months[int(m) - 1]
    except (IndexError, ValueError, TypeError):
        return ""
