import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
from datetime import datetime
import json

# Firebase configuration
FIREBASE_CONFIG = {
    "type": "service_account",
    "project_id": "receipts-ocr-3381a",
    "private_key_id": "",
    "private_key": "",
    "client_email": "",
    "client_id": "",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": ""
}

# Initialize Firebase Admin SDK
def initialize_firebase():
    if not firebase_admin._apps:
        try:
            # Try to use service account key file if it exists
            if os.path.exists('serviceAccountKey.json'):
                cred = credentials.Certificate('serviceAccountKey.json')
                firebase_admin.initialize_app(cred)
            else:
                # Use environment variables or default credentials
                # For development, you'll need to download the service account key
                # from Firebase Console > Project Settings > Service Accounts
                print("Warning: serviceAccountKey.json not found")
                print("Please download your service account key from Firebase Console")
                print("Go to: https://console.firebase.google.com/project/receipts-ocr-3381a/settings/serviceaccounts/adminsdk")
                return None
        except Exception as e:
            print(f"Firebase initialization error: {e}")
            print("Please check your Firebase service account key")
            return None
    
    return firestore.client()

def format_receipt_data(raw_data):
    """
    Convert raw OCR data to the desired format with logging
    """
    import logging
    firebase_logger = logging.getLogger('FIREBASE_SERVICE')
    firebase_logger.setLevel(logging.DEBUG)
    
    firebase_logger.info("🔄 FORMATTING RECEIPT DATA FOR FIREBASE")
    firebase_logger.info(f"📥 Input raw_data keys: {list(raw_data.keys())}")
    
    formatted_data = {
        "store": {
            "name": raw_data.get("merchant_name") or "Unknown Store",
            "location": None,
            "phone": None,
            "pharmacy_phone": None,
            "store_hours": None
        },
        "receipt": {
            "date": raw_data.get("transaction_date"),
            "time": raw_data.get("transaction_time"),
            "cashier": None,
            "receipt_id": raw_data.get("receipt_number"),
            "expires": None
        },
        "items": [],
        "summary": {
            "items_purchased": 0,
            "subtotal": raw_data.get("subtotal"),
            "savings": None,
            "total": raw_data.get("total_amount")
        },
        "payment": {
            "method": raw_data.get("payment_method"),
            "card_type": None,
            "last4": None,
            "amount": raw_data.get("total_amount"),
            "transaction_id": None,
            "ref_no": None
        },
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "processed_by": "OCR",
            "raw_ocr_text": raw_data.get("raw_ocr_text", ""),
            "normalized_ocr_text": raw_data.get("normalized_ocr_text", ""),
            "correlation_id": raw_data.get("correlation_id")
        }
    }
    
    firebase_logger.info("📝 MAPPING STORE DATA:")
    firebase_logger.info(f"  store.name: '{raw_data.get('merchant_name')}' -> '{formatted_data['store']['name']}'")
    firebase_logger.info(f"  store.location: '{raw_data.get('store_location')}' -> '{formatted_data['store']['location']}'")
    firebase_logger.info(f"  store.phone: '{raw_data.get('store_phone')}' -> '{formatted_data['store']['phone']}'")
    
    # Map additional store fields
    formatted_data["store"]["location"] = raw_data.get("store_location")
    formatted_data["store"]["phone"] = raw_data.get("store_phone")
    formatted_data["store"]["store_hours"] = raw_data.get("store_hours")
    formatted_data["store"]["pharmacy_phone"] = raw_data.get("pharmacy_phone")
    firebase_logger.info(f"  store.pharmacy_phone: '{raw_data.get('pharmacy_phone')}' -> '{formatted_data['store']['pharmacy_phone']}'")
    
    firebase_logger.info("📝 MAPPING RECEIPT DATA:")
    firebase_logger.info(f"  receipt.date: '{raw_data.get('transaction_date')}' -> '{formatted_data['receipt']['date']}'")
    firebase_logger.info(f"  receipt.time: '{raw_data.get('transaction_time')}' -> '{formatted_data['receipt']['time']}'")
    firebase_logger.info(f"  receipt.cashier: '{raw_data.get('cashier')}' -> '{formatted_data['receipt']['cashier']}'")
    
    # Map additional receipt fields
    formatted_data["receipt"]["cashier"] = raw_data.get("cashier")
    formatted_data["receipt"]["expires"] = raw_data.get("expires")
    firebase_logger.info(f"  receipt.expires: '{raw_data.get('expires')}' -> '{formatted_data['receipt']['expires']}'")
    
    firebase_logger.info("📝 MAPPING SUMMARY DATA:")
    firebase_logger.info(f"  summary.subtotal: {raw_data.get('subtotal')} -> {formatted_data['summary']['subtotal']}")
    firebase_logger.info(f"  summary.total: {raw_data.get('total_amount')} -> {formatted_data['summary']['total']}")
    firebase_logger.info(f"  summary.savings: {raw_data.get('savings')} -> will be updated")
    
    # Map additional summary fields
    formatted_data["summary"]["savings"] = raw_data.get("savings")
    
    # Format items
    firebase_logger.info("📝 FORMATTING ITEMS:")
    raw_items = raw_data.get("items", [])
    firebase_logger.info(f"  Raw items count: {len(raw_items)}")
    
    formatted_items = []
    total_quantity = 0
    
    for i, item in enumerate(raw_items):
        firebase_logger.info(f"  Item {i+1}: {item}")
        formatted_item = {
            "name": item.get("name", "Unknown Item"),
            "quantity": item.get("quantity", 1),
            "unit_price": item.get("unit_price", 0.0),
            "total": item.get("total_price", item.get("total", 0.0))
        }
        # Preserve parsing metadata when available
        meta_keys = ["parse_mode", "separator", "sequence", "total_source", "unit_source"]
        meta = {k: item.get(k) for k in meta_keys if k in item}
        if meta:
            formatted_item["meta"] = meta
        formatted_items.append(formatted_item)
        total_quantity += formatted_item["quantity"]
        firebase_logger.info(f"    -> Formatted: {formatted_item}")
    
    formatted_data["items"] = formatted_items
    formatted_data["summary"]["items_purchased"] = total_quantity
    
    firebase_logger.info(f"  Total formatted items: {len(formatted_items)}")
    firebase_logger.info(f"  Total quantity: {total_quantity}")
    
    # Map payment details if available
    pay = raw_data.get('payment', {}) if isinstance(raw_data.get('payment'), dict) else {}
    if pay:
        formatted_data['payment']['card_type'] = pay.get('card_type')
        formatted_data['payment']['last4'] = pay.get('last4')
        formatted_data['payment']['transaction_id'] = pay.get('transaction_id')
        formatted_data['payment']['ref_no'] = pay.get('ref_no')
        firebase_logger.info("📝 MAPPING PAYMENT DATA:")
        firebase_logger.info(f"  payment.method: '{formatted_data['payment']['method']}'")
        firebase_logger.info(f"  payment.card_type: '{formatted_data['payment']['card_type']}'")
        firebase_logger.info(f"  payment.last4: '{formatted_data['payment']['last4']}'")
        firebase_logger.info(f"  payment.transaction_id: '{formatted_data['payment']['transaction_id']}'")
        firebase_logger.info(f"  payment.ref_no: '{formatted_data['payment']['ref_no']}'")

    firebase_logger.info("📤 FINAL FORMATTED DATA:")
    firebase_logger.info(json.dumps(formatted_data, indent=2))
    
    return formatted_data

