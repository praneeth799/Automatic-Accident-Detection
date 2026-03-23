"""
Location Service
Priority order:
1. Windows GPS (laptop built-in GPS if available)
2. WiFi/Network geolocation (most accurate for laptops)
3. IP geolocation fallback
Gets street-level accuracy with landmarks.
"""

import requests
import logging
import subprocess
import json
import time

logger = logging.getLogger(__name__)


def get_location():
    """
    Try GPS first, then WiFi geolocation, then IP fallback.
    Returns full location dict with street, area, landmarks.
    """
    # 1. Try Windows GPS
    loc = _try_windows_gps()
    if loc:
        logger.info(f"[GPS] Location from Windows GPS")
        loc = _add_street_details(loc)
        return loc

    # 2. Try WiFi-based geolocation (Google/Mozilla)
    loc = _try_wifi_location()
    if loc:
        logger.info(f"[WiFi] Location from WiFi geolocation")
        loc = _add_street_details(loc)
        return loc

    # 3. Try IP geolocation providers
    for fn in [_ipinfo, _ipapi, _ipapiis]:
        try:
            loc = fn()
            if loc and loc.get("city"):
                loc = _add_street_details(loc)
                return loc
        except Exception as e:
            logger.warning(f"[IP] Provider failed: {e}")
            continue

    return _fallback()


# ------------------------------------------------------------------ #
#  WINDOWS GPS                                                         #
# ------------------------------------------------------------------ #
def _try_windows_gps():
    """
    Try to get GPS coordinates from Windows Location API.
    Works on laptops with built-in GPS or connected GPS device.
    """
    try:
        # PowerShell script to get Windows GPS
        ps_script = """
Add-Type -AssemblyName System.Device
$watcher = New-Object System.Device.Location.GeoCoordinateWatcher
$watcher.Start()
Start-Sleep -Seconds 5
$pos = $watcher.Position.Location
if ($pos.IsUnknown -eq $false) {
    Write-Output "$($pos.Latitude),$($pos.Longitude),$($pos.Altitude),$($pos.HorizontalAccuracy)"
} else {
    Write-Output "UNAVAILABLE"
}
$watcher.Stop()
"""
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout.strip()

        if output and output != "UNAVAILABLE" and "," in output:
            parts = output.split(",")
            lat   = float(parts[0])
            lon   = float(parts[1])
            acc   = float(parts[3]) if len(parts) > 3 else 999

            if -90 <= lat <= 90 and -180 <= lon <= 180:
                logger.info(f"[GPS] Windows GPS: {lat},{lon} acc:{acc}m")
                return _build(
                    city="", region="Telangana",
                    country="IN", postal="",
                    lat=lat, lon=lon,
                    source="Windows GPS"
                )
    except Exception as e:
        logger.debug(f"[GPS] Windows GPS unavailable: {e}")

    return None


# ------------------------------------------------------------------ #
#  WIFI GEOLOCATION                                                    #
# ------------------------------------------------------------------ #
def _try_wifi_location():
    """
    Use Google Geolocation API with WiFi networks.
    More accurate than IP, works on most laptops.
    Uses Mozilla Location Service (free, no API key).
    """
    try:
        # Get nearby WiFi networks using netsh
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True, text=True, timeout=8
        )

        wifi_data   = result.stdout
        access_points = []

        current_bssid  = None
        current_signal = 0

        for line in wifi_data.split("\n"):
            line = line.strip()
            if "BSSID" in line and ":" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    current_bssid = ":".join(parts[1:]).strip()
            elif "Signal" in line and "%" in line:
                try:
                    sig_str = line.split(":")[1].strip().replace("%","")
                    current_signal = int(sig_str)
                except Exception:
                    current_signal = 50

                if current_bssid:
                    # Convert signal % to dBm approx
                    dbm = int((current_signal / 2) - 100)
                    access_points.append({
                        "macAddress":     current_bssid,
                        "signalStrength": dbm,
                    })
                    current_bssid = None

        if not access_points:
            return None

        # Mozilla Location Service (free, no API key needed)
        payload = {
            "wifiAccessPoints": access_points[:10]
        }

        r = requests.post(
            "https://location.services.mozilla.com/v1/geolocate?key=test",
            json=payload,
            timeout=8,
            headers={"Content-Type": "application/json"}
        )

        if r.status_code == 200:
            data    = r.json()
            loc_obj = data.get("location", {})
            lat     = loc_obj.get("lat")
            lon     = loc_obj.get("lng")
            acc     = data.get("accuracy", 999)

            if lat and lon:
                logger.info(f"[WiFi] Location: {lat},{lon} acc:{acc}m")
                return _build(
                    city="", region="Telangana",
                    country="IN", postal="",
                    lat=float(lat), lon=float(lon),
                    source=f"WiFi (acc:{int(acc)}m)"
                )

    except Exception as e:
        logger.debug(f"[WiFi] WiFi location failed: {e}")

    return None


# ------------------------------------------------------------------ #
#  IP GEOLOCATION PROVIDERS                                            #
# ------------------------------------------------------------------ #
def _ipinfo():
    r = requests.get("https://ipinfo.io/json", timeout=6)
    d = r.json()
    if "bogon" in d:
        return None
    lat, lon = d.get("loc", "17.3850,78.4867").split(",")
    return _build(
        city=d.get("city", ""),
        region=d.get("region", ""),
        country=d.get("country", "IN"),
        postal=d.get("postal", ""),
        lat=float(lat), lon=float(lon),
        source="ipinfo.io"
    )


