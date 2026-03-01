"""
ai_interpreter.py
==================
AI Interpretation Layer for the Vedic Astrology Consultation Engine.

This module sits on top of the rule engine (bv_raman_rules.py) and
parashari_engine.py, taking their structured data output and sending it
to the Claude API to generate organic, flowing, professional consultation
prose that reads like a seasoned Jyotish astrologer's personal reading.

Architecture:
  Rule Engine (bv_raman_rules.py)  →  structured chart data (yogas, planet effects, dasha)
  Parashari Engine                 →  Shadbala, Karakas, Avasthas, etc.
       ↓
  AI Interpreter (this module)     →  organic narrative prose via Claude API
       ↓
  deep_interpreter.py              →  assembles into HTML consultation report

The AI layer generates these narrative sections:
  1. Life Overview Narrative     — the astrologer's first impression as flowing prose
  2. Career & Wealth Reading     — dharmic career path + financial trajectory
  3. Relationships & Marriage     — partnership karma, timing, compatibility themes
  4. Current Dasha Narrative      — what the native is experiencing NOW
  5. Health & Longevity           — constitutional tendencies and periods of care
  6. Spiritual Direction          — moksha indicators, karmic lessons, remedial path
  7. Year Ahead Forecast          — practical guidance for the next 12 months

Each section is generated via a focused Claude API call with a Jyotish-expert
system prompt + the structured chart data as context.

Usage:
    from ai_interpreter import generate_ai_narratives
    narratives = generate_ai_narratives(positions, birth, raman_analysis, extended_data)
    # Returns dict of section_name → HTML prose strings

Configuration:
    Set ANTHROPIC_API_KEY environment variable, or pass api_key parameter.
    Set VEDIC_AI_MODEL to override model (default: claude-sonnet-4-5-20250929).
"""

import os
import json
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger("vedic.ai_interpreter")

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS_PER_SECTION = 1500
TEMPERATURE = 0.7

# The master system prompt that shapes all AI interpretations
JYOTISH_SYSTEM_PROMPT = """You are a senior Vedic astrologer (Jyotishi) with 40 years of experience in the Parashari tradition. You studied under B.V. Raman and have deep mastery of Brihat Parashara Hora Shastra.

Your consultation style:
- Write as if speaking directly to the client sitting before you
- Use warm but authoritative classical tone — never casual or pop-astrology
- Weave technical terms naturally (always explain briefly in parentheses on first use)
- Reference specific planetary placements, dignities, and yogas from the chart data provided
- Be specific and personal — never generic. Every sentence should connect to THIS chart
- Use flowing paragraphs, not bullet points or lists
- When discussing challenges, frame them as karmic growth opportunities with actionable remedies
- Include timing references (Dasha periods) when discussing predictions
- Use occasional Sanskrit terms with translations to add authenticity
- NEVER fabricate chart data — only reference what is provided in the context
- Keep each section focused and between 200-350 words
- End each section with a practical takeaway or timing insight

Interpretive priorities:
1. Dignity of planets (exalted/own/friendly/debilitated) shapes their expression
2. House lordship determines what life area a planet governs
3. Yogas represent concentrated karmic potential
4. Dasha periods determine WHEN karmic potentials activate
5. Aspects and conjunctions create relational dynamics between planets
6. Nakshatra placement adds psychological and spiritual depth"""


# ═══════════════════════════════════════════════════════════════════════════════
# CURRENT TRANSIT CALCULATOR — real-time planetary positions via Swiss Ephemeris
# ═══════════════════════════════════════════════════════════════════════════════

# Zodiac signs for degree → sign conversion
_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

