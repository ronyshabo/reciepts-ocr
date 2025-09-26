import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np
import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import uuid

# Load environment variables
load_dotenv()

# Setup logging for OCR service
logging.basicConfig(level=logging.INFO)
ocr_logger = logging.getLogger('OCR_SERVICE')
ocr_logger.setLevel(logging.DEBUG)

# Ensure logs directory and rotating file handler
try:
    os.makedirs('logs', exist_ok=True)
    if not any(isinstance(h, RotatingFileHandler) for h in ocr_logger.handlers):
        file_handler = RotatingFileHandler('logs/ocr.log', maxBytes=1_000_000, backupCount=3)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(name)s: %(message)s')
        file_handler.setFormatter(formatter)
        ocr_logger.addHandler(file_handler)
except Exception as _e:
    # Fall back silently to console-only logging
    pass

def preprocess_image(image_path):
    """
    Enhanced preprocessing for better OCR results on receipts
    """
    # Read image with OpenCV
    img = cv2.imread(image_path)
    
    if img is None:
        raise Exception(f"Could not load image from {image_path}")
    
    # Resize image if too small (helps with OCR accuracy)
    height, width = img.shape[:2]
    if width < 800:
        scale_factor = 800 / width
        new_width = 800
        new_height = int(height * scale_factor)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply slight Gaussian blur to reduce noise while keeping edges
    blurred = cv2.GaussianBlur(gray, (1, 1), 0)
    
    # Apply noise reduction
    denoised = cv2.fastNlMeansDenoising(blurred)
    
    # Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(denoised)
    
    # Apply threshold to get better contrast
    # Try multiple thresholding methods and pick the best one
    thresh1 = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    thresh2 = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    # Use morphological operations to clean up the image
    kernel = np.ones((1,1), np.uint8)
    cleaned = cv2.morphologyEx(thresh1, cv2.MORPH_CLOSE, kernel)
    
    # Save preprocessed image temporarily
    temp_path = "temp_preprocessed.png"
    cv2.imwrite(temp_path, cleaned)
    
    return temp_path

def extract_text_from_image(image_path):
    """
    Extract text from image using enhanced Tesseract OCR
    """
    try:
        # Preprocess image
        preprocessed_path = preprocess_image(image_path)
        
        # Try multiple OCR configurations and pick the best result
        configs = [
            '--oem 3 -l eng --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,:-()/$# ',
            '--oem 3 -l eng --psm 4 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,:-()/$# ',
            '--oem 3 -l eng --psm 6',
            '--oem 3 -l eng --psm 4',
            '--oem 3 -l eng --psm 3'
        ]
        
        best_text = ""
        best_confidence = 0
        
        for config in configs:
            try:
                text = pytesseract.image_to_string(Image.open(preprocessed_path), config=config)
                # Simple heuristic: longer text with reasonable characters is likely better
                confidence_score = len(text.strip()) * (1 - (text.count('!') + text.count('@') + text.count('#')) / len(text) if text else 0)
                
                if confidence_score > best_confidence and len(text.strip()) > 50:
                    best_text = text
                    best_confidence = confidence_score
                    
            except Exception as e:
                print(f"OCR config failed: {config}, error: {e}")
                continue
        
        # If no good result, fall back to basic OCR
        if not best_text.strip():
            best_text = pytesseract.image_to_string(Image.open(preprocessed_path))
        
        # Clean up temporary file
        if os.path.exists(preprocessed_path):
            os.remove(preprocessed_path)
            
        return best_text
    except Exception as e:
        ocr_logger.error(f"OCR Error: {e}")
        return ""


def normalize_ocr_text(text: str) -> str:
    """
    Normalize OCR text: fix common misreads, strip noise lines, unify spacing.
    """
    if not text:
        return text

    # Replace odd unicode quotes/dashes
    replacements = {
        '—': '-', '–': '-', '“': '"', '”': '"', '’': "'", '‘': "'",
        'Orugs': 'Drugs', 'Food-Orugs': 'Food-Drugs', 'Food-Orugs': 'Food-Drugs',
        'iv.hebd.com': 'www.heb.com', 'hebd.com': 'heb.com', 'Hessage': 'Message',
        'InterlNK': 'INTERLINK', 'A M': 'A.M.', 'P M': 'P.M.', ' PW': ' P.M.',
    }
    for a, b in replacements.items():
        text = text.replace(a, b)

    # Normalize decimal commas to dots (e.g., 2,59 -> 2.59)
    text = re.sub(r"(\d),(\d{2})(\b)", r"\1.\2\3", text)
    # Collapse whitespace
    text = re.sub(r"[\t\x0b\x0c\r]", " ", text)
    text = re.sub(r" +", " ", text)

    # Remove excessive repeated punctuation
    text = re.sub(r"[~=]{2,}", "~", text)

    # Remove obvious survey/noise lines later in parsing by filtering, but keep here as-is.
    return text