def _ipapi():
    r = requests.get(
        "http://ip-api.com/json/?fields=status,city,regionName,"
        "country,countryCode,zip,lat,lon",
        timeout=6
    )
    d = r.json()
    if d.get("status") != "success":
        return None
    return _build(
        city=d.get("city", ""),
        region=d.get("regionName", ""),
        country=d.get("countryCode", "IN"),
        postal=d.get("zip", ""),
        lat=float(d.get("lat", 17.3850)),
        lon=float(d.get("lon", 78.4867)),
        source="ip-api.com"
    )


def _ipapiis():
    r = requests.get("https://ipapi.co/json/", timeout=6)
    d = r.json()
    if d.get("error"):
        return None
    return _build(
        city=d.get("city", ""),
        region=d.get("region", ""),
        country=d.get("country_code", "IN"),
        postal=d.get("postal", ""),
        lat=float(d.get("latitude",  17.3850)),
        lon=float(d.get("longitude", 78.4867)),
        source="ipapi.co"
    )


# ------------------------------------------------------------------ #
#  HELPERS                                                             #
# ------------------------------------------------------------------ #
def _build(city, region, country, postal, lat, lon, source):
    maps_link    = f"https://maps.google.com/?q={lat},{lon}"
    full_address = ", ".join([p for p in [city, region, country] if p])
    if postal:
        full_address += f" - {postal}"
    return {
        "city":         city,
        "region":       region,
        "country":      country,
        "postal":       postal,
        "lat":          round(lat, 6),
        "lon":          round(lon, 6),
        "maps_link":    maps_link,
        "full_address": full_address,
        "area":         "",
        "road":         "",
        "landmarks":    [],
        "source":       source,
    }


def _add_street_details(loc):
    """Use OpenStreetMap to get street, area, landmarks."""
    try:
        lat     = loc["lat"]
        lon     = loc["lon"]
        headers = {"User-Agent": "AccidentWatch/1.0"}

        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat, "lon": lon,
                "format": "json",
                "addressdetails": 1,
                "zoom": 17,
                "accept-language": "en",
            },
            headers=headers,
            timeout=7
        )
        data = r.json()
        addr = data.get("address", {})

        road = (addr.get("road") or addr.get("pedestrian") or
                addr.get("footway") or "")
        area = (addr.get("suburb") or addr.get("neighbourhood") or
                addr.get("quarter") or addr.get("city_district") or
                addr.get("county") or "")
        city = (addr.get("city") or addr.get("town") or
                addr.get("village") or loc.get("city", ""))
        postal = loc.get("postal") or addr.get("postcode", "")

        loc["road"]   = road
        loc["area"]   = area
        loc["city"]   = city
        loc["postal"] = postal

        parts = [p for p in [road, area, city, loc["region"]] if p]
        loc["full_address"] = ", ".join(parts)
        if postal:
            loc["full_address"] += f" - {postal}"

        loc["landmarks"] = _get_landmarks(lat, lon, headers)

    except Exception as e:
        logger.warning(f"[LOCATION] Street detail failed: {e}")

    return loc


def _get_landmarks(lat, lon, headers):
    """Find nearby hospitals, police within 1.5km."""
    landmarks = []
    searches  = [
        ("amenity", "hospital",     "Hospital"),
        ("amenity", "police",       "Police Station"),
        ("amenity", "fire_station", "Fire Station"),
        ("amenity", "clinic",       "Clinic"),
    ]
    for key, value, label in searches:
        try:
            query = (
                f'[out:json][timeout:5];'
                f'node["{key}"="{value}"]'
                f'(around:1500,{lat},{lon});'
                f'out 1;'
            )
            r = requests.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
                headers=headers,
                timeout=7
            )
            elements = r.json().get("elements", [])
            for el in elements[:1]:
                name = el.get("tags", {}).get("name", "")
                if name:
                    landmarks.append(f"{name} ({label})")
                    break
        except Exception:
            continue
    return landmarks[:3]


def _fallback():
    return {
        "city": "Hyderabad", "region": "Telangana",
        "country": "IN", "postal": "500001",
        "lat": 17.3850, "lon": 78.4867,
        "maps_link": "https://maps.google.com/?q=17.3850,78.4867",
        "full_address": "Hyderabad, Telangana, IN - 500001",
        "area": "", "road": "", "landmarks": [],
        "source": "fallback",
    }


def format_location_for_sms(loc):
    lines = [f"📍 {loc['full_address']}"]
    if loc.get("road"):
        lines.append(f"🛣  Road    : {loc['road']}")
    if loc.get("area"):
        lines.append(f"🏘  Area    : {loc['area']}")
    if loc.get("postal"):
        lines.append(f"📮 PIN     : {loc['postal']}")
    if loc.get("landmarks"):
        lines.append(f"🏥 Nearby  : {', '.join(loc['landmarks'])}")
    lines.append(f"🗺  Maps    : {loc['maps_link']}")
    lines.append(f"📡 Source   : {loc.get('source','IP')}")
    return "\n".join(lines)


def format_location_for_call(loc):
    parts = [p for p in [
        loc.get("road",""),
        loc.get("area",""),
        loc.get("city","Hyderabad"),
        loc.get("region","Telangana")
    ] if p]
    location_str = ", ".join(parts)
    landmark_str = ""
    if loc.get("landmarks"):
        landmark_str = f"Near {loc['landmarks'][0]}. "
    return location_str, landmark_str
