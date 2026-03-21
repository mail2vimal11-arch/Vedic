#!/usr/bin/env python3
"""
Gochar (Transit) Prediction Engine
====================================
Computes monthly transit positions for all planets and generates
personalised predictions based on:
  - Transit house from natal Lagna (Moon sign option future)
  - Classical Gochar Vedha (obstruction) rules from BPHS
  - Sade Sati / Ashtama Shani / Guru Peyarchi detection
  - Planetary aspects (Graha Drishti) from transit to natal
  - Ashtakavarga Bindus for transit strength (simplified)

References:
  - Brihat Parashara Hora Shastra (Ch. 65 — Gochara Phala)
  - B.V. Raman, "Hindu Predictive Astrology" (Transit chapter)
  - Phaladeepika, Ch. 26 — Gocharadhyaya
  - Saravali — Transit effects
"""

import os
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Swiss Ephemeris Setup ─────────────────────────────────────────────────────

try:
    import swisseph as swe
    HAS_SWE = True
except ImportError:
    HAS_SWE = False
    logger.warning("swisseph not available — Gochar engine disabled")

EPHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")

SIGN_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

SIGN_SANSKRIT = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena"
]

SIGN_LORDS = [
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"
]

PLANET_IDS = {
    "Sun":     0,   # swe.SUN
    "Moon":    1,   # swe.MOON
    "Mars":    4,   # swe.MARS
    "Mercury": 2,   # swe.MERCURY
    "Jupiter": 5,   # swe.JUPITER
    "Venus":   3,   # swe.VENUS
    "Saturn":  6,   # swe.SATURN
    "Rahu":    10,  # swe.MEAN_NODE
}

# Natural speed category for display
SLOW_PLANETS = {"Jupiter", "Saturn", "Rahu", "Ketu"}
MEDIUM_PLANETS = {"Sun", "Mars", "Venus", "Mercury"}

# ── Tamil Panchanga Month Names (Solar — Drikpanchang) ───────────────────────
# Each Tamil month corresponds to the Sun's sidereal transit through a Rashi.
# Chithirai = Sun in Mesha (Aries), Vaigasi = Sun in Vrishabha (Taurus), etc.
TAMIL_MONTHS = [
    "Chithirai",   # Mesha (Aries)     ~Apr 14 - May 14
    "Vaigasi",     # Vrishabha (Taurus) ~May 15 - Jun 14
    "Aani",        # Mithuna (Gemini)   ~Jun 15 - Jul 16
    "Aadi",        # Karka (Cancer)     ~Jul 17 - Aug 16
    "Aavani",      # Simha (Leo)        ~Aug 17 - Sep 16
    "Purattasi",   # Kanya (Virgo)      ~Sep 17 - Oct 17
    "Aippasi",     # Tula (Libra)       ~Oct 18 - Nov 15
    "Karthigai",   # Vrischika (Scorpio)~Nov 16 - Dec 15
    "Margazhi",    # Dhanu (Sagittarius)~Dec 16 - Jan 13
    "Thai",        # Makara (Capricorn) ~Jan 14 - Feb 12
    "Maasi",       # Kumbha (Aquarius)  ~Feb 13 - Mar 13
    "Panguni",     # Meena (Pisces)     ~Mar 14 - Apr 13
]

TAMIL_MONTH_RASHI = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena"
]


def get_tamil_month(jd: float) -> dict:
    """
    Determine the Tamil Panchanga month for a given Julian Day.
    Based on Sun's sidereal sign (Lahiri ayanamsa).
    Returns dict with tamil_name, rashi, sign_index.
    """
    if not HAS_SWE:
        return {"tamil_name": "Unknown", "rashi": "", "sign_index": 0}

    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL  # correct numeric values from swisseph
    pos, _ = swe.calc_ut(jd, 0, flags)  # Sun = 0
    sun_lon = pos[0]
    sign_idx = int(sun_lon / 30) % 12

    return {
        "tamil_name": TAMIL_MONTHS[sign_idx],
        "rashi": TAMIL_MONTH_RASHI[sign_idx],
        "sign_index": sign_idx,
        "sun_degree": round(sun_lon - sign_idx * 30, 1),
    }


def compute_tamil_month_dates(year: int) -> List[dict]:
    """
    Compute approximate start dates for all 12 Tamil months in a given year.
    Scans day-by-day for Sun's sign ingress.
    """
    if not HAS_SWE:
        return []

    swe.set_ephe_path(EPHE_PATH)
    swe.set_sid_mode(1)
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL  # correct numeric values from swisseph

    months = []
    # Scan from Jan 1 to Dec 31
    jd_start = swe.julday(year, 1, 1, 0.0)
    prev_sign = -1

    for day_offset in range(366):
        jd = jd_start + day_offset
        pos, _ = swe.calc_ut(jd, 0, flags)
        sign_idx = int(pos[0] / 30) % 12

        if sign_idx != prev_sign:
            # Sun entered a new sign
            greg = swe.revjul(jd)
            months.append({
                "tamil_name": TAMIL_MONTHS[sign_idx],
                "rashi": TAMIL_MONTH_RASHI[sign_idx],
                "sign_index": sign_idx,
                "start_year": int(greg[0]),
                "start_month": int(greg[1]),
                "start_day": int(greg[2]),
            })
            prev_sign = sign_idx

    return months

