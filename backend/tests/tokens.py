"""Supabase-style access tokens for tests."""

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

# Tests sign their own tokens with this key; the app is pointed at its public half
# instead of Supabase's JWKS. Same algorithm (ES256) and claims as Supabase.
SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
SUPABASE_URL = "https://test-project.supabase.co"
USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"


def make_token(sub=USER_A, key=SIGNING_KEY, algorithm="ES256", **overrides):
    now = int(time.time())
    claims = {
        "sub": sub,
        "aud": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1",
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
        **overrides,
    }
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": "test-key"})


def auth_header(sub=USER_A):
    return {"Authorization": f"Bearer {make_token(sub)}"}