def _get_current_transits() -> str:
    """
    Compute today's sidereal planetary positions using Swiss Ephemeris (Lahiri ayanamsa).
    Returns a formatted string of current transit positions for major planets.
    This ensures the AI uses REAL astronomical data for year-ahead forecasts,
    rather than hallucinating transit positions from training data.
    """
    try:
        import swisseph as swe
        from datetime import datetime, timezone

        ephe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ephe")
        swe.set_ephe_path(ephe_path)
        swe.set_sid_mode(swe.SIDM_LAHIRI)

        now = datetime.now(timezone.utc)
        jd = swe.julday(now.year, now.month, now.day,
                        now.hour + now.minute / 60.0 + now.second / 3600.0)

        flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

        # Planet IDs: Sun=0, Moon=1, Mars=4, Mercury=2, Jupiter=5, Venus=3, Saturn=6
        # Rahu (Mean Node) = 10
        planet_ids = {
            "Jupiter": swe.JUPITER,
            "Saturn": swe.SATURN,
            "Rahu": swe.MEAN_NODE,
            "Sun": swe.SUN,
            "Mars": swe.MARS,
            "Mercury": swe.MERCURY,
            "Venus": swe.VENUS,
        }

        lines = []
        lines.append(f"CURRENT TRANSIT POSITIONS (as of {now.strftime('%d %B %Y')}):")
        lines.append("These are the ACTUAL sidereal positions computed via Swiss Ephemeris.")
        lines.append("Use ONLY these positions when discussing transits — do NOT guess or use memorised data.\n")

        for name, pid in planet_ids.items():
            pos, _ = swe.calc_ut(jd, pid, flags)
            longitude = pos[0]
            sign_idx = int(longitude / 30)
            degrees = longitude - sign_idx * 30
            sign = _SIGNS[sign_idx % 12]
            retro = " (R)" if pos[3] < 0 else ""

            lines.append(f"  {name}: {sign} {degrees:.1f}°{retro}")

        # Ketu is always 180° from Rahu
        rahu_pos, _ = swe.calc_ut(jd, swe.MEAN_NODE, flags)
        ketu_long = (rahu_pos[0] + 180.0) % 360.0
        ketu_sign_idx = int(ketu_long / 30)
        ketu_deg = ketu_long - ketu_sign_idx * 30
        ketu_sign = _SIGNS[ketu_sign_idx % 12]
        lines.append(f"  Ketu: {ketu_sign} {ketu_deg:.1f}° (R)")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Could not compute current transits: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# CHART DATA FORMATTER — prepares structured data for Claude
# ═══════════════════════════════════════════════════════════════════════════════

