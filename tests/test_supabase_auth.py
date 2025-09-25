#!/usr/bin/env python3
"""
Quick test for Supabase JWT authentication
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

def test_supabase_jwt():
    """Test different ways to set JWT authentication"""

    # Create client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")  # anon key

    print(f"Supabase URL: {url[:20]}..." if url else "No URL")
    print(f"Supabase Key: {key[:20]}..." if key else "No Key")

    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_KEY in .env")
        return None

    supabase: Client = create_client(url, key)

    # Test JWT token (replace with real one)
    test_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

    print("\n=== Testing different JWT auth methods ===")

    # Method 1: Direct header (_headers)
    print("\n1. Testing _headers method...")
    try:
        print(f"_headers type: {type(supabase.auth._headers)}")
        print(f"_headers content: {supabase.auth._headers}")

        supabase.auth._headers['Authorization'] = f'Bearer {test_jwt}'
        print("✅ Set via auth._headers")
        print(f"Updated headers: {supabase.auth._headers}")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Method 2: Session method
    print("\n2. Testing session method...")
    try:
        supabase.auth.session = {"access_token": test_jwt}
        print("✅ Set session directly")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Method 3: Check for other methods
    print("\n3. Available auth methods:")
    auth_methods = [attr for attr in dir(supabase.auth) if not attr.startswith('_')]
    for method in auth_methods:
        print(f"  - {method}")

    return supabase

if __name__ == "__main__":
    test_supabase_jwt()