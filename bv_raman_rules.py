"""
bv_raman_rules.py
==================
Comprehensive Jyotish rule engine extracted from B.V. Raman's classical texts:
  - "300 Important Combinations"
  - "How to Judge a Horoscope" Vols 1 & 2
  - "Hindu Predictive Astrology"

Provides:
  1. detect_all_yogas()        — 50+ yoga definitions with conditions & results
  2. planet_in_house_effects() — planet-in-house interpretations for all 12 houses
  3. dasha_interpretation()    — Mahadasha/Bhukti interpretation rules
  4. get_yoga_details()        — look up detailed yoga description by name

All functions accept standard chart data dicts used by the existing engine.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("vedic.raman_rules")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

SIGN_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]
SIGN_LORDS = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter"
}
CLASSICAL_PLANETS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
NATURAL_BENEFICS = ["Jupiter", "Venus", "Mercury", "Moon"]
NATURAL_MALEFICS = ["Sun", "Mars", "Saturn", "Rahu", "Ketu"]

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

KENDRA_HOUSES = {1, 4, 7, 10}
TRIKONA_HOUSES = {1, 5, 9}
DUSTHANA_HOUSES = {6, 8, 12}
UPACHAYA_HOUSES = {3, 6, 10, 11}

PANCHA_MAHAPURUSHA = {
    "Mars": "Ruchaka", "Mercury": "Bhadra", "Jupiter": "Hamsa",
    "Venus": "Malavya", "Saturn": "Sasa"
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
    "Sun":     ["Venus", "Saturn"],
    "Moon":    [],
    "Mars":    ["Mercury"],
    "Mercury": ["Moon"],
    "Jupiter": ["Mercury", "Venus"],
    "Venus":   ["Sun", "Moon"],
    "Saturn":  ["Sun", "Moon", "Mars"],
}

# Sign element mapping
FIRE_SIGNS = {"Aries", "Leo", "Sagittarius"}
EARTH_SIGNS = {"Taurus", "Virgo", "Capricorn"}
AIR_SIGNS = {"Gemini", "Libra", "Aquarius"}
WATER_SIGNS = {"Cancer", "Scorpio", "Pisces"}

SIGN_MODALITY = {
    "Aries": "Movable", "Cancer": "Movable", "Libra": "Movable", "Capricorn": "Movable",
    "Taurus": "Fixed", "Leo": "Fixed", "Scorpio": "Fixed", "Aquarius": "Fixed",
    "Gemini": "Dual", "Virgo": "Dual", "Sagittarius": "Dual", "Pisces": "Dual",
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _norm_sign(name: str) -> str:
    return name.replace("Saggitarius", "Sagittarius")


def _planet_map(positions: dict) -> Dict[str, dict]:
    """Build {planet_name: planet_dict} from positions."""
    return {p["name"]: p for p in positions.get("planets", [])}


def _sign_idx_of(planet_name: str, planet_map: dict) -> Optional[int]:
    """Get the sign index (0-11) of a planet."""
    p = planet_map.get(planet_name)
    if not p:
        return None
    rashi = p.get("rashi", {})
    idx = rashi.get("index")
    if idx is not None:
        return idx
    name = _norm_sign(rashi.get("name", ""))
    if name in SIGN_NAMES:
        return SIGN_NAMES.index(name)
    return None


def _house_of(planet_name: str, planet_map: dict, lagna_idx: int) -> Optional[int]:
    """Get the house (1-12) of a planet."""
    si = _sign_idx_of(planet_name, planet_map)
    if si is None:
        return None
    return ((si - lagna_idx) % 12) + 1


def _sign_of(planet_name: str, planet_map: dict) -> Optional[str]:
    """Get the sign name of a planet."""
    si = _sign_idx_of(planet_name, planet_map)
    if si is not None:
        return SIGN_NAMES[si]
    return None


def _get_dignity(planet: str, sign: str) -> str:
    """Return dignity of a planet in a sign."""
    sign = _norm_sign(sign)
    if sign == EXALTATION_SIGNS.get(planet):
        return "Exalted"
    if sign == DEBILITATION_SIGNS.get(planet):
        return "Debilitated"
    if sign in OWN_SIGNS.get(planet, []):
        return "Own Sign"
    lord = SIGN_LORDS.get(sign, "")
    if lord in FRIENDLY.get(planet, []):
        return "Friendly"
    if lord in ENEMY.get(planet, []):
        return "Enemy"
    return "Neutral"


def _planets_in_house(house: int, planet_map: dict, lagna_idx: int) -> List[str]:
    """Return list of planet names in a given house."""
    result = []
    for pname, pdata in planet_map.items():
        if pname in ("Uranus", "Neptune", "Pluto"):
            continue
        h = _house_of(pname, planet_map, lagna_idx)
        if h == house:
            result.append(pname)
    return result


def _house_lord(house: int, lagna_idx: int) -> str:
    """Return the lord of a given house."""
    sign_idx = (lagna_idx + house - 1) % 12
    return SIGN_LORDS.get(SIGN_NAMES[sign_idx], "")


def _build_house_lord_map(lagna_idx: int) -> Dict[int, str]:
    """Build {house_num: lord_planet} for all 12 houses."""
    return {h: _house_lord(h, lagna_idx) for h in range(1, 13)}


def _is_benefic(planet: str) -> bool:
    return planet in NATURAL_BENEFICS


def _is_malefic(planet: str) -> bool:
    return planet in NATURAL_MALEFICS


def _houses_from(base_house: int, offsets: List[int]) -> List[int]:
    """Get house numbers at given offsets from base house."""
    return [((base_house + o - 1) % 12) + 1 for o in offsets]


def _are_conjunct(p1: str, p2: str, planet_map: dict, lagna_idx: int) -> bool:
    """Check if two planets are in the same house."""
    h1 = _house_of(p1, planet_map, lagna_idx)
    h2 = _house_of(p2, planet_map, lagna_idx)
    return h1 is not None and h2 is not None and h1 == h2


def _in_kendra_from(base_house: int, target_house: int) -> bool:
    """Check if target is in a kendra from base."""
    diff = ((target_house - base_house) % 12)
    return diff in (0, 3, 6, 9)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: YOGA DETECTION (from 300 Important Combinations)
# ═══════════════════════════════════════════════════════════════════════════════

def detect_all_yogas(positions: dict) -> List[dict]:
    """
    Detect all yogas from the chart.
    Returns list of dicts with keys: name, category, planets, houses, strength,
    description, classical_result, source.
    """
    pmap = _planet_map(positions)
    asc = positions.get("ascendant", {})
    lagna_lon = asc.get("longitude", 0.0)
    lagna_idx = int(lagna_lon / 30) % 12

    hlm = _build_house_lord_map(lagna_idx)
    yogas = []

    # Build house-occupants map
    house_occ = {h: [] for h in range(1, 13)}
    for pname in list(pmap.keys()):
        if pname in ("Uranus", "Neptune", "Pluto"):
            continue
        h = _house_of(pname, pmap, lagna_idx)
        if h:
            house_occ[h].append(pname)

    # ── 1. PANCHA MAHAPURUSHA YOGAS (Combinations 31-35) ──────────────────
    for planet, yoga_name in PANCHA_MAHAPURUSHA.items():
        if planet not in pmap:
            continue
        sign = _sign_of(planet, pmap)
        if not sign:
            continue
        dignity = _get_dignity(planet, sign)
        h = _house_of(planet, pmap, lagna_idx)
        if dignity in ("Exalted", "Own Sign") and h in KENDRA_HOUSES:
            descs = {
                "Ruchaka": "The native possesses a strong physique, is adventurous, victorious over enemies, and commands authority. Martial valour and leadership define this life.",
                "Bhadra": "The native is intellectually brilliant, eloquent, learned in scriptures and sciences, and long-lived. Business acumen and scholarly repute are hallmarks.",
                "Hamsa": "The native is righteous, handsome, learned, blessed with comforts, and devoted to higher knowledge. Spiritual wisdom and moral authority define the path.",
                "Malavya": "The native is blessed with beauty, vehicles, fine clothes, and domestic happiness. Artistic talent, sensual refinement, and material prosperity abound.",
                "Sasa": "The native commands servants, possesses wealth, and holds power over villages or towns. Discipline, strategic thinking, and authority over others mark this life.",
            }
            yogas.append({
                "name": f"{yoga_name} Yoga",
                "category": "Pancha Mahapurusha",
                "planets": [planet],
                "houses": [h],
                "strength": "Very Strong",
                "description": f"{planet} in {dignity} in House {h} (Kendra) forms {yoga_name} Yoga — one of the five supreme Pancha Mahapurusha Yogas.",
                "classical_result": descs.get(yoga_name, ""),
                "source": "300 Important Combinations, No. 31-35"
            })

    # ── 2. GAJAKESARI YOGA (Combination 36) ───────────────────────────────
    if "Jupiter" in pmap and "Moon" in pmap:
        jh = _house_of("Jupiter", pmap, lagna_idx)
        mh = _house_of("Moon", pmap, lagna_idx)
        if jh and mh and _in_kendra_from(mh, jh):
            yogas.append({
                "name": "Gajakesari Yoga",
                "category": "Lunar Yoga",
                "planets": ["Jupiter", "Moon"],
                "houses": [jh, mh],
                "strength": "Strong",
                "description": "Jupiter in a Kendra from Moon forms the celebrated Gajakesari Yoga.",
                "classical_result": "The native is splendorous like an elephant-king — intelligent, virtuous, wealthy, endowed with lasting fame and favour from the ruling class. The native outlives enemies and commands respect in all assemblies.",
                "source": "300 Important Combinations, No. 36"
            })

    # ── 3. SUNAPHA YOGA (Combination 37) ──────────────────────────────────
    moon_h = _house_of("Moon", pmap, lagna_idx)
    if moon_h:
        h2_from_moon = ((moon_h) % 12) + 1  # 2nd from Moon
        planets_2nd_from_moon = [p for p in house_occ.get(h2_from_moon, [])
                                  if p not in ("Moon", "Rahu", "Ketu")]
        if planets_2nd_from_moon:
            yogas.append({
                "name": "Sunapha Yoga",
                "category": "Lunar Yoga",
                "planets": planets_2nd_from_moon,
                "houses": [h2_from_moon],
                "strength": "Moderate",
                "description": f"{', '.join(planets_2nd_from_moon)} in the 2nd from Moon forms Sunapha Yoga.",
                "classical_result": "The native is self-made, acquires wealth through personal effort, is intelligent, wealthy, and enjoys a good reputation. Not dependent on inherited fortune.",
                "source": "300 Important Combinations, No. 37"
            })

    # ── 4. ANAPHA YOGA (Combination 38) ───────────────────────────────────
    if moon_h:
        h12_from_moon = ((moon_h - 2) % 12) + 1  # 12th from Moon
        planets_12th_from_moon = [p for p in house_occ.get(h12_from_moon, [])
                                   if p not in ("Moon", "Rahu", "Ketu")]
        if planets_12th_from_moon:
            yogas.append({
                "name": "Anapha Yoga",
                "category": "Lunar Yoga",
                "planets": planets_12th_from_moon,
                "houses": [h12_from_moon],
                "strength": "Moderate",
                "description": f"{', '.join(planets_12th_from_moon)} in the 12th from Moon forms Anapha Yoga.",
                "classical_result": "The native is well-formed in body, virtuous, eloquent, famous, and free from diseases. Spiritual inclinations and dignified bearing distinguish this person.",
                "source": "300 Important Combinations, No. 38"
            })

    # ── 5. DURUDHURA YOGA (Combination 39) ────────────────────────────────
    if moon_h and planets_2nd_from_moon and planets_12th_from_moon:
        yogas.append({
            "name": "Durudhura Yoga",
            "category": "Lunar Yoga",
            "planets": planets_2nd_from_moon + planets_12th_from_moon,
            "houses": [h2_from_moon, h12_from_moon],
            "strength": "Strong",
            "description": "Planets flanking the Moon on both sides form Durudhura Yoga.",
            "classical_result": "The native enjoys abundant wealth, vehicles, comforts, fame, and is generous in nature. Life is rich with material blessings and social standing.",
            "source": "300 Important Combinations, No. 39"
        })

    # ── 6. KEMADRUMA YOGA (Combination 40) ────────────────────────────────
    if moon_h:
        no_2nd = not [p for p in house_occ.get(((moon_h) % 12) + 1, [])
                      if p not in ("Moon", "Rahu", "Ketu")]
        no_12th = not [p for p in house_occ.get(((moon_h - 2) % 12) + 1, [])
                       if p not in ("Moon", "Rahu", "Ketu")]
        no_kendra_from_moon = True
        for offset in [0, 3, 6, 9]:
            kh = ((moon_h + offset - 1) % 12) + 1
            if any(p for p in house_occ.get(kh, []) if p != "Moon"):
                no_kendra_from_moon = False
                break
        if no_2nd and no_12th and no_kendra_from_moon:
            yogas.append({
                "name": "Kemadruma Yoga",
                "category": "Lunar Yoga (Adverse)",
                "planets": ["Moon"],
                "houses": [moon_h],
                "strength": "Adverse",
                "description": "Moon has no planets in the 2nd, 12th, or kendras from it — Kemadruma Yoga.",
                "classical_result": "The native may face poverty, hardship, sorrow, and lack of support despite good birth. Periods of isolation and financial struggle mark the life. However, cancellation occurs if planets aspect Moon or Moon is in a Kendra from Lagna.",
                "source": "300 Important Combinations, No. 40"
            })

    # ── 7. CHANDRA MANGALA YOGA (Combination 41) ─────────────────────────
    if "Moon" in pmap and "Mars" in pmap:
        if _are_conjunct("Moon", "Mars", pmap, lagna_idx):
            yogas.append({
                "name": "Chandra Mangala Yoga",
                "category": "Wealth Yoga",
                "planets": ["Moon", "Mars"],
                "houses": [_house_of("Moon", pmap, lagna_idx)],
                "strength": "Moderate",
                "description": "Moon and Mars conjunct form Chandra Mangala Yoga.",
                "classical_result": "The native earns money through unscrupulous means, deals in earthy products, is skilled, and brave. The mother may be assertive. Wealth fluctuates with effort and enterprise.",
                "source": "300 Important Combinations, No. 41"
            })

    # ── 8. ADHI YOGA (Combination 42) ────────────────────────────────────
    if moon_h:
        adhi_houses = [((moon_h + o - 1) % 12) + 1 for o in [5, 6, 7]]  # 6th, 7th, 8th from Moon
        adhi_benefics = []
        for ah in adhi_houses:
            for p in house_occ.get(ah, []):
                if _is_benefic(p) and p != "Moon":
                    adhi_benefics.append(p)
        if len(adhi_benefics) >= 2:
            yogas.append({
                "name": "Adhi Yoga",
                "category": "Fortune Yoga",
                "planets": adhi_benefics,
                "houses": adhi_houses,
                "strength": "Strong",
                "description": f"Benefics ({', '.join(adhi_benefics)}) in 6th/7th/8th from Moon form Adhi Yoga.",
                "classical_result": "The native becomes a commander, minister, or leader — polite, trustworthy, healthy, prosperous, surrounded by luxury, and able to defeat all adversaries.",
                "source": "300 Important Combinations, No. 42"
            })

    # ── 9. VASUMATHI YOGA (Combination 43) ────────────────────────────────
    if moon_h:
        upachaya_from_moon = [((moon_h + o - 1) % 12) + 1 for o in [2, 5, 9, 10]]  # 3,6,10,11 from Moon
        vasu_benefics = []
        for uh in upachaya_from_moon:
            for p in house_occ.get(uh, []):
                if _is_benefic(p):
                    vasu_benefics.append(p)
        if len(vasu_benefics) >= 3:
            yogas.append({
                "name": "Vasumathi Yoga",
                "category": "Wealth Yoga",
                "planets": vasu_benefics,
                "houses": upachaya_from_moon,
                "strength": "Strong",
                "description": f"Benefics in upachaya houses (3,6,10,11) from Moon form Vasumathi Yoga.",
                "classical_result": "The native is immensely wealthy, commands vast resources, and attains high social status. Financial fortune accumulates steadily through life.",
                "source": "300 Important Combinations, No. 43"
            })

    # ── 10. RAJA YOGAS (Combinations 82-100+) ────────────────────────────
    # Kendra-Trikona lord connections (the foundation of Raja Yoga)
    kendra_lords = set()
    trikona_lords = set()
    for h in KENDRA_HOUSES:
        kendra_lords.add(hlm[h])
    for h in TRIKONA_HOUSES:
        trikona_lords.add(hlm[h])

    # a) Yoga Karaka — single planet rules both kendra and trikona
    yoga_karakas = kendra_lords & trikona_lords
    for yk in yoga_karakas:
        if yk in pmap and yk != hlm[1]:  # exclude lagna lord (both kendra & trikona)
            h = _house_of(yk, pmap, lagna_idx)
            yogas.append({
                "name": f"Yoga Karaka ({yk})",
                "category": "Raja Yoga",
                "planets": [yk],
                "houses": [h],
                "strength": "Very Strong",
                "description": f"{yk} rules both a Kendra and a Trikona — supreme Yoga Karaka for this Lagna.",
                "classical_result": "All significations of this planet are elevated and auspicious. During its Dasha, the native experiences significant rise in status, authority, and prosperity.",
                "source": "300 Important Combinations, Raja Yoga Section"
            })

    # b) Conjunction/aspect of kendra-trikona lords
    for kl in kendra_lords:
        for tl in trikona_lords:
            if kl == tl or kl == hlm.get(1) or tl == hlm.get(1):
                continue
            if kl not in pmap or tl not in pmap:
                continue
            hk = _house_of(kl, pmap, lagna_idx)
            ht = _house_of(tl, pmap, lagna_idx)
            if hk and ht and hk == ht:
                yogas.append({
                    "name": f"Raja Yoga ({kl}-{tl})",
                    "category": "Raja Yoga",
                    "planets": [kl, tl],
                    "houses": [hk],
                    "strength": "Strong",
                    "description": f"Kendra lord {kl} conjoins Trikona lord {tl} in House {hk} — Raja Yoga.",
                    "classical_result": "The native attains power, authority, and fame commensurate with the strength of the combining planets. Government favour, leadership roles, and social elevation result.",
                    "source": "300 Important Combinations, No. 82-100"
                })

    # ── 11. DHARMA-KARMADHIPATI YOGA ─────────────────────────────────────
    lord9 = hlm.get(9)
    lord10 = hlm.get(10)
    if lord9 and lord10 and lord9 != lord10:
        h9 = _house_of(lord9, pmap, lagna_idx)
        h10 = _house_of(lord10, pmap, lagna_idx)
        if h9 and h10 and (h9 == h10 or _in_kendra_from(h9, h10)):
            yogas.append({
                "name": "Dharma-Karmadhipati Yoga",
                "category": "Raja Yoga",
                "planets": [lord9, lord10],
                "houses": [h9, h10],
                "strength": "Strong",
                "description": f"9th lord ({lord9}) and 10th lord ({lord10}) connected — Dharma-Karmadhipati Yoga.",
                "classical_result": "Career and life purpose align with dharmic destiny. The native achieves high professional standing through righteous conduct. Authority earned through merit and moral strength.",
                "source": "300 Important Combinations, Raja Yoga Section"
            })

    # ── 12. VIPARITA RAJA YOGAS ───────────────────────────────────────────
    viparita_names = {6: "Harsha", 8: "Sarala", 12: "Vimala"}
    for dusthana, vname in viparita_names.items():
        lord = hlm.get(dusthana)
        if lord and lord in pmap:
            h = _house_of(lord, pmap, lagna_idx)
            if h in DUSTHANA_HOUSES:
                yogas.append({
                    "name": f"{vname} Viparita Raja Yoga",
                    "category": "Viparita Raja Yoga",
                    "planets": [lord],
                    "houses": [h],
                    "strength": "Moderate",
                    "description": f"{lord} (lord of {dusthana}th) placed in Dusthana House {h} — {vname} Viparita Raja Yoga.",
                    "classical_result": {
                        "Harsha": "The native is happy, fortunate, invincible, physically strong, and enjoys recognition. Enemies self-destruct.",
                        "Sarala": "The native is long-lived, resolute, fearless, prosperous, and celebrated. Obstacles dissolve unexpectedly.",
                        "Vimala": "The native is frugal, contented, happy, independent, and possessed of noble qualities. Losses transform into spiritual gains."
                    }.get(vname, ""),
                    "source": "300 Important Combinations, No. 106-108"
                })

    # ── 13. DHANA YOGAS (Combinations 109-139) ───────────────────────────
    lord2 = hlm.get(2)
    lord11 = hlm.get(11)
    lord5 = hlm.get(5)
    lord9 = hlm.get(9)

    # a) 2nd lord + 11th lord connection
    if lord2 and lord11 and lord2 in pmap and lord11 in pmap:
        h2 = _house_of(lord2, pmap, lagna_idx)
        h11 = _house_of(lord11, pmap, lagna_idx)
        if h2 and h11 and (h2 in KENDRA_HOUSES | TRIKONA_HOUSES or h11 in KENDRA_HOUSES | TRIKONA_HOUSES):
            yogas.append({
                "name": "Dhana Yoga (2nd-11th Lords)",
                "category": "Wealth Yoga",
                "planets": [lord2, lord11],
                "houses": [h2, h11],
                "strength": "Moderate" if h2 != h11 else "Strong",
                "description": f"2nd lord ({lord2}) and 11th lord ({lord11}) favourably placed — Dhana Yoga.",
                "classical_result": "Wealth accumulates through the significations of the involved planets. Income streams are stable and growing. The native acquires property, vehicles, and financial security.",
                "source": "300 Important Combinations, No. 109-113"
            })

    # b) 5th lord + 9th lord (Lakshmi Yoga variant)
    if lord5 and lord9 and lord5 in pmap and lord9 in pmap:
        h5 = _house_of(lord5, pmap, lagna_idx)
        h9l = _house_of(lord9, pmap, lagna_idx)
        if h5 and h9l and (h5 in KENDRA_HOUSES or h9l in KENDRA_HOUSES):
            yogas.append({
                "name": "Lakshmi Yoga",
                "category": "Wealth Yoga",
                "planets": [lord5, lord9],
                "houses": [h5, h9l],
                "strength": "Strong",
                "description": f"5th lord ({lord5}) and 9th lord ({lord9}) in strong positions — Lakshmi Yoga.",
                "classical_result": "The native is blessed by Goddess Lakshmi — wealthy, noble, virtuous, learned, and endowed with many possessions. Prosperity comes through dharmic channels and past-life merit.",
                "source": "300 Important Combinations, No. 114-116"
            })

    # ── 14. NABHAS YOGAS ─────────────────────────────────────────────────
    # Asraya Yogas — based on sign modality distribution
    occupied_signs = set()
    for pname, pdata in pmap.items():
        if pname in ("Uranus", "Neptune", "Pluto", "Rahu", "Ketu"):
            continue
        si = _sign_idx_of(pname, pmap)
        if si is not None:
            occupied_signs.add(SIGN_NAMES[si])

    movable_count = sum(1 for s in occupied_signs if SIGN_MODALITY.get(s) == "Movable")
    fixed_count = sum(1 for s in occupied_signs if SIGN_MODALITY.get(s) == "Fixed")
    dual_count = sum(1 for s in occupied_signs if SIGN_MODALITY.get(s) == "Dual")

    if movable_count >= 4 and fixed_count == 0 and dual_count == 0:
        yogas.append({
            "name": "Rajju Yoga",
            "category": "Nabhas Yoga (Asraya)",
            "planets": list(pmap.keys()),
            "houses": [],
            "strength": "Moderate",
            "description": "All planets in Movable signs form Rajju Yoga.",
            "classical_result": "The native is fond of travel, is handsome, and lives abroad. Restlessness and love of movement characterize the life.",
            "source": "300 Important Combinations, Nabhas Yogas"
        })
    elif fixed_count >= 4 and movable_count == 0 and dual_count == 0:
        yogas.append({
            "name": "Musala Yoga",
            "category": "Nabhas Yoga (Asraya)",
            "planets": list(pmap.keys()),
            "houses": [],
            "strength": "Moderate",
            "description": "All planets in Fixed signs form Musala Yoga.",
            "classical_result": "The native is proud, wealthy, learned, liked by the ruler, and famous. Stability and determination define the character.",
            "source": "300 Important Combinations, Nabhas Yogas"
        })
    elif dual_count >= 4 and movable_count == 0 and fixed_count == 0:
        yogas.append({
            "name": "Nala Yoga",
            "category": "Nabhas Yoga (Asraya)",
            "planets": list(pmap.keys()),
            "houses": [],
            "strength": "Moderate",
            "description": "All planets in Dual signs form Nala Yoga.",
            "classical_result": "The native is skilful, clever, gifted in arts and speech, endowed with wealth and happiness. Adaptability and versatility mark the personality.",
            "source": "300 Important Combinations, Nabhas Yogas"
        })

    # Sankhya Yogas — based on number of houses occupied
    occupied_houses = set()
    for h in range(1, 13):
        if house_occ.get(h):
            occupied_houses.add(h)

    sankhya_map = {
        7: ("Vallaki Yoga", "The native is fond of music, happy, skilful, wealthy, and a leader."),
        6: ("Dama Yoga", "The native is generous, helpful to others, wealthy, and independent."),
        5: ("Pasa Yoga", "The native is skilled in work, talkative, connected with prisoners or bondage, and wealthy through effort."),
        4: ("Kedara Yoga", "The native is useful to many, agricultural, truthful, happy, and wealthy."),
        3: ("Sula Yoga", "The native is sharp, indolent, bold, cruel, poor, and bereft of family support."),
        2: ("Yuga Yoga", "The native is heretical, poor, disliked, outcast, and without wealth or family."),
        1: ("Gola Yoga", "The native is poor, dirty, ignorant, unlearned, and grief-stricken."),
    }
    occ_count = len(occupied_houses)
    if occ_count in sankhya_map:
        sname, sresult = sankhya_map[occ_count]
        yogas.append({
            "name": sname,
            "category": "Sankhya Yoga (Nabhas)",
            "planets": [],
            "houses": list(occupied_houses),
            "strength": "Background",
            "description": f"Planets occupy {occ_count} houses — {sname}.",
            "classical_result": sresult,
            "source": "300 Important Combinations, Sankhya Yogas"
        })

    # ── 15. AKRITI YOGAS (pattern-based) ─────────────────────────────────
    # Kamala Yoga — all planets in Kendras
    kendra_planets = []
    for h in KENDRA_HOUSES:
        kendra_planets.extend(house_occ.get(h, []))
    non_node_planets = [p for p in CLASSICAL_PLANETS if p in pmap]
    if all(_house_of(p, pmap, lagna_idx) in KENDRA_HOUSES for p in non_node_planets if _house_of(p, pmap, lagna_idx)):
        yogas.append({
            "name": "Kamala Yoga",
            "category": "Akriti Yoga (Nabhas)",
            "planets": non_node_planets,
            "houses": list(KENDRA_HOUSES),
            "strength": "Very Strong",
            "description": "All seven planets in Kendra houses form Kamala (Lotus) Yoga.",
            "classical_result": "The native is immensely famous, performs hundreds of meritorious deeds, virtuous, long-lived, and attains celebrity status. Life blooms like a lotus.",
            "source": "300 Important Combinations, Akriti Yogas"
        })

    # Vajra Yoga — benefics in 1st & 7th, malefics in 4th & 10th
    benefics_1_7 = all(
        any(_is_benefic(p) for p in house_occ.get(h, [])) for h in [1, 7]
    )
    malefics_4_10 = all(
        any(_is_malefic(p) for p in house_occ.get(h, [])) for h in [4, 10]
    )
    if benefics_1_7 and malefics_4_10:
        yogas.append({
            "name": "Vajra Yoga",
            "category": "Akriti Yoga (Nabhas)",
            "planets": [],
            "houses": [1, 4, 7, 10],
            "strength": "Moderate",
            "description": "Benefics in Lagna & 7th, malefics in 4th & 10th form Vajra Yoga.",
            "classical_result": "The native is happy in the beginning and end of life, brave, handsome, and thunderbolt-like in striking down opponents.",
            "source": "300 Important Combinations, Akriti Yogas"
        })

    # Yava Yoga — malefics in 1st & 7th, benefics in 4th & 10th
    malefics_1_7 = all(
        any(_is_malefic(p) for p in house_occ.get(h, [])) for h in [1, 7]
    )
    benefics_4_10 = all(
        any(_is_benefic(p) for p in house_occ.get(h, [])) for h in [4, 10]
    )
    if malefics_1_7 and benefics_4_10:
        yogas.append({
            "name": "Yava Yoga",
            "category": "Akriti Yoga (Nabhas)",
            "planets": [],
            "houses": [1, 4, 7, 10],
            "strength": "Moderate",
            "description": "Malefics in Lagna & 7th, benefics in 4th & 10th form Yava Yoga.",
            "classical_result": "The native is happy in middle age, charitable, and practises dharma. Life shape resembles a barley grain — narrow at ends, full in the middle.",
            "source": "300 Important Combinations, Akriti Yogas"
        })

    # ── 16. SAKATA YOGA ──────────────────────────────────────────────────
    if "Jupiter" in pmap and "Moon" in pmap:
        jh = _house_of("Jupiter", pmap, lagna_idx)
        mh = _house_of("Moon", pmap, lagna_idx)
        if jh and mh:
            diff = (jh - mh) % 12
            if diff in (5, 7):  # 6th or 8th from each other
                yogas.append({
                    "name": "Sakata Yoga",
                    "category": "Adverse Yoga",
                    "planets": ["Jupiter", "Moon"],
                    "houses": [jh, mh],
                    "strength": "Adverse",
                    "description": "Jupiter in 6th or 8th from Moon forms Sakata Yoga.",
                    "classical_result": "The native loses fortune repeatedly, faces ups and downs like a cart wheel. Wealth comes and goes. However, this yoga is cancelled if Jupiter is in a Kendra from Lagna.",
                    "source": "300 Important Combinations, Akriti Yogas"
                })

    # ── 17. AMALA YOGA ───────────────────────────────────────────────────
    h10_planets = house_occ.get(10, [])
    h10_benefics = [p for p in h10_planets if _is_benefic(p)]
    if h10_benefics and not any(_is_malefic(p) for p in h10_planets):
        yogas.append({
            "name": "Amala Yoga",
            "category": "Character Yoga",
            "planets": h10_benefics,
            "houses": [10],
            "strength": "Moderate",
            "description": f"Benefic(s) ({', '.join(h10_benefics)}) in 10th house form Amala Yoga.",
            "classical_result": "The native is of spotless character, enjoys lasting fame through righteous deeds, and lives a prosperous, virtuous life. Reputation endures beyond the lifetime.",
            "source": "300 Important Combinations, No. 51"
        })

    # ── 18. PARVATA YOGA ─────────────────────────────────────────────────
    lord1 = hlm.get(1)
    if lord1 and lord1 in pmap:
        h1 = _house_of(lord1, pmap, lagna_idx)
        if h1 in KENDRA_HOUSES | TRIKONA_HOUSES:
            # Check if no malefic in 6th/8th
            mal_6 = any(_is_malefic(p) for p in house_occ.get(6, []))
            mal_8 = any(_is_malefic(p) for p in house_occ.get(8, []))
            if not mal_6 and not mal_8:
                yogas.append({
                    "name": "Parvata Yoga",
                    "category": "Fortune Yoga",
                    "planets": [lord1],
                    "houses": [h1],
                    "strength": "Moderate",
                    "description": f"Lagna lord in Kendra/Trikona with no malefics in 6th/8th — Parvata Yoga.",
                    "classical_result": "The native is prosperous, generous, eloquent, learned, fond of mirth, charitable, and famous. Life is stable like a mountain.",
                    "source": "300 Important Combinations, No. 47"
                })

    # ── 19. KAHALA YOGA ──────────────────────────────────────────────────
    lord4 = hlm.get(4)
    if lord4 and lord1 and lord4 in pmap and lord1 in pmap:
        h4 = _house_of(lord4, pmap, lagna_idx)
        h1 = _house_of(lord1, pmap, lagna_idx)
        if h4 and h1 and (h4 in KENDRA_HOUSES or h1 in KENDRA_HOUSES):
            dig4 = _get_dignity(lord4, _sign_of(lord4, pmap) or "Aries")
            if dig4 in ("Exalted", "Own Sign", "Friendly"):
                yogas.append({
                    "name": "Kahala Yoga",
                    "category": "Strength Yoga",
                    "planets": [lord4, lord1],
                    "houses": [h4, h1],
                    "strength": "Moderate",
                    "description": f"4th lord ({lord4}) strong and connected with Lagna lord — Kahala Yoga.",
                    "classical_result": "The native is energetic, bold, daring, heads a small army, and is stubborn yet prosperous. Physical and mental strength are notable.",
                    "source": "300 Important Combinations, No. 49"
                })

    # ── 20. BUDHA-ADITYA YOGA ────────────────────────────────────────────
    if "Sun" in pmap and "Mercury" in pmap:
        if _are_conjunct("Sun", "Mercury", pmap, lagna_idx):
            # Check Mercury is not combust (within ~14 degrees of Sun)
            sun_lon = pmap["Sun"].get("longitude", 0)
            mer_lon = pmap["Mercury"].get("longitude", 0)
            diff = abs(sun_lon - mer_lon)
            if diff > 180:
                diff = 360 - diff
            if diff > 14:  # Mercury not combust
                yogas.append({
                    "name": "Budha-Aditya Yoga",
                    "category": "Intelligence Yoga",
                    "planets": ["Sun", "Mercury"],
                    "houses": [_house_of("Sun", pmap, lagna_idx)],
                    "strength": "Moderate",
                    "description": "Sun and Mercury conjunct (Mercury not combust) — Budha-Aditya Yoga.",
                    "classical_result": "The native is sweet-tongued, clever, scholarly, virtuous, and of good reputation. Intelligence and communication abilities are outstanding.",
                    "source": "300 Important Combinations, Solar Yogas"
                })

    # ── 21. NEECHABHANGA RAJA YOGA ───────────────────────────────────────
    for planet in CLASSICAL_PLANETS:
        if planet not in pmap:
            continue
        sign = _sign_of(planet, pmap)
        if not sign or sign != DEBILITATION_SIGNS.get(planet):
            continue
        # Check cancellation conditions
        deb_lord = SIGN_LORDS.get(sign, "")
        exalt_sign = EXALTATION_SIGNS.get(planet, "")
        exalt_lord = SIGN_LORDS.get(exalt_sign, "") if exalt_sign else ""

        cancel = False
        # a) Lord of debilitation sign in kendra from Lagna or Moon
        if deb_lord in pmap:
            deb_lord_h = _house_of(deb_lord, pmap, lagna_idx)
            if deb_lord_h in KENDRA_HOUSES:
                cancel = True
        # b) Lord of exaltation sign in kendra from Lagna
        if exalt_lord and exalt_lord in pmap:
            exalt_lord_h = _house_of(exalt_lord, pmap, lagna_idx)
            if exalt_lord_h in KENDRA_HOUSES:
                cancel = True
        # c) Planet that gets exalted in debilitation sign aspects the debilitated planet
        for other_p, ex_sign in EXALTATION_SIGNS.items():
            if ex_sign == sign and other_p in pmap:
                oh = _house_of(other_p, pmap, lagna_idx)
                ph = _house_of(planet, pmap, lagna_idx)
                if oh and ph and _in_kendra_from(ph, oh):
                    cancel = True

        if cancel:
            yogas.append({
                "name": f"Neechabhanga Raja Yoga ({planet})",
                "category": "Raja Yoga",
                "planets": [planet],
                "houses": [_house_of(planet, pmap, lagna_idx)],
                "strength": "Strong",
                "description": f"Debilitated {planet} has cancellation conditions met — Neechabhanga Raja Yoga.",
                "classical_result": "The debilitation is cancelled and the planet functions as if exalted. The native rises from humble beginnings to great heights. Adversity becomes the foundation of unprecedented success.",
                "source": "300 Important Combinations, Neechabhanga Section"
            })

    # ── 22. VESHI YOGA (Combination 44) ──────────────────────────────────
    sun_h = _house_of("Sun", pmap, lagna_idx)
    if sun_h:
        h2_from_sun = (sun_h % 12) + 1
        planets_2nd_sun = [p for p in house_occ.get(h2_from_sun, [])
                          if p not in ("Sun", "Moon", "Rahu", "Ketu")]
        if planets_2nd_sun:
            yogas.append({
                "name": "Veshi Yoga",
                "category": "Solar Yoga",
                "planets": planets_2nd_sun,
                "houses": [h2_from_sun],
                "strength": "Moderate",
                "description": f"{', '.join(planets_2nd_sun)} in 2nd from Sun — Veshi Yoga.",
                "classical_result": "The native is even-tempered, happy, fortunate, lazy, and of good character. Results depend on the nature of the planet in the 2nd from Sun.",
                "source": "300 Important Combinations, No. 44"
            })

    # ── 23. VOSHI YOGA (Combination 45) ──────────────────────────────────
    if sun_h:
        h12_from_sun = ((sun_h - 2) % 12) + 1
        planets_12th_sun = [p for p in house_occ.get(h12_from_sun, [])
                           if p not in ("Sun", "Moon", "Rahu", "Ketu")]
        if planets_12th_sun:
            yogas.append({
                "name": "Voshi Yoga",
                "category": "Solar Yoga",
                "planets": planets_12th_sun,
                "houses": [h12_from_sun],
                "strength": "Moderate",
                "description": f"{', '.join(planets_12th_sun)} in 12th from Sun — Voshi Yoga.",
                "classical_result": "The native is charitable, strong, learned, famous, and of good character. Spiritual inclinations and wisdom mark the person.",
                "source": "300 Important Combinations, No. 45"
            })

    # ── 24. UBHAYACHARI YOGA (Combination 46) ────────────────────────────
    if sun_h:
        p2s = [p for p in house_occ.get((sun_h % 12) + 1, [])
               if p not in ("Sun", "Moon", "Rahu", "Ketu")]
        p12s = [p for p in house_occ.get(((sun_h - 2) % 12) + 1, [])
                if p not in ("Sun", "Moon", "Rahu", "Ketu")]
        if p2s and p12s:
            yogas.append({
                "name": "Ubhayachari Yoga",
                "category": "Solar Yoga",
                "planets": p2s + p12s,
                "houses": [],
                "strength": "Strong",
                "description": "Planets on both sides of Sun form Ubhayachari Yoga.",
                "classical_result": "The native is a king or equal to a king — eloquent, handsome, prosperous, and surrounded by comfort. The Sun's energy is flanked and supported on both sides.",
                "source": "300 Important Combinations, No. 46"
            })

    # ── 25. CHANDAL YOGA (Guru-Chandal) ──────────────────────────────────
    if "Jupiter" in pmap and "Rahu" in pmap:
        if _are_conjunct("Jupiter", "Rahu", pmap, lagna_idx):
            yogas.append({
                "name": "Guru Chandal Yoga",
                "category": "Adverse Yoga",
                "planets": ["Jupiter", "Rahu"],
                "houses": [_house_of("Jupiter", pmap, lagna_idx)],
                "strength": "Adverse",
                "description": "Jupiter conjunct Rahu forms Guru Chandal Yoga.",
                "classical_result": "The native may act against tradition, have unconventional beliefs, or face obstacles in matters of faith and ethics. However, this can also grant innovative thinking and breaking of outdated conventions when well-placed.",
                "source": "Classical combination"
            })

    # ── 26. SHAKATA YOGA CANCELLATION CHECK ──────────────────────────────
    # (Already detected above, but mark if cancelled)

    # ── 27. GAJA YOGA (special form) ─────────────────────────────────────
    # Exalted planet in Kendra aspected by Jupiter
    for planet in CLASSICAL_PLANETS:
        if planet not in pmap or planet == "Jupiter":
            continue
        sign = _sign_of(planet, pmap)
        if not sign or sign != EXALTATION_SIGNS.get(planet):
            continue
        h = _house_of(planet, pmap, lagna_idx)
        if h not in KENDRA_HOUSES:
            continue
        # Check Jupiter aspects this house (7th aspect always, plus special)
        jup_h = _house_of("Jupiter", pmap, lagna_idx)
        if jup_h:
            diff = (h - jup_h) % 12
            if diff in (0, 4, 6, 8):  # conjunct, 5th, 7th, 9th aspect
                yogas.append({
                    "name": f"Gaja Yoga ({planet})",
                    "category": "Fortune Yoga",
                    "planets": [planet, "Jupiter"],
                    "houses": [h],
                    "strength": "Very Strong",
                    "description": f"Exalted {planet} in Kendra aspected by Jupiter — Gaja Yoga.",
                    "classical_result": "The native attains exceptional status, wealth beyond expectation, and is honoured by all. The combination of exaltation and Jupiter's blessing creates supreme fortune.",
                    "source": "300 Important Combinations, Special Raja Yogas"
                })

    # ── 28. PARIJATA YOGA ────────────────────────────────────────────────
    if lord1 and lord1 in pmap:
        lord1_sign = _sign_of(lord1, pmap)
        if lord1_sign:
            lord_of_lord1_sign = SIGN_LORDS.get(lord1_sign, "")
            if lord_of_lord1_sign and lord_of_lord1_sign in pmap:
                disp_dig = _get_dignity(lord_of_lord1_sign,
                                        _sign_of(lord_of_lord1_sign, pmap) or "Aries")
                if disp_dig in ("Exalted", "Own Sign"):
                    yogas.append({
                        "name": "Parijata Yoga",
                        "category": "Fortune Yoga",
                        "planets": [lord1, lord_of_lord1_sign],
                        "houses": [],
                        "strength": "Strong",
                        "description": f"Dispositor chain from Lagna lord ends in exalted/own-sign planet — Parijata Yoga.",
                        "classical_result": "The native is happy in the middle and last parts of life, holds authority in a limited sphere, is righteous, fond of war, and respected by kings. Lasting fortune builds over time.",
                        "source": "300 Important Combinations, No. 48"
                    })

    # ── 29. CHAPA YOGA / ARDHA CHANDRA ───────────────────────────────────
    # All planets in consecutive 7 houses
    for start in range(1, 13):
        consecutive = [((start + i - 1) % 12) + 1 for i in range(7)]
        all_in = True
        for pname in CLASSICAL_PLANETS:
            if pname not in pmap:
                continue
            ph = _house_of(pname, pmap, lagna_idx)
            if ph not in consecutive:
                all_in = False
                break
        if all_in:
            yogas.append({
                "name": "Chapa Yoga",
                "category": "Akriti Yoga (Nabhas)",
                "planets": CLASSICAL_PLANETS,
                "houses": consecutive,
                "strength": "Moderate",
                "description": "All planets in seven consecutive houses form Chapa (Bow) Yoga.",
                "classical_result": "The native is fond of stealing, lying, and wandering. A thief and vagabond in classical texts, though modern interpretation suggests unconventional lifestyle and restlessness.",
                "source": "300 Important Combinations, Akriti Yogas"
            })
            break

    return yogas


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: PLANET-IN-HOUSE EFFECTS (from How to Judge a Horoscope)
# ═══════════════════════════════════════════════════════════════════════════════

# Comprehensive planet-in-house interpretation database
# Keys: (planet, house) → interpretation text
PLANET_HOUSE_EFFECTS = {
    # ── SUN IN HOUSES ─────────────────────────────────────────────────────
    ("Sun", 1): {
        "general": "The native has a commanding personality, strong constitution, and natural authority. Self-confidence is high but there may be a tendency toward pride. Leadership comes naturally.",
        "strong": "When dignified, Sun in the 1st grants royal bearing, excellent health, government favour, and a magnetic personality that draws respect from all quarters.",
        "weak": "When afflicted, there may be health issues related to head or eyes, egoism that alienates others, and conflicts with authority figures. Bile-related disorders are possible.",
    },
    ("Sun", 2): {
        "general": "Wealth comes through government or authority figures. Speech is authoritative and commanding. Family life may be strained due to dominating nature.",
        "strong": "Dignified Sun here grants wealth from government, gold, or positions of authority. Family heritage is distinguished and the native accumulates wealth through effort and status.",
        "weak": "Afflicted Sun causes financial losses through government penalties, eye diseases, harsh speech that creates family discord, and troubled relations with the father.",
    },
    ("Sun", 3): {
        "general": "The native has courage and initiative. Relations with siblings may be competitive. Short journeys bring success. Effort and valour bring recognition.",
        "strong": "Grants extraordinary courage, helpful siblings, success in communications, writing, or media. The native becomes known in their immediate community.",
        "weak": "Difficult relations with younger siblings, hearing problems, chest ailments, and efforts that go unrewarded.",
    },
    ("Sun", 4): {
        "general": "Domestic life is marked by authority but also potential tension. Property matters are significant. The native may have government connections related to land or vehicles.",
        "strong": "Grants property, vehicles, government favour regarding land, and comfortable domestic life. The mother may be strong-willed.",
        "weak": "Disturbed domestic peace, difficult relation with mother, heart-related ailments, and loss of property. The native may change residences frequently.",
    },
    ("Sun", 5): {
        "general": "Intelligence and creativity are prominent. Children bring mixed results. The native has a flair for speculation and politics. Past-life merit manifests through intellect.",
        "strong": "Excellent for intelligence, political success, speculative gains, and well-placed children. Romantic nature with dignified expression.",
        "weak": "Few children or difficulties with children, stomach ailments, and losses through speculation. Ego interferes with love affairs.",
    },
    ("Sun", 6): {
        "general": "Excellent for defeating enemies and overcoming obstacles. The native gains through service, medicine, or law. Health requires attention to digestive system.",
        "strong": "Powerful placement for victory over enemies, success in competitive fields, and service-oriented career. The native rises through overcoming challenges.",
        "weak": "Health issues related to stomach and intestines, trouble through enemies who are persistent, and eye problems.",
    },
    ("Sun", 7): {
        "general": "The spouse may be proud or from a distinguished family. Partnerships require balancing ego. Travel and business partnerships are highlighted.",
        "strong": "Marriage to a person of status, successful partnerships, and gain through business. The native's reputation rises through marriage.",
        "weak": "Marital discord due to dominating nature, delayed marriage, partner's health issues, and troubles in partnerships. Humiliation through relationships.",
    },
    ("Sun", 8): {
        "general": "Longevity may be moderate. Interest in occult sciences and hidden matters. Inheritance from father possible. Transformation through crises.",
        "strong": "Long life, inheritance, interest in research and occult, and ability to navigate crises successfully. Government money may come unexpectedly.",
        "weak": "Eye troubles, conflicts with government, poor digestion, separation from father, and health crises that require careful management.",
    },
    ("Sun", 9): {
        "general": "The native may have a distant or authoritative father. Dharmic inclinations with a preference for structured spiritual practice. Long journeys bring fortune.",
        "strong": "Father is prosperous and influential. The native gains through dharma, pilgrimage, and higher learning. Government favour through righteous actions.",
        "weak": "Strained relations with father, obstacles in higher education, and conflicts with religious or spiritual authorities.",
    },
    ("Sun", 10): {
        "general": "Excellent for career, fame, and public standing. The native achieves high position through personal effort. Government service or political career is indicated.",
        "strong": "One of the best placements — commanding authority, fame, high position, government favour, and success in politics or administration. The native leaves a lasting legacy.",
        "weak": "Career setbacks due to arrogance, conflicts with superiors, and public criticism. The native's ambition may exceed their support systems.",
    },
    ("Sun", 11): {
        "general": "Income and gains come through government, authority figures, or high-placed friends. Desires are fulfilled through effort. Social circle includes influential people.",
        "strong": "Excellent for wealth accumulation, powerful friendships, and fulfilled ambitions. The elder sibling may be prosperous.",
        "weak": "Income fluctuations, disappointments through friends, and unfulfilled ambitions despite effort.",
    },
    ("Sun", 12): {
        "general": "Expenditure may be high, especially on spiritual pursuits or government matters. The native may travel abroad. Interest in liberation and spiritual withdrawal.",
        "strong": "Spiritual attainment, success abroad, and expenditure on worthy causes. The native finds meaning through sacrifice and service.",
        "weak": "Eye problems, enmity with government, financial losses, and possible confinement. Father may face difficulties.",
    },

    # ── MOON IN HOUSES ────────────────────────────────────────────────────
    ("Moon", 1): {
        "general": "The native is handsome, magnetic, changeable, and emotional. Public appeal is strong. Health fluctuates with the Moon's phases. The mind is receptive and sensitive.",
        "strong": "Beautiful appearance, popular, wealthy, sensual, and fond of travel. The native attracts public attention and has emotional intelligence.",
        "weak": "Mental restlessness, changeable temperament, health issues related to water or fluids, and dependency on others for emotional stability.",
    },
    ("Moon", 2): {
        "general": "Wealthy through food, liquids, or public dealings. Sweet speech and attractive face. Family life is emotionally rich but changeable.",
        "strong": "Accumulation of wealth, melodious voice, good food habits, and happy family life. The native may work in food or hospitality industries.",
        "weak": "Financial fluctuations, eye troubles (especially left eye), emotional eating habits, and family instability.",
    },
    ("Moon", 3): {
        "general": "Imaginative mind, many short journeys, and good relations with siblings. The native is resourceful and adaptable in communications.",
        "strong": "Creative intelligence, successful siblings, and gains through writing, travel, or communication. Courage comes from emotional conviction.",
        "weak": "Mental restlessness, troubled sibling relations, and fruitless short journeys. Ear problems possible.",
    },
    ("Moon", 4): {
        "general": "Strong attachment to home, mother, and land. The native seeks emotional security through property and domestic comfort. Very sensitive to environment.",
        "strong": "Excellent — comfortable home, loving mother, many vehicles, landed property, and deep contentment. The native creates a nurturing environment.",
        "weak": "Emotional disturbances, mother's health issues, changing residences, and mental unrest despite material comforts.",
    },
    ("Moon", 5): {
        "general": "The native is intelligent, emotional about children, and has good speculative instincts. Romance is emotionally driven. Creative imagination is powerful.",
        "strong": "Intelligent children, success in speculation, emotional creativity, and romantic happiness. Past-life blessings manifest as emotional wisdom.",
        "weak": "Worry about children, emotional losses in speculation, and mood swings affecting romantic relationships.",
    },
    ("Moon", 6): {
        "general": "The native may have stomach-related health issues. Service to others is emotionally motivated. Enemies may include women or emotional manipulators.",
        "strong": "Success in service or medical fields, victory over enemies through emotional intelligence, and ability to heal others.",
        "weak": "Digestive troubles, emotional enemies, depression, and health issues related to water imbalance. Maternal health may suffer.",
    },
    ("Moon", 7): {
        "general": "The spouse is emotional, beautiful, and possibly changeable. Marriage is emotionally intense. Business partnerships involve the public.",
        "strong": "Beautiful and devoted spouse, happy marriage, successful public dealings, and gains through partnerships.",
        "weak": "Emotional turmoil in marriage, changeable partner, and instability in partnerships. Multiple relationships possible.",
    },
    ("Moon", 8): {
        "general": "Emotional sensitivity to hidden matters and occult. Longevity affected by mental state. Inheritance through mother possible. Chronic health concerns.",
        "strong": "Long life, inheritance, intuitive abilities, and interest in occult or psychology. The native understands hidden emotional currents.",
        "weak": "Mental anguish, chronic illness, troubled inheritance, and emotional crises. Depression and anxiety are indicated.",
    },
    ("Moon", 9): {
        "general": "The native is religiously inclined, devoted to mother and dharma. Fortune comes through emotional intelligence and intuition. Pilgrimage brings peace.",
        "strong": "Blessed with fortune, dharmic nature, good mother, and success through higher learning. The native's emotional wisdom becomes their greatest asset.",
        "weak": "Emotional conflicts with religious beliefs, mother's health issues, and obstructed fortune.",
    },
    ("Moon", 10): {
        "general": "Career involves the public, women, liquids, or emotional services. The native has a public-facing role and fluctuating career path.",
        "strong": "Famous and popular career, favour from women and the public, success in hospitality or healthcare, and many career achievements.",
        "weak": "Unstable career, public criticism, and emotional instability affecting professional life. Career changes frequently.",
    },
    ("Moon", 11): {
        "general": "Gains through women, the public, and emotional connections. Friendships are numerous but emotionally dependent. Desires are largely fulfilled.",
        "strong": "Excellent for wealth, fulfilled desires, many friends, and emotional satisfaction. Income through public-facing work.",
        "weak": "Emotional dependency on friends, fluctuating income, and unfulfilled emotional desires.",
    },
    ("Moon", 12): {
        "general": "Expenditure on comforts and emotional pursuits. The native may live abroad. Sleep disturbances possible. Spiritual inclinations are emotionally motivated.",
        "strong": "Spiritual attainment through devotion, success abroad, and compassionate service. The native finds peace in solitude.",
        "weak": "Insomnia, eye troubles (left eye), emotional losses, and separation from homeland. Mental anguish in isolation.",
    },

    # ── MARS IN HOUSES ────────────────────────────────────────────────────
    ("Mars", 1): {
        "general": "The native is courageous, energetic, muscular, and assertive. A fighter's spirit with possible scars or marks on the body. Leadership through action.",
        "strong": "Powerful physique, commanding presence, military or competitive success, and victory over enemies. The native achieves through bold action.",
        "weak": "Hot-tempered, accident-prone, blood-related disorders, and head injuries. Aggression creates enemies.",
    },
    ("Mars", 2): {
        "general": "Harsh speech, wealth through real estate or engineering. Family life may be combative. Food preferences lean toward spicy or hot.",
        "strong": "Wealth through property, engineering, or military service. The native is assertive in financial matters and accumulates through effort.",
        "weak": "Harsh and wounding speech, family quarrels, eye problems, and financial losses through impulsive decisions.",
    },
    ("Mars", 3): {
        "general": "Extremely courageous and adventurous. Relations with siblings involve competition. Success through effort and initiative. The native cannot sit idle.",
        "strong": "Extraordinary courage, helpful brothers, success in athletics or military, and a pioneering spirit. One of Mars's best placements.",
        "weak": "Dangerous adventures, sibling conflicts, and ear problems. Reckless behavior leads to injuries.",
    },
    ("Mars", 4): {
        "general": "Domestic life involves conflict or construction. Property matters are active. The mother may be strong-willed. Heart health needs attention.",
        "strong": "Property through own effort, vehicles, and land. The native builds from scratch and creates lasting foundations.",
        "weak": "Domestic discord, mother's health issues, heart problems, and loss of property. Accidents at home possible.",
    },
    ("Mars", 5): {
        "general": "Children may be few but courageous. Speculative instincts are aggressive. Intelligence is sharp but impulsive. Romantic nature is passionate.",
        "strong": "Children with martial qualities, success in competitive fields, sharp intelligence, and gains through boldness.",
        "weak": "Miscarriage or difficulty with children, losses in speculation, and impulsive romantic entanglements that cause harm.",
    },
    ("Mars", 6): {
        "general": "Excellent for defeating enemies and overcoming diseases. The native excels in competitive environments. Health is strong when Mars is well-placed.",
        "strong": "Victory over enemies, success in surgery or military, excellent health, and competitive prowess. One of Mars's best houses.",
        "weak": "Accidents, blood disorders, surgical issues, and persistent enemies. Inflammatory diseases.",
    },
    ("Mars", 7): {
        "general": "The spouse is energetic and possibly combative. Marriage involves passion and conflict. Partnerships in business require careful management.",
        "strong": "Passionate marriage, energetic spouse, success in business through bold action, and gains through partnerships.",
        "weak": "Marital conflict (Kuja Dosha), spouse's health issues, and business disputes. Early loss of partner in severe cases.",
    },
    ("Mars", 8): {
        "general": "Accidents, surgeries, and transformative crises mark the life. Interest in occult and research. Inheritance through conflict.",
        "strong": "Long life through resilience, research abilities, occult knowledge, and ability to survive extreme situations.",
        "weak": "Accidents, piles, blood disorders, surgical operations, and danger from fire or weapons. Chronic ailments.",
    },
    ("Mars", 9): {
        "general": "The native may have conflicts with father or spiritual authorities. Courage in dharmic pursuits. Long journeys may involve risk.",
        "strong": "Father is courageous, fortune through bold action, success in foreign lands, and dharmic warrior spirit.",
        "weak": "Conflicts with father, obstacles in higher education, and quarrels with religious authorities. Hot-headed approach to spiritual matters.",
    },
    ("Mars", 10): {
        "general": "Career involves authority, engineering, military, surgery, or competitive fields. The native achieves through bold, decisive action.",
        "strong": "Excellent for career success through authority and boldness. Military, police, surgery, or engineering bring fame. The native rises to commanding positions.",
        "weak": "Career controversies, conflicts with superiors, and professional setbacks due to aggression. Reputation damaged by impulsive actions.",
    },
    ("Mars", 11): {
        "general": "Income through property, engineering, or competitive fields. Friendships with courageous people. Desires fulfilled through effort.",
        "strong": "Excellent for wealth, powerful allies, fulfilled ambitions, and elder siblings who are successful.",
        "weak": "Injury through friends, income through questionable means, and conflicts in social circles.",
    },
    ("Mars", 12): {
        "general": "Expenditure on property or legal matters. The native may live abroad. Hidden enemies. Sexual expenditure. Eye problems.",
        "strong": "Success abroad, property investments, and spiritual warrior energy. The native battles inner demons successfully.",
        "weak": "Financial losses, imprisonment risk, eye diseases, and expenditure that exceeds income. Hidden enemies are dangerous.",
    },

    # ── JUPITER IN HOUSES ─────────────────────────────────────────────────
    ("Jupiter", 1): {
        "general": "The native is wise, optimistic, well-built, and blessed with good fortune. Natural teacher and counsellor. Health is generally robust.",
        "strong": "Handsome appearance, noble character, long life, wealth, good children, and high moral standing. One of the most fortunate placements.",
        "weak": "Overweight, over-optimistic, liver disorders, and a tendency to preach. Good intentions may not always translate to results.",
    },
    ("Jupiter", 2): {
        "general": "Wealth through knowledge, teaching, or advisory roles. Speech is wise and measured. Family values are strong. Accumulation is steady.",
        "strong": "Excellent for wealth, eloquent speech, strong family values, and good dietary habits. The native becomes a respected counsellor.",
        "weak": "Excessive spending on education or religious matters, speech that lacks practical application, and family disputes over dharmic principles.",
    },
    ("Jupiter", 3): {
        "general": "The native lacks courage in the traditional sense but succeeds through wisdom. Siblings may be scholarly. Communication involves teaching.",
        "strong": "Wise siblings, success through writing or education, and intellectual courage. The native teaches and counsels effectively.",
        "weak": "Lack of physical courage, difficult sibling relations, and communication that is too theoretical. Hearing difficulties.",
    },
    ("Jupiter", 4): {
        "general": "Blessed domestic life, property, and vehicles. The mother is wise and religious. The native finds deep happiness through home and family.",
        "strong": "Excellent — large property, comfortable home, wise mother, many vehicles, and deep contentment. Higher education is successful.",
        "weak": "Religious discord at home, over-attachment to comfort, liver problems, and mother's health issues related to weight.",
    },
    ("Jupiter", 5): {
        "general": "Children are wise and fortunate. Intelligence is broad and philosophical. Speculative success through wisdom. Past-life merit manifests strongly.",
        "strong": "One of the best placements — wise children, brilliant mind, success in education, speculation, and politics. The native is blessed by past-life dharma.",
        "weak": "Few children despite desire, theoretical intelligence that lacks practical application, and over-reliance on luck in speculation.",
    },
    ("Jupiter", 6): {
        "general": "The native overcomes enemies through wisdom and dharmic conduct. Health is generally good but liver needs care. Service to others is rewarding.",
        "strong": "Victory over enemies, success in healing or advisory roles, and excellent health through wise living. Debts are cleared through dharmic effort.",
        "weak": "Liver and weight issues, enemies who exploit religious sentiment, and health neglect due to over-confidence.",
    },
    ("Jupiter", 7): {
        "general": "The spouse is wise, virtuous, and from a good family. Marriage brings expansion and fortune. Partnerships are beneficial.",
        "strong": "Excellent marriage, wise and beautiful spouse, successful partnerships, and expansion through relationships.",
        "weak": "Spouse may be dominating or overly moralistic, liver issues, and excessive expectations in marriage.",
    },
    ("Jupiter", 8): {
        "general": "Long life and interest in occult, astrology, or philosophy. Inheritance is possible. The native transforms through wisdom.",
        "strong": "Long life, significant inheritance, deep occult knowledge, and wisdom gained through crises. The native becomes a mystic or researcher.",
        "weak": "Chronic health issues, delayed inheritance, and spiritual crises. Over-confidence in dangerous situations.",
    },
    ("Jupiter", 9): {
        "general": "One of Jupiter's best houses. The native is deeply dharmic, blessed by fortune, and respected as a guide or teacher.",
        "strong": "Excellent — father is prosperous, fortune is abundant, higher education succeeds, and spiritual wisdom is profound. The native becomes a guru or guide.",
        "weak": "Dogmatic religious views, over-reliance on luck, and father's health concerns. Fortune comes but may not be retained.",
    },
    ("Jupiter", 10): {
        "general": "Career involves education, law, banking, or advisory roles. The native achieves high professional standing through wisdom and ethics.",
        "strong": "Excellent career success, public honour, ethical leadership, and professional fame. The native's career serves a higher purpose.",
        "weak": "Career disappointments despite qualifications, and ethical dilemmas in professional life. Over-expansion leads to setbacks.",
    },
    ("Jupiter", 11): {
        "general": "Income and gains through wisdom, education, or advisory work. Friendships with wise and wealthy people. Desires are largely fulfilled.",
        "strong": "Excellent for wealth, influential friends, fulfilled ambitions, and prosperous elder siblings. The native achieves beyond expectations.",
        "weak": "Over-reliance on connections, income that comes with moral compromises, and friends who are more theoretical than helpful.",
    },
    ("Jupiter", 12): {
        "general": "Expenditure on spiritual and charitable causes. The native may travel abroad for education. Interest in liberation (moksha).",
        "strong": "Spiritual attainment, success abroad, charitable nature, and moksha-oriented life. The native finds meaning through sacrifice.",
        "weak": "Excessive spending, financial losses through misplaced generosity, and spiritual confusion. Institutional confinement possible.",
    },

    # ── VENUS IN HOUSES ───────────────────────────────────────────────────
    ("Venus", 1): {
        "general": "The native is attractive, charming, and artistically inclined. Life is marked by comfort and sensual pleasures. Social grace is prominent.",
        "strong": "Beautiful appearance, artistic talent, wealthy, and blessed with comforts and vehicles. The native attracts love and abundance naturally.",
        "weak": "Over-indulgence in sensual pleasures, vanity, and health issues from excess. Relationships become complicated.",
    },
    ("Venus", 2): {
        "general": "Wealth through art, luxury goods, or beauty-related fields. Speech is sweet and poetic. Family life is comfortable and harmonious.",
        "strong": "Excellent for wealth, beautiful voice, happy family, and accumulation of fine things. The native lives in material comfort.",
        "weak": "Excessive spending on luxury, dental or facial problems, and family discord related to indulgence.",
    },
    ("Venus", 3): {
        "general": "Artistic skills in communication, good relations with sisters, and love of travel. The native expresses creatively through writing or media.",
        "strong": "Success in arts, media, or creative communication. Helpful sisters and pleasant short journeys. Artistic courage.",
        "weak": "Superficial communications, strained sister relations, and creative efforts that lack depth.",
    },
    ("Venus", 4): {
        "general": "Beautiful home, comfortable domestic life, and fine vehicles. The mother is beautiful and supportive. Deep love of home and family.",
        "strong": "Excellent — luxurious home, many vehicles, loving mother, and deep domestic happiness. Property accumulation through Venus-related means.",
        "weak": "Over-attachment to luxury, domestic discord over indulgences, and heart ailments from excess.",
    },
    ("Venus", 5): {
        "general": "Romantic nature, creative intelligence, and love of entertainment. Children (especially daughters) bring happiness. Speculative luck in Venus-ruled areas.",
        "strong": "Romantic happiness, creative success, fortunate children, and gains through entertainment or art. Past-life merit in love manifests.",
        "weak": "Complicated love affairs, daughters' health concerns, and losses in speculation related to luxury goods.",
    },
    ("Venus", 6): {
        "general": "Service in beauty or health fields. Enemies may include women. Health requires attention to reproductive and kidney systems.",
        "strong": "Success in health, beauty, or service industries. Victory over enemies through charm and diplomacy.",
        "weak": "Reproductive health issues, kidney problems, enemies among women, and service that does not bring appropriate reward.",
    },
    ("Venus", 7): {
        "general": "Excellent for marriage — the spouse is beautiful, refined, and loving. Partnerships are profitable. Travel and commerce flourish.",
        "strong": "One of the best placements — beautiful and loving spouse, happy marriage, profitable partnerships, and social grace.",
        "weak": "Excessive sensuality in marriage, partner's health issues, and multiple relationships. Over-dependence on partner.",
    },
    ("Venus", 8): {
        "general": "Inheritance through spouse. Interest in occult or tantra. Longevity is generally good. Transformation through relationships.",
        "strong": "Long life, wealth through spouse, and deep knowledge of hidden matters. The native masters the mysteries of relationships.",
        "weak": "Reproductive health issues, troubled inheritance, and emotional crises in relationships. Sexual excess causes problems.",
    },
    ("Venus", 9): {
        "general": "Fortune through art, beauty, or relationships. Father may be artistic or wealthy. Pilgrimage to beautiful places brings blessing.",
        "strong": "Fortune through Venus-ruled pursuits, beautiful spouse of dharmic nature, and higher learning in arts. Father is prosperous.",
        "weak": "Religious conflicts related to pleasure, father's relationship problems, and fortune that is not easily retained.",
    },
    ("Venus", 10): {
        "general": "Career in art, entertainment, luxury, diplomacy, or beauty-related fields. The native achieves fame through creative or social work.",
        "strong": "Excellent for career in arts, fashion, diplomacy, or entertainment. Public favour and fame through grace and beauty.",
        "weak": "Career setbacks due to indulgence, reputation damaged by romantic scandals, and professional over-reliance on charm.",
    },
    ("Venus", 11): {
        "general": "Gains through art, women, and luxury trade. Social circle includes artists and wealthy individuals. Desires for comfort are fulfilled.",
        "strong": "Excellent for wealth, artistic friendships, and fulfilled desires. Income through beauty, luxury, or entertainment industries.",
        "weak": "Excessive spending on pleasure, friends who encourage indulgence, and unfulfilled romantic desires.",
    },
    ("Venus", 12): {
        "general": "Expenditure on pleasure, luxury, and foreign travel. Bed pleasures are prominent. Interest in fine arts and spiritual aesthetics.",
        "strong": "Success abroad, luxurious lifestyle, artistic spiritual practices, and comforts in bedroom. The native enjoys refined pleasures.",
        "weak": "Excessive spending on pleasure, eye problems, and financial losses through romantic entanglements. Separation from homeland.",
    },

    # ── SATURN IN HOUSES ──────────────────────────────────────────────────
    ("Saturn", 1): {
        "general": "The native is serious, disciplined, hardworking, and may appear older than actual age. Life involves struggle and perseverance.",
        "strong": "Disciplined character, authority through hard work, long life, and mastery through patience. The native builds lasting structures.",
        "weak": "Chronic health issues, melancholic temperament, delayed success, and a childhood marked by hardship. Bone and joint problems.",
    },
    ("Saturn", 2): {
        "general": "Wealth comes slowly through sustained effort. Speech is measured and serious. Family life involves responsibility and duty.",
        "strong": "Steady wealth accumulation through discipline, serious and truthful speech, and strong family values rooted in duty.",
        "weak": "Financial hardship, harsh speech, dental problems, and family responsibilities that feel burdensome. Slow wealth growth.",
    },
    ("Saturn", 3): {
        "general": "Courage through patience and endurance. Younger siblings may face hardship. The native succeeds through persistent effort.",
        "strong": "Extraordinary patience, success through persistent effort, and siblings who are disciplined. The native's determination is unshakeable.",
        "weak": "Difficulties with siblings, hearing problems, chest ailments, and courage that comes too late. Effort seems unrewarded.",
    },
    ("Saturn", 4): {
        "general": "Domestic life involves hardship or responsibility. Property matters are delayed but eventual. The mother may face difficulties.",
        "strong": "Property through sustained effort, old or traditional homes, and deep emotional resilience. The native builds lasting foundations through patience.",
        "weak": "Domestic unhappiness, mother's health issues, loss of property, heart problems, and chronic dissatisfaction with home life.",
    },
    ("Saturn", 5): {
        "general": "Children may come late or face difficulties. Intelligence is deep and methodical. Speculation should be avoided. Discipline in creative pursuits.",
        "strong": "Methodical intelligence, disciplined children (though few), success in structured learning, and gains through patience rather than luck.",
        "weak": "Delayed or denied children, stomach ailments, depression, and losses in speculation. Creative blocks and melancholy.",
    },
    ("Saturn", 6): {
        "general": "Excellent for overcoming enemies through persistence. Health requires attention but improves over time. Service-oriented success.",
        "strong": "Victory over enemies and diseases through persistence, success in service-oriented career, and excellent health in later life.",
        "weak": "Chronic diseases, persistent enemies, legal troubles, and health issues that are slow to resolve.",
    },
    ("Saturn", 7): {
        "general": "Marriage is delayed but serious. The spouse is older, mature, or from a different background. Partnerships require patience.",
        "strong": "Stable and enduring marriage (though delayed), mature spouse, successful long-term partnerships, and gains through patience in relationships.",
        "weak": "Significantly delayed marriage, cold spouse, marital hardship, and partnerships that feel burdensome. Possible death or separation of spouse.",
    },
    ("Saturn", 8): {
        "general": "Long life is indicated. Interest in research, occult, and hidden matters. Chronic ailments possible. Transformation through endurance.",
        "strong": "Very long life, deep research abilities, inheritance through patience, and mastery of difficult subjects. The native endures and transcends.",
        "weak": "Chronic ailments (piles, joint pain), troubled inheritance, and prolonged periods of darkness. Accidents involving falls.",
    },
    ("Saturn", 9): {
        "general": "Dharmic path involves discipline and structured practice. Father may face hardship. Fortune comes late but is lasting.",
        "strong": "Disciplined spiritual practice, fortune through patience, and father who teaches through example of hardship. Wisdom of old age.",
        "weak": "Strained relation with father, obstacles in higher education, delayed fortune, and rigid religious views.",
    },
    ("Saturn", 10): {
        "general": "Career involves hard work, authority, and slow but steady rise. Government or institutional work is favoured. The native builds lasting professional structures.",
        "strong": "Excellent for career through sustained effort — government position, administrative authority, and professional respect earned over time. The native becomes an institution builder.",
        "weak": "Career delays, clashes with authority, professional humiliation, and work that feels like endless drudgery. Success comes very late.",
    },
    ("Saturn", 11): {
        "general": "Gains come slowly but are lasting. Friendships are few but loyal. Elder siblings may face hardship. Ambitions fulfilled through patience.",
        "strong": "Steady income, loyal friends, fulfilled long-term ambitions, and gains through government or institutional connections.",
        "weak": "Delayed income, disappointing friendships, elder sibling's hardship, and ambitions that take very long to materialize.",
    },
    ("Saturn", 12): {
        "general": "Expenditure on duty and responsibility. The native may live abroad. Interest in solitude and spiritual discipline. Possible confinement.",
        "strong": "Spiritual discipline, success abroad through hard work, and detachment that brings inner peace. The native finds freedom through surrender.",
        "weak": "Financial losses, imprisonment, exile, chronic foot or eye problems, and expenditure on hospital or legal matters.",
    },

    # ── MERCURY IN HOUSES ─────────────────────────────────────────────────
    ("Mercury", 1): {
        "general": "The native is intelligent, youthful, communicative, and adaptable. Intellectual pursuits dominate. The mind is quick and versatile.",
        "strong": "Brilliant intellect, eloquent speech, youthful appearance, and success in trade, writing, or communication fields.",
        "weak": "Nervous temperament, indecisive nature, skin problems, and intellectual restlessness that prevents depth.",
    },
    ("Mercury", 2): {
        "general": "Wealth through trade, communication, or intellectual work. Speech is clever and witty. Financial acumen is strong.",
        "strong": "Excellent for wealth through trade, eloquent speech, mathematical ability, and happy family life through communication.",
        "weak": "Speech disorders, financial losses through bad deals, and family discord through misunderstanding.",
    },
    ("Mercury", 3): {
        "general": "Excellent for communication, writing, and short travels. The native excels in media, publishing, or trading. Siblings are intellectual.",
        "strong": "One of Mercury's best placements — brilliant writer, successful trader, helpful siblings, and unmatched communication skills.",
        "weak": "Nervous energy, restless siblings, and communication that is too clever for its own good.",
    },
    ("Mercury", 4): {
        "general": "Intellectual home environment, property through trade, and education-focused upbringing. The mother is intelligent.",
        "strong": "Property through trade, educated mother, comfortable home with many books, and success in education.",
        "weak": "Mental restlessness at home, domestic instability, and mother's nervous condition.",
    },
    ("Mercury", 5): {
        "general": "Sharp intelligence, clever children, success in education, and speculative ability through analysis. Creative writing talent.",
        "strong": "Brilliant mind, intelligent children, success in examinations and speculation, and literary talent.",
        "weak": "Over-analysis that prevents action, nervous children, and losses in speculation through overthinking.",
    },
    ("Mercury", 6): {
        "general": "Success in service through intellectual skills. Health issues related to nerves and skin. The native outsmarts enemies.",
        "strong": "Victory over enemies through intelligence, success in legal or medical fields, and health management through knowledge.",
        "weak": "Nervous disorders, skin diseases, intestinal problems, and enemies who are intellectually clever.",
    },
    ("Mercury", 7): {
        "general": "The spouse is intelligent and communicative. Business partnerships involve trade or communication. Marriage involves intellectual companionship.",
        "strong": "Intelligent spouse, successful business partnerships, and marriage based on mental compatibility and communication.",
        "weak": "Spouse is too critical or analytical, communication breakdowns in marriage, and deceptive business partners.",
    },
    ("Mercury", 8): {
        "general": "Interest in research, investigation, and occult. Intelligence delves into hidden matters. Inheritance through documents or trade.",
        "strong": "Research ability, inheritance through legal documents, detective-like mind, and longevity through health awareness.",
        "weak": "Nervous breakdowns, forged documents, and losses through deception. Mental health needs attention.",
    },
    ("Mercury", 9): {
        "general": "Higher education and intellectual dharmic practice. The native learns through analysis and reasoning. Father may be intellectual.",
        "strong": "Success in higher education, intellectual dharma, and teaching. Father is scholarly. Long journeys for learning.",
        "weak": "Doubt-ridden spiritual life, father's intellectual arrogance, and education that lacks practical application.",
    },
    ("Mercury", 10): {
        "general": "Career in communication, trade, writing, teaching, or technology. The native's intellect drives professional success.",
        "strong": "Excellent career through intellect — successful writer, trader, teacher, or technologist. Professional versatility is an asset.",
        "weak": "Career instability due to too many interests, professional deception, and communication failures at work.",
    },
    ("Mercury", 11): {
        "general": "Gains through trade, communication, and intellectual networks. Friends are clever and helpful. Desires fulfilled through wit.",
        "strong": "Excellent for income through trade and communication, intellectual friends, and fulfilled ambitions through cleverness.",
        "weak": "Unreliable friends, income through deception, and desires that change before fulfillment.",
    },
    ("Mercury", 12): {
        "general": "Expenditure on education or communication. The native may write in seclusion. Interest in foreign languages.",
        "strong": "Success abroad through intellect, foreign language skills, and writing in solitude. Analytical spiritual practice.",
        "weak": "Financial losses through bad paperwork, nervous insomnia, and communication failures with foreign entities.",
    },

    # ── RAHU IN HOUSES ────────────────────────────────────────────────────
    ("Rahu", 1): {
        "general": "The native has an unusual or magnetic personality. Unconventional approach to life. Strong desire for worldly experience. May appear exotic or foreign.",
        "strong": "Powerful personality, success in foreign lands, unconventional path to fame, and ability to influence masses.",
        "weak": "Identity confusion, health issues from unknown causes, deception, and restless search for meaning.",
    },
    ("Rahu", 7): {
        "general": "Unconventional marriage or foreign spouse. Partnerships may be unusual. The native is attracted to people from different cultures.",
        "strong": "Marriage to a foreigner or unconventional person. Success in foreign business partnerships.",
        "weak": "Marital deception, spouse may go astray, and partnerships involve hidden agendas.",
    },
    ("Rahu", 10): {
        "general": "Unconventional career path. The native may achieve sudden fame. Career involves technology, foreign connections, or masses.",
        "strong": "Sudden rise in career, fame through unconventional means, and success in technology or foreign trade.",
        "weak": "Career scandals, sudden falls from position, and professional deception.",
    },

    # ── KETU IN HOUSES ────────────────────────────────────────────────────
    ("Ketu", 1): {
        "general": "The native is spiritual, detached, and may have an unusual appearance. Past-life tendencies strongly influence the personality.",
        "strong": "Spiritual awareness, intuitive abilities, and detachment that brings inner peace.",
        "weak": "Identity crisis, health issues from unknown causes, and difficulty connecting with the material world.",
    },
    ("Ketu", 12): {
        "general": "Excellent for spiritual liberation. The native is naturally detached and drawn to moksha. Expenditure on spiritual pursuits.",
        "strong": "One of Ketu's best placements — spiritual awakening, moksha-oriented life, and detachment from material bondage.",
        "weak": "Excessive withdrawal, isolation, and difficulty functioning in the material world.",
    },
}


def planet_in_house_effects(planet: str, house: int) -> dict:
    """
    Return B.V. Raman's interpretation of a planet in a given house.
    Returns dict with 'general', 'strong', 'weak' keys.
    """
    key = (planet, house)
    if key in PLANET_HOUSE_EFFECTS:
        return PLANET_HOUSE_EFFECTS[key]
    # Generic fallback
    return {
        "general": f"{planet} in House {house} influences the significations of this house according to its inherent nature and dignity.",
        "strong": f"When well-placed, {planet} strengthens the house and delivers its positive significations.",
        "weak": f"When afflicted, {planet} may obstruct or distort the natural significations of House {house}.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: DASHA INTERPRETATION (from Hindu Predictive Astrology)
# ═══════════════════════════════════════════════════════════════════════════════

DASHA_YEARS = {
    "Sun": 6, "Moon": 10, "Mars": 7, "Rahu": 18,
    "Jupiter": 16, "Saturn": 19, "Mercury": 17,
    "Ketu": 7, "Venus": 20,
}

MAHADASHA_EFFECTS = {
    "Sun": {
        "general": "A period of 6 years focused on authority, self-expression, government connections, and father-related matters. Health of the native and father are highlighted.",
        "strong": "Rise in position, government favour, gains through authority, recognition, and leadership opportunities. Health is robust, and the native's willpower is at its peak.",
        "weak": "Eye troubles, conflicts with authority, loss of position, father's health issues, and ego-related problems. Fever and bile-related ailments.",
        "sub_periods": {
            "Moon": "Winning favour from superiors, increase in business, fresh enterprises, but possible troubles through women and eye issues.",
            "Mars": "Rheumatic troubles, quarrels, danger of fevers, but also acquisition of wealth in gold and gems, royal favour leading to prosperity.",
            "Rahu": "Many troubles, family disputes, journeys, trouble from relatives and enemies, loss of money, scandals.",
            "Jupiter": "Benefits from friends, increase in education, association with people of high rank, birth of a child, virtuous acts, and court honours.",
            "Saturn": "Constant sickness to family members, new enemies, loss of property, mental worries, displacement from home.",
            "Mercury": "Gain in money, good reputation, new education, but possible trouble through relatives, nervous weakness.",
            "Ketu": "Loss of money, mental affliction, a long journey to a distant place, throat disease, ophthalmias.",
            "Venus": "Gain of money, respect by rulers, likelihood of marriage, increase of property, acquisition of precious stones.",
        },
    },
    "Moon": {
        "general": "A period of 10 years focused on emotions, mind, mother, home, public life, and general happiness. Water-related matters and travel are prominent.",
        "strong": "Public favour, gain of wealth, many friends, comfortable life, successful travel, emotional happiness, and mother's blessings. Popularity and social success.",
        "weak": "Mental restlessness, mother's health issues, domestic disturbances, emotional upheaval, water-related health issues, and changeable fortune.",
        "sub_periods": {
            "Mars": "Quarrels, danger of marital disputes, loss of money, trouble from brothers, danger from fever and fire.",
            "Rahu": "Distress and dangerous diseases, loss of relatives, loss of money, scandals, skin diseases.",
            "Jupiter": "Increase of property, plenty of food, patronage of rulers, birth of a child, success in undertakings.",
            "Saturn": "Wife's death or separation, loss of property, harsh words, mental trouble due to mother, indigestion.",
            "Mercury": "Acquisition of wealth, new clothes and ornaments, intellectual achievement, honour from rulers.",
            "Ketu": "Illness to wife, loss of relatives, stomach ache, loss of property, public criticism.",
            "Venus": "Comforts, acquisition of new clothes, vehicles, romantic happiness, artistic success.",
            "Sun": "Fame, government favour, gain of money through authority, but eye troubles possible.",
        },
    },
    "Mars": {
        "general": "A period of 7 years focused on courage, property, siblings, energy, and competitive matters. Surgery, engineering, and military matters are highlighted.",
        "strong": "Acquisition of wealth and property, victory over enemies, gains through real estate, leadership, and physical prowess. Brothers prosper.",
        "weak": "Accidents, blood disorders, quarrels, surgery, fire-related dangers, sibling problems, and property disputes. Hot temper causes troubles.",
        "sub_periods": {
            "Rahu": "Danger from rulers and robbers, skin diseases, change of residence, journey to a foreign country.",
            "Jupiter": "Favour from superiors, gain of money, birth of children, freedom from illness, public reputation.",
            "Saturn": "Loss of money, disease, danger from arms or operation, litigation, loss of property.",
            "Mercury": "Marriage prospects, knowledge gained, gain of wealth by trade, but fear of insects and enemies.",
            "Ketu": "Family quarrels, loss of money, great sufferings from relatives, poisonous complaints.",
            "Venus": "Acquisition of property, domestic happiness, successful love affairs, religious observances.",
            "Sun": "Royal favour, acquisition of wealth, courage, but fire and heat-related troubles.",
            "Moon": "Domestic comfort, gain of property, emotional happiness, but water-related health concerns.",
        },
    },
    "Jupiter": {
        "general": "A period of 16 years focused on wisdom, expansion, children, dharma, and spiritual growth. Education, law, and religious matters are highlighted.",
        "strong": "Great expansion in all areas — wealth, knowledge, children, spiritual progress, and social status. Teacher or advisory roles bring success. Government favour through dharmic conduct.",
        "weak": "Over-expansion, liver problems, weight gain, false hopes, and religious hypocrisy. Expenditure exceeds income through over-optimism.",
        "sub_periods": {
            "Saturn": "Mixed results — delays but eventual gains through perseverance. Health needs attention. Wisdom through hardship.",
            "Mercury": "Educational success, gains through trade and communication, intellectual achievements, and happy social life.",
            "Ketu": "Spiritual inclinations intensify, possible health issues, detachment from material pursuits.",
            "Venus": "Material prosperity, romantic happiness, artistic appreciation, and social success. One of the best sub-periods.",
            "Sun": "Government favour, rise in position, father's blessings, and authority. Health is strong.",
            "Moon": "Emotional happiness, mother's blessings, public favour, and domestic comfort. Travel brings gains.",
            "Mars": "Energy and courage increase, property gains, but possible conflicts and accidents.",
            "Rahu": "Foreign connections bring gains, but confusion about dharma. Health needs attention.",
        },
    },
    "Saturn": {
        "general": "A period of 19 years focused on discipline, karma, hard work, and structural change. The longest and most transformative Dasha.",
        "strong": "Steady rise through hard work, property acquisition, government position, authority through merit, and lasting achievements. Discipline bears fruit.",
        "weak": "Health challenges (bones, joints, chronic conditions), delays, separations, losses, professional setbacks, and periods of isolation. The weight of karma is felt.",
        "sub_periods": {
            "Mercury": "Intellectual work bears fruit, trade prospers, communication skills improve, but nervous tension possible.",
            "Ketu": "Spiritual awakening through hardship, detachment, possible health crises. Liberation through surrender.",
            "Venus": "Material improvements, comforts increase, relationships improve, but discipline must be maintained.",
            "Sun": "Conflicts with authority, father's health concerns, but possible government connection. Health needs care.",
            "Moon": "Emotional difficulties, mother's health concerns, mental anguish, but eventual emotional maturity.",
            "Mars": "Property disputes, accidents, conflicts, but also courage and decisive action when needed.",
            "Rahu": "Confusion and deception, foreign connections, health mysteries. One of the most challenging sub-periods.",
            "Jupiter": "The best sub-period within Saturn — wisdom, dharma, gradual improvement, and hope through faith.",
        },
    },
    "Mercury": {
        "general": "A period of 17 years focused on intellect, communication, trade, education, and versatility. The mind is sharp and opportunities come through intellectual skills.",
        "strong": "Trade and business flourish, educational achievements, successful writing or communication career, and social cleverness brings gains. The native's versatility is rewarded.",
        "weak": "Nervous disorders, skin problems, indecision, deceptive dealings, and intellectual anxiety. Communication failures cause problems.",
        "sub_periods": {
            "Ketu": "Spiritual analysis, possible skin issues, detachment from intellectual pursuits.",
            "Venus": "Artistic and financial success, happy relationships, social popularity, and material gains.",
            "Sun": "Government favour through intellect, authority positions, but ego conflicts possible.",
            "Moon": "Emotional intelligence improves, public dealings succeed, but mental restlessness.",
            "Mars": "Energy for trade and competition, property gains, but haste causes errors.",
            "Rahu": "Foreign connections, technology gains, but deceptive communications possible.",
            "Jupiter": "Wisdom combines with intellect — education, dharma, and balanced thinking bring success.",
            "Saturn": "Disciplined study, slow but sure gains, health needs attention, but lasting results.",
        },
    },
    "Venus": {
        "general": "A period of 20 years focused on relationships, art, luxury, comfort, and material prosperity. The longest Dasha — marriage, romance, and creativity dominate.",
        "strong": "Excellent period — marriage, wealth, vehicles, fine clothes, artistic success, romantic happiness, and material comfort. Life is pleasurable and fulfilling.",
        "weak": "Over-indulgence, relationship complications, reproductive health issues, financial losses through luxury, and vanity. Excess in all Venus-ruled matters.",
        "sub_periods": {
            "Sun": "Authority through creative expression, government favour, but ego in relationships.",
            "Moon": "Emotional and romantic happiness, public favour, comfortable travel.",
            "Mars": "Passionate relationships, property gains, but conflicts in love possible.",
            "Rahu": "Foreign connections, unconventional relationships, material gains but moral confusion.",
            "Jupiter": "The best sub-period — dharmic prosperity, happy marriage, children, and spiritual growth through beauty.",
            "Saturn": "Discipline in relationships, delayed but lasting comforts, health needs care.",
            "Mercury": "Trade and art combine, intellectual creativity, communication in relationships improves.",
            "Ketu": "Spiritual awakening through relationships, detachment from material excess, artistic depth.",
        },
    },
    "Rahu": {
        "general": "A period of 18 years focused on worldly ambition, foreign connections, technology, and unconventional paths. Rahu amplifies and distorts whatever it touches.",
        "strong": "Sudden rise, foreign success, technological gains, political connections, and unconventional achievements. The native breaks barriers and defies expectations.",
        "weak": "Confusion, deception, health mysteries, scandals, and sudden falls. Obsessive behaviour and addictions. Identity confusion and moral ambiguity.",
        "sub_periods": {
            "Jupiter": "Wisdom tempers Rahu's excess — dharmic connections, spiritual growth despite worldly ambition.",
            "Saturn": "Very challenging — delays, health crises, karmic reckoning, but eventual maturity.",
            "Mercury": "Intellectual gains, foreign communications, technology, but deceptive dealings possible.",
            "Ketu": "Most intense sub-period — spiritual crisis, health issues, past-life karma surfaces. Complete transformation.",
            "Venus": "Material gains, relationships with foreigners, artistic expression, but moral confusion.",
            "Sun": "Authority struggles, father's concerns, government dealings — both gains and conflicts.",
            "Moon": "Emotional turmoil, mother's health, mental restlessness, but intuition sharpens.",
            "Mars": "Accidents, conflicts, but also breakthrough courage. Property gains through unconventional means.",
        },
    },
    "Ketu": {
        "general": "A period of 7 years focused on spirituality, detachment, past-life karma, and liberation. Ketu strips away the unnecessary to reveal the essential.",
        "strong": "Spiritual advancement, occult knowledge, liberation from bondage, and insight into past-life patterns. The native transcends worldly limitations.",
        "weak": "Health mysteries, isolation, loss of direction, and suffering that seems purposeless. Accidents and sudden events. The material world feels hostile.",
        "sub_periods": {
            "Venus": "Material losses but spiritual gains, relationships teach detachment, artistic depth.",
            "Sun": "Authority conflicts, father's concerns, but inner light shines through darkness.",
            "Moon": "Emotional turmoil, mother's concerns, mental anguish, but deep intuition.",
            "Mars": "Accidents, conflicts, but martial courage for spiritual battles. Surgery possible.",
            "Rahu": "Most intense — complete disorientation followed by breakthrough. Health crises possible.",
            "Jupiter": "The best sub-period — spiritual wisdom, dharmic protection, and hope. Guru appears.",
            "Saturn": "Hard karma surfaces, health challenges, but liberation through acceptance.",
            "Mercury": "Analytical detachment, intellectual spiritual practice, but communication difficulties.",
        },
    },
}


def dasha_interpretation(planet: str, sub_planet: Optional[str] = None,
                         planet_map: Optional[dict] = None,
                         lagna_idx: Optional[int] = None) -> dict:
    """
    Return interpretation for a Mahadasha (and optional Bhukti/sub-period).
    Contextualises based on planet's actual chart placement if planet_map provided.
    """
    result = {}
    dasha_data = MAHADASHA_EFFECTS.get(planet, {})

    result["planet"] = planet
    result["years"] = DASHA_YEARS.get(planet, 0)
    result["general"] = dasha_data.get("general", f"Period of {planet} — consult classical texts for detailed results.")

    # Determine strength-specific interpretation
    if planet_map and lagna_idx is not None and planet in planet_map:
        sign = _sign_of(planet, planet_map)
        dignity = _get_dignity(planet, sign) if sign else "Neutral"
        house = _house_of(planet, planet_map, lagna_idx)

        if dignity in ("Exalted", "Own Sign"):
            result["strength_reading"] = dasha_data.get("strong", "")
            result["strength_level"] = "Strong"
        elif dignity in ("Debilitated", "Enemy"):
            result["strength_reading"] = dasha_data.get("weak", "")
            result["strength_level"] = "Weak"
        else:
            result["strength_reading"] = dasha_data.get("strong", "") + " " + dasha_data.get("weak", "")
            result["strength_level"] = "Mixed"

        result["dignity"] = dignity
        result["house"] = house
        result["contextual_note"] = (
            f"{planet} is placed in {dignity} dignity in House {house}. "
            f"The Dasha results will manifest primarily through the significations of House {house} "
            f"and the houses ruled by {planet}."
        )
    else:
        result["strength_reading"] = dasha_data.get("general", "")
        result["strength_level"] = "General"

    # Sub-period interpretation
    if sub_planet:
        sub_data = dasha_data.get("sub_periods", {})
        result["sub_period"] = {
            "planet": sub_planet,
            "reading": sub_data.get(sub_planet, f"Consult classical texts for {planet}-{sub_planet} sub-period results."),
        }

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: YOGA DETAIL LOOKUP
# ═══════════════════════════════════════════════════════════════════════════════

YOGA_DESCRIPTIONS = {
    "Ruchaka Yoga": "Formed when Mars is in own sign or exalted in a Kendra. One of the five Pancha Mahapurusha Yogas. Grants a strong physique, martial valour, command over armies, and fame through courage.",
    "Bhadra Yoga": "Formed when Mercury is in own sign or exalted in a Kendra. One of the five Pancha Mahapurusha Yogas. Grants intellectual brilliance, eloquence, scholarly fame, and long life.",
    "Hamsa Yoga": "Formed when Jupiter is in own sign or exalted in a Kendra. One of the five Pancha Mahapurusha Yogas. Grants righteousness, beauty, learning, spiritual wisdom, and moral authority.",
    "Malavya Yoga": "Formed when Venus is in own sign or exalted in a Kendra. One of the five Pancha Mahapurusha Yogas. Grants beauty, vehicles, domestic happiness, artistic talent, and material prosperity.",
    "Sasa Yoga": "Formed when Saturn is in own sign or exalted in a Kendra. One of the five Pancha Mahapurusha Yogas. Grants command over servants, wealth, power over towns, and strategic authority.",
    "Gajakesari Yoga": "Jupiter in a Kendra from Moon. Grants intelligence, eloquence, lasting fame, wealth, and the ability to overcome obstacles. The native is splendorous like an elephant-king.",
    "Sunapha Yoga": "Planets (other than Sun) in the 2nd from Moon. The native is self-made, wealthy through personal effort, intelligent, and enjoys good reputation.",
    "Anapha Yoga": "Planets (other than Sun) in the 12th from Moon. The native is well-formed, virtuous, eloquent, famous, and free from diseases.",
    "Durudhura Yoga": "Planets on both sides of Moon (2nd and 12th). The native enjoys abundant wealth, vehicles, comforts, and fame.",
    "Kemadruma Yoga": "No planets in 2nd, 12th, or kendras from Moon. Adverse yoga indicating poverty, hardship, and lack of support. Cancelled if Moon is aspected or in Kendra from Lagna.",
    "Adhi Yoga": "Benefics in 6th, 7th, 8th from Moon. The native becomes a commander, minister, or leader — polite, healthy, and prosperous.",
    "Vasumathi Yoga": "Benefics in upachaya houses (3,6,10,11) from Moon. Grants immense wealth and high social status.",
    "Chandra Mangala Yoga": "Moon and Mars conjunct. Wealth through enterprise and earthy products. Brave but possibly unscrupulous.",
    "Budha-Aditya Yoga": "Sun and Mercury conjunct (Mercury not combust). Sweet-tongued, clever, scholarly, and of good reputation.",
    "Neechabhanga Raja Yoga": "Debilitated planet with cancellation conditions met. The native rises from humble beginnings to great heights.",
    "Dharma-Karmadhipati Yoga": "9th and 10th lords connected. Career aligned with dharmic destiny. Authority earned through merit.",
    "Guru Chandal Yoga": "Jupiter conjunct Rahu. May act against tradition but also grants innovative thinking when well-placed.",
    "Sakata Yoga": "Jupiter in 6th or 8th from Moon. Fortune fluctuates like a cart wheel. Cancelled if Jupiter in Kendra from Lagna.",
    "Amala Yoga": "Benefic in 10th house without malefic influence. Spotless character and lasting fame through righteous deeds.",
    "Parvata Yoga": "Lagna lord in Kendra/Trikona with no malefics in 6th/8th. Prosperous, generous, eloquent, and famous.",
    "Lakshmi Yoga": "5th and 9th lords in strong positions. Blessed by Goddess Lakshmi — wealthy, noble, and virtuous.",
}


def get_yoga_details(yoga_name: str) -> str:
    """Return detailed description for a yoga by name."""
    return YOGA_DESCRIPTIONS.get(yoga_name, f"Classical yoga — consult B.V. Raman's texts for detailed description.")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: MASTER FUNCTION — run all rules against a chart
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_chart(positions: dict, birth_dt=None, moon_longitude: float = 0.0) -> dict:
    """
    Run the complete B.V. Raman rule engine against a chart.
    Returns dict with:
      - yogas: list of detected yogas
      - planet_effects: planet-in-house interpretations for all planets
      - dasha_readings: dasha interpretation for current/all periods
    """
    pmap = _planet_map(positions)
    asc = positions.get("ascendant", {})
    lagna_lon = asc.get("longitude", 0.0)
    lagna_idx = int(lagna_lon / 30) % 12

    result = {}

    # 1. Detect all yogas
    try:
        result["yogas"] = detect_all_yogas(positions)
    except Exception as e:
        logger.warning(f"Yoga detection error: {e}")
        result["yogas"] = []

    # 2. Planet-in-house effects for all chart planets
    planet_effects = {}
    for pname in CLASSICAL_PLANETS + ["Rahu", "Ketu"]:
        if pname not in pmap:
            continue
        h = _house_of(pname, pmap, lagna_idx)
        sign = _sign_of(pname, pmap)
        if h and sign:
            effects = planet_in_house_effects(pname, h)
            dignity = _get_dignity(pname, sign)
            planet_effects[pname] = {
                "house": h,
                "sign": sign,
                "dignity": dignity,
                "effects": effects,
                "interpretation": effects.get("strong") if dignity in ("Exalted", "Own Sign") else (
                    effects.get("weak") if dignity in ("Debilitated", "Enemy") else effects.get("general")
                ),
            }
    result["planet_effects"] = planet_effects

    # 3. Dasha readings for all planets
    dasha_readings = {}
    for planet in list(DASHA_YEARS.keys()):
        dasha_readings[planet] = dasha_interpretation(
            planet, planet_map=pmap, lagna_idx=lagna_idx
        )
    result["dasha_readings"] = dasha_readings

    return result