def _format_chart_context(positions: dict, birth: dict,
                          raman_analysis: dict = None,
                          extended_data: dict = None) -> str:
    """
    Format all chart data into a clean text summary for the AI prompt.
    This is the 'knowledge base' that Claude uses to write the narrative.
    """
    lines = []

    # Birth details
    name = birth.get("name", "Native")
    dob = f"{birth.get('day', 1):02d}/{birth.get('month', 1):02d}/{birth.get('year', 2000)}"
    tob = f"{birth.get('hour', 0):02d}:{birth.get('minute', 0):02d}"
    city = birth.get("city", "")
    lines.append(f"NATIVE: {name}")
    lines.append(f"BIRTH: {dob} at {tob}, {city}")

    # Ascendant
    asc = positions.get("ascendant", {})
    lagna_sign = asc.get("rashi", {}).get("name", "Unknown")
    lagna_deg = round(asc.get("longitude", 0) % 30, 2)
    lines.append(f"\nASCENDANT (LAGNA): {lagna_sign} at {lagna_deg}°")

    # Planetary positions
    lines.append("\nPLANETARY POSITIONS:")
    for p in positions.get("planets", []):
        name_p = p.get("name", "")
        sign = p.get("rashi", {}).get("name", "")
        deg = round(p.get("longitude", 0) % 30, 2)
        retro = " (R)" if p.get("retrograde") else ""
        nak = p.get("nakshatra", {}).get("name", "") if "nakshatra" in p else ""
        lines.append(f"  {name_p}: {sign} {deg}°{retro} {f'[Nak: {nak}]' if nak else ''}")

    # Planet effects from B.V. Raman
    if raman_analysis:
        pe = raman_analysis.get("planet_effects", {})
        if pe:
            lines.append("\nPLANET DIGNITIES & HOUSE EFFECTS (B.V. Raman):")
            for pname, pdata in pe.items():
                lines.append(f"  {pname}: House {pdata['house']}, {pdata['sign']} ({pdata['dignity']})")
                lines.append(f"    → {pdata.get('interpretation', '')[:200]}")

        # Yogas
        yogas = raman_analysis.get("yogas", [])
        if yogas:
            lines.append(f"\nYOGAS DETECTED ({len(yogas)}):")
            for y in yogas:
                planets_str = ", ".join(y.get("planets", []))
                lines.append(f"  • {y['name']} ({y['category']}) — Strength: {y['strength']}")
                lines.append(f"    Planets: {planets_str}")
                if y.get("classical_result"):
                    lines.append(f"    Classical Result: {str(y['classical_result'])[:200]}")

        # Dasha readings
        dr = raman_analysis.get("dasha_readings", {})
        if dr:
            lines.append("\nDASHA INTERPRETATIONS:")
            for planet, reading in dr.items():
                sl = reading.get("strength_level", "General")
                h = reading.get("house", "")
                d = reading.get("dignity", "")
                lines.append(f"  {planet} Dasha ({reading.get('years', 0)} yrs): [{sl}] House {h}, {d}")
                if reading.get("strength_reading"):
                    lines.append(f"    → {reading['strength_reading'][:200]}")

    # Extended data from parashari_engine
    if extended_data:
        # Shadbala
        sb = extended_data.get("shadbala", {})
        if sb:
            lines.append("\nSHADBALA (Sixfold Strength):")
            for pname, sdata in sb.items():
                lines.append(f"  {pname}: Total={sdata.get('total', 0)}, "
                           f"Category={sdata.get('category', '')}, "
                           f"Rank={sdata.get('rank', '')}")

        # Karakas
        kr = extended_data.get("karakas", {})
        if kr:
            lines.append("\nCHARA KARAKAS:")
            for kname, kdata in kr.items():
                lines.append(f"  {kname}: {kdata.get('planet', '')} in {kdata.get('sign', '')}")
                if kdata.get("interpretation"):
                    lines.append(f"    → {kdata['interpretation'][:150]}")

        # Longevity
        lm = extended_data.get("longevity_maraka", {})
        if lm:
            lines.append(f"\nLONGEVITY: {lm.get('longevity_category', '')}")
            for m in lm.get("maraka_grahas", []):
                lines.append(f"  Maraka: {m.get('planet', '')} — {m.get('reason', '')}")

        # Avasthas
        av = extended_data.get("avasthas", {})
        if av:
            lines.append("\nAVASTHAS (Planetary States):")
            for pname, adata in av.items():
                lines.append(f"  {pname}: {adata.get('avastha', '')} — {adata.get('delivery', '')} delivery")

    return "\n".join(lines)


