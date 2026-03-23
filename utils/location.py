"""
Real-Time Location Service
Gets exact location of the laptop including:
- City
- Area / Locality
- Nearby landmarks
- Google Maps link
"""

import requests
import logging

logger = logging.getLogger(__name__)


def get_location():
    """
    Get real-time location of the laptop.
    Tries multiple providers for reliability.
    Returns full location with city, area, landmarks.
    """
    providers = [_ipinfo, _ipapi, _ipapiis]

    for fn in providers:
        try:
            result = fn()
            if result and result.get("city"):
                # Get nearby landmarks via reverse geocoding
                result = _add_landmarks(result)
                logger.info(f"[LOCATION] {result['full_address']}")
                return result
        except Exception as e:
            logger.warning(f"[LOCATION] Provider failed: {e}")
            continue

    # Fallback — Hyderabad default
    return _fallback()


def _ipinfo():
    r = requests.get("https://ipinfo.io/json", timeout=5)
    d = r.json()
    lat, lon = d.get("loc", "17.3850,78.4867").split(",")
    return _build(
        city=d.get("city", ""),
        region=d.get("region", ""),
        country=d.get("country", "IN"),
        postal=d.get("postal", ""),
        org=d.get("org", ""),
        lat=float(lat),
        lon=float(lon),
        source="ipinfo.io"
    )


def _ipapi():
    r = requests.get("http://ip-api.com/json/?fields=status,city,regionName,country,countryCode,zip,lat,lon,district,isp", timeout=5)
    d = r.json()
    if d.get("status") != "success":
        return None
    return _build(
        city=d.get("city", ""),
        region=d.get("regionName", ""),
        country=d.get("countryCode", "IN"),
        postal=d.get("zip", ""),
        org=d.get("isp", ""),
        lat=float(d.get("lat", 17.3850)),
        lon=float(d.get("lon", 78.4867)),
        source="ip-api.com"
    )


def _ipapiis():
    r = requests.get("https://ipapi.co/json/", timeout=5)
    d = r.json()
    return _build(
        city=d.get("city", ""),
        region=d.get("region", ""),
        country=d.get("country_code", "IN"),
        postal=d.get("postal", ""),
        org=d.get("org", ""),
        lat=float(d.get("latitude",  17.3850)),
        lon=float(d.get("longitude", 78.4867)),
        source="ipapi.co"
    )


def _build(city, region, country, postal, org, lat, lon, source):
    maps_link    = f"https://maps.google.com/?q={lat},{lon}"
    full_address = f"{city}, {region}, {country}"
    if postal:
        full_address += f" - {postal}"
    return {
        "city":         city,
        "region":       region,
        "country":      country,
        "postal":       postal,
        "org":          org,
        "lat":          lat,
        "lon":          lon,
        "maps_link":    maps_link,
        "full_address": full_address,
        "area":         "",
        "landmarks":    [],
        "source":       source,
    }


def _add_landmarks(loc):
    """
    Use OpenStreetMap Nominatim reverse geocoding to get
    area name and nearby landmarks (hospitals, police, junctions).
    Free, no API key needed.
    """
    try:
        lat = loc["lat"]
        lon = loc["lon"]

        # Reverse geocode for area/locality
        headers = {"User-Agent": "AccidentWatch/1.0"}
        r = requests.get(
            f"https://nominatim.openstreetmap.org/reverse",
            params={
                "lat":            lat,
                "lon":            lon,
                "format":         "json",
                "addressdetails": 1,
                "zoom":           16,
            },
            headers=headers,
            timeout=6
        )
        data = r.json()
        addr = data.get("address", {})

        # Extract area/locality
        area = (
            addr.get("suburb") or
            addr.get("neighbourhood") or
            addr.get("quarter") or
            addr.get("city_district") or
            addr.get("county") or
            ""
        )
        road = addr.get("road", "")
        loc["area"]   = area
        loc["road"]   = road

        # Build detailed address
        parts = [p for p in [road, area, loc["city"], loc["region"]] if p]
        loc["full_address"] = ", ".join(parts)

        # Search nearby landmarks
        landmarks = _get_nearby_landmarks(lat, lon, headers)
        loc["landmarks"] = landmarks

    except Exception as e:
        logger.warning(f"[LOCATION] Landmark fetch failed: {e}")

    return loc


def _get_nearby_landmarks(lat, lon, headers):
    """
    Search for nearby hospitals, police stations,
    fire stations, junctions within 1km.
    """
    landmarks = []
    searches = [
        ("amenity", "hospital"),
        ("amenity", "police"),
        ("amenity", "fire_station"),
        ("highway", "traffic_signals"),
    ]

    for key, value in searches:
        try:
            query = f"""
[out:json][timeout:5];
node["{key}"="{value}"](around:1000,{lat},{lon});
out 1;
"""
            r = requests.post(
                "https://overpass-api.de/api/interpreter",
                data=query,
                headers=headers,
                timeout=6
            )
            elements = r.json().get("elements", [])
            for el in elements[:1]:
                name = el.get("tags", {}).get("name", "")
                if name:
                    landmarks.append(f"{name} ({value.replace('_',' ')})")
        except Exception:
            continue

    return landmarks[:3]  # Max 3 landmarks


def _fallback():
    """Hyderabad fallback when all providers fail."""
    return {
        "city":         "Hyderabad",
        "region":       "Telangana",
        "country":      "IN",
        "postal":       "500001",
        "org":          "",
        "lat":          17.3850,
        "lon":          78.4867,
        "maps_link":    "https://maps.google.com/?q=17.3850,78.4867",
        "full_address": "Hyderabad, Telangana, IN",
        "area":         "Hyderabad",
        "road":         "",
        "landmarks":    [],
        "source":       "fallback",
    }


def format_location_for_sms(loc):
    """Format location info for SMS message."""
    lines = []
    lines.append(f"📍 {loc['full_address']}")
    if loc.get("road"):
        lines.append(f"🛣  Road   : {loc['road']}")
    if loc.get("area"):
        lines.append(f"🏘  Area   : {loc['area']}")
    if loc.get("postal"):
        lines.append(f"📮 PIN    : {loc['postal']}")
    if loc.get("landmarks"):
        lines.append(f"🏥 Nearby : {', '.join(loc['landmarks'])}")
    lines.append(f"🗺  Maps   : {loc['maps_link']}")
    return "\n".join(lines)


def format_location_for_call(loc):
    """Format location for spoken voice message."""
    parts = []
    if loc.get("road"):
        parts.append(loc["road"])
    if loc.get("area"):
        parts.append(loc["area"])
    parts.append(loc.get("city", "Hyderabad"))
    parts.append(loc.get("region", "Telangana"))

    location_str = ", ".join([p for p in parts if p])

    landmark_str = ""
    if loc.get("landmarks"):
        landmark_str = f"Near {loc['landmarks'][0]}. "

    return location_str, landmark_str
