"""
BPHS (Brihat Parashara Hora Shastra) Interpretation Engine
Generates detailed Vedic astrological house interpretations based on chart data
"""

import json
import os
import re
from typing import List, Dict, Any, Optional

# Constants
SIGN_ORDER = ['Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo', 
              'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces']

SIGN_LORDS = {
    'Aries': 'Mars', 'Taurus': 'Venus', 'Gemini': 'Mercury',
    'Cancer': 'Moon', 'Leo': 'Sun', 'Virgo': 'Mercury',
    'Libra': 'Venus', 'Scorpio': 'Mars', 'Sagittarius': 'Jupiter',
    'Capricorn': 'Saturn', 'Aquarius': 'Saturn', 'Pisces': 'Jupiter'
}

HOUSE_TITLES = {
    1: "1st House — Tanu (Self & Body)",
    2: "2nd House — Dhan (Wealth & Family)",
    3: "3rd House — Sahaj (Courage & Siblings)",
    4: "4th House — Bandhu (Home & Mother)",
    5: "5th House — Putra (Intelligence & Children)",
    6: "6th House — Ari (Enemies & Health)",
    7: "7th House — Yuvati (Marriage & Partnership)",
    8: "8th House — Randhra (Longevity & Transformation)",
    9: "9th House — Dharma (Fortune & Father)",
    10: "10th House — Karma (Career & Status)",
    11: "11th House — Labha (Gains & Income)",
    12: "12th House — Vyaya (Liberation & Losses)",
}

PLANET_BPHS_NAMES = {
    'Sun': 'Sūrya', 'Moon': 'Candr', 'Mars': 'Mangal', 'Mercury': 'Budh',
    'Jupiter': 'Guru', 'Venus': 'Śukr', 'Saturn': 'Śani', 'Rahu': 'Rahu', 'Ketu': 'Ketu'
}

# Global data storage
_lord_effects = None
_house_chapters = None


def _load_json_data():
    """Load JSON data files once, searching near the script file"""
    global _lord_effects, _house_chapters

    if _lord_effects is not None and _house_chapters is not None:
        return

    # Look for JSON files in same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs = [
        script_dir,
        os.path.join(script_dir, '..'),
        '/sessions/gracious-inspiring-shannon',
    ]

    def _find_and_load(filename):
        for d in search_dirs:
            path = os.path.join(d, filename)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        return {}

    try:
        _lord_effects = _find_and_load('lord_effects.json')
    except Exception as e:
        print(f"Error loading lord_effects.json: {e}")
        _lord_effects = {}

    try:
        _house_chapters = _find_and_load('house_chapters.json')
    except Exception as e:
        print(f"Error loading house_chapters.json: {e}")
        _house_chapters = {}


def _get_ascendant_sign(chart_data: List[Dict[str, Any]]) -> str:
    """Extract ascendant sign from chart data"""
    for entry in chart_data:
        if entry.get('planet') in ['Ascendant', 'Lagna']:
            return entry.get('sign', 'Aries')
    
    # Fallback: find planet in house 1
    for entry in chart_data:
        if entry.get('house') == 1:
            return entry.get('sign', 'Aries')
    
    return 'Aries'


def _get_house_sign(ascendant_sign: str, house_num: int) -> str:
    """Calculate which sign occupies a given house"""
    try:
        asc_index = SIGN_ORDER.index(ascendant_sign)
    except ValueError:
        asc_index = 0  # default to Aries if sign name not recognised
    house_index = (asc_index + house_num - 1) % 12
    return SIGN_ORDER[house_index]


def _get_planets_in_house(chart_data: List[Dict[str, Any]], house_num: int) -> List[str]:
    """Get list of planet names in a specific house"""
    planets = []
    for entry in chart_data:
        if entry.get('house') == house_num and entry.get('planet') not in ['Ascendant', 'Lagna']:
            planets.append(entry['planet'])
    return planets