def _format_current_dasha_context(current_dasha: dict = None) -> str:
    """Format current dasha period info for timing-specific queries."""
    if not current_dasha:
        return "Current Dasha period: Not available."

    lines = ["CURRENT DASHA PERIOD:"]
    lines.append(f"  Mahadasha: {current_dasha.get('maha', 'Unknown')}")
    lines.append(f"    Period: {current_dasha.get('maha_start', '')} to {current_dasha.get('maha_end', '')}")
    lines.append(f"  Antardasha: {current_dasha.get('antar', 'Unknown')}")
    lines.append(f"    Period: {current_dasha.get('antar_start', '')} to {current_dasha.get('antar_end', '')}")
    if current_dasha.get("pratyantar"):
        lines.append(f"  Pratyantardasha: {current_dasha.get('pratyantar', '')}")
        lines.append(f"    Period: {current_dasha.get('pratyantar_start', '')} to {current_dasha.get('pratyantar_end', '')}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION PROMPT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

SECTION_PROMPTS = {
    "life_overview": """Based on the chart data below, write the LIFE OVERVIEW section of this consultation.

Cover these themes in flowing prose (NOT bullet points):
- The essential nature of this Lagna (ascendant) and what it means for the native's life path
- The strongest planetary placements and what they promise
- The most significant yogas and their combined effect on destiny
- The overarching karmic theme — what is this soul here to accomplish?
- Any notable strengths and challenges visible in the planetary configuration

Write as a seasoned astrologer giving a personal reading. Be specific to THIS chart.
Address the native directly using "you" and "your".
Length: 250-350 words.

CHART DATA:
{chart_context}""",

    "career_wealth": """Based on the chart data below, write the CAREER & WEALTH section of this consultation.

Cover these themes in flowing prose:
- The 10th house (career) lord's placement, dignity, and what career path it indicates
- The 2nd house (wealth) and 11th house (gains) — financial trajectory
- Any Dhana Yogas (wealth combinations) or Raja Yogas (power combinations) and their career implications
- The Yoga Karaka planet's role in professional success
- Specific career fields that align with this chart's planetary configuration
- Timing — which Dasha periods will activate career peaks and wealth accumulation
- Practical guidance for career decisions

Address the native directly. Be specific about planet placements and dignities.
Length: 250-350 words.

CHART DATA:
{chart_context}""",

    "relationships": """Based on the chart data below, write the RELATIONSHIPS & MARRIAGE section of this consultation.

Cover these themes in flowing prose:
- The 7th house lord's placement and dignity — what kind of partner is indicated
- The Darakaraka (spouse significator) from the Chara Karaka scheme
- Venus's condition and role in romantic happiness
- Any yogas affecting marriage (Satkaletra Yoga, Vivaha Yoga, or adverse combinations)
- Timing of marriage — which Dasha period activates the 7th house
- The quality of marital life based on the 7th lord and Venus
- Any challenges and remedies for relationship harmony
- Family life and children (5th house themes)

Address the native directly. Be compassionate but honest about challenges.
Length: 250-350 words.

CHART DATA:
{chart_context}""",

    "current_period": """Based on the chart data below, write the CURRENT DASHA PERIOD ANALYSIS section.

This is the most practically important section — what is happening NOW.

Cover these themes in flowing prose:
- The current Mahadasha lord — its dignity, house, and what life themes it activates
- The current Antardasha — how it modifies the Mahadasha experience
- Specific events and developments the native can expect in this period
- Areas of life that are most active and demanding attention
- Opportunities that are available during this period
- Challenges to watch for and how to navigate them
- Practical timing advice — what to do now vs. what to wait for
- When the current sub-period ends and what the next one brings

Address the native directly. Be practical and actionable.
Length: 300-400 words.

CHART DATA:
{chart_context}

{dasha_context}""",

    "health_longevity": """Based on the chart data below, write the HEALTH & LONGEVITY section.

Cover these themes in flowing prose:
- The longevity assessment (Purna/Madhya/Alpa Ayu) and what it means
- Constitutional tendencies based on the Lagna and its lord
- Specific health vulnerabilities indicated by planetary placements (6th, 8th houses)
- Maraka planets and the periods requiring health vigilance
- The role of the Moon (mental health) and Sun (vitality) in overall wellness
- Preventive measures aligned with Ayurvedic and classical Jyotish wisdom
- Periods of good health and periods requiring extra care

Address the native directly. Be reassuring but responsible — frame as preventive guidance.
Length: 200-300 words.

CHART DATA:
{chart_context}""",

    "spiritual_direction": """Based on the chart data below, write the SPIRITUAL DIRECTION & REMEDIES section.

Cover these themes in flowing prose:
- The 9th house (dharma) and 12th house (moksha) — spiritual orientation
- The Atmakaraka (soul significator) and its message about spiritual evolution
- Ketu's placement — past-life karmic residue and what the soul has already mastered
- Rahu's placement — the karmic frontier and what the soul needs to learn
- Jupiter's role as the guru planet — access to spiritual wisdom and teachers
- Specific remedial measures (Upaya) tailored to this chart:
  * Gemstone (Ratna) recommendations based on the Yoga Karaka and weak planets
  * Mantra prescriptions for strengthening key planets
  * Charitable acts (Dana) aligned with planetary weaknesses
  * Spiritual practices suited to this native's temperament
- The overall karmic direction — what is the soul's deepest purpose in this birth?

Address the native directly. End with an inspiring and empowering message.
Length: 300-400 words.

CHART DATA:
{chart_context}""",

    "year_ahead": """Based on the chart data below, write the YEAR AHEAD FORECAST section.

This should be practical, month-aware guidance for the next 12 months.

Cover these themes in flowing prose:
- The current Dasha/Bhukti and what it means for the coming year
- Key planetary transits and their likely effects (based on natal chart)
- Career and financial outlook for the next 12 months
- Relationship developments expected
- Health focus areas
- Auspicious periods for major decisions (starting ventures, property, travel)
- Challenging periods that require caution
- Overall theme or 'flavour' of the year ahead
- 3-5 specific, actionable pieces of advice

CRITICAL: When discussing transits, you MUST use ONLY the actual transit positions
provided below. Do NOT guess or rely on memorised ephemeris data. The transit data
below is computed in real time from Swiss Ephemeris and is authoritative.

Address the native directly. Be optimistic but realistic.
Length: 250-350 words.

CHART DATA:
{chart_context}

{dasha_context}

{transit_context}""",
}


# ═══════════════════════════════════════════════════════════════════════════════
# CLAUDE API CALLER
# ═══════════════════════════════════════════════════════════════════════════════

def _call_claude(system_prompt: str, user_prompt: str,
                 api_key: str = None, model: str = None,
                 max_tokens: int = MAX_TOKENS_PER_SECTION) -> str:
    """
    Call the Claude API and return the text response.
    Uses the anthropic Python SDK if available, otherwise falls back to requests.
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    model = model or os.environ.get("VEDIC_AI_MODEL", DEFAULT_MODEL)

    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY set — AI interpretation unavailable")
        return ""

    # Try anthropic SDK first
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key, timeout=45.0)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Anthropic SDK call failed: {e}, falling back to requests")

    # Fallback: direct HTTP request
    try:
        import requests
        headers = {
            "x-api-key": api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": TEMPERATURE,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("content", [{}])[0].get("text", "")
        else:
            logger.error(f"Claude API error {resp.status_code}: {resp.text[:300]}")
            return ""
    except Exception as e:
        logger.error(f"Claude API request failed: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def generate_ai_narratives(
    positions: dict,
    birth: dict,
    raman_analysis: dict = None,
    extended_data: dict = None,
    current_dasha: dict = None,
    api_key: str = None,
    model: str = None,
    sections: List[str] = None,
) -> Dict[str, str]:
    """
    Generate all AI narrative sections for the consultation report.

    Args:
        positions:      planetary positions dict from chart_gen
        birth:          birth data dict
        raman_analysis: output from bv_raman_rules.analyze_chart()
        extended_data:  output from parashari_engine.compute_extended_data()
        current_dasha:  current dasha period info dict
        api_key:        Anthropic API key (or set ANTHROPIC_API_KEY env var)
        model:          Claude model to use (default: claude-sonnet-4-5-20250929)
        sections:       list of section names to generate (default: all)

    Returns:
        Dict mapping section names to HTML-formatted narrative strings.
        Empty strings for sections that failed or were skipped.
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.info("No API key — returning empty AI narratives (rule engine output only)")
        return {s: "" for s in SECTION_PROMPTS}

    # Format chart context once (shared across all sections)
    chart_context = _format_chart_context(positions, birth, raman_analysis, extended_data)
    dasha_context = _format_current_dasha_context(current_dasha)
    transit_context = _get_current_transits()  # Real-time Swiss Ephemeris transit data

    # All 7 sections restored — Standard instance (2GB RAM, 1 CPU) active
    if sections is None:
        sections = list(SECTION_PROMPTS.keys())

    narratives = {}
    for section_name in sections:
        template = SECTION_PROMPTS.get(section_name, "")
        if not template:
            narratives[section_name] = ""
            continue

        user_prompt = template.format(
            chart_context=chart_context,
            dasha_context=dasha_context,
            transit_context=transit_context,
        )

        try:
            logger.info(f"Generating AI narrative: {section_name}")
            start = time.time()
            raw_text = _call_claude(
                system_prompt=JYOTISH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                api_key=api_key,
                model=model,
            )
            elapsed = time.time() - start
            logger.info(f"  → {section_name}: {len(raw_text)} chars in {elapsed:.1f}s")

            # Convert plain text to HTML paragraphs
            if raw_text:
                paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
                html_text = "\n".join(f"<p>{p}</p>" for p in paragraphs)
                narratives[section_name] = html_text
            else:
                narratives[section_name] = ""

        except Exception as e:
            logger.error(f"AI narrative generation failed for {section_name}: {e}")
            narratives[section_name] = ""

    return narratives


# ═══════════════════════════════════════════════════════════════════════════════
# HTML RENDERING — AI Narrative sections for the consultation report
# ═══════════════════════════════════════════════════════════════════════════════

SECTION_TITLES = {
    "life_overview":       ("Life Overview", "Jeevan Darshan", "A holistic reading of your life's trajectory"),
    "career_wealth":       ("Career & Wealth", "Karma & Artha", "Professional path and financial destiny"),
    "relationships":       ("Relationships & Marriage", "Vivaha & Bandhu", "Partnership karma and family bonds"),
    "current_period":      ("Current Period Analysis", "Vartamana Dasha", "What you are experiencing now"),
    "health_longevity":    ("Health & Longevity", "Arogya & Ayu", "Constitutional tendencies and preventive guidance"),
    "spiritual_direction": ("Spiritual Direction & Remedies", "Dharma & Moksha Marga", "Your soul's deepest purpose and remedial path"),
    "year_ahead":          ("Year Ahead Forecast", "Varsha Phala", "Practical guidance for the next 12 months"),
}


def render_ai_narrative_html(narratives: Dict[str, str]) -> str:
    """
    Render all AI narrative sections into styled HTML blocks
    that can be inserted into the consultation report.
    """
    if not any(narratives.values()):
        return ""

    sections_html = ""
    for section_name, content in narratives.items():
        if not content:
            continue

        title, sanskrit, subtitle = SECTION_TITLES.get(
            section_name,
            (section_name.replace("_", " ").title(), "", "")
        )

        sections_html += f"""
    <div class="ai-section">
      <div class="ai-section-hd">
        <div class="ai-section-title">{title}</div>
        <div class="ai-section-skt">{sanskrit}</div>
        <div class="ai-section-sub">{subtitle}</div>
      </div>
      <div class="ai-narrative">
        {content}
      </div>
    </div>"""

    if not sections_html:
        return ""

    return f"""
<div class="section ai-consultation">
  <div class="sec-hd">
    <span class="sec-tag" style="background:linear-gradient(135deg,#C9A84C,#8B6914);
          color:#1a1205;font-weight:700;">AI CONSULTATION</span>
    <div>
      <div class="sec-title">Personalised Consultation Narrative</div>
      <span class="sec-skt">&#2332;&#2381;&#2351;&#2379;&#2340;&#2367;&#2359; &#2346;&#2352;&#2366;&#2350;&#2352;&#2381;&#2358;
        &middot; AI-Powered Interpretation Layer</span>
    </div>
    <div class="sec-line"></div>
  </div>
  <div class="callout" style="border-color:rgba(201,168,76,.4);">
    <strong style="color:var(--gold);">About this section:</strong>
    The following narrative is generated by an advanced AI interpretation layer
    that synthesises the classical rule engine output with the wisdom of
    B.V. Raman's textual tradition. Each paragraph is grounded in the actual
    planetary data of your birth chart — nothing is generic or templated.
  </div>
  {sections_html}
</div>"""


def render_ai_styles() -> str:
    """Return CSS styles for the AI narrative sections."""
    return """
    /* ── AI CONSULTATION NARRATIVE ── */
    .ai-consultation {
      border: 1px solid rgba(201,168,76,.25);
      border-radius: 8px;
      padding: 0;
      margin-top: 32px;
    }
    .ai-section {
      margin: 24px 0;
      padding: 0 20px;
    }
    .ai-section-hd {
      margin-bottom: 16px;
      padding-bottom: 10px;
      border-bottom: 1px solid rgba(201,168,76,.15);
    }
    .ai-section-title {
      font-size: 17px;
      font-weight: 600;
      color: var(--gold);
      letter-spacing: 0.5px;
    }
    .ai-section-skt {
      font-size: 11px;
      color: rgba(201,168,76,.5);
      font-style: italic;
      margin-top: 2px;
    }
    .ai-section-sub {
      font-size: 12px;
      color: rgba(250,246,238,.45);
      margin-top: 3px;
    }
    .ai-narrative {
      font-size: 14px;
      line-height: 1.75;
      color: rgba(250,246,238,.82);
    }
    .ai-narrative p {
      margin: 0 0 14px 0;
      text-indent: 1.5em;
    }
    .ai-narrative p:first-child {
      text-indent: 0;
    }
    .ai-narrative p:first-child::first-letter {
      font-size: 2em;
      float: left;
      line-height: 1;
      margin-right: 6px;
      color: var(--gold);
      font-weight: 700;
    }
    .ai-narrative strong {
      color: var(--gold);
    }
    """
