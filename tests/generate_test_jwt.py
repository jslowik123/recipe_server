#!/usr/bin/env python3
"""
Generate test JWT tokens for testing API endpoints
"""
import jwt
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def generate_test_jwt():
    """Generate a test JWT token that works with our Supabase setup"""
    # Get JWT secret from environment
    JWT_SECRET = os.getenv('SUPABASE_JWT_SECRET')

    if not JWT_SECRET:
        raise ValueError("SUPABASE_JWT_SECRET not found in environment variables")

    # Payload mit Supabase-ähnlichen Claims
    payload = {
        'sub': 'test-user-uuid-123',  # Simulierte User-ID
        'aud': 'authenticated',       # Audience - wichtig für Supabase!
        'role': 'authenticated',      # Supabase-Rolle
        'iss': 'supabase',            # Issuer
        'iat': int(time.time()),      # Issued at (aktuelle Zeit)
        'exp': int(time.time()) + 3600,  # Ablauf in 1 Stunde
        'email': 'test@example.com'   # Optional
    }

    # Generiere den JWT mit HS256
    token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')
    return token

def validate_jwt(token, secret=None):
    """Check if a JWT token is valid and not expired"""
    if secret is None:
        secret = os.getenv('SUPABASE_JWT_SECRET')

    try:
        # Decode and validate token
        payload = jwt.decode(
            token,
            secret,
            algorithms=['HS256'],
            audience='authenticated'
        )

        # Check expiration
        exp = payload.get('exp', 0)
        now = int(time.time())

        if exp > now:
            time_left = exp - now
            expires_at = datetime.fromtimestamp(exp)
            print(f"✅ Token is VALID")
            print(f"   Expires: {expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Time left: {time_left // 60}m {time_left % 60}s")
            return True
        else:
            expired_at = datetime.fromtimestamp(exp)
            print(f"❌ Token is EXPIRED")
            print(f"   Expired at: {expired_at.strftime('%Y-%m-%d %H:%M:%S')}")
            return False

    except jwt.ExpiredSignatureError:
        print("❌ Token is EXPIRED")
        return False
    except jwt.InvalidTokenError as e:
        print(f"❌ Token is INVALID: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating token: {e}")
        return False

def get_test_token():
    """Convenience function to get a test token"""
    return generate_test_jwt()

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        # Validate existing token
        token_to_check = sys.argv[1]
        print(f"🔍 Validating provided JWT token...")
        print(f"Token: {token_to_check[:50]}...")
        validate_jwt(token_to_check)
    else:
        # Generate new token
        try:
            print("🔑 Generating new test JWT token...")
            token = generate_test_jwt()
            print('Test-JWT:', token)

            print('\n🔍 Validating generated token...')
            is_valid = validate_jwt(token)

            if is_valid:
                print('\n📋 Payload decoded:')
                JWT_SECRET = os.getenv('SUPABASE_JWT_SECRET')
                decoded = jwt.decode(token, JWT_SECRET, algorithms=['HS256'], audience='authenticated')
                for key, value in decoded.items():
                    if key in ['iat', 'exp']:
                        readable_time = datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S')
                        print(f'  {key}: {value} ({readable_time})')
                    else:
                        print(f'  {key}: {value}')

            print('\n💡 Usage:')
            print('  python3 tests/generate_test_jwt.py                    # Generate new token')
            print('  python3 tests/generate_test_jwt.py <token>           # Validate existing token')
            print('  from tests.generate_test_jwt import get_test_token, validate_jwt')

        except Exception as e:
            print(f'❌ Error generating token: {e}')