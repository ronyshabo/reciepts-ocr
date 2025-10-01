import re
from enum import Enum
from typing import Optional

class Merchant(str, Enum):
    HEB = "H-E-B"
    HOME_DEPOT = "Home Depot"
    RESTAURANT_DEPOT = "Restaurant Depot"
    UNKNOWN = "Unknown"

HEB_PATTERNS = [r"\bH[-\s]*E[-\s]*B\b", r"\bHEB\b", r"Food-Drugs", r"Burnet\s*Rd", r"Austin.*TX"]
HOME_DEPOT_PATTERNS = [r"HOME\s*DEPOT", r"\bHD\b", r"HOMEDepot.com", r"\bPRO\b"]
RESTAURANT_DEPOT_PATTERNS = [r"RESTAURANT\s*DEPOT", r"RD#?\b", r"Jetro|JETRO"]


def _matches_any(text: str, patterns) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def detect_merchant(text: str) -> Merchant:
    text = text or ""
    sample = "\n".join([l.strip() for l in text.splitlines()[:30]])
    if _matches_any(sample, HEB_PATTERNS):
        return Merchant.HEB
    if _matches_any(sample, HOME_DEPOT_PATTERNS):
        return Merchant.HOME_DEPOT
    if _matches_any(sample, RESTAURANT_DEPOT_PATTERNS):
        return Merchant.RESTAURANT_DEPOT
    return Merchant.UNKNOWN
