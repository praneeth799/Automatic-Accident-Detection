"""
Test Location Detection
Run this FIRST to verify your location is detected correctly.
python test_location.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.location import get_location

print("="*55)
print("  LOCATION DETECTION TEST")
print("="*55)
print("\nFetching your laptop location...\n")

loc = get_location()

print(f"  Full Address : {loc['full_address']}")
print(f"  City         : {loc['city']}")
print(f"  Area         : {loc.get('area', 'N/A')}")
print(f"  Road         : {loc.get('road', 'N/A')}")
print(f"  Region       : {loc['region']}")
print(f"  Postal       : {loc.get('postal', 'N/A')}")
print(f"  Latitude     : {loc['lat']}")
print(f"  Longitude    : {loc['lon']}")
print(f"  Maps Link    : {loc['maps_link']}")
print(f"  Source       : {loc.get('source', 'N/A')}")

if loc.get("landmarks"):
    print(f"\n  Nearby Landmarks:")
    for lm in loc["landmarks"]:
        print(f"    • {lm}")
else:
    print(f"\n  Nearby Landmarks: None found within 1km")

print(f"\n{'='*55}")
print("  If location looks correct → run python test_alert.py")
print("  If wrong city → check internet connection")
print("="*55)
