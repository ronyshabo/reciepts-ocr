from flask import Flask, request, render_template, jsonify, redirect, url_for, session
from services import process_receipt, save_receipt_data, get_user_receipts, get_user_receipt_by_id, verify_firebase_token
import os
from datetime import datetime
from dotenv import load_dotenv
from functools import wraps

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def require_auth(f):
    """
    Decorator to require authentication for routes
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for Firebase ID token in request headers
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({
                'error': 'Authentication required',
                'message': 'Authorization header missing. Please include Bearer token.',
                'code': 'MISSING_AUTH_HEADER'
            }), 401
        
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'error': 'Authentication required', 
                'message': 'Invalid authorization header format. Use Bearer <token>.',
                'code': 'INVALID_AUTH_FORMAT'
            }), 401
            
        id_token = auth_header[7:]  # Remove 'Bearer ' prefix
        
        try:
            auth_result = verify_firebase_token(id_token)
            if auth_result['success']:
                # Store user info in request context
                request.user = {
                    'user_id': auth_result['user_id'],
                    'email': auth_result['email'],
                    'name': auth_result['name']
                }
                return f(*args, **kwargs)
            else:
                return jsonify({
                    'error': 'Authentication failed',
                    'message': auth_result.get('message', 'Invalid token'),
                    'code': 'TOKEN_VERIFICATION_FAILED',
                    'details': auth_result.get('error')
                }), 401
                
        except Exception as e:
            return jsonify({
                'error': 'Authentication error',
                'message': 'Failed to verify authentication token',
                'code': 'AUTH_PROCESSING_ERROR',
                'details': str(e)
            }), 401
    
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/upload', methods=['POST'])
@require_auth
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file:
        try:
            filename = file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Validate token is still fresh before processing
            # Re-verify the token to ensure it's still valid for the long operation
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                id_token = auth_header[7:]
                auth_result = verify_firebase_token(id_token)
                if not auth_result['success']:
                    return jsonify({
                        'success': False,
                        'error': 'Token validation failed during processing',
                        'message': 'Please refresh your session and try again',
                        'code': 'TOKEN_EXPIRED_DURING_PROCESSING'
                    }), 401
            
            # Process the receipt using OCR
            print(f"Starting OCR processing for user: {request.user['email']}")
            result = process_receipt(filepath)
            print(f"OCR processing completed for user: {request.user['email']}")
            
            if result['success']:
                receipt_data = result['data']
                
                # Final token check before saving to Firebase
                final_auth_result = verify_firebase_token(id_token)
                if not final_auth_result['success']:
                    # OCR succeeded but token expired, return the data anyway but warn user
                    return jsonify({
                        'success': True,
                        'warning': 'Processing completed but session expired during save',
                        'receipt_data': receipt_data,
                        'firebase_result': {'success': False, 'message': 'Session expired during save'},
                        'user': request.user,
                        'message': 'Receipt processed successfully but not saved. Please refresh and try uploading again to save.'
                    })
                
                # Save the processed data to Firebase with user ID
                firebase_result = save_receipt_data(receipt_data, request.user['user_id'])
                
                return jsonify({
                    'success': True,
                    'receipt_data': receipt_data,
                    'firebase_result': firebase_result,
                    'user': request.user
                })
            else:
                return jsonify({
                    'success': False,
                    'error': result.get('error', 'Failed to process receipt')
                }), 500
        
        except Exception as e:
            print(f"Upload error for user {request.user.get('email', 'unknown')}: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Upload processing failed: {str(e)}'
            }), 500
        
        finally:
            # Clean up uploaded file
            try:
                if 'filepath' in locals() and os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass
    
    return jsonify({'error': 'File upload failed'}), 400

@app.route('/validate-session', methods=['POST'])
def validate_session():
    """
    Validate current session and token freshness
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({
            'valid': False,
            'error': 'No token provided'
        }), 401
    
    id_token = auth_header[7:]
    auth_result = verify_firebase_token(id_token)
    
    if auth_result['success']:
        # Calculate time until expiration
        exp_time = auth_result.get('exp', 0)
        current_time = datetime.now().timestamp()
        time_until_exp = exp_time - current_time
        
        return jsonify({
            'valid': True,
            'user': {
                'user_id': auth_result['user_id'],
                'email': auth_result['email'],
                'name': auth_result['name']
            },
            'token_info': {
                'expires_at': exp_time,
                'issued_at': auth_result.get('iat'),
                'time_until_expiration': time_until_exp,
                'expires_soon': time_until_exp < 300  # Less than 5 minutes
            }
        })
    else:
        return jsonify({
            'valid': False,
            'error': auth_result.get('error'),
            'message': auth_result.get('message')
        }), 401

@app.route('/health')
def health_check():
    """
    Health check endpoint
    """
    return jsonify({
        'status': 'healthy',
        'message': 'Receipt Processor API is running',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/refresh-token', methods=['POST'])
def refresh_token():
    """
    Endpoint to help with token refresh validation
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({
            'error': 'Authentication required',
            'message': 'Valid Bearer token required'
        }), 401
    
    id_token = auth_header[7:]
    auth_result = verify_firebase_token(id_token)
    
    if auth_result['success']:
        return jsonify({
            'success': True,
            'message': 'Token is valid',
            'user': {
                'user_id': auth_result['user_id'],
                'email': auth_result['email'],
                'name': auth_result['name']
            },
            'token_info': {
                'expires_at': auth_result.get('exp'),
                'issued_at': auth_result.get('iat')
            }
        })
    else:
        return jsonify({
            'success': False,
            'error': auth_result.get('error'),
            'message': auth_result.get('message')
        }), 401

@app.route('/test-auth')
def test_auth():
    """
    Test route to check Firebase authentication setup
    """
    return jsonify({
        'message': 'Test auth endpoint',
        'instructions': 'Send a POST request with Authorization: Bearer <token> header'
    })

@app.route('/test-auth', methods=['POST'])
@require_auth 
def test_auth_post():
    """
    Test authenticated route
    """
    return jsonify({
        'message': 'Authentication successful!',
        'user': request.user
    })

@app.route('/receipts')
@require_auth
def view_receipts():
    result = get_user_receipts(request.user['user_id'])
    if result['success']:
        return jsonify({
            'success': True,
            'count': len(result['data']),
            'receipts': result['data'],
            'user': request.user
        })
    else:
        return jsonify({'error': result}), 500

@app.route('/receipt/<receipt_id>')
@require_auth
def view_receipt(receipt_id):
    result = get_user_receipt_by_id(request.user['user_id'], receipt_id)
    if result['success']:
        return jsonify({
            'success': True,
            'receipt': result['data'],
            'user': request.user
        })
    else:
        return jsonify({'error': result}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)