def verify_firebase_token(id_token):
    """
    Verify Firebase ID token and return user info
    """
    try:
        if not id_token:
            return {
                'success': False,
                'error': 'Empty token',
                'message': 'ID token is empty or None'
            }
        
        # Ensure Firebase is initialized
        db = initialize_firebase()
        if db is None:
            return {
                'success': False,
                'error': 'Firebase not initialized',
                'message': 'Firebase Admin SDK is not properly initialized'
            }
            
        print(f"Verifying token for user: {id_token[:50]}...")  # Debug log
        decoded_token = auth.verify_id_token(id_token)
        print(f"Token verified successfully for user: {decoded_token.get('email')}")  # Debug log
        
        return {
            'success': True,
            'user_id': decoded_token['uid'],
            'email': decoded_token.get('email'),
            'name': decoded_token.get('name'),
            'exp': decoded_token.get('exp'),
            'iat': decoded_token.get('iat')
        }
    except auth.ExpiredIdTokenError as e:
        print(f"Token expired error: {str(e)}")
        return {
            'success': False,
            'error': 'Token expired',
            'message': 'Firebase ID token has expired. Please refresh your session.'
        }
    except auth.RevokedIdTokenError as e:
        print(f"Token revoked error: {str(e)}")
        return {
            'success': False,
            'error': 'Token revoked', 
            'message': 'Firebase ID token has been revoked. Please sign in again.'
        }
    except auth.InvalidIdTokenError as e:
        print(f"Invalid token error: {str(e)}")
        return {
            'success': False,
            'error': 'Invalid token',
            'message': f'Firebase ID token is invalid: {str(e)}'
        }
    except Exception as e:
        print(f"General token verification error: {str(e)}")
        return {
            'success': False,
            'error': 'Verification failed',
            'message': f'Failed to verify Firebase ID token: {str(e)}'
        }