def _get_lord_house(chart_data: List[Dict[str, Any]], lord_name: str) -> int:
    """Find which house the given lord is currently in"""
    for entry in chart_data:
        if entry.get('planet') == lord_name:
            return entry.get('house', 1)
    return 1


def _get_lord_bphs_text(house_num: int, lord_house: int) -> str:
    """Retrieve BPHS sloka text for lord placement"""
    _load_json_data()
    
    if not _lord_effects:
        return ""
    
    # lord_effects is keyed by house number (from where lord rules)
    # inner keys are placement houses (where lord is)
    house_key = str(house_num)
    placement_key = str(lord_house)
    
    text = _lord_effects.get(house_key, {}).get(placement_key, "")
    return text if text else ""


def _clean_chapter_text(text: str) -> str:
    """Clean chapter text for display"""
    if not text:
        return ""
    
    # Remove chapter markers and clean up
    text = re.sub(r'Ch\.\s+\d+\.\s+', '', text)
    text = re.sub(r'[0-9]+\-[0-9]+\.\s+', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _get_house_summary(house_num: int, max_chars: int = 600) -> str:
    """Get first 600 chars of house chapter from BPHS"""
    _load_json_data()
    
    if not _house_chapters:
        return ""
    
    chapter_text = _house_chapters.get(str(house_num), "")
    cleaned = _clean_chapter_text(chapter_text)
    return cleaned[:max_chars] if cleaned else ""


def _extract_planet_notes(house_num: int, planets_in_house: List[str]) -> List[str]:
    """Extract planet-specific passages from house chapter"""
    _load_json_data()
    
    if not _house_chapters or not planets_in_house:
        return []
    
    chapter_text = _house_chapters.get(str(house_num), "")
    if not chapter_text:
        return []
    
    planet_notes = []
    
    for planet in planets_in_house:
        # Get BPHS name for planet
        bphs_name = PLANET_BPHS_NAMES.get(planet, planet)
        
        # Search for planet mentions in chapter text
        # Case-insensitive search
        pattern = re.compile(rf'{re.escape(bphs_name)}.*?[.!?]', re.IGNORECASE | re.DOTALL)
        matches = pattern.findall(chapter_text)
        
        if matches:
            # Get the first match, truncate to 200 chars
            note = matches[0].strip()
            note = re.sub(r'\s+', ' ', note)  # normalize whitespace
            note = note[:200]
            if note:
                planet_notes.append(f"{planet}: {note}")
    
    return planet_notes


def generate_bphs_interpretations(chart_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate BPHS interpretations for all 12 houses
    
    Args:
        chart_data: List of dicts with planet, house, sign, degrees info
        
    Returns:
        List of 12 house interpretation dicts
    """
    _load_json_data()
    
    # Determine ascendant sign
    ascendant_sign = _get_ascendant_sign(chart_data)
    
    houses = []
    
    for house_num in range(1, 13):
        # Get sign occupying this house
        house_sign = _get_house_sign(ascendant_sign, house_num)
        
        # Get lord of this sign
        lord_name = SIGN_LORDS.get(house_sign, 'Sun')
        
        # Find which house this lord is in
        lord_house = _get_lord_house(chart_data, lord_name)
        
        # Get BPHS text for this lord placement
        lord_bphs = _get_lord_bphs_text(house_num, lord_house)
        
        # Get planets in this house
        occupants = _get_planets_in_house(chart_data, house_num)
        
        # Get house summary from chapter
        house_summary = _get_house_summary(house_num)
        
        # Extract planet-specific notes
        planet_notes = _extract_planet_notes(house_num, occupants)
        
        # Build house dict
        house_dict = {
            'house': house_num,
            'title': HOUSE_TITLES.get(house_num, f"{house_num} House"),
            'sign': house_sign,
            'lord': lord_name,
            'lord_house': lord_house,
            'lord_bphs': lord_bphs,
            'occupants': occupants,
            'house_summary': house_summary,
            'planet_notes': planet_notes,
        }
        
        houses.append(house_dict)
    
    return houses


def generate_bphs_from_positions(positions: dict) -> list:
    """
    Wrapper that accepts the `positions` dict format from app.py / chart_gen.py
    and returns BPHS house interpretations.

    positions dict structure:
    {
        "ascendant": {"sign_index": int, "rashi": {"name": str, "lord": str}, ...},
        "planets": [{"name": str, "house": int, "sign_index": int,
                     "rashi": {"name": str}, "longitude": float, ...}, ...]
    }
    """
    # Convert to the flat list format expected by generate_bphs_interpretations
    chart_data = []

    asc = positions.get("ascendant", {})
    asc_sign = asc.get("rashi", {}).get("name", "Aries")
    chart_data.append({
        "planet": "Ascendant",
        "house": 1,
        "sign": asc_sign,
        "degrees": asc.get("sign_deg", 0.0),
    })

    for p in positions.get("planets", []):
        chart_data.append({
            "planet": p.get("name", ""),
            "house": p.get("house", 1),
            "sign": p.get("rashi", {}).get("name", "Aries"),
            "degrees": p.get("longitude", 0.0),
        })

    return generate_bphs_interpretations(chart_data)


def main():
    """Test the engine with sample data"""
    test_data = [
        {'planet': 'Sun', 'house': 1, 'sign': 'Leo', 'degrees': 24.5},
        {'planet': 'Moon', 'house': 3, 'sign': 'Libra', 'degrees': 12.0},
        {'planet': 'Mars', 'house': 5, 'sign': 'Sagittarius', 'degrees': 8.3},
        {'planet': 'Mercury', 'house': 2, 'sign': 'Virgo', 'degrees': 5.1},
        {'planet': 'Jupiter', 'house': 9, 'sign': 'Aries', 'degrees': 22.0},
        {'planet': 'Venus', 'house': 12, 'sign': 'Cancer', 'degrees': 3.7},
        {'planet': 'Saturn', 'house': 7, 'sign': 'Aquarius', 'degrees': 15.9},
        {'planet': 'Rahu', 'house': 6, 'sign': 'Capricorn', 'degrees': 18.2},
        {'planet': 'Ketu', 'house': 12, 'sign': 'Cancer', 'degrees': 18.2},
        {'planet': 'Ascendant', 'house': 1, 'sign': 'Leo', 'degrees': 0.0},
    ]
    
    print("=" * 80)
    print("BPHS Interpretation Engine Test")
    print("=" * 80)
    print()
    
    results = generate_bphs_interpretations(test_data)
    
    # Print House 1
    print("HOUSE 1 INTERPRETATION:")
    print("-" * 80)
    house1 = results[0]
    print(f"House: {house1['house']}")
    print(f"Title: {house1['title']}")
    print(f"Sign: {house1['sign']}")
    print(f"Lord: {house1['lord']}")
    print(f"Lord House: {house1['lord_house']}")
    print(f"Occupants: {house1['occupants']}")
    print(f"\nLord BPHS: {house1['lord_bphs'][:200]}..." if len(house1['lord_bphs']) > 200 else f"\nLord BPHS: {house1['lord_bphs']}")
    print(f"\nHouse Summary: {house1['house_summary']}")
    print(f"\nPlanet Notes: {house1['planet_notes']}")
    print()
    
    # Print House 9
    print("=" * 80)
    print("HOUSE 9 INTERPRETATION:")
    print("-" * 80)
    house9 = results[8]
    print(f"House: {house9['house']}")
    print(f"Title: {house9['title']}")
    print(f"Sign: {house9['sign']}")
    print(f"Lord: {house9['lord']}")
    print(f"Lord House: {house9['lord_house']}")
    print(f"Occupants: {house9['occupants']}")
    print(f"\nLord BPHS: {house9['lord_bphs'][:200]}..." if len(house9['lord_bphs']) > 200 else f"\nLord BPHS: {house9['lord_bphs']}")
    print(f"\nHouse Summary: {house9['house_summary']}")
    print(f"\nPlanet Notes: {house9['planet_notes']}")
    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
