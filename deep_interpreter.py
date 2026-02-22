"""
Deep Vedic Astrology Interpretation Engine
==========================================
Cross-references classical BPHS texts (lord_effects.json, house_chapters.json),
planetary dignities, yoga detection, nakshatra analysis, and Vimshottari Dasha
to produce a comprehensive, consultation-quality HTML report.

Cross-referenced sources:
  - Brihat Parasara Hora Shastra (Girish Chand Sharma & Maharishi Parashara eds.)
  - lord_effects.json  — BPHS slokas for lord-in-house placements
  - house_chapters.json — BPHS chapter summaries for each house
  - interpretations.py  — classical planet-in-house text layer
  - bphs_engine.py      — existing BPHS sloka engine

Author: Vedic Astrology Deep Engine
"""

import os
import json
import math
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any

logger = logging.getLogger("vedic.deep")

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

    # Yogas
    yogas = detect_yogas(positions, lagna_sign_idx, house_lord_map)

    # House interpretations
    house_interps = generate_house_interpretations(
        positions, lagna_sign_idx, house_lord_map, planet_map
    )

    # Nakshatra rising (for lagna)
    lagna_lon = asc.get("longitude", 0)
    lagna_nak = get_nakshatra(lagna_lon)

    # Moon nakshatra
    moon_nak = nakshatra_info if nakshatra_info else get_nakshatra(moon_longitude)

    # ── HTML Assembly ─────────────────────────────────────────────────────────

    html_parts = [_html_head(name)]
    html_parts.append(_html_cover(name, dob, tob, city, country,
                                   lagna_sign, lagna_skt, lagna_lord,
                                   lagna_nak, moon_nak, yogas, active_dasha))
    html_parts.append('<div class="page">')
    html_parts.append(_html_planet_table(positions, lagna_sign_idx, house_lord_map))
    html_parts.append(_html_yogas_section(yogas))
    html_parts.append(_html_houses_section(house_interps))
    html_parts.append(_html_dasha_section(dasha_timeline, active_dasha, birth_dt))
    html_parts.append(_html_nakshatra_section(lagna_nak, moon_nak, planet_map))
    if ashtakvarga:
        html_parts.append(_html_ashtakvarga(ashtakvarga))
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
  <div class="cover-sup">Brihat Parasara Hora Shastra &middot; Classical Vedic Consultation</div>
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
    BPHS Cross-Referenced &middot; Lahiri Ayanamsa &middot; Generated {datetime.now().strftime("%B %Y")}
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
        cls = "yoga-card pancha" if y.get("category") == "Pancha Mahapurusha" else "yoga-card"
        strength_color = {"Very Strong": "#FFD700", "Strong": "#69F0AE", "Moderate": "var(--gold)"}.get(
            y.get("strength", ""), "var(--gold)")
        cards += f"""
      <div class="{cls}">
        <div class="yname">{y["name"]}</div>
        <div class="ytype">{y.get("category","Yoga")}</div>
        <div class="yform">{y.get("planet","")} &middot; House {y.get("house","")}</div>
        <div style="font-size:11px;color:{strength_color};margin-bottom:8px;">
          Strength: {y.get("strength","")}</div>
        <div class="ytext">{y.get("description","")}</div>
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">YOGAS</span>
    <div><div class="sec-title">Graha Yogas &mdash; Planetary Power Combinations</div>
         <span class="sec-skt">Pancha Mahapurusha &middot; Raja Yoga &middot; Dhana Yoga</span></div>
    <div class="sec-line"></div>
  </div>
  <div class="callout">
    <strong style="color:var(--gold);">Yoga Summary:</strong>
    {len(yogas)} significant yoga(s) detected in this chart, including
    {sum(1 for y in yogas if y.get("category")=="Pancha Mahapurusha")} Pancha Mahapurusha Yoga(s).
    These represent the chart's primary power concentrations.
  </div>
  <div class="yoga-grid">{cards}</div>
</div>"""


def _html_houses_section(house_interps: List[dict]) -> str:
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
      </div>"""

    return f"""
<div class="section">
  <div class="sec-hd">
    <span class="sec-tag">HOUSES</span>
    <div><div class="sec-title">Bhava Vishleshan &mdash; All 12 Houses</div>
         <span class="sec-skt">&#2349;&#2366;&#2357; &#2357;&#2367;&#2358;&#2381;&#2354;&#2375;&#2359;&#2339;</span></div>
    <div class="sec-line"></div>
  </div>
  {blocks}
</div>"""


def _lord_verdict(planet: str, own_house: int, placed_house: int, dignity: str) -> str:
    """Generate a brief verdict for a lord's placement."""
    if placed_house in KENDRA_HOUSES:
        pos = "a Kendra (angular house) — strong and fully expressed."
    elif placed_house in TRIKONA_HOUSES:
        pos = "a Trikona (trine) — auspicious and dharmic."
    elif placed_house in DUSTHANA_HOUSES:
        pos = "a Dusthana (difficult house) — challenges but potential for Viparita Yoga."
    else:
        pos = "a neutral house."

    dig_note = {
        "Exalted":     "The planet is exalted — maximum strength and grace.",
        "Own Sign":    "The planet is in own sign — fully comfortable and expressive.",
        "Friendly":    "In a friendly sign — positive and supportive.",
        "Enemy Sign":  "In an enemy sign — some tension; results require effort.",
        "Debilitated": "Debilitated — significant challenges; Neecha Bhanga if applicable.",
        "Neutral":     "In a neutral sign — moderate results.",
    }.get(dignity, "")

    return f"Placed in {pos} {dig_note} This connects the {own_house}th house themes to the {placed_house}th house arena."


def _html_dasha_section(timeline: List[dict], active: Optional[dict], birth_dt: datetime) -> str:
    rows = ""
    now = datetime.now()
    for period in timeline:
        is_current = period["start"] <= now <= period["end"]
        cls = "dasha-row current" if is_current else "dasha-row"
        cur = '<span class="cur-badge">CURRENT</span>' if is_current else ""
        pc = _planet_colour(period["planet"])
        start_str = period["start"].strftime("%b %Y")
        end_str = period["end"].strftime("%b %Y")
        rows += f"""
      <div class="{cls}">
        <div class="dp-col">
          <div class="dp-name" style="color:{pc};">{period["planet"]}</div>
          <div class="dp-yr">{DASHA_YEARS[period["planet"]]} yrs</div>
        </div>
        <div class="dd-col">
          <div class="dd-range">{start_str} &rarr; {end_str} {cur}</div>
          <div class="dd-text">{_dasha_brief(period["planet"])}</div>
        </div>
      </div>"""

    active_block = ""
    if active:
        active_block = f"""
      <div class="callout pos" style="margin-top:24px;">
        <strong style="color:#00C864;">Active Mahadasha: {active["planet"]}</strong>
        ({active["start"].strftime("%b %Y")} &ndash; {active["end"].strftime("%b %Y")})<br/>
        {_dasha_brief(active["planet"])}
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
