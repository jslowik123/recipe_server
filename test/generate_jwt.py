# generate_jwt.py
import jwt
import time
import uuid
from dotenv import load_dotenv
import os

load_dotenv()
# === DEINE SUPABASE DATEN ===
SUPABASE_JWT_SECRET = os.getenv('SUPABASE_JWT_SECRET')

# === FUNKTION: JWT für normalen User ===
def generate_user_jwt(user_id=None, email="test@example.com"):
    if user_id is None:
        user_id = str(uuid.uuid4())  # Zufällige UUID

    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",    # WICHTIG für RLS
        "aud": "authenticated",
        "iss": "supabase",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600  # 1 Stunde gültig
    }

    token = jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")
    return token

# === FUNKTION: JWT für Admin (service_role) ===
def generate_service_jwt():
    payload = {
        "role": "service_role",     # Admin-Rechte
        "iss": "supabase",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600
    }
    return jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")

# === TEST ===
if __name__ == "__main__":
    print("User JWT:")
    print(generate_user_jwt())
    print("\nService JWT:")
    print(generate_service_jwt())