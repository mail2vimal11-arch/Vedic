"""
parashari_engine.py
===================
Extended Parashari computation module for the 20-section BPHS consultation.

Computes:
  Sec 4:  Special Lagnas       — Hora, Ghati, Bhava, Varnada
  Sec 5:  Shodasha Varga       — D2 through D30 (key divisional charts)
  Sec 8:  Drishti Analysis     — Graha + Rashi aspects
  Sec 9:  Shadbala             — Sthana, Dig, Naisargika, Chesta strength
  Sec 10: Aragala              — Intervention / obstruction per house
  Sec 11: Chara Karakas        — Atmakaraka through Darakaraka
  Sec 13: Longevity & Maraka   — Longevity category + Maraka planets
  Sec 14: Avasthas             — Baladi planetary states
"""

import math
import logging
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("vedic.parashari")

# ── Constants ────────────────────────────────────────────────────────────────

SIGN_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]
SIGN_LORDS = {
    "Aries": "Mars",   "Taurus": "Venus",  "Gemini": "Mercury",
    "Cancer": "Moon",  "Leo": "Sun",        "Virgo": "Mercury",
    "Libra": "Venus",  "Scorpio": "Mars",   "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter"
}
CLASSICAL_PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]

SIGN_MODALITY = {
    "Aries": "Cardinal", "Cancer": "Cardinal", "Libra": "Cardinal", "Capricorn": "Cardinal",
    "Taurus": "Fixed", "Leo": "Fixed", "Scorpio": "Fixed", "Aquarius": "Fixed",
    "Gemini": "Mutable", "Virgo": "Mutable", "Sagittarius": "Mutable", "Pisces": "Mutable",
}

EXALTATION_SIGNS = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces", "Saturn": "Libra"
}
DEBILITATION_SIGNS = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
    "Mercury": "Pisces", "Jupiter": "Capricorn", "Venus": "Virgo", "Saturn": "Aries"
}
OWN_SIGNS = {
    "Sun": ["Leo"], "Moon": ["Cancer"], "Mars": ["Aries", "Scorpio"],
    "Mercury": ["Gemini", "Virgo"], "Jupiter": ["Sagittarius", "Pisces"],
    "Venus": ["Taurus", "Libra"], "Saturn": ["Capricorn", "Aquarius"],
}

# Shadbala constants
NAISARGIKA_BALA = {
    "Sun": 60, "Moon": 51.43, "Venus": 42.86,
    "Jupiter": 34.29, "Mercury": 25.71, "Mars": 17.14, "Saturn": 8.57
}
DIG_BALA_HOUSE = {
    "Sun": 10, "Jupiter": 10,
    "Moon": 4, "Venus": 4,
    "Mars": 1, "Saturn": 7,
    "Mercury": 1,
}

# Drishti special aspects: {planet: [house_offset_from_planet (0-indexed)]}
SPECIAL_ASPECTS = {
    "Mars":    [3, 6, 7],   # 4th, 7th, 8th from Mars
    "Jupiter": [4, 6, 8],   # 5th, 7th, 9th
    "Saturn":  [2, 6, 9],   # 3rd, 7th, 10th
    "Rahu":    [4, 6, 8],   # 5th, 7th, 9th (like Jupiter)
    "Ketu":    [4, 6, 8],
}

# Karaka names and meanings
KARAKA_NAMES = [
    "Atmakaraka", "Amatyakaraka", "Bhratrikaraka",
    "Matrikaraka", "Pitrikaraka", "Putrakaraka",
    "Gnatikaraka", "Darakaraka"
]
KARAKA_MEANINGS = {
    "Atmakaraka":   "Soul significator — primary life purpose and karmic direction",
    "Amatyakaraka": "Minister — career, worldly execution, and support systems",
    "Bhratrikaraka": "Siblings — fraternal bonds, courage, and competitive drive",
    "Matrikaraka":  "Mother — nurturing, comfort, home, and emotional foundations",
    "Pitrikaraka":  "Father — authority, guidance, dharma, and paternal inheritance",
    "Putrakaraka":  "Children — creativity, intelligence, progeny, and past-life merit",
    "Gnatikaraka":  "Relatives — extended family, disputes, and competitors",
    "Darakaraka":   "Spouse — partnership, marriage, and nature of life companion",
}


