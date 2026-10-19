"""Who is calling: the Supabase access token on every /api request.

Supabase signs access tokens with an asymmetric key (ES256 on this project)
and publishes the public half at a JWKS URL. Verifying locally means no call
to Supabase per request; the keys are fetched once and cached.
"""

import uuid
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Request

from app.config import settings

ALGORITHMS = ["ES256", "RS256"]  # never HS256 or "none"


class Unauthorized(Exception):
    pass


@lru_cache(maxsize=1)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    # Supabase caches this endpoint for 10 minutes; refetch on that schedule so
    # a rotated key is picked up.
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600)


def _signing_key(token: str):
    jwks = _jwks_client(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")
    return jwks.get_signing_key_from_jwt(token).key


def user_id_from(authorization: str | None) -> uuid.UUID:
    """The caller's user id, or Unauthorized with a message safe to show."""
    if not settings.supabase_url:
        # Fail closed: a deploy that forgot SUPABASE_URL must not be open.
        raise Unauthorized("Sign-in is not configured on the server.")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("Sign in to continue.")
    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=ALGORITHMS,
            audience="authenticated",
            issuer=f"{settings.supabase_url}/auth/v1",
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise Unauthorized("Your session is invalid or has expired. Sign in again.") from exc


def _current_user(request: Request) -> uuid.UUID:
    return request.state.user_id  # set by the authenticate middleware


# The signed-in user's id, for any endpoint under /api.
CurrentUser = Annotated[uuid.UUID, Depends(_current_user)]