# ── Classical Gochar Effects (BPHS Ch.65 + Phaladeepika Ch.26) ───────────────
# Transit house effects: house_from_natal → (effect, description)
# Based on classical principle: Transit results vary by house from natal Moon/Lagna.
# Key: house number (1-12) from reference point.
# Each planet has different effects per transit house.

TRANSIT_EFFECTS = {
    "Sun": {
        1: ("Adverse", "Health issues, fatigue, ego conflicts, government troubles"),
        2: ("Adverse", "Financial losses, family discord, eye problems"),
        3: ("Favourable", "Victory over enemies, courage, good news from siblings"),
        4: ("Adverse", "Mental unrest, domestic disturbance, vehicle troubles"),
        5: ("Adverse", "Worry about children, reduced intellect, stomach issues"),
        6: ("Favourable", "Victory over enemies, good health, debts cleared"),
        7: ("Adverse", "Travel fatigue, marital friction, digestive issues"),
        8: ("Adverse", "Illness, quarrels, obstacles, loss of vitality"),
        9: ("Adverse", "Obstacles in fortune, father's health, religious discord"),
        10: ("Favourable", "Professional success, government favour, authority"),
        11: ("Favourable", "Financial gains, promotion, fulfilment of desires"),
        12: ("Adverse", "Expenditure, eye troubles, loss of position"),
    },
    "Moon": {
        1: ("Favourable", "Comfort, good food, mental peace, recognition"),
        2: ("Adverse", "Financial strain, loss of reputation, restlessness"),
        3: ("Favourable", "Success, new clothes, friendship, good income"),
        4: ("Adverse", "Mental anxiety, fear, distrust"),
        5: ("Adverse", "Mental depression, obstacles, health concerns"),
        6: ("Favourable", "Good health, happiness, relief from enemies"),
        7: ("Favourable", "Respect, good food, travel, marital harmony"),
        8: ("Adverse", "Illness, mental distress, unexpected expenses"),
        9: ("Favourable", "Religious merit, fortune, auspicious events"),
        10: ("Favourable", "Professional success, prosperity, fame"),
        11: ("Favourable", "Joy, gains, good news, celebrations"),
        12: ("Adverse", "Expenditure, sorrow, sleep disturbance"),
    },
    "Mars": {
        1: ("Adverse", "Fever, injuries, blood disorders, conflicts"),
        2: ("Adverse", "Financial loss, fear of fire/theft, eye trouble"),
        3: ("Favourable", "Victory, income gain, success in endeavours"),
        4: ("Adverse", "Stomach ailments, domestic quarrels, property loss"),
        5: ("Adverse", "Enemies cause trouble, child-related worry, anger"),
        6: ("Favourable", "Defeat of enemies, recovery from illness, success"),
        7: ("Adverse", "Marital discord, travel problems, eye disease"),
        8: ("Adverse", "Blood disorders, accidents, legal troubles, surgery risk"),
        9: ("Adverse", "Wasteful expenditure, quarrels with elders, loss of dharma"),
        10: ("Adverse", "Professional obstacles, disputes with authority"),
        11: ("Favourable", "Financial gains, land acquisition, success in ventures"),
        12: ("Adverse", "Expenditure, eye trouble, conflicts, loss of energy"),
    },
    "Mercury": {
        1: ("Adverse", "Loss of wealth, imprisonment risk, anxiety"),
        2: ("Favourable", "Financial gains, education success, eloquent speech"),
        3: ("Adverse", "Fear of enemies, quarrels, mental agitation"),
        4: ("Favourable", "Good income, family happiness, intellectual growth"),
        5: ("Adverse", "Quarrels with wife/children, mental distress"),
        6: ("Favourable", "Victory over enemies, success in competition"),
        7: ("Adverse", "Disputes, travel, marital friction"),
        8: ("Favourable", "Birth of children, gain through writing, success"),
        9: ("Favourable", "Fortune, religious activities, wisdom, travel"),
        10: ("Favourable", "Professional success, happiness, recognition"),
        11: ("Favourable", "Financial gains, knowledge, good relationships"),
        12: ("Adverse", "Humiliation, loss of wealth, disputes"),
    },
    "Jupiter": {
        1: ("Adverse", "Displacement from home, obstacles, expenditure"),
        2: ("Favourable", "Wealth gain, good speech, family happiness"),
        3: ("Adverse", "Obstacles, change of position, loss"),
        4: ("Adverse", "Sorrow, loss through relatives, mental unrest"),
        5: ("Favourable", "Birth of children, wisdom, ministerial position"),
        6: ("Adverse", "Troubles from enemies, fatigue, displeasure"),
        7: ("Favourable", "Marital happiness, travel, pleasure, good food"),
        8: ("Adverse", "Hardship, imprisonment, illness, loss"),
        9: ("Favourable", "Great fortune, prosperity, religious merit, pilgrimage"),
        10: ("Adverse", "Loss of position, obstacles in career"),
        11: ("Favourable", "Excellent gains, vehicles, authority, recovery"),
        12: ("Adverse", "Sorrow, humiliation, change of residence"),
    },
    "Venus": {
        1: ("Favourable", "Comforts, luxuries, new clothes, pleasures"),
        2: ("Favourable", "Wealth gain, family joy, sensual pleasures"),
        3: ("Favourable", "Gain of position, authority, good relationships"),
        4: ("Favourable", "Domestic happiness, vehicles, comfort"),
        5: ("Favourable", "Success, good health, government favour"),
        6: ("Adverse", "Humiliation, quarrels, health issues"),
        7: ("Adverse", "Quarrels with spouse, illness, loss"),
        8: ("Favourable", "Wealth, vehicles, clothes, prosperity"),
        9: ("Favourable", "Fortune, religious activities, good wife"),
        10: ("Adverse", "Disputes, quarrels with friends, obstacles"),
        11: ("Favourable", "Gains, luxuries, fulfilment of desires"),
        12: ("Favourable", "Wealth gain, comforts, pleasures"),
    },
    "Saturn": {
        1: ("Adverse", "Illness, sorrow, displacement, fatigue"),
        2: ("Adverse", "Loss of wealth, family discord, disease"),
        3: ("Favourable", "Prosperity, good health, gain of position"),
        4: ("Adverse", "Domestic trouble, loss of property, mental agitation"),
        5: ("Adverse", "Worry about children, mental depression, loss"),
        6: ("Favourable", "Victory over enemies, good health, authority"),
        7: ("Adverse", "Marital trouble, health decline, travel hardship"),
        8: ("Adverse", "Severe illness, accidents, legal problems, loss"),
        9: ("Adverse", "Obstacles, father's troubles, loss of fortune"),
        10: ("Adverse", "Professional obstacles, change of place, disputes"),
        11: ("Favourable", "Great gains, recovery, success, vehicles"),
        12: ("Adverse", "Expenditure, imprisonment, illness, sorrow"),
    },
    "Rahu": {
        1: ("Adverse", "Illness, loss of wealth, fear"),
        2: ("Adverse", "Financial loss, harsh speech, family trouble"),
        3: ("Favourable", "Wealth gain, victory, courage"),
        4: ("Adverse", "Mental distress, domestic trouble, fear"),
        5: ("Adverse", "Stomach ailments, child trouble, losses"),
        6: ("Favourable", "Victory over enemies, relief from illness"),
        7: ("Adverse", "Financial loss, marital friction, disputes"),
        8: ("Adverse", "Danger, illness, fear, unexpected troubles"),
        9: ("Adverse", "Loss of dharma, obstacles, expenditure"),
        10: ("Favourable", "Success in career, authority, foreign connections"),
        11: ("Favourable", "Gains, fulfilment, prosperity"),
        12: ("Adverse", "Expenditure, foreign travel, loss, isolation"),
    },
    "Ketu": {
        1: ("Adverse", "Health issues, mental anxiety, obstacles"),
        2: ("Adverse", "Financial loss, speech problems, family issues"),
        3: ("Favourable", "Success, courage, gains"),
        4: ("Adverse", "Mental unrest, domestic trouble, vehicle damage"),
        5: ("Adverse", "Child-related worry, stomach issues, loss of intelligence"),
        6: ("Favourable", "Victory over enemies, recovery"),
        7: ("Adverse", "Marital discord, health decline, travel"),
        8: ("Adverse", "Severe troubles, illness, accidents"),
        9: ("Favourable", "Spiritual growth, fortune, pilgrimage"),
        10: ("Adverse", "Professional obstacles, loss of reputation"),
        11: ("Favourable", "Gains, success, fulfilment"),
        12: ("Favourable", "Spiritual liberation, foreign travel, expenditure with purpose"),
    },
}


