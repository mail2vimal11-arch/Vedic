"""
Panchanga Engine — PyJHora Integration
========================================
Computes the five limbs of the Vedic day (Panchanga) and
additional auspicious/inauspicious time periods using PyJHora.

Based on:
- Brihat Parashara Hora Shastra (BPHS)
- Vedanga Jyotisha traditions
- Drik (observational) system

Provides:
  - Tithi, Yogam, Karana, Vaara, Nakshatra
  - Rahu Kalam, Yama Ganda, Gulika Kalam
  - Abhijit Muhurta, Brahma Muhurtha
  - Sunrise/Sunset
  - Yogas detected from birth chart
  - Ritu (season) and Samvatsara (Vedic year)
"""

import socket
import swisseph as swe

# Hard cap any geocoding/HTTP calls made by PyJHora at 5 seconds
# (prevents gunicorn worker from hanging indefinitely on Render)
socket.setdefaulttimeout(5)

import jhora.panchanga.drik as drik
from jhora import const

# ── Name Lookup Tables ────────────────────────────────────────────────────

TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Purnima/Amavasya",
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Amavasya"
]

TITHI_PAKSHA = [
    "Shukla","Shukla","Shukla","Shukla","Shukla",
    "Shukla","Shukla","Shukla","Shukla","Shukla",
    "Shukla","Shukla","Shukla","Shukla","Shukla",
    "Krishna","Krishna","Krishna","Krishna","Krishna",
    "Krishna","Krishna","Krishna","Krishna","Krishna",
    "Krishna","Krishna","Krishna","Krishna","Krishna"
]

YOGA_NAMES = [
    "Vishkambha","Priti","Ayushman","Saubhagya","Shobhana",
    "Atiganda","Sukarma","Dhriti","Shula","Ganda",
    "Vriddhi","Dhruva","Vyaghata","Harshana","Vajra",
    "Siddhi","Vyatipata","Variyan","Parigha","Shiva",
    "Siddha","Sadhya","Shubha","Shukla","Brahma",
    "Indra","Vaidhriti"
]

KARANA_NAMES = [
    "Kimstughna","Bava","Balava","Kaulava","Taitila",
    "Garija","Vanija","Vishti","Bava","Balava",
    "Kaulava","Taitila","Garija","Vanija","Vishti",
    "Bava","Balava","Kaulava","Taitila","Garija",
    "Vanija","Vishti","Bava","Balava","Kaulava",
    "Taitila","Garija","Vanija","Vishti","Bava",
    "Balava","Kaulava","Taitila","Garija","Vanija",
    "Vishti","Bava","Balava","Kaulava","Taitila",
    "Garija","Vanija","Vishti","Shakuni","Chatushpada",
    "Naga","Kimstughna"
]

VAARA_NAMES = [
    "Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"
]

VAARA_LORDS = [
    "Moon","Mars","Mercury","Jupiter","Venus","Saturn","Sun"
]

NAKSHATRA_NAMES = [
    "Ashwini","Bharani","Krittika","Rohini","Mrigashira",
    "Ardra","Punarvasu","Pushya","Ashlesha","Magha",
    "Purva Phalguni","Uttara Phalguni","Hasta","Chitra","Swati",
    "Vishakha","Anuradha","Jyeshtha","Mula","Purva Ashadha",
    "Uttara Ashadha","Shravana","Dhanishtha","Shatabhisha",
    "Purva Bhadrapada","Uttara Bhadrapada","Revati","Abhijit"
]

NAKSHATRA_LORDS = [
    "Ketu","Venus","Sun","Moon","Mars",
    "Rahu","Jupiter","Saturn","Mercury","Ketu",
    "Venus","Sun","Moon","Mars","Rahu",
    "Jupiter","Saturn","Mercury","Ketu","Venus",
    "Sun","Moon","Mars","Rahu","Jupiter",
    "Saturn","Mercury","Sun"
]

RITU_NAMES = [
    "Vasanta (Spring)","Grishma (Summer)","Varsha (Monsoon)",
    "Sharad (Autumn)","Hemanta (Pre-Winter)","Shishira (Winter)"
]

YOGA_QUALITY = {
    "Vishkambha": "Inauspicious", "Priti": "Auspicious", "Ayushman": "Auspicious",
    "Saubhagya": "Auspicious", "Shobhana": "Auspicious", "Atiganda": "Inauspicious",
    "Sukarma": "Auspicious", "Dhriti": "Auspicious", "Shula": "Inauspicious",
    "Ganda": "Inauspicious", "Vriddhi": "Auspicious", "Dhruva": "Auspicious",
    "Vyaghata": "Inauspicious", "Harshana": "Auspicious", "Vajra": "Inauspicious",
    "Siddhi": "Auspicious", "Vyatipata": "Inauspicious", "Variyan": "Auspicious",
    "Parigha": "Inauspicious", "Shiva": "Auspicious", "Siddha": "Auspicious",
    "Sadhya": "Auspicious", "Shubha": "Auspicious", "Shukla": "Auspicious",
    "Brahma": "Auspicious", "Indra": "Auspicious", "Vaidhriti": "Inauspicious"
}


