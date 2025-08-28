import jwt
import uuid
import os
from datetime import datetime, timedelta
from typing import Optional, List
import json
from dotenv import load_dotenv


class SupabaseJWTGenerator:
    """
    Generiert gültige Supabase JWTs für Tests und Load Tests
    """

    def __init__(self, jwt_secret: Optional[str] = None):
        """
        Initialisiert den JWT Generator

        Args:
            jwt_secret: Supabase JWT Secret. Falls None, wird SUPABASE_JWT_SECRET aus ENV gelesen

        """
        load_dotenv()
        self.jwt_secret = jwt_secret or os.getenv("SUPABASE_JWT_SECRET")

        if not self.jwt_secret:
            raise ValueError(
                "JWT Secret erforderlich! Setze SUPABASE_JWT_SECRET in ENV oder übergebe jwt_secret Parameter"
            )

    def create_jwt(
            self,
            user_id: Optional[str] = None,
            email: Optional[str] = None,
            expires_in_hours: int = 1
    ) -> str:
        """
        Erstellt einen gültigen Supabase JWT

        Args:
            user_id: User ID (UUID). Falls None, wird automatisch generiert
            email: Email Adresse. Falls None, wird automatisch generiert
            expires_in_hours: JWT Gültigkeit in Stunden (Standard: 1)

        Returns:
            JWT Token als String
        """
        if not user_id:
            user_id = str(uuid.uuid4())

        if not email:
            email = f"test-{user_id[:8]}@example.com"

        now = datetime.now()

        payload = {
            # Erforderlich für deine verify_token Funktion
            "aud": "authenticated",
            "sub": user_id,
            "exp": int((now + timedelta(hours=expires_in_hours)).timestamp()),
            "iat": int(now.timestamp()),

            # Standard Supabase Claims
            "iss": "https://supabase.co/auth/v1",
            "role": "authenticated",
            "aal": "aal1",
            "session_id": str(uuid.uuid4()),
            "email": email,
            "phone": "",
            "is_anonymous": False,
            "app_metadata": {
                "provider": "email",
                "providers": ["email"]
            },
            "user_metadata": {}
        }

        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def create_multiple_jwts(self, count: int) -> List[str]:
        """
        Erstellt mehrere JWTs für Load Tests

        Args:
            count: Anzahl der zu erstellenden JWTs

        Returns:
            Liste von JWT Tokens
        """
        tokens = []
        for i in range(count):
            token = self.create_jwt(
                user_id=f"loadtest-user-{i:04d}",
                email=f"loadtest{i:04d}@example.com"
            )
            tokens.append(token)
        return tokens

    def validate_jwt(self, token: str) -> dict:
        """
        Validiert einen JWT und gibt die Claims zurück (für Debugging)

        Args:
            token: JWT Token

        Returns:
            Dictionary mit den JWT Claims

        Raises:
            jwt.ExpiredSignatureError: Token ist abgelaufen
            jwt.InvalidTokenError: Token ist ungültig
        """
        return jwt.decode(
            token,
            self.jwt_secret,
            algorithms=["HS256"],
            audience="authenticated"
        )

    def debug_jwt(self, token: str) -> None:
        """
        Zeigt JWT Inhalt für Debugging an

        Args:
            token: JWT Token zum Debuggen
        """
        try:
            # Header ohne Validierung
            header = jwt.get_unverified_header(token)
            print("=== JWT HEADER ===")
            print(json.dumps(header, indent=2))

            # Payload ohne Validierung
            payload = jwt.decode(token, options={"verify_signature": False})
            print("\n=== JWT PAYLOAD ===")
            print(json.dumps(payload, indent=2, default=str))

            # Validierung testen
            print("\n=== VALIDIERUNG ===")
            validated = self.validate_jwt(token)
            print("✅ JWT ist gültig!")
            print(f"User ID: {validated.get('sub')}")
            print(f"Email: {validated.get('email')}")
            print(f"Expires: {datetime.fromtimestamp(validated.get('exp'))}")

        except jwt.ExpiredSignatureError:
            print("❌ JWT ist abgelaufen")
        except jwt.InvalidTokenError as e:
            print(f"❌ JWT ist ungültig: {e}")
        except Exception as e:
            print(f"❌ Fehler beim Debuggen: {e}")


# Usage Examples
if __name__ == "__main__":
    # JWT Generator initialisieren
    generator = SupabaseJWTGenerator()

    # Einzelnen JWT erstellen
    print("=== EINZELNER JWT ===")
    single_token = generator.create_jwt(
        user_id="test-user-123",
        email="test@example.com"
    )
    print(f"Token: {single_token[:50]}...")

    # JWT debuggen
    print("\n=== JWT DEBUG ===")
    generator.debug_jwt(single_token)

    # # Mehrere JWTs für Load Test erstellen
    # print("\n=== LOAD TEST JWTS ===")
    # load_test_tokens = generator.create_multiple_jwts(5)  # 5 für Demo
    #
    # for i, token in enumerate(load_test_tokens):
    #     print(f"Token {i + 1}: {token[:30]}...")
    #
    # print(f"\n✅ {len(load_test_tokens)} JWTs für Load Test erstellt!")