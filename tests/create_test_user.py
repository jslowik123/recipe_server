#!/usr/bin/env python3
"""
Create a real test user in Supabase for testing
"""
import os
import uuid
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def create_test_user():
    """Create a test user in Supabase"""

    # Get Supabase credentials
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not service_key:
        print("❌ SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing in .env")
        return None

    print(f"🔗 Connecting to Supabase: {url}")

    try:
        # Create client with service role key (has admin permissions)
        supabase = create_client(url, service_key)

        # Generate consistent test user ID
        test_user_id = "test-user-uuid-123"  # Same as in JWT generator
        test_email = "test@example.com"

        print(f"👤 Creating test user: {test_email}")

        # Try to create user (this might fail if user exists)
        try:
            response = supabase.auth.admin.create_user({
                "email": test_email,
                "password": "testpassword123",
                "user_metadata": {"name": "Test User"},
                "email_confirm": True
            })

            user_id = response.user.id
            print(f"✅ Created new user: {user_id}")
            print(f"📧 Email: {test_email}")

            # Update JWT generator to use real user ID
            update_jwt_generator(user_id)

            return user_id

        except Exception as create_error:
            print(f"⚠️  User creation failed: {create_error}")
            print("User might already exist. Trying to find existing user...")

            # Try to list users to find existing test user
            try:
                users = supabase.auth.admin.list_users()
                for user in users.data:
                    if user.email == test_email:
                        print(f"✅ Found existing test user: {user.id}")
                        update_jwt_generator(user.id)
                        return user.id

                print("❌ Test user not found")
                return None

            except Exception as list_error:
                print(f"❌ Could not list users: {list_error}")
                return None

    except Exception as e:
        print(f"❌ Error connecting to Supabase: {e}")
        return None

def update_jwt_generator(real_user_id):
    """Update the JWT generator to use real user ID"""
    jwt_file = "/Users/jasperslowik/Cursor/apify/tests/generate_test_jwt.py"

    try:
        with open(jwt_file, 'r') as f:
            content = f.read()

        # Replace the test user ID with real one
        updated_content = content.replace(
            "'sub': 'test-user-uuid-123'",
            f"'sub': '{real_user_id}'"
        )

        with open(jwt_file, 'w') as f:
            f.write(updated_content)

        print(f"✅ Updated JWT generator with real user ID: {real_user_id}")

    except Exception as e:
        print(f"⚠️  Could not update JWT generator: {e}")

if __name__ == "__main__":
    user_id = create_test_user()
    if user_id:
        print(f"\n🎉 Test user ready!")
        print(f"User ID: {user_id}")
        print(f"\n💡 Now you can run your WebSocket tests:")
        print(f"python3 tests/test_websocket.py")
    else:
        print(f"\n❌ Failed to create test user")