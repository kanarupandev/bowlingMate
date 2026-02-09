import re

def extract_speed(text: str) -> str:
    """
    Extracts speeds like '120 km/h' or 'SPEED_EST: 145 km/h' from string.
    Returns '0 km/h' if not found.
    """
    # Look for a number followed by km/h
    match = re.search(r'(\d+)\s*km/h', text)
    if match:
        return f"{match.group(1)} km/h"
    return "0 km/h"