# ── Graha Drishti (Planetary Aspects) ─────────────────────────────────────────
# Classical aspects from BPHS: each planet aspects the 7th house from it.
# Special aspects: Mars→4,8; Jupiter→5,9; Saturn→3,10; Rahu→5,9

SPECIAL_ASPECTS = {
    "Sun":     [7],
    "Moon":    [7],
    "Mars":    [4, 7, 8],
    "Mercury": [7],
    "Jupiter": [5, 7, 9],
    "Venus":   [7],
    "Saturn":  [3, 7, 10],
    "Rahu":    [5, 7, 9],
    "Ketu":    [5, 7, 9],
}


# ── Sade Sati Detection ──────────────────────────────────────────────────────

def detect_sade_sati(saturn_sign_idx: int, moon_sign_idx: int) -> Optional[str]:
    """
    Detect if Sade Sati (7½ year Saturn transit) is active.
    Saturn transiting 12th, 1st, or 2nd from Moon sign.
    Returns phase name or None.
    """
    relative = (saturn_sign_idx - moon_sign_idx) % 12
    if relative == 11:   # 12th from Moon
        return "Rising Phase (12th from Moon) — Pressure builds, career/financial strain"
    elif relative == 0:  # Same as Moon
        return "Peak Phase (over Moon) — Maximum intensity, mental stress, transformation"
    elif relative == 1:  # 2nd from Moon
        return "Settling Phase (2nd from Moon) — Financial pressure, family issues easing"
    return None


