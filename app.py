"""
Vedic Astrology Web Application
=================================
Production-ready Flask application providing Vedic birth chart generation,
Vimshottari Dasha calculation, and South Indian chart rendering.

API Endpoints:
    POST /api/chart          — Full birth chart + Dasha report (JSON)
    POST /api/consultation   — Deep BPHS consultation HTML report
    GET  /api/health         — Health check
    GET  /                   — Serve the web application
"""

import os
import io
import re
import logging
import traceback
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, send_from_directory, Response
)

from config import get_config
from chart_gen import calculate_positions, generate_south_chart, format_dms
from panchanga import compute_panchanga
from interpretations import generate_interpretations
from bphs_engine import generate_bphs_from_positions
from vims_engine import (
    compute_moon_longitude, calc_nakshatra, get_full_dasha_report,
    get_dasha_timeline, find_active_periods
)
from deep_interpreter import generate_consultation_html, generate_consultation_html_partial, SECTION_KEYS, SECTION_LABELS
from parashari_engine import compute_extended_data

# AI Interpretation Layer (optional — requires ANTHROPIC_API_KEY)
try:
    from ai_interpreter import generate_ai_narratives, generate_ai_narratives_parallel
    HAS_AI_LAYER = True
except ImportError:
    HAS_AI_LAYER = False

# B.V. Raman Rule Engine (optional — enhances yoga detection)
try:
    from bv_raman_rules import analyze_chart as raman_analyze_chart
    HAS_RAMAN_RULES = True
except ImportError:
    HAS_RAMAN_RULES = False

# Gochar (Transit) Engine
try:
    from gochar_engine import compute_monthly_transits, compute_twelve_month_overview
    HAS_GOCHAR = True
