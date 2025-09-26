import firebase_admin
from firebase_admin import credentials, firestore
import os
from datetime import datetime
import json

# Initialize Firebase Admin SDK
def initialize_firebase():
    if not firebase_admin._apps:
        # For now, we'll use the web config you provided
        # You'll need to get a service account key for admin SDK
        # But we can start with Firestore client configuration
        
        # This is a temporary solution - you'll need service account key
        # Download it from Firebase Console > Project Settings > Service Accounts
        try:
            cred = credentials.Certificate('serviceAccountKey.json')
            firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"Firebase initialization error: {e}")
            print("Please download your service account key and place it as 'serviceAccountKey.json'")
            return None
    
    return firestore.client()

def save_receipt_data(receipt_data):
    """
    Save receipt data to Firebase Firestore
    """
    try:
        db = initialize_firebase()
        if db is None:
            return {
                'success': False,
                'error': 'Firebase not initialized',
                'message': 'Failed to initialize Firebase'
            }
        
        # Add timestamp
        receipt_data['created_at'] = datetime.now()
        receipt_data['updated_at'] = datetime.now()
        
        # Add to receipts collection
        doc_ref = db.collection('receipts').add(receipt_data)
        
        return {
            'success': True,
            'document_id': doc_ref[1].id,
            'message': 'Receipt saved successfully'
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to save receipt'
        }

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