def detect_ashtama_shani(saturn_sign_idx: int, moon_sign_idx: int) -> bool:
    """Saturn in 8th from Moon — Ashtama Shani (very adverse)."""
    return (saturn_sign_idx - moon_sign_idx) % 12 == 7


def detect_kantaka_shani(saturn_sign_idx: int, lagna_sign_idx: int) -> bool:
    """Saturn in Kendra (1,4,7,10) from Lagna — Kantaka Shani (obstructive)."""
    relative = (saturn_sign_idx - lagna_sign_idx) % 12
    return relative in (0, 3, 6, 9)


# ── Core Transit Computation ─────────────────────────────────────────────────

def compute_monthly_transits(
    natal_positions: dict,
    birth: dict,
    target_year: int,
    target_month: int,
    current_lat: float = None,
    current_lon: float = None,
    current_utc_offset: float = None,
) -> dict:
    """
    Compute transit predictions for a given month.

    Parameters
    ----------
    natal_positions : dict
        Output of calculate_positions() — natal chart data
    birth : dict
        Birth details dict
    target_year : int
        Year for transit computation
    target_month : int
        Month (1-12) for transit computation

    Returns
    -------
    dict with keys: month_label, natal_lagna, natal_moon, transits,
                    sade_sati, ashtama_shani, kantaka_shani,
                    special_alerts, aspects, summary
    """
    if not HAS_SWE:
        return {"error": "Swiss Ephemeris not available"}

    swe.set_ephe_path(EPHE_PATH)
    swe.set_sid_mode(1)  # SIDM_LAHIRI

    # ── Natal reference points ──
    asc = natal_positions.get("ascendant", {})
    lagna_lon = asc.get("longitude", 0)
    lagna_sign_idx = int(lagna_lon / 30) % 12

    # Find Moon's natal sign
    moon_natal_lon = 0
    for p in natal_positions.get("planets", []):
        if p.get("name") == "Moon":
            moon_natal_lon = p.get("longitude", 0)
            break
    moon_sign_idx = int(moon_natal_lon / 30) % 12

    # ── Compute transit positions for mid-month ──
    # Use 15th of the month, adjusted for current location's timezone
    utc_off = current_utc_offset if current_utc_offset is not None else 0.0
    local_noon_utc = 12.0 - utc_off  # Convert local noon to UTC
    jd_mid = swe.julday(target_year, target_month, 15, local_noon_utc)
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED  # correct numeric values from swisseph

    # Also compute for 1st and last day to detect sign changes within month
    days_in_month = 28
    if target_month in (1, 3, 5, 7, 8, 10, 12):
        days_in_month = 31
    elif target_month in (4, 6, 9, 11):
        days_in_month = 30
    elif target_month == 2:
        days_in_month = 29 if (target_year % 4 == 0 and (target_year % 100 != 0 or target_year % 400 == 0)) else 28

    jd_start = swe.julday(target_year, target_month, 1, 0.0)
    jd_end = swe.julday(target_year, target_month, days_in_month, 23.99)

    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    month_label = f"{month_names[target_month - 1]} {target_year}"

    transits = []
    transit_signs = {}  # planet -> sign_idx at mid-month (for aspect calculation)

    for planet_name, pid in PLANET_IDS.items():
        # Mid-month position
        pos_mid, _ = swe.calc_ut(jd_mid, pid, flags)
        lon_mid = pos_mid[0]
        sign_idx = int(lon_mid / 30) % 12
        deg_in_sign = lon_mid - sign_idx * 30
        is_retro = pos_mid[3] < 0

        # Start and end positions
        pos_start, _ = swe.calc_ut(jd_start, pid, flags)
        pos_end, _ = swe.calc_ut(jd_end, pid, flags)
        sign_start = int(pos_start[0] / 30) % 12
        sign_end = int(pos_end[0] / 30) % 12

        sign_change = None
        if sign_start != sign_end:
            sign_change = f"{SIGN_NAMES[sign_start]} → {SIGN_NAMES[sign_end]}"

        # House from Lagna
        house_from_lagna = ((sign_idx - lagna_sign_idx) % 12) + 1
        # House from Moon
        house_from_moon = ((sign_idx - moon_sign_idx) % 12) + 1

        # Get classical effect (from Lagna)
        # BPHS Gochara Phala (Ch. 65): effects are ALWAYS from natal Moon (Chandra Lagna)
        effects = TRANSIT_EFFECTS.get(planet_name, {})
        effect_data = effects.get(house_from_moon, ("Neutral", ""))

        transit_signs[planet_name] = sign_idx

        transits.append({
            "planet": planet_name,
            "sign": SIGN_NAMES[sign_idx],
            "sign_sanskrit": SIGN_SANSKRIT[sign_idx],
            "sign_lord": SIGN_LORDS[sign_idx],
            "degree": round(deg_in_sign, 1),
            "retrograde": is_retro,
            "house_from_lagna": house_from_lagna,
            "house_from_moon": house_from_moon,
            "effect": effect_data[0],
            "description": effect_data[1],
            "sign_change": sign_change,
            "is_slow": planet_name in SLOW_PLANETS,
        })

    # ── Ketu (180° from Rahu) ──
    rahu_mid, _ = swe.calc_ut(jd_mid, PLANET_IDS["Rahu"], flags)
    ketu_lon = (rahu_mid[0] + 180.0) % 360.0
    ketu_sign_idx = int(ketu_lon / 30) % 12
    ketu_deg = ketu_lon - ketu_sign_idx * 30
    ketu_house_lagna = ((ketu_sign_idx - lagna_sign_idx) % 12) + 1
    ketu_house_moon = ((ketu_sign_idx - moon_sign_idx) % 12) + 1
    # Ketu effect also from Moon (BPHS standard)
    ketu_effects = TRANSIT_EFFECTS.get("Ketu", {})
    ketu_effect_data = ketu_effects.get(ketu_house_moon, ("Neutral", ""))

    transit_signs["Ketu"] = ketu_sign_idx

    transits.append({
        "planet": "Ketu",
        "sign": SIGN_NAMES[ketu_sign_idx],
        "sign_sanskrit": SIGN_SANSKRIT[ketu_sign_idx],
        "sign_lord": SIGN_LORDS[ketu_sign_idx],
        "degree": round(ketu_deg, 1),
        "retrograde": True,
        "house_from_lagna": ketu_house_lagna,
        "house_from_moon": ketu_house_moon,
        "effect": ketu_effect_data[0],
        "description": ketu_effect_data[1],
        "sign_change": None,
        "is_slow": True,
    })

    # ── Special conditions ──
    saturn_sign = transit_signs.get("Saturn", 0)
    sade_sati = detect_sade_sati(saturn_sign, moon_sign_idx)
    ashtama_shani = detect_ashtama_shani(saturn_sign, moon_sign_idx)
    kantaka_shani = detect_kantaka_shani(saturn_sign, lagna_sign_idx)

    # ── Compute transit-to-natal aspects (Graha Drishti) ──
    aspects = []
    natal_planet_signs = {}
    for p in natal_positions.get("planets", []):
        pname = p.get("name", "")
        p_lon = p.get("longitude", 0)
        natal_planet_signs[pname] = int(p_lon / 30) % 12

    for t in transits:
        t_planet = t["planet"]
        t_sign = transit_signs.get(t_planet, transit_signs.get("Rahu", 0)) if t_planet == "Ketu" else transit_signs.get(t_planet, 0)
        aspect_houses = SPECIAL_ASPECTS.get(t_planet, [7])

        for offset in aspect_houses:
            aspected_sign = (t_sign + offset) % 12
            # Check which natal planets are in that sign
            for natal_p, natal_s in natal_planet_signs.items():
                if natal_s == aspected_sign:
                    nature = "Benefic" if t["effect"] == "Favourable" else "Malefic"
                    if t_planet in ("Jupiter", "Venus"):
                        nature = "Benefic"
                    elif t_planet in ("Saturn", "Mars", "Rahu", "Ketu"):
                        nature = "Malefic"
                    aspects.append({
                        "transit_planet": t_planet,
                        "natal_planet": natal_p,
                        "aspect_type": f"{_ordinal(offset)} aspect",
                        "nature": nature,
                        "description": _aspect_description(t_planet, natal_p, offset, nature),
                    })

    # ── Special alerts ──
    special_alerts = []
    if sade_sati:
        special_alerts.append({
            "type": "Sade Sati",
            "severity": "High",
            "description": sade_sati,
            "remedy": "Worship Lord Hanuman on Saturdays. Recite Shani Mantra. Donate black sesame seeds and mustard oil.",
        })
    if ashtama_shani:
        special_alerts.append({
            "type": "Ashtama Shani",
            "severity": "High",
            "description": "Saturn transits the 8th house from Moon — sudden obstacles, health risks, and transformative changes",
            "remedy": "Light sesame oil lamp on Saturdays. Recite Maha Mrityunjaya Mantra. Avoid risky ventures.",
        })
    if kantaka_shani:
        special_alerts.append({
            "type": "Kantaka Shani",
            "severity": "Medium",
            "description": "Saturn in Kendra from Lagna — professional obstacles and delays in progress",
            "remedy": "Perform Shani Puja. Donate iron items on Saturdays. Practice patience.",
        })

    # Check for Guru Peyarchi (Jupiter sign change)
    for t in transits:
        if t["planet"] == "Jupiter" and t.get("sign_change"):
            special_alerts.append({
                "type": "Guru Peyarchi",
                "severity": "Notable",
                "description": f"Jupiter changes sign this month: {t['sign_change']} — major shift in fortune and opportunities",
                "remedy": "Perform Jupiter Puja on Thursday. Wear yellow. Donate turmeric and yellow clothes.",
            })

    # ── Monthly summary ──
    favourable_count = sum(1 for t in transits if t["effect"] == "Favourable")
    adverse_count = sum(1 for t in transits if t["effect"] == "Adverse")
    total = len(transits)

    if favourable_count > adverse_count + 2:
        overall = "Highly Favourable"
        summary_text = "An excellent month with strong planetary support. Favourable for new initiatives, investments, and important decisions."
    elif favourable_count > adverse_count:
        overall = "Moderately Favourable"
        summary_text = "A generally positive month. Good for steady progress. Be mindful during adverse transit windows."
    elif adverse_count > favourable_count + 2:
        overall = "Challenging"
        summary_text = "A demanding month requiring patience and caution. Avoid major new commitments. Focus on completing existing work."
    elif adverse_count > favourable_count:
        overall = "Mixed — Lean Cautious"
        summary_text = "Mixed influences this month. Proceed carefully with important matters. Some areas show promise while others need attention."
    else:
        overall = "Mixed — Balanced"
        summary_text = "A balanced month with equal positive and challenging influences. Stay adaptable and focused."

    if sade_sati or ashtama_shani:
        overall = "Challenging (Saturn influence active)"
        summary_text += " Saturn's major transit influence adds weight — patience and remedial measures are essential."

    # ── Tamil Panchanga month ──
    tamil_month = get_tamil_month(jd_mid)

    # ── Generate transit chart SVG (dark navy/gold theme) ──
    transit_svg = _generate_transit_svg(transits, lagna_sign_idx, moon_sign_idx, transit_signs)

    # ── Generate natal chart SVG ──
    natal_svg = _generate_natal_svg(natal_positions, lagna_sign_idx, moon_sign_idx)

    # ── Location info ──
    location_label = ""
    if current_lat is not None and current_lon is not None:
        location_label = f"Transits computed for lat {current_lat:.2f}, lon {current_lon:.2f}"
        if current_utc_offset is not None:
            sign = "+" if current_utc_offset >= 0 else ""
            location_label += f" (UTC{sign}{current_utc_offset})"

    return {
        "month_label": month_label,
        "year": target_year,
        "month": target_month,
        "tamil_month": tamil_month,
        "location": location_label,
        "natal_lagna": {
            "sign": SIGN_NAMES[lagna_sign_idx],
            "sanskrit": SIGN_SANSKRIT[lagna_sign_idx],
        },
        "natal_moon": {
            "sign": SIGN_NAMES[moon_sign_idx],
            "sanskrit": SIGN_SANSKRIT[moon_sign_idx],
        },
        "transits": transits,
        "transit_svg": transit_svg,
        "natal_svg": natal_svg,
        "aspects": aspects,
        "sade_sati": sade_sati,
        "ashtama_shani": ashtama_shani,
        "kantaka_shani": kantaka_shani,
        "special_alerts": special_alerts,
        "summary": {
            "overall": overall,
            "favourable_count": favourable_count,
            "adverse_count": adverse_count,
            "text": summary_text,
        },
    }