except ImportError:
    HAS_GOCHAR = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vedic")


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised when user input fails validation."""
    pass


def validate_birth_data(data):
    """
    Validate and sanitise birth data from the client.

    Returns a clean dict or raises ValidationError.
    """
    errors = []

    # Required fields
    required = ["year", "month", "day", "hour", "minute", "latitude", "longitude", "utc_offset"]
    for field in required:
        if field not in data or data[field] is None or data[field] == "":
            errors.append(f"Missing required field: {field}")

    if errors:
        raise ValidationError("; ".join(errors))

    try:
        year = int(data["year"])
        month = int(data["month"])
        day = int(data["day"])
        hour = int(data["hour"])
        minute = int(data["minute"])
        second = int(data.get("second", 0) or 0)
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])
        utc_offset = float(data["utc_offset"])
    except (ValueError, TypeError) as e:
        raise ValidationError(f"Invalid numeric value: {e}")

    # Range checks
    if not (1 <= year <= 2200):
        errors.append("Year must be between 1 and 2200")
    if not (1 <= month <= 12):
        errors.append("Month must be between 1 and 12")
    if not (1 <= day <= 31):
        errors.append("Day must be between 1 and 31")
    if not (0 <= hour <= 23):
        errors.append("Hour must be between 0 and 23")
    if not (0 <= minute <= 59):
        errors.append("Minute must be between 0 and 59")
    if not (0 <= second <= 59):
        errors.append("Second must be between 0 and 59")
    if not (-90 <= latitude <= 90):
        errors.append("Latitude must be between -90 and 90")
    if not (-180 <= longitude <= 180):
        errors.append("Longitude must be between -180 and 180")
    if not (-12 <= utc_offset <= 14):
        errors.append("UTC offset must be between -12 and 14")

    if errors:
        raise ValidationError("; ".join(errors))

    # Sanitise name
    name = str(data.get("name", "Native") or "Native").strip()
    name = re.sub(r'[<>&"\']', '', name)[:100]

    return {
        "name": name,
        "gender": str(data.get("gender", "")).strip()[:20],
        "year": year,
        "month": month,
        "day": day,
        "hour": hour,
        "minute": minute,
        "second": second,
        "latitude": latitude,
        "longitude": longitude,
        "utc_offset": utc_offset,
        "city": re.sub(r'[<>&"\']', '', str(data.get("city", "")).strip())[:100],
        "country": re.sub(r'[<>&"\']', '', str(data.get("country", "")).strip())[:100],
    }


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    cfg = get_config()
    app.config.from_object(cfg)

    # Ensure output directory
    os.makedirs(app.config.get("OUTPUT_DIR", "output"), exist_ok=True)

    # ----- Security headers middleware -----
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # ----- Routes -----

    @app.route("/")
    def index():
        """Serve the main application page."""
        return render_template("index.html")

    @app.route("/api/health")
    def health():
        """Health check endpoint for monitoring."""
        return jsonify({"status": "ok", "service": "vedic-astrology", "version": "1.0.0"})

    @app.route("/api/chart", methods=["POST"])
    def generate_chart():
        """
        Generate a complete Vedic birth chart with planetary positions,
        South Indian chart SVG, Vimshottari Dasha timeline, and current
        running Dasha periods.

        Expects JSON body with birth data.
        Returns JSON with all computed results.
        """
        try:
            data = request.get_json(force=True)
            if not data:
                return jsonify({"error": "No JSON data provided"}), 400

            birth = validate_birth_data(data)
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            return jsonify({"error": "Invalid request data"}), 400

        try:
            # 1. Calculate planetary positions
            positions = calculate_positions(
                year=birth["year"], month=birth["month"], day=birth["day"],
                hour=birth["hour"], minute=birth["minute"], second=birth["second"],
                utc_offset=birth["utc_offset"],
                latitude=birth["latitude"], longitude=birth["longitude"],
            )

            # 2. Generate South Indian chart SVG
            output_dir = app.config.get("OUTPUT_DIR", "output")
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', birth["name"])[:50]
            filename = f"chart_{safe_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            svg_path = generate_south_chart(
                positions,
                person_name=birth["name"],
                output_dir=output_dir,
                filename=filename,
            )

            # Read SVG content for inline display (jyotichart writes UTF-16-LE)
            svg_content = ""
            if svg_path and os.path.exists(svg_path):
                with open(svg_path, "rb") as f:
                    raw = f.read()
                for enc in ("utf-8-sig", "utf-16", "utf-16-le", "latin-1"):
                    try:
                        svg_content = raw.decode(enc)
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue

            # 3. Moon longitude for Dasha calculation
            moon_lon = compute_moon_longitude(
                birth["year"], birth["month"], birth["day"],
                birth["hour"], birth["minute"], birth["second"],
                birth["utc_offset"],
            )

            # 4. Nakshatra details
            nakshatra = calc_nakshatra(moon_lon)

            # 5. Full Dasha report
            birth_dt = datetime(
                birth["year"], birth["month"], birth["day"],
                birth["hour"], birth["minute"], birth["second"],
            )
            dasha_report = get_full_dasha_report(birth_dt, moon_lon)

            # 6. Currently running Dasha
            timeline = get_dasha_timeline(moon_lon, birth_dt)
            now = datetime.now()
            active = find_active_periods(timeline, now)

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

            # 7. Build planet positions for JSON response
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

            asc = positions["ascendant"]
            ascendant_json = {
                "sign": asc["rashi"]["name"],
                "sign_sanskrit": asc["rashi"]["sanskrit"],
                "degrees": format_dms(asc["sign_deg"]),
                "lord": asc["rashi"]["lord"],
                "longitude": round(asc["longitude"], 4),
            }

            # 8. House interpretations — classical text layer + direct BPHS slokas from PDF
            interpretations = generate_interpretations(positions)
            bphs_interpretations = generate_bphs_from_positions(positions)
            # Merge: add bphs_data field to each house interpretation
            for i, house in enumerate(interpretations):
                if i < len(bphs_interpretations):
                    house["bphs_lord_sloka"] = bphs_interpretations[i].get("lord_bphs", "")
                    house["bphs_house_summary"] = bphs_interpretations[i].get("house_summary", "")
                    house["bphs_planet_notes"] = bphs_interpretations[i].get("planet_notes", [])

            # 9. Panchanga via PyJHora
            panchanga = compute_panchanga(
                year=birth["year"], month=birth["month"], day=birth["day"],
                hour=birth["hour"], minute=birth["minute"], second=birth["second"],
                utc_offset=birth["utc_offset"],
                latitude=birth["latitude"], longitude=birth["longitude"],
                city=birth["city"], country=birth["country"],
            )

            response = {
                "success": True,
                "birth_details": {
                    "name": birth["name"],
                    "gender": birth["gender"],
                    "date": f"{birth['day']:02d}-{birth['month']:02d}-{birth['year']}",
                    "time": f"{birth['hour']:02d}:{birth['minute']:02d}:{birth['second']:02d}",
                    "city": birth["city"],
                    "country": birth["country"],
                    "latitude": birth["latitude"],
                    "longitude": birth["longitude"],
                    "utc_offset": birth["utc_offset"],
                },
                "chart": {
                    "julian_day": round(positions["jd"], 6),
                    "ayanamsa": format_dms(positions["ayanamsa"]),
                    "ayanamsa_deg": round(positions["ayanamsa"], 6),
                    "ascendant": ascendant_json,
                    "planets": planets_json,
                },
                "svg_chart": svg_content,
                "nakshatra": {
                    "name": nakshatra["name"],
                    "number": nakshatra["number"],
                    "pada": nakshatra["pada"],
                    "lord": nakshatra["lord"],
                },
                "moon_longitude": round(moon_lon, 4),
                "dasha_report": dasha_report,
                "current_dasha": current_dasha,
                "panchanga": panchanga,
                "interpretations": interpretations,
            }

            logger.info(f"Chart generated for {birth['name']} — "
                        f"{birth['day']}/{birth['month']}/{birth['year']}")

            return jsonify(response)

        except Exception as e:
            logger.error(f"Chart generation failed: {traceback.format_exc()}")
            return jsonify({"error": f"Calculation error: {str(e)}"}), 500

    @app.route("/api/consultation", methods=["POST"])
    def generate_consultation():
        """
        Generate a full, deep-consultation Vedic astrology HTML report.

        Accepts the same JSON body as /api/chart and returns a standalone
        HTML document containing BPHS cross-referenced interpretations,
        yoga analysis, dasha narrative, nakshatra deep-dive, and remedies.

        Returns: text/html — the full consultation report as an HTML page.
        """
        try:
            data = request.get_json(force=True)
            if not data:
                return jsonify({"error": "No JSON data provided"}), 400

            birth = validate_birth_data(data)
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            return jsonify({"error": "Invalid request data"}), 400

        try:
            # 1. Planetary positions
            positions = calculate_positions(
                year=birth["year"], month=birth["month"], day=birth["day"],
                hour=birth["hour"], minute=birth["minute"], second=birth["second"],
                utc_offset=birth["utc_offset"],
                latitude=birth["latitude"], longitude=birth["longitude"],
            )

            # 2. Moon longitude & Nakshatra
            moon_lon = compute_moon_longitude(
                birth["year"], birth["month"], birth["day"],
                birth["hour"], birth["minute"], birth["second"],
                birth["utc_offset"],
            )
            nakshatra_info = calc_nakshatra(moon_lon)

            # 3. Vimshottari Dasha report (HTML string)
            birth_dt = datetime(
                birth["year"], birth["month"], birth["day"],
                birth["hour"], birth["minute"], birth["second"],
            )
            dasha_report = get_full_dasha_report(birth_dt, moon_lon)

            # 4. Currently active Dasha periods
            timeline = get_dasha_timeline(moon_lon, birth_dt)
            now = datetime.now()
            active = find_active_periods(timeline, now)

            current_dasha = None
            if active:
                current_dasha = {
                    "maha":        active["maha"]["dasha_lord"],
                    "maha_start":  active["maha"]["start_date"].strftime("%d-%b-%Y"),
                    "maha_end":    active["maha"]["end_date"].strftime("%d-%b-%Y"),
                    "antar":       active["antar"]["antar_lord"],
                    "antar_start": active["antar"]["start_date"].strftime("%d-%b-%Y"),
                    "antar_end":   active["antar"]["end_date"].strftime("%d-%b-%Y"),
                }
                if active.get("pratyantar"):
                    current_dasha["pratyantar"] = active["pratyantar"]["pratyantar_lord"]
                    current_dasha["pratyantar_start"] = active["pratyantar"]["start_date"].strftime("%d-%b-%Y")
                    current_dasha["pratyantar_end"]   = active["pratyantar"]["end_date"].strftime("%d-%b-%Y")

            # 5. Extended Parashari computations (Shadbala, Vargas, Karakas, etc.)
            extended_data = compute_extended_data(
                positions=positions, birth=birth, moon_longitude=moon_lon
            )

            # 5b. B.V. Raman rule engine analysis
            raman_analysis = None
            if HAS_RAMAN_RULES:
                try:
                    raman_analysis = raman_analyze_chart(positions, birth_dt, moon_lon)
                except Exception as e:
                    logger.warning(f"B.V. Raman analysis error: {e}")

            # 5c. AI Interpretation Layer (generates organic prose via Claude API)
            ai_narratives = None
            if HAS_AI_LAYER and os.environ.get("ANTHROPIC_API_KEY"):
                try:
                    ai_narratives = generate_ai_narratives(
                        positions=positions,
                        birth=birth,
                        raman_analysis=raman_analysis,
                        extended_data=extended_data,
                        current_dasha=current_dasha,
                    )
                    ai_count = sum(1 for v in ai_narratives.values() if v)
                    logger.info(f"AI narratives generated: {ai_count} sections")
                except Exception as e:
                    logger.warning(f"AI narrative generation error: {e}")
                    ai_narratives = None

            # 6. Build deep consultation HTML via the BPHS cross-referenced engine
            html_report = generate_consultation_html(
                birth=birth,
                positions=positions,
                moon_longitude=moon_lon,
                nakshatra_info=nakshatra_info,
                dasha_report=dasha_report,
                current_dasha=current_dasha,
                ashtakvarga=None,  # Future: wire in Ashtakvarga computation
                extended_data=extended_data,
                ai_narratives=ai_narratives,
            )

            logger.info(f"Deep consultation generated for {birth['name']} — "
                        f"{birth['day']}/{birth['month']}/{birth['year']}")

            return Response(html_report, mimetype="text/html; charset=utf-8")

        except Exception as e:
            logger.error(f"Consultation generation failed: {traceback.format_exc()}")
            return jsonify({"error": f"Consultation error: {str(e)}"}), 500

    @app.route("/api/consultation-sections", methods=["GET"])
    def get_consultation_sections():
        """Return the list of available consultation sections for the dropdown."""
        sections = [{"key": k, "label": SECTION_LABELS[k]} for k in SECTION_KEYS]
        return jsonify({"sections": sections})

    @app.route("/api/consultation-partial", methods=["POST"])
    def generate_consultation_partial():
        """
        Generate a consultation report with only selected sections.

        Accepts same birth data as /api/consultation plus:
            sections: list of section keys to include (default: all)
            include_ai: bool — whether to generate AI narrative (default: true)
        """
        try:
            data = request.get_json(force=True)
            if not data:
                return jsonify({"error": "No JSON data provided"}), 400
            birth = validate_birth_data(data)
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            return jsonify({"error": "Invalid request data"}), 400

        try:
            sections_list = data.get("sections", None)  # None = all
            include_ai = data.get("include_ai", True)

            # 1. Planetary positions
            positions = calculate_positions(
                year=birth["year"], month=birth["month"], day=birth["day"],
                hour=birth["hour"], minute=birth["minute"], second=birth["second"],
                utc_offset=birth["utc_offset"],
                latitude=birth["latitude"], longitude=birth["longitude"],
            )

            # 2. Moon longitude & Nakshatra
            moon_lon = compute_moon_longitude(
                birth["year"], birth["month"], birth["day"],
                birth["hour"], birth["minute"], birth["second"],
                birth["utc_offset"],
            )
            nakshatra_info = calc_nakshatra(moon_lon)

            # 3. Dasha
            birth_dt = datetime(
                birth["year"], birth["month"], birth["day"],
                birth["hour"], birth["minute"], birth["second"],
            )
            dasha_report = get_full_dasha_report(birth_dt, moon_lon)

            # 4. Active Dasha
            timeline = get_dasha_timeline(moon_lon, birth_dt)
            now = datetime.now()
            active = find_active_periods(timeline, now)
            current_dasha = None
            if active:
                current_dasha = {
                    "maha":        active["maha"]["dasha_lord"],
                    "maha_start":  active["maha"]["start_date"].strftime("%d-%b-%Y"),
                    "maha_end":    active["maha"]["end_date"].strftime("%d-%b-%Y"),
                    "antar":       active["antar"]["antar_lord"],
                    "antar_start": active["antar"]["start_date"].strftime("%d-%b-%Y"),
                    "antar_end":   active["antar"]["end_date"].strftime("%d-%b-%Y"),
                }
                if active.get("pratyantar"):
                    current_dasha["pratyantar"] = active["pratyantar"]["pratyantar_lord"]
                    current_dasha["pratyantar_start"] = active["pratyantar"]["start_date"].strftime("%d-%b-%Y")
                    current_dasha["pratyantar_end"]   = active["pratyantar"]["end_date"].strftime("%d-%b-%Y")

            # 5. Extended computations
            extended_data = compute_extended_data(
                positions=positions, birth=birth, moon_longitude=moon_lon
            )

            raman_analysis = None
            if HAS_RAMAN_RULES:
                try:
                    raman_analysis = raman_analyze_chart(positions, birth_dt, moon_lon)
                except Exception as e:
                    logger.warning(f"B.V. Raman analysis error: {e}")

            # 6. AI Narratives — parallel generation
            ai_narratives = None
            if include_ai and HAS_AI_LAYER and os.environ.get("ANTHROPIC_API_KEY"):
                try:
                    ai_narratives = generate_ai_narratives_parallel(
                        positions=positions,
                        birth=birth,
                        raman_analysis=raman_analysis,
                        extended_data=extended_data,
                        current_dasha=current_dasha,
                    )
                    ai_count = sum(1 for v in ai_narratives.values() if v)
                    logger.info(f"AI narratives (parallel): {ai_count} sections")
                except Exception as e:
                    logger.warning(f"Parallel AI generation failed, trying sequential: {e}")
                    try:
                        ai_narratives = generate_ai_narratives(
                            positions=positions, birth=birth,
                            raman_analysis=raman_analysis,
                            extended_data=extended_data,
                            current_dasha=current_dasha,
                        )
                    except Exception:
                        ai_narratives = None

            # 7. Build partial HTML
            html_report = generate_consultation_html_partial(
                birth=birth,
                positions=positions,
                moon_longitude=moon_lon,
                nakshatra_info=nakshatra_info,
                dasha_report=dasha_report,
                current_dasha=current_dasha,
                ashtakvarga=None,
                extended_data=extended_data,
                ai_narratives=ai_narratives,
                sections_list=sections_list,
            )

            logger.info(f"Partial consultation for {birth['name']} — "
                        f"sections: {sections_list or 'ALL'}")

            return Response(html_report, mimetype="text/html; charset=utf-8")

        except Exception as e:
            logger.error(f"Partial consultation failed: {traceback.format_exc()}")
            return jsonify({"error": f"Consultation error: {str(e)}"}), 500

    # ── Gochar (Transit Prediction) Endpoints ─────────────────────────────
    @app.route("/api/gochar", methods=["POST"])
    def get_gochar():
        """
        Compute monthly Gochar (transit) predictions.

        Accepts same birth data as /api/chart plus:
            year: int — target year (default: current)
            month: int — target month 1-12 (default: current)
        """
        if not HAS_GOCHAR:
            return jsonify({"error": "Gochar engine not available"}), 500

        try:
            data = request.get_json(force=True)
            if not data:
                return jsonify({"error": "No JSON data provided"}), 400
            birth = validate_birth_data(data)
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            return jsonify({"error": "Invalid request data"}), 400

        try:
            from datetime import datetime as dt
            now = dt.now()
            target_year = int(data.get("year", now.year))
            target_month = int(data.get("month", now.month))

            if target_month < 1 or target_month > 12:
                return jsonify({"error": "Month must be 1-12"}), 400

            # Calculate natal positions
            positions = calculate_positions(
                year=birth["year"], month=birth["month"], day=birth["day"],
                hour=birth["hour"], minute=birth["minute"], second=birth["second"],
                utc_offset=birth["utc_offset"],
                latitude=birth["latitude"], longitude=birth["longitude"],
            )

            result = compute_monthly_transits(positions, birth, target_year, target_month)

            logger.info(f"Gochar for {birth['name']} — {result['month_label']}: "
                        f"{result['summary']['overall']}")

            return jsonify(result)

        except Exception as e:
            logger.error(f"Gochar computation failed: {traceback.format_exc()}")
            return jsonify({"error": f"Gochar error: {str(e)}"}), 500

    @app.route("/api/gochar/overview", methods=["POST"])
    def get_gochar_overview():
        """12-month transit overview (lightweight summaries)."""
        if not HAS_GOCHAR:
            return jsonify({"error": "Gochar engine not available"}), 500

        try:
            data = request.get_json(force=True)
            birth = validate_birth_data(data)
        except (ValidationError, Exception) as e:
            return jsonify({"error": str(e)}), 400

        try:
            positions = calculate_positions(
                year=birth["year"], month=birth["month"], day=birth["day"],
                hour=birth["hour"], minute=birth["minute"], second=birth["second"],
                utc_offset=birth["utc_offset"],
                latitude=birth["latitude"], longitude=birth["longitude"],
            )

            overview = compute_twelve_month_overview(positions, birth)
            return jsonify({"overview": overview})

        except Exception as e:
            logger.error(f"Gochar overview failed: {traceback.format_exc()}")
            return jsonify({"error": f"Overview error: {str(e)}"}), 500

    @app.route("/output/<path:filename>")
    def serve_chart(filename):
        """Serve generated chart SVG files."""
        output_dir = app.config.get("OUTPUT_DIR", "output")
        return send_from_directory(output_dir, filename)

    @app.route("/horoscope")
    def serve_horoscope():
        """Serve the pre-generated horoscope report for download."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return send_from_directory(
            base_dir, "horoscope_11Sep2009_Dubai.html",
            as_attachment=True,
            download_name="horoscope_11Sep2009_Dubai.html",
        )

    @app.route("/horoscope/view")
    def view_horoscope():
        """View the pre-generated horoscope report in browser."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return send_from_directory(base_dir, "horoscope_11Sep2009_Dubai.html")

    # ----- Error handlers -----

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Endpoint not found"}), 404
        return render_template("index.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

    return app


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