def save_receipt_data(receipt_data, user_id):
    """
    Save receipt data to Firebase Firestore for a specific user
    """
    try:
        db = initialize_firebase()
        if db is None:
            return {
                'success': False,
                'error': 'Firebase not initialized',
                'message': 'Failed to initialize Firebase. Please check your service account key.'
            }
        
        # Format the data according to the new structure
        formatted_data = format_receipt_data(receipt_data)
        
        # Add user information
        formatted_data['user_id'] = user_id
        formatted_data['metadata']['user_id'] = user_id
        
        # Add to user's receipts subcollection
        doc_ref = db.collection('users').document(user_id).collection('receipts').add(formatted_data)
        
        # Also add to global receipts collection for admin purposes (optional)
        db.collection('receipts').add({**formatted_data, 'document_id': doc_ref[1].id})
        
        return {
            'success': True,
            'document_id': doc_ref[1].id,
            'message': 'Receipt saved successfully',
            'formatted_data': formatted_data
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to save receipt to Firebase'
        }

def get_user_receipts(user_id):
    """
    Retrieve all receipts for a specific user
    """
    try:
        db = initialize_firebase()
        if db is None:
            return {'success': False, 'message': 'Firebase not initialized'}
            
        receipts = []
        docs = db.collection('users').document(user_id).collection('receipts').stream()
        
        for doc in docs:
            receipt_data = doc.to_dict()
            receipt_data['id'] = doc.id
            receipts.append(receipt_data)
        
        return {'success': True, 'data': receipts}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_user_receipt_by_id(user_id, receipt_id):
    """
    Retrieve a specific receipt for a user
    """
    try:
        db = initialize_firebase()
        if db is None:
            return {'success': False, 'message': 'Firebase not initialized'}
            
        doc_ref = db.collection('users').document(user_id).collection('receipts').document(receipt_id)
        doc = doc_ref.get()
        
        if doc.exists:
            return {'success': True, 'data': doc.to_dict()}
        else:
            return {'success': False, 'message': 'Receipt not found'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_receipt_by_id(receipt_id):
    """
    Retrieve a receipt by its document ID
    """
    try:
        db = initialize_firebase()
        if db is None:
            return {'success': False, 'message': 'Firebase not initialized'}
            
        doc_ref = db.collection('receipts').document(receipt_id)
        doc = doc_ref.get()
        
        if doc.exists:
            return {'success': True, 'data': doc.to_dict()}
        else:
            return {'success': False, 'message': 'Receipt not found'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_all_receipts():
    """
    Retrieve all receipts
    """
    try:
        db = initialize_firebase()
        if db is None:
            return {'success': False, 'message': 'Firebase not initialized'}
            
        receipts = []
        docs = db.collection('receipts').stream()
        
        for doc in docs:
            receipt_data = doc.to_dict()
            receipt_data['id'] = doc.id
            receipts.append(receipt_data)
        
        return {'success': True, 'data': receipts}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}