def clean_item_name(name: str) -> str:
    """Cleanup for item names to remove stray leading tokens and punctuation."""
    if not name:
        return name
    s = name.strip()
    # Remove leading non-letters/punctuation and isolated leading numbers
    s = re.sub(r"^[^A-Za-z]+", "", s)
    s = re.sub(r"^\d+\s+", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s

def parse_receipt_text(text):
    """
    Enhanced parsing specifically for H-E-B receipts with comprehensive logging
    """
    lines = text.strip().split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    
    # Initialize the receipt data structure
    receipt_data = {
        "merchant_name": None,
        "transaction_date": None,
        "transaction_time": None,
        "total_amount": None,
        "subtotal": None,
        "tax_amount": None,
        "items": [],
        "payment_method": None,
        "receipt_number": None,
        "currency": "USD",
        "store_location": None,
        "store_phone": None,
        "pharmacy_phone": None,
        "cashier": None,
        "savings": None,
        "items_purchased": 0,
        "store_hours": None,
        "expires": None
    }
    
    ocr_logger.info("="*60)
    ocr_logger.info("🔍 STARTING OCR RECEIPT PARSING")
    ocr_logger.info("="*60)
    ocr_logger.info(f"📝 Initial receipt_data structure:")
    ocr_logger.info(json.dumps(receipt_data, indent=2))
    
    # Enhanced patterns for H-E-B receipts
    date_patterns = [
        r'\b(\d{2})[/-](\d{2})[/-](\d{2,4})\b',
        r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b',
        r'(\d{4})-(\d{2})-(\d{2})'
    ]
    time_patterns = [
        r'\b(\d{1,2}):(\d{2})\s*(AM|PM)\b',
        r'\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(?:AM|PM)?\b'
    ]
    price_pattern = r'\$?(\d+\.\d{2})'
    phone_pattern = r'\((\d{3})\)\s*(\d{3})-(\d{4})'
    
    # H-E-B specific patterns
    heb_patterns = [
        r'H-E-B|HEB',
        r'Food-Drugs',
        r'Burnet\s*Rd',
        r'Austin.*TX'
    ]
    
    ocr_logger.info(f"📄 Processing {len(lines)} lines of OCR text")
    ocr_logger.info("Raw OCR lines (first 20):")
    for i, line in enumerate(lines[:20]):
        ocr_logger.info(f"  {i:2}: '{line}'")
    
    # Extract H-E-B store information
    ocr_logger.info("\n🏪 EXTRACTING MERCHANT INFORMATION")
    heb_confidence = 0
    for line in lines:
        for pattern in heb_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                heb_confidence += 1
                ocr_logger.info(f"   ✅ H-E-B pattern found in: '{line}' (confidence: {heb_confidence})")
                break
    
    if heb_confidence >= 2:
        receipt_data["merchant_name"] = "H-E-B"
        ocr_logger.info(f"   🎯 MERCHANT SET: receipt_data['merchant_name'] = '{receipt_data['merchant_name']}'")
    else:
        ocr_logger.warning(f"   ⚠️ H-E-B confidence too low ({heb_confidence}), merchant not set")
    
    # Extract store details
    ocr_logger.info("\n📍 EXTRACTING STORE DETAILS")
    # We'll use a sliding window of lines to infer context (e.g., Pharmacy label near phone)
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Store location - look for address patterns
        if re.search(r'\d+.*burnet.*rd.*austin.*tx', line_lower):
            receipt_data["store_location"] = line.strip()
            ocr_logger.info(f"   🎯 LOCATION SET: receipt_data['store_location'] = '{receipt_data['store_location']}'")
            ocr_logger.info(f"      Matched pattern in line {i}: '{line}'")
        elif re.search(r'\d+.*austin.*tx.*\d{5}', line_lower):
            receipt_data["store_location"] = line.strip()
            ocr_logger.info(f"   🎯 LOCATION SET: receipt_data['store_location'] = '{receipt_data['store_location']}'")
            ocr_logger.info(f"      Matched alt pattern in line {i}: '{line}'")
            
        # Phone number
        phone_match = re.search(phone_pattern, line)
        if phone_match:
            phone_formatted = f"({phone_match.group(1)}) {phone_match.group(2)}-{phone_match.group(3)}"
            # Look around for pharmacy keyword within +/- 2 lines
            neighbor_text = ' '.join(lines[max(0, i-2):min(len(lines), i+3)]).lower()
            if ('pharmacy' in neighbor_text or 'pharm' in neighbor_text) and not receipt_data.get('pharmacy_phone'):
                receipt_data['pharmacy_phone'] = phone_formatted
                ocr_logger.info(f"   🎯 PHARMACY_PHONE SET: '{receipt_data['pharmacy_phone']}' from line {i}")
            elif not receipt_data.get('store_phone'):
                receipt_data["store_phone"] = phone_formatted
                ocr_logger.info(f"   🎯 PHONE SET: receipt_data['store_phone'] = '{receipt_data['store_phone']}' from line {i}")
        
        # Store hours
        if re.search(r'(store\s*hours|\d+\s*a\.?m\.?\s*(to|-)\s*\d+\s*p\.?m\.?)', line_lower):
            # capture across up to 2 lines to preserve ranges
            hours_block = ' '.join([line] + lines[i+1:i+3])
            receipt_data["store_hours"] = hours_block.strip()
            ocr_logger.info(f"   🎯 HOURS SET: receipt_data['store_hours'] = '{receipt_data['store_hours']}'")
            ocr_logger.info(f"      Found starting at line {i}: '{hours_block}'")
            
        # Cashier/checkout info
        if re.search(r'self\s*checkout\s*\d+|cashier\s*\d+|self\s*checkout', line_lower):
            receipt_data["cashier"] = line.strip()
            ocr_logger.info(f"   🎯 CASHIER SET: receipt_data['cashier'] = '{receipt_data['cashier']}' (line {i})")
    
    # Extract transaction date and time
    ocr_logger.info("\n📅 EXTRACTING DATE AND TIME")
    for i, line in enumerate(lines):
        # Try different date formats
        for j, date_pattern in enumerate(date_patterns):
            date_match = re.search(date_pattern, line)
            if date_match and not receipt_data["transaction_date"]:
                try:
                    if len(date_match.groups()) == 3:
                        month, day, year = date_match.groups()
                        if len(year) == 2:
                            year = '20' + year
                        formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                        receipt_data["transaction_date"] = formatted_date
                        ocr_logger.info(f"   🎯 DATE SET: receipt_data['transaction_date'] = '{receipt_data['transaction_date']}'")
                        ocr_logger.info(f"      Pattern {j} matched in line {i}: '{line}'")
                        ocr_logger.info(f"      Raw groups: {date_match.groups()} -> {formatted_date}")
                        break
                except Exception as e:
                    ocr_logger.error(f"   ❌ Date parsing error: {e}")
                    continue
        
        # Extract time
        for j, time_pattern in enumerate(time_patterns):
            time_match = re.search(time_pattern, line)
            if time_match and not receipt_data["transaction_time"]:
                try:
                    hour = time_match.group(1)
                    minute = time_match.group(2)
                    period = time_match.group(3) if len(time_match.groups()) >= 3 else ""
                    formatted_time = f"{hour}:{minute} {period}".strip()
                    receipt_data["transaction_time"] = formatted_time
                    ocr_logger.info(f"   🎯 TIME SET: receipt_data['transaction_time'] = '{receipt_data['transaction_time']}'")
                    ocr_logger.info(f"      Pattern {j} matched in line {i}: '{line}'")
                    ocr_logger.info(f"      Raw groups: {time_match.groups()} -> {formatted_time}")
                    break
                except Exception as e:
                    ocr_logger.error(f"   ❌ Time parsing error: {e}")
                    continue
    
    # Extract receipt ID and receipt expiry
    ocr_logger.info("\n🆔 EXTRACTING RECEIPT ID")
    receipt_id_patterns = [
        r'(\d{13,}[A-Z]+\d+[/]\d+[/]\d+)',  # Long format like 6959040925251107A674/73/00202
        r'receipt.*?([A-Z0-9/]{10,})',
        r'ref.*?no.*?[:\s]*([A-Z0-9]+)',
        r'transaction.*?id.*?[:\s]*([A-Z0-9]+)'
    ]
    
    for i, line in enumerate(lines):
        for j, pattern in enumerate(receipt_id_patterns):
            match = re.search(pattern, line, re.IGNORECASE)
            if match and not receipt_data["receipt_number"]:
                receipt_data["receipt_number"] = match.group(1)
                ocr_logger.info(f"   🎯 RECEIPT_ID SET: receipt_data['receipt_number'] = '{receipt_data['receipt_number']}'")
                ocr_logger.info(f"      Pattern {j} matched in line {i}: '{line}'")
                break
        if receipt_data["receipt_number"]:
            break

    # Extract expiry
    for i, line in enumerate(lines):
        m = re.search(r'receipt\s+expires\s+on\s+(\d{2})[-/](\d{2})[-/](\d{2,4})', line, re.IGNORECASE)
        if m:
            mm, dd, yy = m.groups()
            if len(yy) == 2:
                yy = '20' + yy
            receipt_data['expires'] = f"{yy}-{mm}-{dd}"
            ocr_logger.info(f"   🎯 EXPIRES SET: receipt_data['expires'] = '{receipt_data['expires']}' (line {i})")
            break
    
    # Extract totals and amounts
    ocr_logger.info("\n💰 EXTRACTING FINANCIAL DATA")
    for i, line in enumerate(lines):
        line_lower = line.lower().replace('*', '').replace('~', '')

        # Prioritize explicit 'Total Sale' line if present
        if re.search(r'\btotal\s*sale\b', line_lower):
            m = re.search(r'(\d+\.\d{2})', line)
            if m:
                try:
                    receipt_data["total_amount"] = float(m.group(1))
                    ocr_logger.info(f"   🎯 TOTAL_SALE SET: receipt_data['total_amount'] = {receipt_data['total_amount']} (line {i}) -> '{line}'")
                    continue
                except Exception as e:
                    ocr_logger.error(f"   ❌ Total Sale parsing error: {e}")
        
        # Look for subtotal
        if re.search(r'subtotal', line_lower):
            price_matches = re.findall(price_pattern, line)
            if price_matches:
                try:
                    amount = float(price_matches[-1])
                    receipt_data["subtotal"] = amount
                    ocr_logger.info(f"   🎯 SUBTOTAL SET: receipt_data['subtotal'] = {receipt_data['subtotal']}")
                    ocr_logger.info(f"      Found in line {i}: '{line}' -> extracted: {price_matches}")
                except Exception as e:
                    ocr_logger.error(f"   ❌ Subtotal parsing error: {e}")
        
        # Look for total
        elif re.search(r'total', line_lower) and not re.search(r'subtotal', line_lower):
            price_matches = re.findall(price_pattern, line)
            if price_matches:
                try:
                    amount = float(price_matches[-1])
                    receipt_data["total_amount"] = amount
                    ocr_logger.info(f"   🎯 TOTAL SET: receipt_data['total_amount'] = {receipt_data['total_amount']}")
                    ocr_logger.info(f"      Found in line {i}: '{line}' -> extracted: {price_matches}")
                except Exception as e:
                    ocr_logger.error(f"   ❌ Total parsing error: {e}")
        
        # Look for tax
        elif re.search(r'tax', line_lower):
            price_matches = re.findall(price_pattern, line)
            if price_matches:
                try:
                    amount = float(price_matches[-1])
                    receipt_data["tax_amount"] = amount
                    ocr_logger.info(f"   🎯 TAX SET: receipt_data['tax_amount'] = {receipt_data['tax_amount']}")
                    ocr_logger.info(f"      Found in line {i}: '{line}' -> extracted: {price_matches}")
                except Exception as e:
                    ocr_logger.error(f"   ❌ Tax parsing error: {e}")
        
        # Look for savings
        elif re.search(r'sav(ed|ings?)', line_lower):
            price_matches = re.findall(price_pattern, line)
            if price_matches:
                try:
                    amount = float(price_matches[-1])
                    receipt_data["savings"] = amount
                    ocr_logger.info(f"   🎯 SAVINGS SET: receipt_data['savings'] = {receipt_data['savings']}")
                    ocr_logger.info(f"      Found in line {i}: '{line}' -> extracted: {price_matches}")
                except Exception as e:
                    ocr_logger.error(f"   ❌ Savings parsing error: {e}")
        
        # Items purchased count
        elif re.search(r'items?\s*purchased', line_lower):
            numbers = re.findall(r'\b(\d+)\b', line)
            if numbers:
                try:
                    count = int(numbers[0])
                    receipt_data["items_purchased"] = count
                    ocr_logger.info(f"   🎯 ITEM_COUNT SET: receipt_data['items_purchased'] = {receipt_data['items_purchased']}")
                    ocr_logger.info(f"      Found in line {i}: '{line}' -> extracted: {numbers}")
                except Exception as e:
                    ocr_logger.error(f"   ❌ Items purchased parsing error: {e}")
    
    # Extract payment information
    ocr_logger.info("\n💳 EXTRACTING PAYMENT INFORMATION")
    payment_info = {}
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        if re.search(r'debit|credit', line_lower):
            if 'capitalone' in line_lower or 'capital.*one' in line_lower:
                payment_info['card_type'] = 'CapitalOne Debit'
                payment_info['method'] = 'Debit'
                ocr_logger.info(f"   🎯 PAYMENT DETECTED: CapitalOne Debit in line {i}: '{line}'")
            elif 'debit' in line_lower:
                payment_info['method'] = 'Debit'
                ocr_logger.info(f"   🎯 PAYMENT DETECTED: Debit in line {i}: '{line}'")
            elif 'credit' in line_lower:
                payment_info['method'] = 'Credit'
                ocr_logger.info(f"   🎯 PAYMENT DETECTED: Credit in line {i}: '{line}'")
        
        # Look for card last 4 digits
        if re.search(r'\d{4}', line) and ('debit' in line_lower or 'credit' in line_lower or 'chip read' in line_lower):
            card_match = re.search(r'(\d{4})', line)
            if card_match:
                payment_info['last4'] = card_match.group(1)
                ocr_logger.info(f"   🎯 CARD_LAST4 DETECTED: {card_match.group(1)} in line {i}: '{line}'")
        
        # Look for reference numbers
        if re.search(r'ref.*no', line_lower):
            ref_match = re.search(r'ref.*no.*?[:\s]*(\d+)', line_lower)
            if ref_match:
                payment_info['ref_no'] = ref_match.group(1)
                ocr_logger.info(f"   🎯 REF_NO DETECTED: {ref_match.group(1)} in line {i}: '{line}'")
        
        # Look for approval/transaction numbers
        if re.search(r'appr.*no|transaction', line_lower):
            trans_match = re.search(r'(?:appr.*no|transaction).*?[:\s]*(\d+)', line_lower)
            if trans_match:
                payment_info['transaction_id'] = trans_match.group(1)
                ocr_logger.info(f"   🎯 TRANS_ID DETECTED: {trans_match.group(1)} in line {i}: '{line}'")
    
    # Apply payment info
    receipt_data["payment_method"] = payment_info.get('method')
    if payment_info:
        receipt_data['payment'] = payment_info
    if payment_info.get('method'):
        ocr_logger.info(f"   🎯 PAYMENT_METHOD SET: receipt_data['payment_method'] = '{receipt_data['payment_method']}'")
    
    # Extract items - This is the trickiest part for poor OCR
    ocr_logger.info("\n🛒 EXTRACTING ITEMS")
    items = []
    item_extraction_attempts = 0
    consumed_indices = set()

    # Regexes for two-line and single-line items with named groups, capturing separators and optional sequence numbers
    qty_unit_total_re = re.compile(
        r'(?i)^\s*(?P<qty>\d+)\s*(?:e\s*a\.?|each|x)?\s*@?\s*(?:[A-Za-z0-9]+\s*/\s*)?(?P<unit>\d+\.\d{2})\s*(?:(?P<sep>=|f(?:w)?)|[^0-9])?\s*(?P<total>\d+\.\d{2})\s*(?:[^0-9].*)?$'
    )
    qty_unit_only_re = re.compile(
        r'(?i)^\s*(?P<qty>\d+)\s*(?:e\s*a\.?|each|x)?\s*@?\s*(?:[A-Za-z0-9]+\s*/\s*)?(?P<unit>\d+\.\d{2})\s*(?:[^0-9].*)?$'
    )
    combined_line_total_re = re.compile(
        r'(?i)^(?:(?P<seq>\d+)\s*[-.)]\s*)?(?P<name>.+?)\s+(?P<qty>\d+)\s*(?:e\s*a\.?|each|x)?\s*@?\s*(?:[A-Za-z0-9]+\s*/\s*)?(?P<unit>\d+\.\d{2})\s*(?:(?P<sep>=|f(?:w)?)|[^0-9])?\s*(?P<total>\d+\.\d{2})\s*(?:[^0-9].*)?$'
    )
    combined_line_unit_only_re = re.compile(
        r'(?i)^(?:(?P<seq>\d+)\s*[-.)]\s*)?(?P<name>.+?)\s+(?P<qty>\d+)\s*(?:e\s*a\.?|each|x)?\s*@?\s*(?:[A-Za-z0-9]+\s*/\s*)?(?P<unit>\d+\.\d{2})\s*(?:[^0-9].*)?$'
    )
    name_price_noisy_re = re.compile(
        r'(?i)^(?:(?P<seq>\d+)\s*[-.)]\s*)?(?P<name>.+?)\s*(?P<sep>:|=|~|\$|f(?:w)?)\s*(?P<price>\d+\.\d{2})\s*$'
    )

    seq_prefix_re = re.compile(r'^\s*(?P<seq>\d+)\s*[-.)]\s*')
    def extract_sequence(s: str):
        m = seq_prefix_re.match(s or '')
        return int(m.group('seq')) if m else None

    # Helper to decide if a line looks like an item name-only line
    def looks_like_item_name(s: str) -> bool:
        if not s or re.search(r'\d+\.\d{2}', s):
            return False
        low = s.lower()
        bad = ['survey', 'certificate', 'expires', 'receipt', 'items purchased', 'total', 'subtotal', 'tax', 'debit', 'credit', 'pharmacy', 'store hours']
        if any(b in low for b in bad):
            return False
        # Heuristic: contains at least 2 alphabetic tokens
        tokens = [t for t in re.split(r'\s+', s) if t]
        alpha_tokens = [t for t in tokens if re.search(r'[a-zA-Z]', t)]
        return len(alpha_tokens) >= 2

    i = 0
    while i < len(lines):
        if i in consumed_indices:
            i += 1
            continue
        line = lines[i].strip()
        low = line.lower()

        # Skip clear non-item zones
        non_item_keywords = [
            'food-drugs', 'survey', 'certificate', 'expires', 'burnet rd', 'austin, tx',
            'debit', 'credit', 'ref no', 'appr no', 'aid', 'tsi', 'interlink', 'chip read',
            'phone:', 'pharmacy', 'store hours', 'receipt', 'items purchased', 'subtotal', 'tax', 'total sale'
        ]
        if any(k in low for k in non_item_keywords):
            i += 1
            continue

        # Pattern A-1: current line is qty/unit (with or without total) and previous line is a name -> reverse pairing
        prev_line = lines[i-1].strip() if i-1 >= 0 else None
        if prev_line and (qty_unit_total_re.match(line) or qty_unit_only_re.match(line)) and looks_like_item_name(prev_line) and (i-1) not in consumed_indices:
            try:
                if qty_unit_total_re.match(line):
                    mrev = qty_unit_total_re.match(line)
                    qty = int(mrev.group('qty')); unit_price = float(mrev.group('unit')); total = float(mrev.group('total')); sep = mrev.group('sep')
                else:
                    mrev = qty_unit_only_re.match(line)
                    qty = int(mrev.group('qty')); unit_price = float(mrev.group('unit')); total = round(qty * unit_price, 2); sep = None
                name = clean_item_name(prev_line)
                expected = round(qty * unit_price, 2)
                if abs(expected - total) <= 0.11:
                    total = expected
                item_data = {
                    'name': name,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'total': total,
                    'parse_mode': 'two_line',
                    'total_source': 'computed' if sep is None else 'line_or_snapped',
                    'unit_source': 'line',
                    'separator': sep,
                    'sequence': extract_sequence(prev_line)
                }
                items.append(item_data)
                ocr_logger.info(f"   🎯 ITEM ADDED (reverse pair prev+curr) at {i-1},{i}: {json.dumps(item_data)}")
                consumed_indices.add(i-1); consumed_indices.add(i)
                i += 1
                continue
            except Exception as e:
                ocr_logger.error(f"   ❌ Reverse-pair parse error at {i-1},{i}: {e}")

        # Pattern A0: combined one-line with name + qty + unit + total
        m0 = combined_line_total_re.match(line)
        if m0:
            try:
                name = clean_item_name(m0.group('name').strip())
                qty = int(m0.group('qty'))
                unit_price = float(m0.group('unit'))
                total = float(m0.group('total'))
                sep = m0.group('sep'); seq = m0.group('seq'); seq = int(seq) if seq else None
                expected = round(qty * unit_price, 2)
                if abs(expected - total) <= 0.11:
                    total = expected
                item_data = {
                    'name': name,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'total': total,
                    'parse_mode': 'combined_one_line',
                    'total_source': 'line_or_snapped',
                    'unit_source': 'line',
                    'separator': sep,
                    'sequence': seq
                }
                items.append(item_data)
                ocr_logger.info(f"   🎯 ITEM ADDED (combined 1-line) at {i}: {json.dumps(item_data)}")
                i += 1
                continue
            except Exception as e:
                ocr_logger.error(f"   ❌ Combined 1-line parse error at {i}: {e}")
        else:
            m0b = combined_line_unit_only_re.match(line)
            if m0b:
                try:
                    name = clean_item_name(m0b.group('name').strip())
                    qty = int(m0b.group('qty'))
                    unit_price = float(m0b.group('unit'))
                    total = round(qty * unit_price, 2)
                    seq = m0b.group('seq'); seq = int(seq) if seq else None
                    item_data = {
                        'name': name,
                        'quantity': qty,
                        'unit_price': unit_price,
                        'total': total,
                        'parse_mode': 'combined_one_line_unit_only',
                        'total_source': 'computed',
                        'unit_source': 'line',
                        'separator': None,
                        'sequence': seq
                    }
                    items.append(item_data)
                    ocr_logger.info(f"   🎯 ITEM ADDED (combined 1-line, computed total) at {i}: {json.dumps(item_data)}")
                    i += 1
                    continue
                except Exception as e:
                    ocr_logger.error(f"   ❌ Combined 1-line (unit-only) parse error at {i}: {e}")

        # Guard: if this line looks like a qty/unit line but there's no name before it, don't treat it as an item
        if (qty_unit_total_re.match(line) or qty_unit_only_re.match(line)) and not (prev_line and looks_like_item_name(prev_line)):
            ocr_logger.info(f"   ℹ️ Qty/unit line at {i} without a preceding name; skipping: '{line}'")
            i += 1
            continue

        # Pattern A: name line followed by quantity/price line
        if looks_like_item_name(line) and i + 1 < len(lines):
            next_line = lines[i+1].strip()
            m = qty_unit_total_re.match(next_line)
            if m:
                try:
                    qty = int(m.group('qty'))
                    unit_price = float(m.group('unit'))
                    total = float(m.group('total'))
                    sep = m.group('sep')
                    name = clean_item_name(line)
                    seq = extract_sequence(line)
                    expected = round(qty * unit_price, 2)
                    if abs(expected - total) <= 0.11:
                        total = expected
                    item_data = {
                        'name': name,
                        'quantity': qty,
                        'unit_price': unit_price,
                        'total': total,
                        'parse_mode': 'two_line',
                        'total_source': 'line_or_snapped',
                        'unit_source': 'line',
                        'separator': sep,
                        'sequence': seq
                    }
                    items.append(item_data)
                    ocr_logger.info(f"   🎯 ITEM ADDED (2-line) at {i}-{i+1}: {json.dumps(item_data)}")
                    consumed_indices.add(i); consumed_indices.add(i+1)
                    i += 2
                    continue
                except Exception as e:
                    ocr_logger.error(f"   ❌ Two-line item parse error at {i}: {e}")
            else:
                m_unit_only = qty_unit_only_re.match(next_line)
                if m_unit_only:
                    try:
                        qty = int(m_unit_only.group('qty'))
                        unit_price = float(m_unit_only.group('unit'))
                        total = round(qty * unit_price, 2)
                        name = clean_item_name(line)
                        seq = extract_sequence(line)
                        item_data = {
                            'name': name,
                            'quantity': qty,
                            'unit_price': unit_price,
                            'total': total,
                            'parse_mode': 'two_line_unit_only',
                            'total_source': 'computed',
                            'unit_source': 'line',
                            'separator': None,
                            'sequence': seq
                        }
                        items.append(item_data)
                        ocr_logger.info(f"   🎯 ITEM ADDED (2-line, computed total) at {i}-{i+1}: {json.dumps(item_data)}")
                        consumed_indices.add(i); consumed_indices.add(i+1)
                        i += 2
                        continue
                    except Exception as e:
                        ocr_logger.error(f"   ❌ Two-line (unit-only) parse error at {i}: {e}")
            ocr_logger.info(f"   ℹ️ Name line at {i} but next line not qty/price: '{next_line}'")

        # Pattern B: single-line with noisy separator before price (e.g., 'f')
        m2 = name_price_noisy_re.match(line)
        if m2:
            try:
                name = clean_item_name(m2.group('name').strip())
                price = float(m2.group('price'))
                sep = m2.group('sep'); seq = m2.group('seq'); seq = int(seq) if seq else None
                item_data = {
                    'name': name,
                    'quantity': 1,
                    'unit_price': price,
                    'total': price,
                    'parse_mode': 'single_line',
                    'total_source': 'line',
                    'unit_source': 'line',
                    'separator': sep,
                    'sequence': seq
                }
                items.append(item_data)
                ocr_logger.info(f"   🎯 ITEM ADDED (1-line noisy): {json.dumps(item_data)}")
                i += 1
                continue
            except Exception as e:
                ocr_logger.error(f"   ❌ Noisy single-line parse error at {i}: {e}")

        # Pattern C: fallback to previous single-line patterns
        item_patterns = [
            r'^(\d+)\s+(.+?)\s+(\d+\.\d{2})$',  # Qty Item Price
            r'^(.+?)\s+(\d+\.\d{2})$',            # Item Price
            r'^(\d+)\s*x\s*(.+?)\s+(\d+\.\d{2})$',  # Qty x Item Price
            r'^(.+?)\s+(\d+)\s+(\d+\.\d{2})$'   # Item  Qty  Price
        ]
        matched = False
        for j, pat in enumerate(item_patterns):
            mm = re.search(pat, line)
            if mm:
                groups = mm.groups()
                try:
                    if j == 0:
                        qty = int(groups[0]); name = groups[1].strip(); total = float(groups[2]); unit = round(total/qty, 2) if qty>0 else total
                    elif j == 1:
                        name = groups[0].strip(); total = float(groups[1]); qty = 1; unit = total
                    elif j == 2:
                        qty = int(groups[0]); name = groups[1].strip(); total = float(groups[2]); unit = round(total/qty, 2) if qty>0 else total
                    else:
                        name = groups[0].strip(); qty = int(groups[1]); total = float(groups[2]); unit = round(total/qty, 2) if qty>0 else total
                    item_data = {'name': clean_item_name(name), 'quantity': qty, 'unit_price': unit, 'total': total}
                    items.append(item_data)
                    ocr_logger.info(f"   🎯 ITEM ADDED (fallback j={j}): {json.dumps(item_data)}")
                    matched = True
                    break
                except Exception as e:
                    ocr_logger.error(f"   ❌ Fallback pattern error j={j} at {i}: {e}")
        if not matched:
            # Not an item, move on
            i += 1
        else:
            i += 1
    
    receipt_data["items"] = items
    actual_item_count = sum(item["quantity"] for item in items) if items else receipt_data["items_purchased"]
    receipt_data["items_purchased"] = actual_item_count
    
    ocr_logger.info(f"   🎯 ITEMS SET: receipt_data['items'] = {len(items)} items")
    ocr_logger.info(f"   🎯 ITEM_COUNT UPDATED: receipt_data['items_purchased'] = {receipt_data['items_purchased']}")
    
    # If we couldn't extract items but have an items count, create placeholder
    if not items and receipt_data["items_purchased"] > 0:
        ocr_logger.warning(f"   ⚠️ No items parsed but expected count is {receipt_data['items_purchased']}")
        # Dump surrounding lines to assist debugging
        ocr_logger.info("   🔎 Dumping last 30 OCR lines for item-detection debugging:")
        for idx, l in enumerate(lines[-30:]):
            ocr_logger.info(f"      {len(lines)-30+idx:3}: {l}")
    
    ocr_logger.info("\n" + "="*60)
    ocr_logger.info("📋 FINAL RECEIPT DATA STRUCTURE")
    ocr_logger.info("="*60)
    ocr_logger.info(json.dumps(receipt_data, indent=2))
    
    ocr_logger.info(f"\n📊 PARSING SUMMARY:")
    ocr_logger.info(f"   Merchant: {receipt_data['merchant_name'] or 'NOT_SET'}")
    ocr_logger.info(f"   Date: {receipt_data['transaction_date'] or 'NOT_SET'}")
    ocr_logger.info(f"   Time: {receipt_data['transaction_time'] or 'NOT_SET'}")
    ocr_logger.info(f"   Total: ${receipt_data['total_amount'] or 'NOT_SET'}")
    ocr_logger.info(f"   Items: {len(items)} parsed, {receipt_data['items_purchased']} expected")
    ocr_logger.info(f"   Payment: {receipt_data['payment_method'] or 'NOT_SET'}")
    
    return receipt_data

def process_receipt(image_path):
    """
    Process receipt image using OCR with comprehensive logging
    """
    corr_id = str(uuid.uuid4())[:8]
    ocr_logger.info(f"[{corr_id}] 🚀 STARTING RECEIPT PROCESSING")
    ocr_logger.info(f"[{corr_id}] 📁 Image path: {image_path}")
    
    try:
        # Extract text using OCR
        ocr_logger.info(f"[{corr_id}] 🔤 EXTRACTING TEXT FROM IMAGE")
        extracted_text = extract_text_from_image(image_path)
        ocr_logger.info(f"[{corr_id}] 📝 Raw OCR text length: {len(extracted_text)} characters")

        if not extracted_text.strip():
            ocr_logger.error("❌ No text extracted from image")
            return {
                'success': False,
                'error': 'No text could be extracted from the image',
                'message': 'OCR failed to read any text from the receipt'
            }

        # Normalize and parse the extracted text
        ocr_logger.info(f"[{corr_id}] 🔧 NORMALIZING TEXT")
        normalized_text = normalize_ocr_text(extracted_text)
        ocr_logger.info(f"[{corr_id}] 🔍 PARSING EXTRACTED TEXT")
        receipt_data = parse_receipt_text(normalized_text)

        # Add raw and normalized OCR text and correlation id for debugging
        receipt_data["raw_ocr_text"] = extracted_text
        receipt_data["normalized_ocr_text"] = normalized_text
        receipt_data["correlation_id"] = corr_id
        ocr_logger.info(f"[{corr_id}] ✅ Added raw_ocr_text, normalized_ocr_text, correlation_id to receipt_data")

        ocr_logger.info(f"[{corr_id}] 🎉 RECEIPT PROCESSING COMPLETED SUCCESSFULLY")
        ocr_logger.info(f"[{corr_id}] 📊 Final data keys: {list(receipt_data.keys())}")

        return {
            'success': True,
            'data': receipt_data
        }
    
    except Exception as e:
        error_message = str(e)
        ocr_logger.error(f"💥 RECEIPT PROCESSING FAILED: {error_message}")
        
        if "tesseract" in error_message.lower():
            ocr_logger.error("🔧 Tesseract OCR installation issue detected")
            return {
                'success': False,
                'error': 'Tesseract OCR not installed',
                'message': 'Please install Tesseract OCR: sudo apt-get install tesseract-ocr'
            }
        else:
            return {
                'success': False,
                'error': error_message,
                'message': 'Failed to process receipt with OCR'
            }