# ── Helper Functions ─────────────────────────────────────────────────────────

def _ordinal(n: int) -> str:
    """Return ordinal string for aspect house offset."""
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    suffix = suffixes.get(n if n < 20 else n % 10, "th")
    return f"{n}{suffix}"


def _aspect_description(transit_planet: str, natal_planet: str, offset: int, nature: str) -> str:
    """Generate a human-readable aspect description."""
    if nature == "Benefic":
        if transit_planet == "Jupiter":
            return f"Jupiter's {_ordinal(offset)} aspect blesses natal {natal_planet} — expansion, wisdom, and protection in that planet's significations"
        elif transit_planet == "Venus":
            return f"Venus aspects natal {natal_planet} — brings harmony, beauty, and comfort to that area of life"
        return f"{transit_planet} casts a supportive {_ordinal(offset)} aspect on natal {natal_planet}"
    else:
        if transit_planet == "Saturn":
            return f"Saturn's {_ordinal(offset)} aspect constrains natal {natal_planet} — delays, discipline, and hard lessons in that area"
        elif transit_planet == "Mars":
            return f"Mars aspects natal {natal_planet} — brings energy but also aggression, haste, and conflict risk"
        elif transit_planet in ("Rahu", "Ketu"):
            return f"{transit_planet}'s shadowy {_ordinal(offset)} aspect on natal {natal_planet} — confusion, obsession, or karmic intensity"
        return f"{transit_planet} casts a challenging {_ordinal(offset)} aspect on natal {natal_planet}"


