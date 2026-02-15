"""
Vedic Astrology Web Application
=================================
Production-ready Flask application providing Vedic birth chart generation,
Vimshottari Dasha calculation, and South Indian chart rendering.

API Endpoints:
    POST /api/chart          — Full birth chart + Dasha report
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
from vims_engine import (
    compute_moon_longitude, calc_nakshatra, get_full_dasha_report,
    get_dasha_timeline, find_active_periods
)

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
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not app.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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
            }

            logger.info(f"Chart generated for {birth['name']} — "
                        f"{birth['day']}/{birth['month']}/{birth['year']}")

            return jsonify(response)

        except Exception as e:
            logger.error(f"Chart generation failed: {traceback.format_exc()}")
            return jsonify({"error": f"Calculation error: {str(e)}"}), 500

    @app.route("/output/<path:filename>")
    def serve_chart(filename):
        """Serve generated chart SVG files."""
        output_dir = app.config.get("OUTPUT_DIR", "output")
        return send_from_directory(output_dir, filename)

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
    app.run(host="0.0.0.0", port=5000, debug=True)
