from enum import Enum
from typing import Dict, Any

from .detector import Merchant

# For now, reuse the existing H-E-B parser by delegating to ocr_service.parse_receipt_text
# Later, you can move the H-E-B-specific logic into a dedicated module.

def parse_heb(text: str) -> Dict[str, Any]:
    from ..ocr_service import parse_receipt_text as parse_heb_internal
    return parse_heb_internal(text)


def parse_home_depot(text: str) -> Dict[str, Any]:
    # Minimal placeholder: set merchant name and raw text
    return {
        "merchant_name": "Home Depot",
        "raw_ocr_text": text,
        "items": [],
        "summary": {},
    }


def parse_restaurant_depot(text: str) -> Dict[str, Any]:
    # Minimal placeholder: set merchant name and raw text
    return {
        "merchant_name": "Restaurant Depot",
        "raw_ocr_text": text,
        "items": [],
        "summary": {},
    }


def parse_by_merchant(text: str, merchant: Merchant) -> Dict[str, Any]:
    if merchant == Merchant.HEB:
        return parse_heb(text)
    if merchant == Merchant.HOME_DEPOT:
        return parse_home_depot(text)
    if merchant == Merchant.RESTAURANT_DEPOT:
        return parse_restaurant_depot(text)
    # Default fallback: just return raw and unknown merchant
    return {
        "merchant_name": "Unknown",
        "raw_ocr_text": text,
        "items": [],
        "summary": {},
    }