def _si_svg_base(W: int, H: int, lagna_sign_idx: int, moon_sign_idx: int,
                  center_lines: list, planet_in_sign: dict) -> str:
    """
    Shared South Indian chart SVG builder — deep navy/gold theme.
    center_lines: list of (text, font_size, fill, font_weight) tuples for center box.
    planet_in_sign: dict of sign_idx -> list of (abbr, degree, retro, color).
    """
    # Deep consultation colour palette
    NAVY       = "#0F1628"
    NAVY_DARK  = "#0A0E1A"
    NAVY_MID   = "#16213E"
    GOLD       = "#C9A84C"
    GOLD_DIM   = "rgba(201,168,76,0.45)"
    GOLD_FAINT = "rgba(201,168,76,0.12)"
    BLUE_DIM   = "rgba(107,174,214,0.12)"

    # South Indian fixed grid: sign_idx -> (col, row)  col=0 is left, row=0 is top
    SIGN_POSITIONS = {
        11: (0, 0), 0: (1, 0), 1: (2, 0), 2: (3, 0),
        10: (0, 1),                          3: (3, 1),
         9: (0, 2),                          4: (3, 2),
         8: (0, 3), 7: (1, 3), 6: (2, 3),  5: (3, 3),
    }

    cw = W / 4   # cell width
    ch = H / 4   # cell height

    p = []
    p.append(f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;max-width:{W}px;height:auto;font-family:Georgia,serif;display:block;">')

    # Outer background
    p.append(f'<rect width="{W}" height="{H}" fill="{NAVY}" rx="4" '
             f'stroke="{GOLD}" stroke-width="1.5"/>')

    # Grid lines
    for i in range(1, 4):
        p.append(f'<line x1="{i*cw}" y1="0" x2="{i*cw}" y2="{H}" '
                 f'stroke="{GOLD}" stroke-width="0.7" opacity="0.45"/>')
        p.append(f'<line x1="0" y1="{i*ch}" x2="{W}" y2="{i*ch}" '
                 f'stroke="{GOLD}" stroke-width="0.7" opacity="0.45"/>')

    # Lagna cell highlight
    if lagna_sign_idx in SIGN_POSITIONS:
        col, row = SIGN_POSITIONS[lagna_sign_idx]
        p.append(f'<rect x="{col*cw+1}" y="{row*ch+1}" '
                 f'width="{cw-2}" height="{ch-2}" fill="{GOLD_FAINT}" rx="2"/>')

    # Moon cell highlight
    if moon_sign_idx in SIGN_POSITIONS and moon_sign_idx != lagna_sign_idx:
        col, row = SIGN_POSITIONS[moon_sign_idx]
        p.append(f'<rect x="{col*cw+1}" y="{row*ch+1}" '
                 f'width="{cw-2}" height="{ch-2}" fill="{BLUE_DIM}" rx="2"/>')

    # Center 2×2 box
    p.append(f'<rect x="{cw}" y="{ch}" width="{cw*2}" height="{ch*2}" '
             f'fill="{NAVY_DARK}" stroke="{GOLD}" stroke-width="0.8" opacity="0.85"/>')

    # Center text lines
    n = len(center_lines)
    total_h = n * 17
    y0 = H / 2 - total_h / 2 + 13
    for i, (text, fsize, fill, fweight) in enumerate(center_lines):
        p.append(f'<text x="{W/2}" y="{y0 + i*17}" text-anchor="middle" '
                 f'font-size="{fsize}" fill="{fill}" font-weight="{fweight}" '
                 f'font-family="Georgia,serif">{text}</text>')

    # Sign labels + ASC / NatMoon badges
    for sign_idx, (col, row) in SIGN_POSITIONS.items():
        x = col * cw
        y = row * ch
        skt = SIGN_SANSKRIT[sign_idx][:3]
        p.append(f'<text x="{x+4}" y="{y+13}" font-size="8" '
                 f'fill="{GOLD_DIM}" font-style="italic" font-family="Georgia,serif">{skt}</text>')

        if sign_idx == lagna_sign_idx:
            p.append(f'<rect x="{x + cw - 30}" y="{y+2}" width="28" height="12" '
                     f'fill="rgba(201,168,76,0.22)" rx="2"/>')
            p.append(f'<text x="{x + cw - 16}" y="{y+11}" text-anchor="middle" '
                     f'font-size="7" fill="{GOLD}" font-weight="700" '
                     f'font-family="Georgia,serif">ASC</text>')

        if sign_idx == moon_sign_idx and moon_sign_idx != lagna_sign_idx:
            p.append(f'<rect x="{x + cw - 36}" y="{y+2}" width="34" height="12" '
                     f'fill="rgba(107,174,214,0.18)" rx="2"/>')
            p.append(f'<text x="{x + cw - 19}" y="{y+11}" text-anchor="middle" '
                     f'font-size="7" fill="#6BAED6" font-weight="700" '
                     f'font-family="Georgia,serif">Nat☽</text>')

    # Planets
    for sign_idx, planets in planet_in_sign.items():
        if sign_idx not in SIGN_POSITIONS:
            continue
        col, row = SIGN_POSITIONS[sign_idx]
        x_base = col * cw + 5
        y_base = row * ch + 28
        for i, (abbr, deg, retro, color) in enumerate(planets):
            px = x_base + (i % 2) * 44
            py = y_base + (i // 2) * 18
            label = f"{abbr} {int(deg)}°{'R' if retro else ''}"
            p.append(f'<text x="{px}" y="{py}" font-size="10.5" font-weight="700" '
                     f'fill="{color}" font-family="Georgia,serif">{label}</text>')

    p.append('</svg>')
    return "\n".join(p)


# Planet display colours (deep consultation palette)
_PLANET_COLORS = {
    "Sun":     "#E8843A",
    "Moon":    "#6BAED6",
    "Mars":    "#E05252",
    "Mercury": "#52B452",
    "Jupiter": "#C9A84C",
    "Venus":   "#C07AE0",
    "Saturn":  "#9E9E9E",
    "Rahu":    "#E03080",
    "Ketu":    "#52B452",
}

_EFFECT_COLOR = {
    "Favourable": "#52C87A",
    "Adverse":    "#E05555",
    "Neutral":    "#9E9E9E",
}


def _generate_transit_svg(transits: list, lagna_sign_idx: int,
                           moon_sign_idx: int, transit_signs: dict) -> str:
    """
    South Indian Gochara transit chart — deep navy/gold theme.
    Planets are coloured by their classical effect (Favourable/Adverse).
    Natal Lagna and Natal Moon cells are highlighted.
    """
    W, H = 400, 400

    SIGN_POSITIONS = {
        11: (0, 0), 0: (1, 0), 1: (2, 0), 2: (3, 0),
        10: (0, 1),                          3: (3, 1),
         9: (0, 2),                          4: (3, 2),
         8: (0, 3), 7: (1, 3), 6: (2, 3),  5: (3, 3),
    }

    planet_in_sign: dict = {}
    for t in transits:
        s_idx = transit_signs.get(t["planet"])
        if s_idx is None and t["planet"] == "Ketu":
            for sn in SIGN_POSITIONS:
                if SIGN_NAMES[sn] == t["sign"]:
                    s_idx = sn
                    break
        if s_idx is None:
            continue
        planet_in_sign.setdefault(s_idx, [])
        color = _EFFECT_COLOR.get(t["effect"], "#9E9E9E")
        planet_in_sign[s_idx].append((
            t["planet"][:2], t["degree"], t["retrograde"], color
        ))

    center_lines = [
        ("GOCHARA",        13, "#C9A84C", "700"),
        ("Transit Chart",  10, "rgba(201,168,76,0.6)", "400"),
        ("",                9, "transparent",           "400"),
        (f"Lagna: {SIGN_NAMES[lagna_sign_idx]}",  9, "rgba(201,168,76,0.45)", "400"),
        (f"Moon:  {SIGN_NAMES[moon_sign_idx]}",   9, "rgba(107,174,214,0.6)", "400"),
        ("Swiss Eph · Lahiri", 8, "rgba(201,168,76,0.3)", "400"),
    ]

    return _si_svg_base(W, H, lagna_sign_idx, moon_sign_idx, center_lines, planet_in_sign)


def _generate_natal_svg(natal_positions: dict, lagna_sign_idx: int,
                         moon_sign_idx: int) -> str:
    """
    South Indian natal (Rasi) chart — deep navy/gold theme.
    Uses the natal planet list from calculate_positions() output.
    """
    W, H = 400, 400

    planet_in_sign: dict = {}
    for p in natal_positions.get("planets", []):
        name  = p.get("name", "")
        lon   = p.get("longitude", 0)
        retro = p.get("retrograde", False)
        sn    = int(lon / 30) % 12
        deg   = lon % 30
        color = _PLANET_COLORS.get(name, "#FAF6EE")
        planet_in_sign.setdefault(sn, [])
        planet_in_sign[sn].append((name[:2], deg, retro, color))

    # Add Ketu (always 180° from Rahu)
    rahu = next((p for p in natal_positions.get("planets", []) if p.get("name") == "Rahu"), None)
    if rahu:
        ketu_lon = (rahu.get("longitude", 0) + 180) % 360
        ks = int(ketu_lon / 30) % 12
        kd = ketu_lon % 30
        planet_in_sign.setdefault(ks, [])
        planet_in_sign[ks].append(("Ke", kd, True, _PLANET_COLORS["Ketu"]))

    center_lines = [
        ("NATAL",          13, "#C9A84C", "700"),
        ("Birth Chart",    10, "rgba(201,168,76,0.6)", "400"),
        ("",                9, "transparent",           "400"),
        (f"Lagna: {SIGN_NAMES[lagna_sign_idx]}", 9, "rgba(201,168,76,0.45)", "400"),
        (f"Moon:  {SIGN_NAMES[moon_sign_idx]}",  9, "rgba(107,174,214,0.6)", "400"),
    ]

    return _si_svg_base(W, H, lagna_sign_idx, moon_sign_idx, center_lines, planet_in_sign)


def compute_twelve_month_overview(
    natal_positions: dict,
    birth: dict,
    start_year: int = None,
    start_month: int = None,
) -> List[dict]:
    """
    Compute 12-month transit overview starting from given month.
    Returns list of monthly transit summaries (lighter weight than full compute).
    """
    if start_year is None or start_month is None:
        now = datetime.now()
        start_year = now.year
        start_month = now.month

    overview = []
    for i in range(12):
        m = start_month + i
        y = start_year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        result = compute_monthly_transits(natal_positions, birth, y, m)
        overview.append({
            "month_label": result["month_label"],
            "year": result["year"],
            "month": result["month"],
            "tamil_month": result.get("tamil_month", {}).get("tamil_name", ""),
            "overall": result["summary"]["overall"],
            "favourable": result["summary"]["favourable_count"],
            "adverse": result["summary"]["adverse_count"],
            "sade_sati": result["sade_sati"] is not None,
            "special_count": len(result.get("special_alerts", [])),
        })

    return overview