# ── Helper Functions ──────────────────────────────────────────────────────

def _float_to_time(h):
    """Convert decimal hours to HH:MM string."""
    if h is None:
        return "N/A"
    try:
        h = float(h) % 24
        hh = int(h)
        mm = int((h - hh) * 60)
        return f"{hh:02d}:{mm:02d}"
    except:
        return "N/A"


def _safe_name(names_list, index, default="Unknown"):
    """Safely get name from list by index."""
    try:
        idx = int(index) % len(names_list)
        return names_list[idx]
    except:
        return default


# ── Main Panchanga Calculation ────────────────────────────────────────────

def compute_panchanga(year, month, day, hour, minute, second,
                      utc_offset, latitude, longitude, city="", country=""):
    """
    Compute full Panchanga for a given birth date/time/place.

    Returns a dict with:
        - Five limbs: tithi, yogam, karana, vaara, nakshatra
        - Auspicious times: rahu_kalam, yama_ganda, gulika_kalam
        - Muhurtas: abhijit, brahma_muhurtha
        - Sunrise / Sunset
        - Ritu (season)
        - Day quality summary
    """
    try:
        # Set up Swiss Ephemeris
        swe.set_sid_mode(swe.SIDM_LAHIRI)

        # Julian Day in UT
        decimal_hour_local = hour + minute / 60.0 + second / 3600.0
        jd_ut = swe.julday(year, month, day, decimal_hour_local - utc_offset)

        # PyJHora place object
        place = drik.Place(city or "Birth Place", latitude, longitude, utc_offset)

        result = {}

        # ── 1. TITHI ──────────────────────────────────────────────────────
        try:
            tit = drik.tithi(jd_ut, place)
            tit_index = int(tit[0]) - 1  # PyJHora returns 1-based
            tit_name = _safe_name(TITHI_NAMES, tit_index)
            paksha = TITHI_PAKSHA[tit_index] if tit_index < len(TITHI_PAKSHA) else "Unknown"
            result["tithi"] = {
                "number": tit_index + 1,
                "name": tit_name,
                "paksha": paksha,
                "completion": round(float(tit[1]), 2) if len(tit) > 1 else None
            }
        except Exception as e:
            result["tithi"] = {"name": "Unknown", "error": str(e)}

        # ── 2. YOGAM ─────────────────────────────────────────────────────
        try:
            yog = drik.yogam(jd_ut, place)
            yog_index = int(yog[0]) - 1
            yog_name = _safe_name(YOGA_NAMES, yog_index)
            result["yogam"] = {
                "number": yog_index + 1,
                "name": yog_name,
                "quality": YOGA_QUALITY.get(yog_name, "Neutral"),
                "completion": round(float(yog[1]), 2) if len(yog) > 1 else None
            }
        except Exception as e:
            result["yogam"] = {"name": "Unknown", "error": str(e)}

        # ── 3. KARANA ─────────────────────────────────────────────────────
        try:
            kar = drik.karana(jd_ut, place)
            kar_index = int(kar[0]) - 1
            kar_name = _safe_name(KARANA_NAMES, kar_index)
            result["karana"] = {
                "number": kar_index + 1,
                "name": kar_name,
                "completion": round(float(kar[1]), 2) if len(kar) > 1 else None
            }
        except Exception as e:
            result["karana"] = {"name": "Unknown", "error": str(e)}

        # ── 4. VAARA (Weekday) ────────────────────────────────────────────
        try:
            vaar = int(drik.vaara(jd_ut))
            result["vaara"] = {
                "number": vaar,
                "name": _safe_name(VAARA_NAMES, vaar),
                "lord": _safe_name(VAARA_LORDS, vaar)
            }
        except Exception as e:
            result["vaara"] = {"name": "Unknown", "error": str(e)}

        # ── 5. NAKSHATRA ──────────────────────────────────────────────────
        try:
            # Get Moon sidereal longitude for nakshatra
            calc_flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
            moon_pos, _ = swe.calc_ut(jd_ut, swe.MOON, calc_flags)
            moon_lon = moon_pos[0]
            nak_index = int(moon_lon / (360 / 27))
            pada = int((moon_lon % (360 / 27)) / (360 / 27 / 4)) + 1
            nak_name = _safe_name(NAKSHATRA_NAMES, nak_index)
            nak_lord = _safe_name(NAKSHATRA_LORDS, nak_index)
            result["nakshatra"] = {
                "number": nak_index + 1,
                "name": nak_name,
                "pada": pada,
                "lord": nak_lord,
                "moon_longitude": round(moon_lon, 4)
            }
        except Exception as e:
            result["nakshatra"] = {"name": "Unknown", "error": str(e)}

        # ── 6. SUNRISE / SUNSET ───────────────────────────────────────────
        try:
            sr = drik.sunrise(jd_ut, place)
            ss = drik.sunset(jd_ut, place)
            result["sunrise"] = sr[1] if len(sr) > 1 else _float_to_time(sr[0])
            result["sunset"] = ss[1] if len(ss) > 1 else _float_to_time(ss[0])
        except Exception as e:
            result["sunrise"] = "N/A"
            result["sunset"] = "N/A"

        # ── 7. RAHU KALAM ─────────────────────────────────────────────────
        try:
            rk = drik.raahu_kaalam(jd_ut, place)
            result["rahu_kalam"] = {
                "start": rk[0] if isinstance(rk[0], str) else _float_to_time(rk[0]),
                "end": rk[1] if isinstance(rk[1], str) else _float_to_time(rk[1])
            }
        except Exception as e:
            result["rahu_kalam"] = {"start": "N/A", "end": "N/A"}

        # ── 8. YAMA GANDA ─────────────────────────────────────────────────
        try:
            yg = drik.yamaganda_kaalam(jd_ut, place)
            result["yama_ganda"] = {
                "start": yg[0] if isinstance(yg[0], str) else _float_to_time(yg[0]),
                "end": yg[1] if isinstance(yg[1], str) else _float_to_time(yg[1])
            }
        except Exception as e:
            result["yama_ganda"] = {"start": "N/A", "end": "N/A"}

        # ── 9. GULIKA KALAM ───────────────────────────────────────────────
        try:
            gk = drik.gulikai_kaalam(jd_ut, place)
            result["gulika_kalam"] = {
                "start": gk[0] if isinstance(gk[0], str) else _float_to_time(gk[0]),
                "end": gk[1] if isinstance(gk[1], str) else _float_to_time(gk[1])
            }
        except Exception as e:
            result["gulika_kalam"] = {"start": "N/A", "end": "N/A"}

        # ── 10. ABHIJIT MUHURTA ───────────────────────────────────────────
        try:
            am = drik.abhijit_muhurta(jd_ut, place)
            result["abhijit_muhurta"] = {
                "start": am[0] if isinstance(am[0], str) else _float_to_time(am[0]),
                "end": am[1] if isinstance(am[1], str) else _float_to_time(am[1])
            }
        except Exception as e:
            result["abhijit_muhurta"] = {"start": "N/A", "end": "N/A"}

        # ── 11. BRAHMA MUHURTHA ───────────────────────────────────────────
        try:
            bm = drik.brahma_muhurtha(jd_ut, place)
            result["brahma_muhurtha"] = {
                "start": _float_to_time(bm[0]),
                "end": _float_to_time(bm[1])
            }
        except Exception as e:
            result["brahma_muhurtha"] = {"start": "N/A", "end": "N/A"}

        # ── 12. CHANDRA BALAM ─────────────────────────────────────────────
        try:
            cb = drik.chandrabalam(jd_ut, place)
            result["chandra_balam"] = {
                "good_houses": list(cb) if cb else [],
                "description": "Houses where Moon's transit is beneficial"
            }
        except Exception as e:
            result["chandra_balam"] = {"good_houses": []}

        # ── 13. RITU (Season) ─────────────────────────────────────────────
        try:
            # Ritu based on solar month (2 solar months = 1 ritu)
            sun_pos, _ = swe.calc_ut(jd_ut, swe.SUN, swe.FLG_SWIEPH | swe.FLG_SIDEREAL)
            solar_month = int(sun_pos[0] / 30) % 12
            ritu_index = solar_month // 2
            ritu_name = _safe_name(RITU_NAMES, ritu_index)
            result["ritu"] = {
                "index": ritu_index + 1,
                "name": ritu_name
            }
        except Exception as e:
            result["ritu"] = {"name": "Unknown"}

        # ── 14. DAY QUALITY SUMMARY ───────────────────────────────────────
        try:
            yogam_quality = result.get("yogam", {}).get("quality", "Neutral")
            tithi_name = result.get("tithi", {}).get("name", "")
            vaara_name = result.get("vaara", {}).get("name", "")
            inauspicious_tithis = ["Ashtami", "Chaturdashi", "Amavasya"]
            tithi_bad = any(t in tithi_name for t in inauspicious_tithis)
            day_quality = "Auspicious" if yogam_quality == "Auspicious" and not tithi_bad else \
                          "Inauspicious" if yogam_quality == "Inauspicious" or tithi_bad else "Neutral"
            result["day_quality"] = {
                "overall": day_quality,
                "note": f"Based on Yogam ({yogam_quality}) and Tithi"
            }
        except:
            result["day_quality"] = {"overall": "Unknown"}

        return result

    except Exception as e:
        return {"error": f"Panchanga calculation failed: {str(e)}"}