def _get_planet_map(positions: dict) -> Dict[str, dict]:
    """Build {planet_name: planet_dict} from positions."""
    return {p["name"]: p for p in positions.get("planets", [])}


def _norm_sign(name: str) -> str:
    """Normalise spelling variants of Sagittarius."""
    return name.replace("Saggitarius", "Sagittarius")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — SPECIAL LAGNAS
# ─────────────────────────────────────────────────────────────────────────────

def compute_special_lagnas(positions: dict, birth: dict) -> dict:
    """
    Compute Hora Lagna, Ghati Lagna, Bhava Lagna, and Varnada Lagna.
    Uses approximate sunrise at 06:00 local time.
    """
    hour = birth.get("hour", 6)
    minute = birth.get("minute", 0)
    second = birth.get("second", 0)

    local_time_hrs = hour + minute / 60.0 + second / 3600.0
    sunrise_approx = 6.0
    elapsed_hrs = local_time_hrs - sunrise_approx
    if elapsed_hrs < 0:
        elapsed_hrs += 24

    asc = positions.get("ascendant", {})
    lagna_lon = asc.get("longitude", 0.0)
    lagna_sign_idx = int(lagna_lon / 30) % 12
    lagna_deg = lagna_lon % 30

    # Hora Lagna — advances ~1 sign per hour
    hl_advance = elapsed_hrs
    hl_sign_idx = int(lagna_sign_idx + hl_advance) % 12
    hl_deg = (lagna_deg + (hl_advance % 1) * 30) % 30

    # Ghati Lagna — advances 1 sign per 2 ghatikas (~48 min)
    elapsed_ghatikas = elapsed_hrs * 2.5
    gl_sign_idx = int(lagna_sign_idx + elapsed_ghatikas) % 12
    gl_deg = (lagna_deg + (elapsed_ghatikas % 1) * 30) % 30

    # Bhava Lagna — equals natal Lagna at birth
    bl_sign_idx = lagna_sign_idx
    bl_deg = lagna_deg

    # Varnada Lagna — classical parity-based derivation
    la_num = lagna_sign_idx + 1
    hl_num = hl_sign_idx + 1
    la_odd = (lagna_sign_idx % 2 == 0)
    hl_odd = (hl_sign_idx % 2 == 0)
    if la_odd == hl_odd:
        vl_count = (la_num + hl_num - 1) % 12
    else:
        vl_count = abs(la_num - hl_num)
        if vl_count == 0:
            vl_count = 12
    vl_sign_idx = (vl_count - 1) % 12

    hl_interps = {
        0: "Wealth through initiative — the self is the primary resource.",
        1: "Wealth through accumulation, land, and Venus-ruled resources.",
        2: "Wealth through trade, communication, and multiple income streams.",
        3: "Wealth through emotional intelligence, nurturing, and real estate.",
        4: "Wealth through authority, leadership, and government connections.",
        5: "Wealth through skilled service, precision, and methodical effort.",
        6: "Wealth through partnership, commerce, and balanced exchange.",
        7: "Wealth through research, transformation, and hidden resources.",
        8: "Wealth through wisdom, teaching, and dharmic activity.",
        9: "Wealth through sustained effort, structure, and institutional roles.",
        10: "Wealth through social networks, innovation, and collective causes.",
        11: "Wealth through spiritual service, creative arts, and overseas connections.",
    }
    gl_interps = {
        0: "Power flows through bold action and personal authority.",
        1: "Power accumulates through material resources and patient effort.",
        2: "Power expressed through intellect, communication, and versatility.",
        3: "Power through emotional depth, family bonds, and protective instincts.",
        4: "Power through royal command, fame, and solar authority.",
        5: "Power through critical analysis, service excellence, and health mastery.",
        6: "Power through diplomacy, justice, and the art of balance.",
        7: "Power through transformation, occult knowledge, and deep investigation.",
        8: "Power through wisdom, dharmic authority, and philosophical reach.",
        9: "Power through discipline, institutional rank, and sustained ambition.",
        10: "Power through social reform, collective vision, and humanitarian causes.",
        11: "Power through spiritual depth, creative vision, and compassionate service.",
    }

    def _info(s_idx, deg, name, interp):
        sn = SIGN_NAMES[s_idx % 12]
        return {
            "name": name, "sign": sn, "sign_idx": s_idx % 12,
            "degree": round(deg, 2), "lord": SIGN_LORDS.get(sn, ""),
            "interpretation": interp,
        }

    return {
        "hora_lagna": _info(hl_sign_idx, hl_deg, "Hora Lagna (HL)",
                            hl_interps.get(hl_sign_idx % 12, "Wealth indicators from the Hora Lagna.")),
        "ghati_lagna": _info(gl_sign_idx, gl_deg, "Ghati Lagna (GL)",
                             gl_interps.get(gl_sign_idx % 12, "Power indicators from the Ghati Lagna.")),
        "bhava_lagna": _info(bl_sign_idx, bl_deg, "Bhava Lagna (BL)",
                             "Bhava Lagna coincides with the natal Lagna — confirms the ascending sign."),
        "varnada_lagna": _info(vl_sign_idx, lagna_deg, "Varnada Lagna (VL)",
                               f"Varnada Lagna in {SIGN_NAMES[vl_sign_idx % 12]} — indicates health, longevity, and life-force trajectory."),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — SHODASHA VARGA (DIVISIONAL CHARTS)
# ─────────────────────────────────────────────────────────────────────────────

def _d2_sign(si, d):
    """D2 Hora: odd→Leo/Cancer, even→Cancer/Leo."""
    p = 0 if d < 15 else 1
    if si % 2 == 0:
        return 4 if p == 0 else 3
    return 3 if p == 0 else 4

def _d3_sign(si, d):
    """D3 Drekkana: own, 5th, 9th."""
    return (si + int(d / 10) * 4) % 12

def _d7_sign(si, d):
    """D7 Saptamsha."""
    p = int(d / (30 / 7))
    return (si + p) % 12 if si % 2 == 0 else (si + 6 + p) % 12

def _d9_sign(si, d):
    """D9 Navamsha: cardinal→Aries, fixed→Sagittarius, mutable→Leo."""
    p = int(d / (30 / 9))
    start = [0, 8, 4][si % 3]
    return (start + p) % 12

def _d10_sign(si, d):
    """D10 Dashamsha."""
    p = int(d / 3)
    return (si + p) % 12 if si % 2 == 0 else (si + 8 + p) % 12

def _d12_sign(si, d):
    """D12 Dwadashamsha: from own sign."""
    return (si + int(d / 2.5)) % 12

def _d16_sign(si, d):
    """D16 Shodashamsha."""
    p = int(d / (30 / 16))
    start = [0, 4, 8][si % 3]
    return (start + p) % 12

def _d20_sign(si, d):
    """D20 Vimsamsha."""
    p = int(d / 1.5)
    start = [0, 8, 4][si % 3]
    return (start + p) % 12

def _d24_sign(si, d):
    """D24 Chaturvimsamsha."""
    p = int(d / 1.25)
    return (4 + p) % 12 if si % 2 == 0 else (3 + p) % 12

def _d27_sign(si, d):
    """D27 Nakshatramsha."""
    p = int(d / (30 / 27))
    start = [0, 3, 6, 9][si % 4]
    return (start + p) % 12

def _d30_sign(si, d):
    """D30 Trimsamsha."""
    odd_cutoffs  = [(5, 0), (10, 9), (18, 8), (25, 2), (30, 6)]
    even_cutoffs = [(5, 6), (12, 2), (20, 8), (25, 9), (30, 0)]
    cutoffs = odd_cutoffs if si % 2 == 0 else even_cutoffs
    for limit, s_idx in cutoffs:
        if d < limit:
            return s_idx
    return 0


def compute_vargas(positions: dict) -> dict:
    """Compute key divisional charts for all planets + Lagna."""
    planet_map = _get_planet_map(positions)
    asc = positions.get("ascendant", {})
    lagna_lon = asc.get("longitude", 0.0)

    varga_funcs = {
        "D2": _d2_sign, "D3": _d3_sign, "D7": _d7_sign,
        "D9": _d9_sign, "D10": _d10_sign, "D12": _d12_sign,
        "D16": _d16_sign, "D20": _d20_sign, "D24": _d24_sign,
        "D27": _d27_sign, "D30": _d30_sign,
    }

    result = {}
    for chart_name, fn in varga_funcs.items():
        chart = {}
        la_idx = int(lagna_lon / 30) % 12
        la_deg = lagna_lon % 30
        chart["Lagna"] = SIGN_NAMES[fn(la_idx, la_deg)]

        for p_name in CLASSICAL_PLANETS + ["Rahu", "Ketu"]:
            if p_name not in planet_map:
                continue
            p_lon = planet_map[p_name].get("longitude", 0.0)
            s_idx = int(p_lon / 30) % 12
            d_in_s = p_lon % 30
            chart[p_name] = SIGN_NAMES[fn(s_idx, d_in_s)]

        result[chart_name] = chart
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — DRISHTI (ASPECT) ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def compute_drishti(positions: dict) -> dict:
    """Compute Graha Drishti and Rashi Drishti."""
    planet_map = _get_planet_map(positions)
    asc = positions.get("ascendant", {})
    lagna_lon = asc.get("longitude", 0.0)
    lagna_sign_idx = int(lagna_lon / 30) % 12

    graha_aspects = {}
    houses_aspected = {h: [] for h in range(1, 13)}

    for p_name, p_data in planet_map.items():
        if p_name in ("Uranus", "Neptune", "Pluto"):
            continue
        p_lon = p_data.get("longitude", 0.0)
        p_sign_idx = int(p_lon / 30) % 12
        p_house = ((p_sign_idx - lagna_sign_idx) % 12) + 1

        offsets = list(SPECIAL_ASPECTS.get(p_name, [6]))
        if 6 not in offsets:
            offsets.append(6)

        aspects = []
        for offset in offsets:
            aspected_sign = (p_sign_idx + offset) % 12
            aspected_house = ((aspected_sign - lagna_sign_idx) % 12) + 1
            label = {3: "4th", 4: "5th", 6: "7th", 7: "8th", 8: "9th",
                     2: "3rd", 9: "10th"}.get(offset, f"{offset+1}th")
            aspects.append({
                "house": aspected_house, "sign": SIGN_NAMES[aspected_sign],
                "strength": "Full", "from_house": p_house, "label": label,
            })
            if p_name not in houses_aspected[aspected_house]:
                houses_aspected[aspected_house].append(p_name)

        graha_aspects[p_name] = aspects

    # Rashi Drishti
    movable = [0, 3, 6, 9]
    fixed = [1, 4, 7, 10]
    dual = [2, 5, 8, 11]
    rashi_aspects = {}
    for s_idx in range(12):
        aspected = []
        if s_idx in movable:
            next_fixed = (s_idx + 1) % 12
            aspected = [SIGN_NAMES[f] for f in fixed if f != next_fixed]
        elif s_idx in fixed:
            prev_movable = (s_idx - 1) % 12
            aspected = [SIGN_NAMES[m] for m in movable if m != prev_movable]
        elif s_idx in dual:
            aspected = [SIGN_NAMES[d] for d in dual if d != s_idx]
        rashi_aspects[SIGN_NAMES[s_idx]] = aspected

    return {
        "graha": graha_aspects,
        "rashi": rashi_aspects,
        "houses_aspected": houses_aspected,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — SHADBALA (SIMPLIFIED)
# ─────────────────────────────────────────────────────────────────────────────

def _sthana_bala(planet: str, sign: str) -> float:
    """Positional strength based on dignity (0-60)."""
    sign = _norm_sign(sign)
    if sign == EXALTATION_SIGNS.get(planet):
        return 60.0
    if sign == DEBILITATION_SIGNS.get(planet):
        return 3.0
    if sign in OWN_SIGNS.get(planet, []):
        return 45.0
    # Simplified friendly/enemy
    lord = SIGN_LORDS.get(sign, "")
    from deep_interpreter import FRIENDLY, ENEMY
    if lord in FRIENDLY.get(planet, []):
        return 35.0
    if lord in ENEMY.get(planet, []):
        return 12.0
    return 22.0  # neutral


def _dig_bala(planet: str, house: int) -> float:
    """Directional strength (0-60)."""
    best = DIG_BALA_HOUSE.get(planet, 10)
    worst = (best + 6 - 1) % 12 + 1
    if house == best:
        return 60.0
    if house == worst:
        return 0.0
    distance = abs(house - best)
    if distance > 6:
        distance = 12 - distance
    return round(60.0 * (1 - distance / 6.0), 1)


def compute_shadbala(positions: dict) -> dict:
    """Compute simplified Shadbala for the 7 classical planets."""
    planet_map = _get_planet_map(positions)
    asc = positions.get("ascendant", {})
    lagna_lon = asc.get("longitude", 0.0)
    lagna_sign_idx = int(lagna_lon / 30) % 12

    result = {}
    for p_name in CLASSICAL_PLANETS:
        if p_name not in planet_map:
            continue
        p = planet_map[p_name]
        sign = _norm_sign(p.get("rashi", {}).get("name", "Aries"))
        p_sign_idx = int(p.get("longitude", 0.0) / 30) % 12
        house = ((p_sign_idx - lagna_sign_idx) % 12) + 1
        is_retro = p.get("retrograde", False)

        sthana = _sthana_bala(p_name, sign)
        dig = _dig_bala(p_name, house)
        naisargika = NAISARGIKA_BALA.get(p_name, 30)
        chesta = 60.0 if is_retro else 30.0
        total = sthana + dig + naisargika + chesta

        isht = round((total / 240.0) * 60, 1)
        kasht = round(60.0 - isht, 1)

        if total >= 160:
            category = "Exceptionally Strong"
        elif total >= 130:
            category = "Strong"
        elif total >= 100:
            category = "Moderate"
        elif total >= 70:
            category = "Weak"
        else:
            category = "Very Weak"

        result[p_name] = {
            "sthana_bala": sthana, "dig_bala": dig,
            "naisargika_bala": naisargika, "chesta_bala": chesta,
            "total": round(total, 1), "isht": isht, "kasht": kasht,
            "category": category, "retrograde": is_retro,
            "sign": sign, "house": house,
        }

    ranked = sorted(result.items(), key=lambda x: x[1]["total"], reverse=True)
    for rank, (p_name, data) in enumerate(ranked, 1):
        result[p_name]["rank"] = rank

    return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — ARAGALA
# ─────────────────────────────────────────────────────────────────────────────

def compute_aragala(positions: dict) -> dict:
    """Compute Aragala / Virodha Aragala for each house."""
    planet_map = _get_planet_map(positions)
    asc = positions.get("ascendant", {})
    lagna_lon = asc.get("longitude", 0.0)
    lagna_sign_idx = int(lagna_lon / 30) % 12

    house_planets = {h: [] for h in range(1, 13)}
    for p_name, p_data in planet_map.items():
        if p_name in ("Uranus", "Neptune", "Pluto"):
            continue
        p_sign_idx = int(p_data.get("longitude", 0.0) / 30) % 12
        house = ((p_sign_idx - lagna_sign_idx) % 12) + 1
        house_planets[house].append(p_name)

    def _house_from_ref(ref, offset):
        return ((ref + offset - 1 - 1) % 12) + 1

    result = {}
    for ref in range(1, 13):
        supporters = []
        for p in house_planets.get(_house_from_ref(ref, 2), []):
            supporters.append((p, "2nd — Dhana Aragala"))
        for p in house_planets.get(_house_from_ref(ref, 4), []):
            supporters.append((p, "4th — Sukha Aragala"))
        for p in house_planets.get(_house_from_ref(ref, 11), []):
            supporters.append((p, "11th — Labha Aragala"))
        for p in house_planets.get(_house_from_ref(ref, 5), []):
            supporters.append((p, "5th — Putri Aragala"))

        blockers = []
        for p in house_planets.get(_house_from_ref(ref, 3), []):
            blockers.append((p, "3rd — blocks Labha"))
        for p in house_planets.get(_house_from_ref(ref, 10), []):
            blockers.append((p, "10th — blocks Sukha"))
        for p in house_planets.get(_house_from_ref(ref, 12), []):
            blockers.append((p, "12th — blocks Dhana"))

        if len(supporters) > len(blockers):
            verdict = "Supported"
        elif len(blockers) > len(supporters):
            verdict = "Obstructed"
        elif supporters and blockers:
            verdict = "Mixed"
        else:
            verdict = "Neutral"

        result[ref] = {"supporters": supporters, "blockers": blockers, "verdict": verdict}

    return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — CHARA KARAKAS
# ─────────────────────────────────────────────────────────────────────────────

def compute_karakas(positions: dict) -> dict:
    """Compute Chara Karakas — planets ranked by degree within sign."""
    planet_map = _get_planet_map(positions)
    planet_degrees = {}
    for p_name in CLASSICAL_PLANETS:
        if p_name not in planet_map:
            continue
        p_lon = planet_map[p_name].get("longitude", 0.0)
        planet_degrees[p_name] = p_lon % 30

    ranked = sorted(planet_degrees.items(), key=lambda x: x[1], reverse=True)

    qualities = {
        "Sun":     "solar authority and self-sovereignty",
        "Moon":    "emotional intelligence and nurturing instinct",
        "Mars":    "courage, drive, and warrior energy",
        "Mercury": "analytical intellect and communicative skill",
        "Jupiter": "wisdom, dharmic knowledge, and teaching power",
        "Venus":   "refined taste, relational harmony, and prosperity",
        "Saturn":  "discipline, karmic reckoning, and structured mastery",
    }

    karakas = {}
    for i, karaka_name in enumerate(KARAKA_NAMES[:len(ranked)]):
        if i >= len(ranked):
            break
        planet, degree = ranked[i]
        sign_idx = int(planet_map[planet]["longitude"] / 30) % 12
        sign = SIGN_NAMES[sign_idx]
        quality = qualities.get(planet, "planetary energy")

        if karaka_name == "Atmakaraka":
            interp = (f"{planet} as Atmakaraka places {quality} at the centre of the soul's karmic "
                      f"mission. The native's deepest learning runs through {planet}'s domain.")
        elif karaka_name == "Amatyakaraka":
            interp = (f"{planet} as Amatyakaraka channels worldly achievement through {quality}. "
                      f"Profession and mentors bear {planet}'s signature.")
        elif karaka_name == "Darakaraka":
            interp = (f"{planet} as Darakaraka describes the life partner — someone embodying "
                      f"{quality}. The native attracts a companion shaped by {planet}'s nature.")
        else:
            interp = f"{planet} governs this karaka through {quality}, placed in {sign}."

        karakas[karaka_name] = {
            "planet": planet, "degree_in_sign": round(degree, 2),
            "sign": sign, "meaning": KARAKA_MEANINGS.get(karaka_name, ""),
            "interpretation": interp,
        }

    return karakas


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13 — LONGEVITY & MARAKA
# ─────────────────────────────────────────────────────────────────────────────

def compute_longevity_maraka(positions: dict) -> dict:
    """Assess longevity type and identify Maraka Grahas."""
    planet_map = _get_planet_map(positions)
    asc = positions.get("ascendant", {})
    lagna_lon = asc.get("longitude", 0.0)
    lagna_sign_idx = int(lagna_lon / 30) % 12

    house_lord_map = {}
    for h in range(1, 13):
        s_idx = (lagna_sign_idx + h - 1) % 12
        house_lord_map[h] = SIGN_LORDS.get(SIGN_NAMES[s_idx], "")

    lagna_lord = house_lord_map.get(1, "")
    eighth_lord = house_lord_map.get(8, "")

    def _sign_of(planet):
        if planet in planet_map:
            return SIGN_NAMES[int(planet_map[planet].get("longitude", 0.0) / 30) % 12]
        return "Aries"

    ll_sign = _sign_of(lagna_lord)
    el_sign = _sign_of(eighth_lord)
    moon_sign = _sign_of("Moon")

    mod_score = {"Fixed": 3, "Cardinal": 2, "Mutable": 1}
    scores = [
        mod_score.get(SIGN_MODALITY.get(_norm_sign(ll_sign), "Cardinal"), 2),
        mod_score.get(SIGN_MODALITY.get(_norm_sign(el_sign), "Cardinal"), 2),
        mod_score.get(SIGN_MODALITY.get(_norm_sign(moon_sign), "Cardinal"), 2),
    ]
    avg = sum(scores) / len(scores)

    if avg >= 2.5:
        cat = "Long (Purna Ayu)"
        desc = ("Fixed signs dominate the longevity trio — the constitution is durable. "
                "Health vigilance during Maraka Dasha periods is advised.")
    elif avg >= 1.8:
        cat = "Medium (Madhya Ayu)"
        desc = ("Cardinal signs create some variability. "
                "Maraka Dasha periods require careful attention to health.")
    else:
        cat = "Short (Alpa Ayu) — assess with full Shadbala"
        desc = ("Mutable signs dominate — must be confirmed against full Shadbala. "
                "Remedial measures are strongly indicated.")

    lord_2 = house_lord_map.get(2, "")
    lord_7 = house_lord_map.get(7, "")
    marakas = []
    if lord_2:
        marakas.append({"planet": lord_2, "reason": "Lord of 2nd house (primary Maraka)",
                        "danger_period": f"{lord_2} Mahadasha / Antardasha"})
    if lord_7 and lord_7 != lord_2:
        marakas.append({"planet": lord_7, "reason": "Lord of 7th house (primary Maraka)",
                        "danger_period": f"{lord_7} Mahadasha / Antardasha"})

    # Planets occupying 2nd or 7th
    house_occ = {h: [] for h in range(1, 13)}
    for p_name, p_data in planet_map.items():
        if p_name in ("Uranus", "Neptune", "Pluto"):
            continue
        p_h = ((int(p_data.get("longitude", 0.0) / 30) % 12 - lagna_sign_idx) % 12) + 1
        house_occ[p_h].append(p_name)

    for p in house_occ.get(2, []):
        if p not in [m["planet"] for m in marakas]:
            marakas.append({"planet": p, "reason": "Occupant of 2nd house (secondary Maraka)",
                            "danger_period": f"{p} Mahadasha / Antardasha"})
    for p in house_occ.get(7, []):
        if p not in [m["planet"] for m in marakas]:
            marakas.append({"planet": p, "reason": "Occupant of 7th house (secondary Maraka)",
                            "danger_period": f"{p} Mahadasha / Antardasha"})

    return {
        "longevity_category": cat, "longevity_description": desc,
        "basis": {
            "lagna_lord": lagna_lord, "lagna_lord_sign": ll_sign,
            "eighth_lord": eighth_lord, "eighth_lord_sign": el_sign,
            "moon_sign": moon_sign,
        },
        "maraka_grahas": marakas,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14 — AVASTHAS (BALADI PLANETARY STATES)
# ─────────────────────────────────────────────────────────────────────────────

AVASTHA_ODD  = ["Bala", "Kumara", "Yuva", "Vriddha", "Mrita"]
AVASTHA_EVEN = ["Mrita", "Vriddha", "Yuva", "Kumara", "Bala"]
AVASTHA_DELIVERY = {"Bala": "25%", "Kumara": "50%", "Yuva": "100%", "Vriddha": "50%", "Mrita": "0-25%"}
AVASTHA_DESC = {
    "Bala":    "Infancy — potential exists but cannot deliver full results yet.",
    "Kumara":  "Youth — growing strength, results unfold progressively.",
    "Yuva":    "Prime — 100% delivery; significations manifest fully.",
    "Vriddha": "Old age — declining capacity, about half the promised results.",
    "Mrita":   "Dead state — minimal delivery; remedial measures strongly advised.",
}

def compute_avasthas(positions: dict) -> dict:
    """Compute Baladi Avasthas for all classical planets + nodes."""
    planet_map = _get_planet_map(positions)
    result = {}
    for p_name in CLASSICAL_PLANETS + ["Rahu", "Ketu"]:
        if p_name not in planet_map:
            continue
        p_lon = planet_map[p_name].get("longitude", 0.0)
        sign_idx = int(p_lon / 30) % 12
        deg = p_lon % 30
        seq = AVASTHA_ODD if sign_idx % 2 == 0 else AVASTHA_EVEN
        state_idx = min(int(deg / 6), 4)
        avastha = seq[state_idx]
        result[p_name] = {
            "avastha": avastha, "degree_in_sign": round(deg, 2),
            "sign": SIGN_NAMES[sign_idx],
            "delivery": AVASTHA_DELIVERY.get(avastha, ""),
            "description": AVASTHA_DESC.get(avastha, ""),
        }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MASTER FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def compute_extended_data(positions: dict, birth: dict,
                          moon_longitude: float = 0.0) -> dict:
    """
    Run all extended Parashari computations and return a unified dict.
    Called from app.py and passed to generate_consultation_html().
    """
    sections = {}

    computations = [
        ("special_lagnas",    lambda: compute_special_lagnas(positions, birth)),
        ("vargas",            lambda: compute_vargas(positions)),
        ("drishti",           lambda: compute_drishti(positions)),
        ("shadbala",          lambda: compute_shadbala(positions)),
        ("aragala",           lambda: compute_aragala(positions)),
        ("karakas",           lambda: compute_karakas(positions)),
        ("longevity_maraka",  lambda: compute_longevity_maraka(positions)),
        ("avasthas",          lambda: compute_avasthas(positions)),
    ]

    for key, fn in computations:
        try:
            sections[key] = fn()
        except Exception as e:
            logger.warning(f"{key} computation error: {e}")
            sections[key] = {}

    return sections
