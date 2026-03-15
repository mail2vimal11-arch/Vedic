"""
Varshaphal (Annual / Progressed Horoscope) Engine
===================================================
Based on: "Varshaphal or The Hindu Progressed Horoscope"
          by B.V. Raman, Raman Publications, 2nd Edition 1947

Implements the Tajaka system of annual horoscopy:
  1. Compute the exact Solar Return moment (Sun returns to birth longitude)
  2. Erect the Annual (Progressed) chart for that moment at the birth place
  3. Determine Varsheshwara (Lord of the Year) via 5 applicants
  4. Compute Muntha and its lord
  5. Compute Sahams (sensitive points): Punya, Guru, Kirthi, Mitra, Raja, etc.
  6. Detect Tajaka Yogas: Ishkavala, Induvara, Ithasala, Easarapha, etc.
  7. Compute Varsha Dasa (annual dasa periods based on Krisamsas)
  8. Interpret house results from annual chart per BPHS/Tajaka rules
  9. Generate South Indian chart SVG for the annual chart

References: Chapters I–XII and Appendix I–II of the source text.
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("vedic.varshaphal")

try:
    import swisseph as swe
    HAS_SWE = True
except ImportError:
    HAS_SWE = False
    logger.warning("swisseph not available — Varshaphal engine disabled")

import os
EPHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")

# ── Constants ─────────────────────────────────────────────────────────────────

RASHI_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
RASHI_SANSKRIT = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena",
]
RASHI_LORDS = [
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter",
]

PLANET_IDS = {
    "Sun": swe.SUN if HAS_SWE else 0,
    "Moon": swe.MOON if HAS_SWE else 1,
    "Mars": swe.MARS if HAS_SWE else 4,
    "Mercury": swe.MERCURY if HAS_SWE else 2,
    "Jupiter": swe.JUPITER if HAS_SWE else 5,
    "Venus": swe.VENUS if HAS_SWE else 3,
    "Saturn": swe.SATURN if HAS_SWE else 6,
    "Rahu": swe.MEAN_NODE if HAS_SWE else 10,
}

# Two-letter abbreviations for chart rendering
PLANET_ABBR = {
    "Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me",
    "Jupiter": "Ju", "Venus": "Ve", "Saturn": "Sa",
    "Rahu": "Ra", "Ketu": "Ke",
}

# Tajaka planetary friendships (Art. 12, Ch. III)
# In Tajaka: Sun, Moon, Mars, Jupiter are friends of each other
# Mercury, Venus, Saturn, Rahu have same friends as enemies
# Different from Parashari friendships
TAJAKA_FRIENDS = {
    "Sun":     ["Moon", "Mars", "Jupiter"],
    "Moon":    ["Sun", "Mercury"],
    "Mars":    ["Sun", "Moon", "Jupiter"],
    "Mercury": ["Moon", "Mars", "Jupiter", "Venus", "Saturn"],
    "Jupiter": ["Sun", "Moon", "Mars"],
    "Venus":   ["Mercury", "Saturn"],
    "Saturn":  ["Mercury", "Venus"],
    "Rahu":    ["Mercury", "Venus", "Saturn"],
}
TAJAKA_ENEMIES = {
    "Sun":     ["Mercury", "Venus", "Saturn", "Rahu"],
    "Moon":    ["Mars", "Jupiter", "Venus", "Saturn", "Rahu"],
    "Mars":    ["Mercury", "Venus", "Saturn", "Rahu"],
    "Mercury": ["Sun", "Rahu"],
    "Jupiter": ["Mercury", "Venus", "Saturn", "Rahu"],
    "Venus":   ["Sun", "Moon", "Mars", "Jupiter"],
    "Saturn":  ["Sun", "Moon", "Mars", "Jupiter"],
    "Rahu":    ["Sun", "Moon", "Mars", "Jupiter"],
}

# ── Aspects in Tajaka (Art. 13) ───────────────────────────────────────────────
# Tajaka aspects differ from Parashari:
# Friendly aspect: Trine (5,9) and Sextile (3,11)
# Inimical aspect: Square (4,10) and Opposition (7)
# No aspect: 2, 6, 8, 12

# ── Tajaka Strength: Pancha-vargeeya Bala (Art. 40) ──────────────────────────
# Five kinds of divisional strengths:
# Kshetrabala (sign), Ochchabala (exaltation), Haddabala,
# Drekkhanabala, Navamsabala
# Sum / 4 => if above 10: powerful, 5-10 ordinary, below 5 weak, above 15 very strong

# Exaltation degrees (for Ochchabala calculation, Art. 34)
EXALTATION_DEG = {
    "Sun": 10.0,       # Aries 10°
    "Moon": 33.0,      # Taurus 3°
    "Mars": 298.0,     # Capricorn 28°
    "Mercury": 165.0,  # Virgo 15°
    "Jupiter": 95.0,   # Cancer 5°
    "Venus": 357.0,    # Pisces 27°
    "Saturn": 200.0,   # Libra 20°
    "Rahu": 50.0,      # Taurus 20°
}

# Moolatrikona signs
MOOLATRIKONA = {
    "Sun": 4,       # Leo
    "Moon": 3,      # Cancer (first 3°)
    "Mars": 0,      # Aries
    "Mercury": 5,   # Virgo
    "Jupiter": 8,   # Sagittarius
    "Venus": 6,     # Libra
    "Saturn": 10,   # Aquarius
}

# Own signs
OWN_SIGNS = {
    "Sun": [4],
    "Moon": [3],
    "Mars": [0, 7],
    "Mercury": [2, 5],
    "Jupiter": [8, 11],
    "Venus": [1, 6],
    "Saturn": [9, 10],
    "Rahu": [10],
    "Ketu": [7],
}

# Lord of Thririasis (Trirasi) — DAY and NIGHT rulers (Art. 46, Ch. IV)
# For day births: rulers of signs in groups of 3 starting from Aries
# For night births: different set
TRIRASI_DAY = {
    # Sign index → Trirasi lord
    0: "Sun", 1: "Sun", 2: "Sun",      # Aries-Gemini
    3: "Venus", 4: "Venus", 5: "Venus", # Cancer-Virgo
    6: "Saturn", 7: "Saturn", 8: "Saturn", # Libra-Sagittarius
    9: "Jupiter", 10: "Jupiter", 11: "Jupiter", # Capricorn-Pisces
}
TRIRASI_NIGHT = {
    0: "Jupiter", 1: "Jupiter", 2: "Jupiter",
    3: "Moon", 4: "Moon", 5: "Moon",
    6: "Mercury", 7: "Mercury", 8: "Mercury",
    9: "Mars", 10: "Mars", 11: "Mars",
}

# ── Varsha Dasa planet periods (365.25 days proportional) ─────────────────────
# Each planet gets Dasa proportional to its Krisamsas (degrees remaining in sign)

# Results of Varsha Dasas (Ch. X, Art. 98-105)
VARSHA_DASA_RESULTS = {
    "Sun": {
        "strong": "Honour, wealth, and prestige. Governmental favour, respect from authorities.",
        "ordinary": "Moderate success, some recognition. Average health and vitality.",
        "weak": "Troubles from authorities, health issues, humiliation. Eye problems possible.",
    },
    "Moon": {
        "strong": "Mental happiness, gain of wealth, good relations. Acquisition of clothes and ornaments.",
        "ordinary": "Moderate peace of mind. Some gains through trade and commerce.",
        "weak": "Mental anguish, quarrels with relatives, loss through water-related issues.",
    },
    "Mars": {
        "strong": "Victory over enemies, gain of property, courage and valour. Fresh appointments.",
        "ordinary": "Moderate energy, some opposition. Mixed results in ventures.",
        "weak": "Trouble from enemies, blood-related diseases, accidents. Surgical intervention possible.",
    },
    "Mercury": {
        "strong": "Fame in mathematics and sciences, intellectual success. Acquisition of friends.",
        "ordinary": "Average intellectual pursuits, moderate gains through education.",
        "weak": "Nervous disorders, unfounded fears. Loss through friends and misunderstandings.",
    },
    "Jupiter": {
        "strong": "Religious fervour, charitable disposition, birth of a child. Great fortune.",
        "ordinary": "Moderate fortune, some religious inclination. Pilgrimage possible.",
        "weak": "Loss of wealth, disappointment from children. Family conflicts.",
    },
    "Venus": {
        "strong": "Luxurious living, gain of vehicles, happiness from spouse. Artistic success.",
        "ordinary": "Moderate comforts, average marital happiness.",
        "weak": "Quarrels with spouse or partner, symptoms of venereal troubles. Loss of comforts.",
    },
    "Saturn": {
        "strong": "Wealth through foreign effort, high political acts of charity and generosity.",
        "ordinary": "Hard work with moderate results. Slow but steady progress.",
        "weak": "Grief, suffering, disappointments. Misunderstanding among relatives. Mental unrest.",
    },
    "Rahu": {
        "strong": "Gains through unconventional means, foreign connections. Sudden windfalls.",
        "ordinary": "Mixed results, some confusion. Average progress in ventures.",
        "weak": "Troubles from hidden enemies, snake fear, poisoning. Sudden reverses.",
    },
    "Ketu": {
        "strong": "Spiritual advancement, occult knowledge. Liberation from bondage.",
        "ordinary": "Some spiritual inclination, moderate detachment.",
        "weak": "Loss of position, troubles from mysterious causes. Skin diseases.",
    },
}

# Results of Bhavas in Annual Chart (Ch. IX, Art. 86-97)
ANNUAL_BHAVA_RESULTS = {
    1: "First Bhava — Body, colour, caste, character, life, happiness and age. "
       "If the lord is strong and well-aspected, the native will be happy and prosperous.",
    2: "Second Bhava — Wealth, general happiness. If Jupiter aspects the second house, "
       "the native will have much wealth during the year.",
    3: "Third Bhava — Brothers, servants, and valour. Lord with 8th lord "
       "indicates loss of a brother.",
    4: "Fourth Bhava — Father's money, conveyances, mother. Powerful Sun causes "
       "prosperity to the father. Powerful Moon produces results for the mother.",
    5: "Fifth Bhava — Children, general education. Saturn in the fifth produces "
       "heterodoxical tendencies. If Putra Saham is in house 5, birth of a child predicted.",
    6: "Sixth Bhava — Debts, diseases, enemies. Evil Sahams in sixth cause "
       "unfavourable results. The native suffers from several diseases.",
    7: "Seventh Bhava — Husband/wife, trade, loss, domestic harmony. Conjugal happiness "
       "or disputes predicted from this Bhava.",
    8: "Eighth Bhava — Longevity, death, fighting, lost articles. Annual lord in 8th "
       "with evil conjunctions indicates troubles from fires and poisons.",
    9: "Ninth Bhava — Religion, travels, father and intelligence. If Mars is annual lord "
       "and unaspected by evil planets, remains in houses 3 or 9, results of Sukra possible.",
    10: "Tenth Bhava — Increase in paternal properties, money, professional promotions. "
        "The annual lord must be well placed for professional prosperity.",
    11: "Eleventh Bhava — Requirements of articles, gains, friends, daughters. "
        "Guru with Muntha in the first house gives income from learning.",
    12: "Twelfth Bhava — Indicates enemies, expenses, evil, loss. "
        "If Kuja or Sani is annual lord with Moon in 10th house, the native loses cattle.",
}

# Muntha results in different houses (Art. 56, Ch. VI)
MUNTHA_RESULTS = {
    1: "Few enemies, great power and success.",
    2: "Happy, honour, good earnings and happiness.",
    3: "Prosperity and good fourth — abundant earnings.",
    4: "Laziness, fifth children, wisdom, religious learning.",
    5: "Suffering, remorse, debts, diseases, and enemies — seventh unfriendly.",
    6: "Quarrels and failure. Eighth — expenses, in start places, sudden dangers.",
    7: "Ninth — fortune. Favours from superior teeth — success, elevated happiness.",
    8: "Gain as a beneficial aspect and the result is happiness.",
    9: "To houses six, seven, eight and one: an inimical aspect. The result is generally harmful.",
    10: "Favourable situation. Muntha lord in 6, 8, 12 with malefics indicates troubles.",
    11: "Gain of wealth and friends. Planets forming good aspects produce breaks and results.",
    12: "Diseases and enemies. Results vary according to the nature of aspects on Muntha.",
}

# ══════════════════════════════════════════════════════════════════════════════
#  CORE COMPUTATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _init_swe():
    """Initialise Swiss Ephemeris with Lahiri ayanamsa."""
    if not HAS_SWE:
        return
    swe.set_ephe_path(EPHE_PATH)
    swe.set_sid_mode(swe.SIDM_LAHIRI)


def _jd_from_datetime(dt: datetime, utc_offset: float = 0.0) -> float:
    """Convert datetime to Julian Day (UT)."""
    ut_hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0 - utc_offset
    return swe.julday(dt.year, dt.month, dt.day, ut_hour)


def _get_sidereal_longitude(jd: float, planet_id: int) -> float:
    """Get sidereal longitude of a planet at given JD."""
    flags = swe.FLG_SIDEREAL | swe.FLG_SPEED
    result = swe.calc_ut(jd, planet_id, flags)
    return result[0][0] % 360.0


def _get_asc_longitude(jd: float, lat: float, lon: float) -> float:
    """Get sidereal Ascendant longitude at given JD and location."""
    houses, ascs = swe.houses_ex(jd, lat, lon, b"P", swe.FLG_SIDEREAL)
    return ascs[0] % 360.0


def compute_solar_return(birth_jd: float, birth_sun_lon: float,
                         target_year: int, utc_offset: float = 0.0) -> float:
    """
    Find the exact Julian Day when the Sun returns to its birth sidereal longitude
    in the target year. This is the moment the Varshaphal chart is erected.

    Uses iterative Newton-Raphson refinement for sub-second precision.
    (Art. 9: "New Year begins when the Sun comes back to the same degree
     he occupied at the time of birth")
    """
    _init_swe()

    # Initial estimate: around the birthday in the target year
    est_jd = swe.julday(target_year, 6, 15, 12.0)  # mid-year start

    # Search in a window around birthday
    # Sun moves ~1° per day, so search ±200 days from mid-year
    best_jd = est_jd
    best_diff = 999.0

    # Coarse search: step by 1 day
    for day_offset in range(-200, 201):
        test_jd = est_jd + day_offset
        sun_lon = _get_sidereal_longitude(test_jd, swe.SUN)
        diff = abs(sun_lon - birth_sun_lon)
        if diff > 180:
            diff = 360 - diff
        if diff < best_diff:
            best_diff = diff
            best_jd = test_jd

    # Fine refinement: Newton-Raphson (Sun moves ~0.9856°/day)
    jd = best_jd
    for _ in range(20):
        sun_lon = _get_sidereal_longitude(jd, swe.SUN)
        diff = sun_lon - birth_sun_lon
        # Handle wrap-around
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360
        if abs(diff) < 0.0001:  # ~0.36 arc-seconds precision
            break
        # Sun speed ≈ 0.9856°/day
        jd -= diff / 0.9856

    return jd


def compute_annual_positions(solar_return_jd: float, lat: float, lon: float) -> dict:
    """
    Compute all planetary positions and Ascendant for the solar return moment.
    Returns dict with 'planets', 'ascendant', 'ayanamsa'.
    """
    _init_swe()

    ayanamsa = swe.get_ayanamsa_ut(solar_return_jd)

    # Ascendant
    asc_lon = _get_asc_longitude(solar_return_jd, lat, lon)
    asc_sign_idx = int(asc_lon / 30.0) % 12
    asc_deg = asc_lon % 30.0

    planets = []
    for name, pid in PLANET_IDS.items():
        lon = _get_sidereal_longitude(solar_return_jd, pid)
        sign_idx = int(lon / 30.0) % 12
        sign_deg = lon % 30.0

        # Retrograde check
        flags = swe.FLG_SIDEREAL | swe.FLG_SPEED
        result = swe.calc_ut(solar_return_jd, pid, flags)
        speed = result[0][3]
        retro = speed < 0

        house = ((sign_idx - asc_sign_idx) % 12) + 1

        planets.append({
            "name": name,
            "longitude": round(lon, 4),
            "sign_idx": sign_idx,
            "sign": RASHI_NAMES[sign_idx],
            "sign_sanskrit": RASHI_SANSKRIT[sign_idx],
            "sign_deg": round(sign_deg, 4),
            "house": house,
            "retrograde": retro,
            "lord": RASHI_LORDS[sign_idx],
        })

    # Ketu = Rahu + 180°
    rahu_data = next(p for p in planets if p["name"] == "Rahu")
    ketu_lon = (rahu_data["longitude"] + 180.0) % 360.0
    ketu_sign_idx = int(ketu_lon / 30.0) % 12
    ketu_deg = ketu_lon % 30.0
    ketu_house = ((ketu_sign_idx - asc_sign_idx) % 12) + 1
    planets.append({
        "name": "Ketu",
        "longitude": round(ketu_lon, 4),
        "sign_idx": ketu_sign_idx,
        "sign": RASHI_NAMES[ketu_sign_idx],
        "sign_sanskrit": RASHI_SANSKRIT[ketu_sign_idx],
        "sign_deg": round(ketu_deg, 4),
        "house": ketu_house,
        "retrograde": True,
        "lord": RASHI_LORDS[ketu_sign_idx],
    })

    return {
        "planets": planets,
        "ascendant": {
            "longitude": round(asc_lon, 4),
            "sign_idx": asc_sign_idx,
            "sign": RASHI_NAMES[asc_sign_idx],
            "sign_sanskrit": RASHI_SANSKRIT[asc_sign_idx],
            "sign_deg": round(asc_deg, 4),
            "lord": RASHI_LORDS[asc_sign_idx],
        },
        "ayanamsa": round(ayanamsa, 4),
        "jd": solar_return_jd,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  MUNTHA (Art. 44, Ch. IV)
# ══════════════════════════════════════════════════════════════════════════════

def compute_muntha(birth_asc_sign_idx: int, birth_year: int, target_year: int) -> dict:
    """
    Muntha — a sensitive point that moves one sign per year from birth Ascendant.
    "Add the number of the ascendant at birth to the number of years elapsed
     between birth and the current birthday." (Art. 44)

    Muntha sign = (Ascendant sign index + years elapsed) mod 12
    """
    years_elapsed = target_year - birth_year
    muntha_sign_idx = (birth_asc_sign_idx + years_elapsed) % 12
    muntha_lord = RASHI_LORDS[muntha_sign_idx]

    return {
        "sign_idx": muntha_sign_idx,
        "sign": RASHI_NAMES[muntha_sign_idx],
        "sign_sanskrit": RASHI_SANSKRIT[muntha_sign_idx],
        "lord": muntha_lord,
        "years_elapsed": years_elapsed,
    }


def muntha_house(muntha_sign_idx: int, annual_asc_sign_idx: int) -> int:
    """House of Muntha in the annual chart."""
    return ((muntha_sign_idx - annual_asc_sign_idx) % 12) + 1


# ══════════════════════════════════════════════════════════════════════════════
#  VARSHESHWARA — LORD OF THE YEAR (Art. 43-46, Ch. IV)
# ══════════════════════════════════════════════════════════════════════════════

def determine_varsheshwara(annual_positions: dict, birth_positions: dict,
                           muntha_data: dict, is_day_birth: bool) -> dict:
    """
    Determine the Lord of the Year (Varsheshwara) from 5 applicants:
      (a) Lord of the sign occupied by Sun or Moon at birth
      (b) Lord of the Ascendant in the Birth Horoscope
      (c) Lord of the Ascendant in the Progressed (Annual) Horoscope
      (d) Lord of Muntha
      (e) Lord of Thririasis (Trirasi)

    The planet that is strongest and the most dignified becomes Varsheshwara.
    (Art. 43: "The relative power of these five planets must be thoroughly
     scrutinised and the strongest declared as lord of the year")
    """
    annual_asc = annual_positions["ascendant"]
    birth_asc_sign_idx = birth_positions["ascendant"]["sign_idx"]

    # Collect all 5 applicants
    # (a) Lord of Sun's sign at birth OR Moon's sign at birth
    birth_sun = next((p for p in birth_positions["planets"] if p["name"] == "Sun"), None)
    birth_moon = next((p for p in birth_positions["planets"] if p["name"] == "Moon"), None)

    applicants = {}

    if birth_sun:
        applicants["Lord of birth Sun sign"] = RASHI_LORDS[birth_sun["sign_idx"]]
    if birth_moon:
        applicants["Lord of birth Moon sign"] = RASHI_LORDS[birth_moon["sign_idx"]]

    # (b) Lord of birth Ascendant
    applicants["Lord of birth Ascendant"] = RASHI_LORDS[birth_asc_sign_idx]

    # (c) Lord of annual Ascendant
    applicants["Lord of annual Ascendant"] = annual_asc["lord"]

    # (d) Lord of Muntha
    applicants["Lord of Muntha"] = muntha_data["lord"]

    # (e) Lord of Thririasis
    annual_asc_sign = annual_asc["sign_idx"]
    if is_day_birth:
        trirasi_lord = TRIRASI_DAY.get(annual_asc_sign, "Jupiter")
    else:
        trirasi_lord = TRIRASI_NIGHT.get(annual_asc_sign, "Moon")
    applicants["Lord of Thririasis"] = trirasi_lord

    # Score each unique planet candidate based on dignity in annual chart
    unique_planets = set(applicants.values())
    scores = {}
    for planet in unique_planets:
        p_data = next((p for p in annual_positions["planets"] if p["name"] == planet), None)
        if not p_data:
            scores[planet] = 0
            continue

        score = 0
        sign_idx = p_data["sign_idx"]

        # Kshetrabala (sign strength)
        if sign_idx in OWN_SIGNS.get(planet, []):
            score += 30  # Own sign = 30 units (Art. 33)
        elif sign_idx == MOOLATRIKONA.get(planet, -1):
            score += 25  # Moolatrikona
        # Exaltation check
        exalt_lon = EXALTATION_DEG.get(planet, -1)
        if exalt_lon >= 0:
            exalt_sign = int(exalt_lon / 30) % 12
            if sign_idx == exalt_sign:
                score += 20  # Exalted

        # House strength: Angular houses (1,4,7,10) strongest
        house = p_data["house"]
        if house in (1, 4, 7, 10):
            score += 15  # Kendra
        elif house in (5, 9):
            score += 10  # Trikona
        elif house in (2, 11):
            score += 5   # Dhana/Labha

        # Retrograde planets lose some strength
        if p_data["retrograde"] and planet not in ("Rahu", "Ketu"):
            score -= 5

        # Count how many applicant roles this planet fills
        role_count = sum(1 for v in applicants.values() if v == planet)
        score += role_count * 3  # Bonus for multiple roles

        scores[planet] = score

    # Select highest scoring planet
    varsheshwara = max(scores, key=scores.get) if scores else "Jupiter"

    return {
        "lord": varsheshwara,
        "applicants": applicants,
        "scores": scores,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SAHAMS — Sensitive Points (Ch. VII, Art. 64-76)
# ══════════════════════════════════════════════════════════════════════════════

def compute_sahams(annual_positions: dict, is_day_birth: bool) -> List[dict]:
    """
    Compute Tajaka Sahams (sensitive points) per B.V. Raman's formulas.

    Punya Saham (Art. 65):
      Day:  Moon's long - Sun's long + Ascendant
      Night: Sun's long - Moon's long + Ascendant

    Other Sahams follow similar day/night formulas (Art. 66-74).
    """
    asc_lon = annual_positions["ascendant"]["longitude"]

    def get_lon(name):
        p = next((p for p in annual_positions["planets"] if p["name"] == name), None)
        return p["longitude"] if p else 0.0

    sun_lon = get_lon("Sun")
    moon_lon = get_lon("Moon")
    mars_lon = get_lon("Mars")
    merc_lon = get_lon("Mercury")
    jup_lon = get_lon("Jupiter")
    ven_lon = get_lon("Venus")
    sat_lon = get_lon("Saturn")

    # Compute Punya Saham first — needed for other Sahams
    if is_day_birth:
        punya_lon = (moon_lon - sun_lon + asc_lon) % 360
    else:
        punya_lon = (sun_lon - moon_lon + asc_lon) % 360

    sahams = []

    def add_saham(name, lon, meaning):
        lon = lon % 360
        sign_idx = int(lon / 30) % 12
        deg = lon % 30
        lord = RASHI_LORDS[sign_idx]
        sahams.append({
            "name": name,
            "longitude": round(lon, 2),
            "sign": RASHI_NAMES[sign_idx],
            "sign_sanskrit": RASHI_SANSKRIT[sign_idx],
            "degree": round(deg, 2),
            "lord": lord,
            "meaning": meaning,
        })

    # 1. Punya Saham — Religious merit, fortune (Art. 65)
    add_saham("Punya", punya_lon,
              "Religious merit, fortune, and general prosperity")

    # 2. Guru Saham — Preceptor, knowledge (Art. 66)
    if is_day_birth:
        guru_s = moon_lon - sun_lon + asc_lon
    else:
        guru_s = sun_lon - moon_lon + asc_lon
    # Note: same as Punya for this simplified version
    # B.V. Raman: Night = Punya Saham – Guru's long
    guru_s2 = punya_lon - jup_lon + asc_lon
    add_saham("Guru", guru_s2 % 360,
              "Preceptor, higher knowledge, and spiritual guide")

    # 3. Kirthi Saham — Fame (Art. 67)
    if is_day_birth:
        kirthi = jup_lon - punya_lon + asc_lon
    else:
        kirthi = punya_lon - jup_lon + asc_lon
    add_saham("Kirthi", kirthi % 360,
              "Fame, reputation, and public recognition")

    # 4. Mitra Saham — Friends (Art. 68)
    if is_day_birth:
        mitra = moon_lon - sun_lon + asc_lon
    else:
        mitra = sun_lon - moon_lon + asc_lon
    # Simplified: Mitra = Punya Saham long + 30° (as per Raman)
    add_saham("Mitra", (punya_lon + 30) % 360,
              "Friends, allies, and benefactors")

    # 5. Raja Saham — Royalty/Authority (Art. 69)
    if is_day_birth:
        raja = sun_lon - sat_lon + asc_lon
    else:
        raja = sat_lon - sun_lon + asc_lon
    add_saham("Raja", raja % 360,
              "Authority, government favour, political success")

    # 6. Putra Saham — Children (Art. 70)
    if is_day_birth:
        putra = jup_lon - moon_lon + asc_lon
    else:
        putra = moon_lon - jup_lon + asc_lon
    add_saham("Putra", putra % 360,
              "Children, progeny, creative output")

    # 7. Jeeva Saham — Life/Vitality (Art. 71)
    if is_day_birth:
        jeeva = sat_lon - jup_lon + asc_lon
    else:
        jeeva = jup_lon - sat_lon + asc_lon
    add_saham("Jeeva", jeeva % 360,
              "Life force, vitality, and health")

    # 8. Vyapara Saham — Trade/Business (Art. 72)
    if is_day_birth:
        vyapara = moon_lon - merc_lon + asc_lon
    else:
        vyapara = merc_lon - moon_lon + asc_lon
    add_saham("Vyapara", vyapara % 360,
              "Trade, business, and commercial success")

    # 9. Vivaha Saham — Marriage (Art. 73)
    if is_day_birth:
        vivaha = ven_lon - sat_lon + asc_lon
    else:
        vivaha = sat_lon - ven_lon + asc_lon
    add_saham("Vivaha", vivaha % 360,
              "Marriage, partnerships, and conjugal happiness")

    # 10. Sarira Saham — Body/Health (Art. 74)
    if is_day_birth:
        sarira = sat_lon - mars_lon + asc_lon
    else:
        sarira = mars_lon - sat_lon + asc_lon
    add_saham("Sarira", sarira % 360,
              "Physical body, health, and constitution")

    return sahams


# ══════════════════════════════════════════════════════════════════════════════
#  TAJAKA YOGAS (Ch. VII, Art. 57-63)
# ══════════════════════════════════════════════════════════════════════════════

def detect_tajaka_yogas(annual_positions: dict) -> List[dict]:
    """
    Detect special Tajaka Yogas formed in the annual chart.

    Key Yogas from B.V. Raman (Art. 57-63):
    - Ishkavala: Planets in Kendras (1, 4, 7, 10) and Panaparas (2, 5, 8, 11)
      without any in Apoklimas (3, 6, 9, 12) — great power and success
    - Induvara: Planets only in Apoklimas — results of success but after hardship
    - Ithasala: Faster planet applying to slower planet within orb — event will happen
    - Easarapha: Separating aspect (opposite of Ithasala) — disappointments
    - Nakta Yoga: Moon applying to aspect without aspect being completed
    - Yamaya Yoga: Similar to Ithasala with retrograde involvement
    - Khallaasra: Obstruction of Ithasala by a third planet
    - Radda Yoga: Planet on retrograde or combust obstructing Ithasala
    - Duhphali Kuttha: All planets below horizon
    """
    planets = annual_positions["planets"]
    yogas = []

    # Classify planets by house type
    kendra_planets = [p["name"] for p in planets if p["house"] in (1, 4, 7, 10)]
    panapara_planets = [p["name"] for p in planets if p["house"] in (2, 5, 8, 11)]
    apoklima_planets = [p["name"] for p in planets if p["house"] in (3, 6, 9, 12)]

    # 1. ISHKAVALA YOGA (Art. 58)
    # All planets in Kendras and Panaparas, none in Apoklimas (3,6,9,12)
    main_planets = [p for p in planets if p["name"] not in ("Rahu", "Ketu")]
    main_in_apoklima = [p["name"] for p in main_planets if p["house"] in (3, 6, 9, 12)]
    if len(main_in_apoklima) == 0 and len(kendra_planets) > 0:
        yogas.append({
            "name": "Ishkavala Yoga",
            "type": "Benefic",
            "description": "All planets occupy Kendras and Panaparas without any in "
                           "Apoklimas. This produces great power, success, and fortune "
                           "during the year.",
            "planets": kendra_planets + panapara_planets,
        })

    # 2. INDUVARA YOGA (Art. 59)
    # All planets only in Apoklimas
    main_in_kendra_pan = [p["name"] for p in main_planets
                          if p["house"] in (1, 2, 4, 5, 7, 8, 10, 11)]
    if len(main_in_kendra_pan) == 0 and len(apoklima_planets) > 0:
        yogas.append({
            "name": "Induvara Yoga",
            "type": "Mixed",
            "description": "All planets in Apoklima houses. Disappointments of "
                           "undertaking, but eventually moving and dispersed interests.",
            "planets": apoklima_planets,
        })

    # 3. ITHASALA YOGA (Art. 60)
    # A faster-moving planet applying to conjunction/aspect with a slower planet
    # Check major conjunctions (planets in same sign with applying degrees)
    PLANET_SPEED_ORDER = ["Moon", "Mercury", "Venus", "Sun", "Mars", "Jupiter", "Saturn"]
    for i, fast_name in enumerate(PLANET_SPEED_ORDER[:-1]):
        fast = next((p for p in planets if p["name"] == fast_name), None)
        if not fast:
            continue
        for slow_name in PLANET_SPEED_ORDER[i+1:]:
            slow = next((p for p in planets if p["name"] == slow_name), None)
            if not slow:
                continue
            # Same sign = conjunction Ithasala
            if fast["sign_idx"] == slow["sign_idx"]:
                if fast["sign_deg"] < slow["sign_deg"]:
                    yogas.append({
                        "name": "Ithasala Yoga",
                        "type": "Benefic",
                        "description": f"{fast_name} applies to conjunction with {slow_name} "
                                       f"in {fast['sign']}. The event signified by these planets "
                                       f"will materialise during the year.",
                        "planets": [fast_name, slow_name],
                    })
            # Trine aspect (5/9 houses apart)
            house_diff = abs(fast["sign_idx"] - slow["sign_idx"]) % 12
            if house_diff in (4, 8):  # 5th/9th house = 4/8 sign difference
                yogas.append({
                    "name": "Ithasala Yoga (Trine)",
                    "type": "Benefic",
                    "description": f"{fast_name} and {slow_name} form a trine Ithasala. "
                                   f"Favourable results through the matters they signify.",
                    "planets": [fast_name, slow_name],
                })

    # 4. EASARAPHA YOGA (Art. 61)
    # Separating aspect — faster planet has already crossed the slower planet
    for i, fast_name in enumerate(PLANET_SPEED_ORDER[:-1]):
        fast = next((p for p in planets if p["name"] == fast_name), None)
        if not fast:
            continue
        for slow_name in PLANET_SPEED_ORDER[i+1:]:
            slow = next((p for p in planets if p["name"] == slow_name), None)
            if not slow:
                continue
            if fast["sign_idx"] == slow["sign_idx"] and fast["sign_deg"] > slow["sign_deg"]:
                diff = fast["sign_deg"] - slow["sign_deg"]
                if diff < 10:  # Within orb
                    yogas.append({
                        "name": "Easarapha Yoga",
                        "type": "Malefic",
                        "description": f"{fast_name} separating from {slow_name} in "
                                       f"{fast['sign']}. Disappointments and non-fulfillment "
                                       f"of expectations related to matters they signify.",
                        "planets": [fast_name, slow_name],
                    })

    # 5. KHALLAASRA YOGA (Art. 62)
    # A third planet between two forming Ithasala, obstructing it
    for yoga in list(yogas):
        if yoga["name"] == "Ithasala Yoga" and len(yoga["planets"]) == 2:
            p1 = next((p for p in planets if p["name"] == yoga["planets"][0]), None)
            p2 = next((p for p in planets if p["name"] == yoga["planets"][1]), None)
            if p1 and p2 and p1["sign_idx"] == p2["sign_idx"]:
                blockers = [p for p in planets
                            if p["sign_idx"] == p1["sign_idx"]
                            and p["name"] not in yoga["planets"]
                            and p["name"] not in ("Rahu", "Ketu")
                            and min(p1["sign_deg"], p2["sign_deg"]) < p["sign_deg"] < max(p1["sign_deg"], p2["sign_deg"])]
                for b in blockers:
                    yogas.append({
                        "name": "Khallaasra Yoga",
                        "type": "Obstructive",
                        "description": f"{b['name']} obstructs the Ithasala between "
                                       f"{yoga['planets'][0]} and {yoga['planets'][1]}. "
                                       f"The promised result faces obstacles.",
                        "planets": [b["name"]] + yoga["planets"],
                    })

    # 6. DUHPHALI KUTTHA (Art. 63)
    # All planets in houses 1-6 (below horizon in South Indian chart terms)
    below_horizon = all(p["house"] <= 6 for p in main_planets)
    if below_horizon:
        yogas.append({
            "name": "Duhphali Kuttha Yoga",
            "type": "Malefic",
            "description": "All planets below the horizon. General weakness and "
                           "lack of visibility during the year. Efforts may not "
                           "receive due recognition.",
            "planets": [p["name"] for p in main_planets],
        })

    # Check for benefics in Kendras (auspicious general yoga)
    benefics_in_kendra = [p for p in planets
                          if p["name"] in ("Jupiter", "Venus", "Mercury", "Moon")
                          and p["house"] in (1, 4, 7, 10)]
    if len(benefics_in_kendra) >= 2:
        yogas.append({
            "name": "Benefics in Kendras",
            "type": "Benefic",
            "description": f"Multiple benefics ({', '.join(p['name'] for p in benefics_in_kendra)}) "
                           f"occupy angular houses. General prosperity, good health, "
                           f"and favourable outcomes during the year.",
            "planets": [p["name"] for p in benefics_in_kendra],
        })

    # Check for malefics in Kendras (challenging)
    malefics_in_kendra = [p for p in planets
                          if p["name"] in ("Saturn", "Mars", "Rahu", "Ketu")
                          and p["house"] in (1, 4, 7, 10)]
    if len(malefics_in_kendra) >= 2:
        yogas.append({
            "name": "Malefics in Kendras",
            "type": "Malefic",
            "description": f"Multiple malefics ({', '.join(p['name'] for p in malefics_in_kendra)}) "
                           f"in angular houses. Obstacles, conflicts, and health "
                           f"concerns during the year.",
            "planets": [p["name"] for p in malefics_in_kendra],
        })

    return yogas


# ══════════════════════════════════════════════════════════════════════════════
#  VARSHA DASA (Annual Dasas) — Ch. V, Art. 48-49
# ══════════════════════════════════════════════════════════════════════════════

def compute_varsha_dasa(annual_positions: dict) -> List[dict]:
    """
    Compute Varsha Dasa (annual Dasa periods).

    Method (Art. 49): "Convert the longitudes of planets and the Ascendant
    into degrees. Reject the signs and considering the degrees etc.,
    tabulate the positions of planets and the ascendant in the ascending
    order of their number of degrees."

    Krisamsas = fractional degree in sign (sign_deg).
    The planet with smallest Krisamsas rules first.
    Duration proportional to (Krisamsas / total_of_all) * 365.25 days.
    """
    all_bodies = []

    # Ascendant entry
    asc = annual_positions["ascendant"]
    all_bodies.append({
        "name": "Lagna",
        "krisamsas": asc["sign_deg"],
        "sign": asc["sign"],
    })

    # Planets (exclude Ketu — only 8 classical planets + Lagna used)
    for p in annual_positions["planets"]:
        if p["name"] == "Ketu":
            continue
        all_bodies.append({
            "name": p["name"],
            "krisamsas": p["sign_deg"],
            "sign": p["sign"],
        })

    # Sort by krisamsas (ascending) — smallest degree first
    all_bodies.sort(key=lambda x: x["krisamsas"])

    total_krisamsas = sum(b["krisamsas"] for b in all_bodies)
    if total_krisamsas == 0:
        total_krisamsas = 1  # Safety

    dasas = []
    for body in all_bodies:
        fraction = body["krisamsas"] / total_krisamsas
        days = fraction * 365.25
        hours = (days - int(days)) * 24

        # Determine strength for result lookup
        strength = "ordinary"
        if body["name"] != "Lagna":
            p_data = next((p for p in annual_positions["planets"]
                           if p["name"] == body["name"]), None)
            if p_data:
                sign_idx = p_data["sign_idx"]
                if sign_idx in OWN_SIGNS.get(body["name"], []):
                    strength = "strong"
                elif p_data["house"] in (6, 8, 12):
                    strength = "weak"
                elif p_data["house"] in (1, 4, 7, 10):
                    strength = "strong"

        result_text = ""
        if body["name"] in VARSHA_DASA_RESULTS:
            result_text = VARSHA_DASA_RESULTS[body["name"]].get(strength, "")
        elif body["name"] == "Lagna":
            if strength == "strong":
                result_text = "Honour, prestige, and general well-being. The Lagna Dasa favours personal initiatives."
            else:
                result_text = "Ordinary personal health and moderate success in undertakings."

        dasas.append({
            "name": body["name"],
            "krisamsas": round(body["krisamsas"], 2),
            "days": int(days),
            "hours": round(hours, 1),
            "strength": strength,
            "result": result_text,
        })

    return dasas


# ══════════════════════════════════════════════════════════════════════════════
#  ANNUAL HOUSE INTERPRETATIONS (Ch. IX)
# ══════════════════════════════════════════════════════════════════════════════

def interpret_annual_houses(annual_positions: dict, muntha_data: dict,
                            varsheshwara: dict) -> List[dict]:
    """
    Generate interpretations for each of the 12 houses in the annual chart.
    Based on Ch. IX (Art. 86-97) and general Tajaka principles.
    """
    asc_sign_idx = annual_positions["ascendant"]["sign_idx"]
    planets = annual_positions["planets"]
    vl = varsheshwara["lord"]  # Varsheshwara

    houses = []
    for h in range(1, 13):
        house_sign_idx = (asc_sign_idx + h - 1) % 12
        house_lord = RASHI_LORDS[house_sign_idx]

        # Planets in this house
        occupants = [p for p in planets if p["house"] == h]
        occupant_names = [p["name"] for p in occupants]

        # Base interpretation from classical text
        base_text = ANNUAL_BHAVA_RESULTS.get(h, "")

        # Muntha placement
        m_house = muntha_house(muntha_data["sign_idx"], asc_sign_idx)
        muntha_note = ""
        if m_house == h:
            muntha_note = f"Muntha is placed in this house ({muntha_data['sign']}). "
            muntha_note += MUNTHA_RESULTS.get(h, "")

        # Varsheshwara connection
        varshesh_note = ""
        if house_lord == vl:
            varshesh_note = f"The lord of this house ({house_lord}) is also the Varsheshwara (Lord of the Year), strengthening this house's significations."
        if vl in occupant_names:
            varshesh_note += f" The Varsheshwara {vl} occupies this house, bringing special focus to its matters."

        # Occupant effects
        occupant_notes = []
        for occ in occupants:
            is_benefic = occ["name"] in ("Jupiter", "Venus", "Mercury", "Moon")
            effect = "favourable" if is_benefic else "challenging"
            if occ["retrograde"] and occ["name"] not in ("Rahu", "Ketu"):
                effect += " but delayed"
            occupant_notes.append(f"{occ['name']} in {occ['sign']} ({effect})")

        houses.append({
            "house": h,
            "sign": RASHI_NAMES[house_sign_idx],
            "sign_sanskrit": RASHI_SANSKRIT[house_sign_idx],
            "lord": house_lord,
            "occupants": occupant_names,
            "occupant_details": occupant_notes,
            "base_interpretation": base_text,
            "muntha_note": muntha_note,
            "varsheshwara_note": varshesh_note,
        })

    return houses


# ══════════════════════════════════════════════════════════════════════════════
#  SOUTH INDIAN CHART SVG FOR ANNUAL CHART
# ══════════════════════════════════════════════════════════════════════════════

def generate_annual_chart_svg(annual_positions: dict, muntha_data: dict,
                              title: str = "Annual Chart") -> str:
    """
    Generate an inline SVG of the South Indian chart for the annual horoscope.
    Shows planet abbreviations colour-coded and Muntha position.
    """
    W, H = 400, 420
    CELL = 90
    MARGIN = 20
    # Fixed South Indian grid positions
    GRID = {
        11: (0, 0), 0: (0, 1), 1: (0, 2), 2: (0, 3),
        10: (1, 0),                         3: (1, 3),
        9:  (2, 0),                         4: (2, 3),
        8:  (3, 0), 7: (3, 1), 6: (3, 2), 5: (3, 3),
    }

    asc_sign_idx = annual_positions["ascendant"]["sign_idx"]

    # Build occupancy map: sign_idx -> list of planet abbreviations
    occupancy = {i: [] for i in range(12)}
    for p in annual_positions["planets"]:
        abbr = PLANET_ABBR.get(p["name"], p["name"][:2])
        is_benefic = p["name"] in ("Jupiter", "Venus", "Mercury", "Moon")
        colour = "#2e7d32" if is_benefic else "#c62828"
        if p["name"] in ("Rahu", "Ketu"):
            colour = "#6a1b9a"
        occupancy[p["sign_idx"]].append((abbr, colour, p.get("retrograde", False)))

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'style="max-width:400px;font-family:sans-serif;">',
        f'<rect width="{W}" height="{H}" fill="#fdf6e3" rx="8"/>',
        f'<text x="{W//2}" y="16" text-anchor="middle" font-size="12" '
        f'fill="#5d4037" font-weight="bold">{title}</text>',
    ]

    # Draw 4×4 grid
    for sign_idx, (row, col) in GRID.items():
        x = MARGIN + col * CELL
        y = 22 + row * CELL

        # Highlight Lagna sign
        fill = "#fff8e1" if sign_idx == asc_sign_idx else "#fffef7"
        svg_lines.append(
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
            f'fill="{fill}" stroke="#8d6e63" stroke-width="1"/>'
        )

        # Sign label (Sanskrit abbreviation)
        label = RASHI_SANSKRIT[sign_idx][:3]
        svg_lines.append(
            f'<text x="{x+3}" y="{y+12}" font-size="8" fill="#8d6e63">{label}</text>'
        )

        # Mark Lagna
        if sign_idx == asc_sign_idx:
            svg_lines.append(
                f'<text x="{x+CELL-3}" y="{y+12}" text-anchor="end" '
                f'font-size="7" fill="#bf360c" font-weight="bold">Asc</text>'
            )

        # Mark Muntha
        if sign_idx == muntha_data["sign_idx"]:
            svg_lines.append(
                f'<text x="{x+CELL-3}" y="{y+CELL-4}" text-anchor="end" '
                f'font-size="7" fill="#1565c0" font-weight="bold">Mu</text>'
            )

        # Planet abbreviations
        bodies = occupancy[sign_idx]
        for bi, (abbr, colour, retro) in enumerate(bodies):
            px = x + 8 + (bi % 3) * 28
            py = y + 30 + (bi // 3) * 18
            display = f"{abbr}(R)" if retro else abbr
            svg_lines.append(
                f'<text x="{px}" y="{py}" font-size="11" fill="{colour}" '
                f'font-weight="bold">{display}</text>'
            )

    # Centre label
    cx = MARGIN + CELL
    cy = 22 + CELL
    svg_lines.append(
        f'<rect x="{cx}" y="{cy}" width="{CELL*2}" height="{CELL*2}" '
        f'fill="#fff3e0" stroke="#8d6e63" stroke-width="0.5"/>'
    )
    svg_lines.append(
        f'<text x="{cx + CELL}" y="{cy + CELL - 5}" text-anchor="middle" '
        f'font-size="11" fill="#5d4037" font-weight="bold">VARSHAPHAL</text>'
    )
    svg_lines.append(
        f'<text x="{cx + CELL}" y="{cy + CELL + 10}" text-anchor="middle" '
        f'font-size="9" fill="#795548">Annual Chart</text>'
    )

    svg_lines.append("</svg>")
    return "\n".join(svg_lines)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def compute_varshaphal(birth: dict, birth_positions: dict,
                       target_year: int) -> dict:
    """
    Master function: compute the complete Varshaphal (Annual Horoscope) for a given year.

    Parameters:
      birth: dict with keys year, month, day, hour, minute, second,
             utc_offset, latitude, longitude, name, gender
      birth_positions: dict from chart_gen.calculate_positions() — the natal chart
      target_year: the year for which to compute the annual chart

    Returns:
      dict with all Varshaphal data: solar return time, annual positions,
      Muntha, Varsheshwara, Sahams, Tajaka Yogas, Varsha Dasa, house interpretations,
      and SVG chart.
    """
    if not HAS_SWE:
        return {"error": "Swiss Ephemeris not available"}

    _init_swe()

    # 1. Birth Sun longitude (sidereal)
    birth_dt = datetime(birth["year"], birth["month"], birth["day"],
                        birth["hour"], birth["minute"], birth.get("second", 0))
    birth_jd = _jd_from_datetime(birth_dt, birth["utc_offset"])
    birth_sun_lon = _get_sidereal_longitude(birth_jd, swe.SUN)

    # Birth Ascendant sign index
    birth_asc_lon = _get_asc_longitude(birth_jd, birth["latitude"], birth["longitude"])
    birth_asc_sign_idx = int(birth_asc_lon / 30.0) % 12

    # 2. Solar Return for target year
    solar_return_jd = compute_solar_return(birth_jd, birth_sun_lon, target_year,
                                           birth["utc_offset"])

    # Convert solar return JD to datetime
    sr_data = swe.revjul(solar_return_jd)
    sr_year, sr_month, sr_day, sr_ut = sr_data
    sr_hour = int(sr_ut)
    sr_min = int((sr_ut - sr_hour) * 60)
    sr_sec = int(((sr_ut - sr_hour) * 60 - sr_min) * 60)
    # Add UTC offset back for local time display
    local_ut = sr_ut + birth["utc_offset"]
    local_hour = int(local_ut) % 24
    local_min = int((local_ut - int(local_ut)) * 60)

    solar_return_info = {
        "jd": round(solar_return_jd, 6),
        "utc_date": f"{int(sr_year)}-{int(sr_month):02d}-{int(sr_day):02d}",
        "utc_time": f"{sr_hour:02d}:{sr_min:02d}:{sr_sec:02d} UTC",
        "local_time": f"{local_hour:02d}:{local_min:02d} (UTC+{birth['utc_offset']})",
    }

    # 3. Compute annual chart positions at solar return moment
    annual_positions = compute_annual_positions(
        solar_return_jd, birth["latitude"], birth["longitude"]
    )

    # Build birth_positions in same format if needed
    birth_pos_formatted = _format_birth_positions(birth_positions, birth_asc_sign_idx)

    # 4. Determine if day or night birth (Sun above/below horizon)
    sun_house = next((p["house"] for p in annual_positions["planets"]
                      if p["name"] == "Sun"), 1)
    is_day_birth = sun_house in (7, 8, 9, 10, 11, 12)  # Sun above horizon

    # 5. Muntha
    muntha = compute_muntha(birth_asc_sign_idx, birth["year"], target_year)
    m_house = muntha_house(muntha["sign_idx"], annual_positions["ascendant"]["sign_idx"])
    muntha["house_in_annual"] = m_house
    muntha["house_result"] = MUNTHA_RESULTS.get(m_house, "")

    # 6. Varsheshwara
    varsheshwara = determine_varsheshwara(
        annual_positions, birth_pos_formatted, muntha, is_day_birth
    )

    # 7. Sahams
    sahams = compute_sahams(annual_positions, is_day_birth)

    # 8. Tajaka Yogas
    tajaka_yogas = detect_tajaka_yogas(annual_positions)

    # 9. Varsha Dasa
    varsha_dasa = compute_varsha_dasa(annual_positions)

    # 10. House interpretations
    house_interps = interpret_annual_houses(annual_positions, muntha, varsheshwara)

    # 11. Generate SVG chart
    age = target_year - birth["year"]
    chart_title = f"Varshaphal — Year {target_year} (Age {age})"
    annual_svg = generate_annual_chart_svg(annual_positions, muntha, chart_title)

    # 12. General estimate (Art. 55)
    general_estimate = _general_estimate(annual_positions, muntha, varsheshwara)

    return {
        "success": True,
        "target_year": target_year,
        "age": age,
        "solar_return": solar_return_info,
        "annual_positions": {
            "ascendant": annual_positions["ascendant"],
            "planets": annual_positions["planets"],
            "ayanamsa": annual_positions["ayanamsa"],
        },
        "muntha": muntha,
        "varsheshwara": varsheshwara,
        "sahams": sahams,
        "tajaka_yogas": tajaka_yogas,
        "varsha_dasa": varsha_dasa,
        "house_interpretations": house_interps,
        "annual_svg": annual_svg,
        "general_estimate": general_estimate,
        "is_day_chart": is_day_birth,
    }


def _format_birth_positions(positions: dict, birth_asc_sign_idx: int) -> dict:
    """Convert natal chart_gen positions dict to the format used by Varshaphal."""
    formatted_planets = []
    for p in positions.get("planets", []):
        sign_idx = p.get("rashi", {}).get("index", int(p.get("longitude", 0) / 30) % 12)
        formatted_planets.append({
            "name": p["name"],
            "sign_idx": sign_idx,
            "longitude": p.get("longitude", 0),
            "sign_deg": p.get("sign_deg", p.get("longitude", 0) % 30),
            "house": p.get("house", ((sign_idx - birth_asc_sign_idx) % 12) + 1),
            "sign": RASHI_NAMES[sign_idx],
            "retrograde": p.get("retrograde", False),
        })
    return {
        "planets": formatted_planets,
        "ascendant": {
            "sign_idx": birth_asc_sign_idx,
            "sign": RASHI_NAMES[birth_asc_sign_idx],
            "lord": RASHI_LORDS[birth_asc_sign_idx],
        },
    }


def _general_estimate(annual_positions: dict, muntha: dict,
                      varsheshwara: dict) -> str:
    """
    General estimate for the year (Art. 55).
    "If the ascendant or the 10th house is favourably aspected in the
     Progressed Horoscope by the Sun, Moon, Jupiter or Mars, the
     year will be a prosperous one."

    Muntha house classification per B.V. Raman (Art. 56):
      Favourable houses: 1, 2, 3, 4, 5, 10, 11
      Unfavourable houses: 6, 7, 8, 9, 12
    """
    planets = annual_positions["planets"]

    # Benefics and malefics on 1st / 10th house of annual chart (Art. 55)
    benefics_on_angles = []
    malefics_on_angles = []
    for p in planets:
        if p["house"] in (1, 10):
            if p["name"] in ("Jupiter", "Venus", "Moon"):
                benefics_on_angles.append(p["name"])
            elif p["name"] in ("Saturn", "Mars", "Rahu", "Ketu"):
                malefics_on_angles.append(p["name"])

    vl = varsheshwara["lord"]
    vl_data = next((p for p in planets if p["name"] == vl), None)
    vl_house = vl_data["house"] if vl_data else 0
    # Varsheshwara is strong in Kendra (1,4,7,10) or Trikona (5,9); house 8/12 is weak
    vl_strong = vl_house in (1, 4, 5, 7, 9, 10)
    vl_weak   = vl_house in (6, 8, 12)

    # Muntha: favourable in 1,2,3,4,5,10,11 per B.V. Raman Art. 56
    muntha_h = muntha.get("house_in_annual", 0)
    muntha_good = muntha_h in (1, 2, 3, 4, 5, 10, 11)

    # Build a coherent, non-contradictory estimate
    parts = []

    # 1. Overall prosperity signal
    if benefics_on_angles:
        parts.append(
            f"Benefic planets ({', '.join(benefics_on_angles)}) occupy the Ascendant or "
            f"10th house of the annual chart — a clear sign of prosperity and success "
            f"during this Varsha year."
        )
    elif malefics_on_angles:
        # Only mention malefics on angles if there are NO benefics there
        parts.append(
            f"Malefics ({', '.join(malefics_on_angles)}) occupy the 1st or 10th house "
            f"of the annual chart — this Varsha calls for careful and measured effort."
        )
    else:
        parts.append("The annual chart shows a mixed disposition for the year ahead.")

    # 2. Varsheshwara assessment
    if vl_strong and vl not in malefics_on_angles:
        parts.append(
            f"The Varsheshwara {vl} is well-placed in house {vl_house}, "
            f"conferring its significations strongly through this year."
        )
    elif vl_strong and vl in malefics_on_angles:
        parts.append(
            f"The Varsheshwara {vl} is placed in house {vl_house} — "
            f"its angular position brings prominence but also demands discipline, "
            f"as it is a natural malefic."
        )
    elif vl_weak:
        parts.append(
            f"The Varsheshwara {vl} in house {vl_house} is in a dusthana (6th/8th/12th), "
            f"indicating that results may come through delays and extra effort."
        )
    else:
        parts.append(
            f"The Varsheshwara {vl} in house {vl_house} gives moderate results; "
            f"consistent effort will improve outcomes."
        )

    # 3. Muntha assessment
    if muntha_good:
        parts.append(
            f"Muntha in house {muntha_h} ({muntha['sign']}) is favourable — "
            f"{muntha.get('house_result', 'indicating general good fortune for this area of life.')}"
        )
    else:
        parts.append(
            f"Muntha in house {muntha_h} ({muntha['sign']}) is in an unfavourable position — "
            f"{muntha.get('house_result', 'caution advised in matters of this house.')}"
        )

    return " ".join(parts)
