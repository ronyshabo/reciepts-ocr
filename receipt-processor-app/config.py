import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_secret_key_here'
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY') or 'your_openai_api_key_here'
    FIREBASE_CONFIG = {
        "apiKey": os.environ.get('FIREBASE_API_KEY') or 'your_firebase_api_key_here',
        "authDomain": os.environ.get('FIREBASE_AUTH_DOMAIN') or 'your_firebase_auth_domain_here',
        "projectId": os.environ.get('FIREBASE_PROJECT_ID') or 'your_firebase_project_id_here',
        "storageBucket": os.environ.get('FIREBASE_STORAGE_BUCKET') or 'your_firebase_storage_bucket_here',
        "messagingSenderId": os.environ.get('FIREBASE_MESSAGING_SENDER_ID') or 'your_firebase_messaging_sender_id_here',
        "appId": os.environ.get('FIREBASE_APP_ID') or 'your_firebase_app_id_here',
        "measurementId": os.environ.get('FIREBASE_MEASUREMENT_ID') or 'your_firebase_measurement_id_here'
    }