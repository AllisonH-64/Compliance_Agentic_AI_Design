"""Bearer-token authentication and role-based access control.

Split out of app/main.py so it can be imported by both the FastAPI app and the
optional LLM triage agent's router (router.py, repo root) without a circular
import -- main.py would otherwise need to import router.py to mount it, while
router.py needs these auth primitives to protect its own endpoint.
"""

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import InvalidTokenError, PyJWKClientError

from app.models import UserRole


AUTH_ALGORITHM = "HS256"
AUTH_SECRET_ENV_VAR = "COMPLIANCE_AUTH_SECRET"
AUTH_KEYS_JSON_ENV_VAR = "COMPLIANCE_AUTH_KEYS_JSON"
AUTH_ISSUER_ENV_VAR = "COMPLIANCE_AUTH_ISSUER"
AUTH_AUDIENCE_ENV_VAR = "COMPLIANCE_AUTH_AUDIENCE"
AUTH_JWKS_URL_ENV_VAR = "COMPLIANCE_AUTH_JWKS_URL"
ALLOW_INSECURE_HEADERS_ENV_VAR = "COMPLIANCE_ALLOW_INSECURE_HEADERS"


def _get_auth_secret() -> str:
    secret = os.getenv(AUTH_SECRET_ENV_VAR)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Missing {AUTH_SECRET_ENV_VAR} environment configuration",
        )

    return secret


def _allow_insecure_headers() -> bool:
    value = os.getenv(ALLOW_INSECURE_HEADERS_ENV_VAR, "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _get_auth_keys() -> dict[str, str]:
    raw_keys = os.getenv(AUTH_KEYS_JSON_ENV_VAR)
    if not raw_keys:
        return {}

    try:
        parsed_keys = json.loads(raw_keys)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid JSON in {AUTH_KEYS_JSON_ENV_VAR}",
        ) from error

    if not isinstance(parsed_keys, dict) or not parsed_keys:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{AUTH_KEYS_JSON_ENV_VAR} must be a non-empty object",
        )

    normalized_keys: dict[str, str] = {}
    for key_id, key_secret in parsed_keys.items():
        if not isinstance(key_id, str) or not key_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{AUTH_KEYS_JSON_ENV_VAR} contains invalid key identifier",
            )
        if not isinstance(key_secret, str) or not key_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{AUTH_KEYS_JSON_ENV_VAR} contains invalid secret value",
            )
        normalized_keys[key_id] = key_secret

    return normalized_keys


def _select_auth_secret(token: str) -> str:
    auth_keys = _get_auth_keys()
    if auth_keys:
        try:
            unverified_header = jwt.get_unverified_header(token)
        except InvalidTokenError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from error

        key_id = unverified_header.get("kid")
        if not isinstance(key_id, str) or not key_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token missing key identifier",
            )

        secret = auth_keys.get(key_id)
        if secret is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token key identifier is not trusted",
            )

        return secret

    return _get_auth_secret()


@lru_cache(maxsize=1)
def _get_jwks_client() -> jwt.PyJWKClient:
    # Cached for the life of the process: Cognito's signing keys rotate rarely, and
    # PyJWKClient does its own internal caching/refresh against the JWKS URL below.
    return jwt.PyJWKClient(os.environ[AUTH_JWKS_URL_ENV_VAR])


def _decode_token_claims(token: str) -> dict:
    issuer = os.getenv(AUTH_ISSUER_ENV_VAR)
    audience = os.getenv(AUTH_AUDIENCE_ENV_VAR)
    jwks_url = os.getenv(AUTH_JWKS_URL_ENV_VAR)

    decode_options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_sub": True,
        "verify_iss": bool(issuer),
        "verify_aud": bool(audience),
    }

    try:
        if jwks_url:
            # Cognito (and OIDC IdPs generally) signs RS256 and never hands out a
            # static secret, so this path fetches the matching public key from the
            # issuer's JWKS instead of the HS256 shared-secret path below.
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token).key
            return jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=issuer,
                audience=audience,
                options=decode_options,
            )

        secret = _select_auth_secret(token)
        return jwt.decode(
            token,
            secret,
            algorithms=[AUTH_ALGORITHM],
            issuer=issuer,
            audience=audience,
            options=decode_options,
        )
    except (InvalidTokenError, PyJWKClientError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from error


def _parse_bearer_token(authorization: str) -> str:
    auth_scheme, _, token = authorization.partition(" ")

    if auth_scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer token format",
        )

    return token


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    role: UserRole


def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> AuthContext:
    if authorization is not None:
        token = _parse_bearer_token(authorization)
        claims = _decode_token_claims(token)

        user_id = claims.get("sub")
        role_claim = claims.get("role")

        if role_claim is None:
            # Cognito Groups map 1:1 onto UserRole (see infra/data_stack.py) and are
            # forwarded in the "cognito:groups" claim -- a list on ID tokens, but
            # handle a comma-separated string too in case an access token is sent.
            groups_claim = claims.get("cognito:groups")
            if isinstance(groups_claim, list) and groups_claim:
                role_claim = groups_claim[0]
            elif isinstance(groups_claim, str) and groups_claim:
                role_claim = groups_claim.split(",")[0].strip()

        if not isinstance(user_id, str) or not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing valid subject claim")

        if not isinstance(role_claim, str) or not role_claim:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing valid role claim")

        try:
            role = UserRole(role_claim)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid user role") from error

        return AuthContext(user_id=user_id, role=role)

    if not _allow_insecure_headers():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token",
        )

    if x_user_id is None or x_user_role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id or X-User-Role header",
        )

    try:
        role = UserRole(x_user_role)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid user role") from error

    return AuthContext(user_id=x_user_id, role=role)


def require_roles(*allowed_roles: UserRole):
    def dependency(current_user: Annotated[AuthContext, Depends(get_current_user)]) -> AuthContext:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User role not permitted")

        return current_user

    return dependency
