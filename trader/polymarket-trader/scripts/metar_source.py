"""
METAR Observation Source — Fetch current weather observations from aviation stations.

Sources (tried in order):
  1. aviationweather.gov — free, no API key, US government (PRIMARY)
  2. NOAA TGFTP — plain text, no key, fallback only

Optional fallback (silently skipped if no API key present):
  - CheckWX — free tier (10k calls/month), decoded JSON
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# CheckWX API key (optional fallback only - silently skips if not present)
_ENV_PATH = Path(os.path.expanduser("~/.tinyclaw/polymarket.env"))
_CHECKWX_KEY = None

def _load_checkwx_key():
    """Load CheckWX key if available. Returns empty string if not found (no error/warning)."""
    global _CHECKWX_KEY
    if _CHECKWX_KEY is not None:
        return _CHECKWX_KEY
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text().splitlines():
            if line.strip().startswith("CHECKWX_API_KEY="):
                _CHECKWX_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                return _CHECKWX_KEY
    _CHECKWX_KEY = ""
    return _CHECKWX_KEY


# ---------------------------------------------------------------------------
# Raw METAR parsing
# ---------------------------------------------------------------------------

def parse_metar_temp_c(raw: str) -> float | None:
    """
    Extract temperature in Celsius from a raw METAR string.

    Format: TT/DD where T=temperature, D=dewpoint
    Negative values prefixed with M (minus), e.g. M03/M08 = -3°C / -8°C
    """
    match = re.search(r'\b(M?\d{2})/(M?\d{2})\b', raw)
    if not match:
        return None
    temp_str = match.group(1)
    return float(-int(temp_str[1:]) if temp_str.startswith('M') else int(temp_str))


# ---------------------------------------------------------------------------
# Source 1: aviationweather.gov
# ---------------------------------------------------------------------------

def _fetch_avwx(icao: str, hours: int = 0) -> list | None:
    """Fetch METAR(s) from aviationweather.gov. Returns list of observation dicts."""
    url = f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json"
    if hours > 0:
        url += f"&hours={hours}"
    try:
        req = Request(url, headers={"User-Agent": "TinyClaw/1.0"})
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data if isinstance(data, list) and data else None
    except Exception:
        return None


def _parse_avwx_obs(obs: dict) -> dict | None:
    """Convert aviationweather.gov observation dict to our standard format."""
    temp_c = obs.get("temp")
    if temp_c is None:
        return None

    obs_time_unix = obs.get("obsTime")
    if obs_time_unix:
        obs_dt = datetime.fromtimestamp(obs_time_unix, tz=timezone.utc)
        age_min = int((datetime.now(timezone.utc) - obs_dt).total_seconds() / 60)
        obs_time_iso = obs_dt.isoformat()
    else:
        age_min = 999
        obs_time_iso = ""

    return {
        "icao": obs.get("icaoId", ""),
        "temp_c": float(temp_c),
        "temp_f": float(temp_c) * 9 / 5 + 32,
        "obs_time": obs_time_iso,
        "age_minutes": age_min,
        "raw": obs.get("rawOb", ""),
        "source": "aviationweather",
    }


# ---------------------------------------------------------------------------
# Source 2: CheckWX
# ---------------------------------------------------------------------------

def _fetch_checkwx(icao: str) -> dict | None:
    """Fetch latest METAR from CheckWX (requires API key)."""
    key = _load_checkwx_key()
    if not key:
        return None
    url = f"https://api.checkwx.com/metar/{icao}/decoded"
    try:
        req = Request(url, headers={"X-API-Key": key, "User-Agent": "TinyClaw/1.0"})
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read())
        results = data.get("data", [])
        if not results:
            return None
        obs = results[0]

        temp_c = obs.get("temperature", {}).get("celsius")
        if temp_c is None:
            return None

        # Parse observation time
        obs_time_str = obs.get("observed", "")
        age_min = 999
        obs_time_iso = ""
        if obs_time_str:
            try:
                obs_dt = datetime.fromisoformat(obs_time_str.replace("Z", "+00:00"))
                age_min = int((datetime.now(timezone.utc) - obs_dt).total_seconds() / 60)
                obs_time_iso = obs_dt.isoformat()
            except Exception:
                pass

        return {
            "icao": obs.get("icao", icao),
            "temp_c": float(temp_c),
            "temp_f": float(temp_c) * 9 / 5 + 32,
            "obs_time": obs_time_iso,
            "age_minutes": age_min,
            "raw": obs.get("raw_text", ""),
            "source": "checkwx",
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Source 3: NOAA TGFTP
# ---------------------------------------------------------------------------

def _fetch_tgftp(icao: str) -> dict | None:
    """Fetch latest METAR from NOAA TGFTP plain text."""
    url = f"https://tgftp.nws.noaa.gov/data/observations/metar/stations/{icao}.TXT"
    try:
        req = Request(url, headers={"User-Agent": "TinyClaw/1.0"})
        resp = urlopen(req, timeout=10)
        text = resp.read().decode("utf-8", errors="replace")
        lines = text.strip().splitlines()
        if len(lines) < 2:
            return None

        # First line: observation time (YYYY/MM/DD HH:MM)
        time_line = lines[0].strip()
        raw_metar = lines[1].strip()

        temp_c = parse_metar_temp_c(raw_metar)
        if temp_c is None:
            return None

        # Parse observation time
        age_min = 999
        obs_time_iso = ""
        try:
            obs_dt = datetime.strptime(time_line, "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)
            age_min = int((datetime.now(timezone.utc) - obs_dt).total_seconds() / 60)
            obs_time_iso = obs_dt.isoformat()
        except Exception:
            pass

        return {
            "icao": icao,
            "temp_c": temp_c,
            "temp_f": temp_c * 9 / 5 + 32,
            "obs_time": obs_time_iso,
            "age_minutes": age_min,
            "raw": raw_metar,
            "source": "tgftp",
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_metar_observation(icao: str) -> dict | None:
    """
    Fetch the latest METAR observation for a given ICAO station code.

    Returns dict with temp_c, temp_f, obs_time, age_minutes, raw, source.
    Returns None if all sources fail, observation is stale (>90 min), or ICAO is invalid.
    """
    if not icao or len(icao) != 4:
        return None

    icao = icao.upper()

    # Source 1: aviationweather.gov (PRIMARY - no key required)
    avwx = _fetch_avwx(icao)
    if avwx:
        obs = _parse_avwx_obs(avwx[0])
        if obs and obs["age_minutes"] <= 90:
            return obs

    # Source 2: NOAA TGFTP (fallback, no key)
    tgftp = _fetch_tgftp(icao)
    if tgftp and tgftp["age_minutes"] <= 90:
        return tgftp

    # Source 3: CheckWX (optional fallback - silently skipped if no key)
    checkwx = _fetch_checkwx(icao)
    if checkwx and checkwx["age_minutes"] <= 90:
        return checkwx

    return None


def get_daily_high_so_far(icao: str) -> dict | None:
    """
    Return the maximum temperature observed so far at this station today (UTC).

    Fetches last 24h of METAR observations and returns the running maximum.
    """
    if not icao or len(icao) != 4:
        return None

    icao = icao.upper()

    # Use aviationweather.gov 24h history
    obs_list = _fetch_avwx(icao, hours=24)
    if not obs_list:
        return None

    max_temp_c = None
    obs_count = 0
    first_obs_utc = None
    last_obs_utc = None

    for obs in obs_list:
        temp_c = obs.get("temp")
        if temp_c is None:
            continue

        obs_count += 1
        temp_c = float(temp_c)

        if max_temp_c is None or temp_c > max_temp_c:
            max_temp_c = temp_c

        obs_time_unix = obs.get("obsTime")
        if obs_time_unix:
            obs_iso = datetime.fromtimestamp(obs_time_unix, tz=timezone.utc).isoformat()
            if first_obs_utc is None or obs_iso < first_obs_utc:
                first_obs_utc = obs_iso
            if last_obs_utc is None or obs_iso > last_obs_utc:
                last_obs_utc = obs_iso

    if max_temp_c is None:
        return None

    return {
        "icao": icao,
        "max_temp_c": max_temp_c,
        "max_temp_f": max_temp_c * 9 / 5 + 32,
        "obs_count": obs_count,
        "first_obs_utc": first_obs_utc or "",
        "last_obs_utc": last_obs_utc or "",
    }


def assess_resolution_confidence(
    icao: str,
    threshold_temp_c: float,
    side: str,
    hours_to_resolution: float,
) -> dict:
    """
    Assess how confirmed the outcome looks based on METAR observations.

    Returns dict with thesis_confirmed, thesis_impossible, suggest_topup, etc.
    """
    result = {
        "metar_available": False,
        "current_temp_c": None,
        "daily_high_c": None,
        "thesis_confirmed": False,
        "thesis_impossible": False,
        "confidence_note": "METAR unavailable",
        "suggest_topup": False,
        "max_topup_price": 0.0,
    }

    # Fetch current observation
    obs = get_metar_observation(icao)
    if obs:
        result["metar_available"] = True
        result["current_temp_c"] = obs["temp_c"]

    # Fetch daily high
    daily = get_daily_high_so_far(icao)
    if daily:
        result["daily_high_c"] = daily["max_temp_c"]

    if not result["metar_available"] and result["daily_high_c"] is None:
        return result

    daily_high = result["daily_high_c"]
    current_temp = result["current_temp_c"]
    side = side.upper()

    # --- Time-scaled max top-up price ---
    if hours_to_resolution >= 6:
        max_topup = 0.75
    elif hours_to_resolution >= 4:
        max_topup = 0.78
    elif hours_to_resolution >= 2:
        max_topup = 0.82
    elif hours_to_resolution >= 1:
        max_topup = 0.88
    else:
        max_topup = 0.92
    result["max_topup_price"] = max_topup

    # --- Thesis confirmation logic ---
    if side == "NO":
        # NO bet: temp will NOT exceed threshold
        if daily_high is not None and daily_high < threshold_temp_c:
            if hours_to_resolution < 3:
                # Physically unlikely to gain 2°C+ in final 3h of a cooling day
                result["thesis_confirmed"] = True
                result["confidence_note"] = (
                    f"CONFIRMED: daily high {daily_high:.1f}°C < threshold {threshold_temp_c:.1f}°C "
                    f"with {hours_to_resolution:.1f}h to go — unlikely to breach"
                )
                result["suggest_topup"] = True
            else:
                result["confidence_note"] = (
                    f"Favorable: daily high {daily_high:.1f}°C < threshold {threshold_temp_c:.1f}°C "
                    f"but {hours_to_resolution:.1f}h remain — too early to confirm"
                )

        # Check if threshold was already breached (daily high or current)
        breached_temp = None
        if daily_high is not None and daily_high >= threshold_temp_c:
            breached_temp = daily_high
        elif current_temp is not None and current_temp >= threshold_temp_c:
            breached_temp = current_temp

        if breached_temp is not None:
            # Already breached — NO thesis is impossible
            result["thesis_impossible"] = True
            result["thesis_confirmed"] = False
            result["suggest_topup"] = False
            result["confidence_note"] = (
                f"IMPOSSIBLE: observed high {breached_temp:.1f}°C >= threshold {threshold_temp_c:.1f}°C — "
                f"threshold already breached"
            )

    elif side == "YES":
        # YES bet: temp WILL exceed threshold
        if daily_high is not None and daily_high >= threshold_temp_c:
            # Already happened — YES is confirmed
            result["thesis_confirmed"] = True
            result["confidence_note"] = (
                f"CONFIRMED: daily high {daily_high:.1f}°C >= threshold {threshold_temp_c:.1f}°C — "
                f"already reached"
            )
            result["suggest_topup"] = True

        if daily_high is not None and daily_high < threshold_temp_c and hours_to_resolution < 2:
            # Below threshold with <2h to go — likely impossible
            result["thesis_impossible"] = True
            result["confidence_note"] = (
                f"UNLIKELY: daily high {daily_high:.1f}°C < threshold {threshold_temp_c:.1f}°C "
                f"with only {hours_to_resolution:.1f}h to go"
            )

    return result
