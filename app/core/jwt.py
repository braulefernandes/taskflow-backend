import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings

SUPPORTED_ALGORITHMS = {"HS256": hashlib.sha256}


class TokenError(Exception):
    pass


class TokenExpiredError(TokenError):
    pass


class InvalidTokenError(TokenError):
    pass


def create_access_token(
    *,
    subject: str,
    expires_delta: timedelta | None = None,
    organization_id: str | None = None,
    role: str | None = None,
    issued_at: datetime | None = None,
    secret_key: str | None = None,
    algorithm: str | None = None,
) -> str:
    token_algorithm = algorithm or settings.jwt_algorithm
    token_secret = secret_key or settings.jwt_secret_key
    now = issued_at or datetime.now(UTC)
    expires_at = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if organization_id is not None:
        payload["org"] = organization_id
    if role is not None:
        payload["role"] = role

    return encode_jwt(payload, secret_key=token_secret, algorithm=token_algorithm)


def decode_access_token(
    token: str,
    *,
    secret_key: str | None = None,
    algorithm: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    expected_algorithm = algorithm or settings.jwt_algorithm
    token_secret = secret_key or settings.jwt_secret_key
    payload = decode_jwt(
        token,
        secret_key=token_secret,
        algorithm=expected_algorithm,
    )
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        raise InvalidTokenError("Token invalido.")
    current_time = int((now or datetime.now(UTC)).timestamp())
    if expires_at <= current_time:
        raise TokenExpiredError("Token expirado.")
    if not isinstance(payload.get("sub"), str) or not payload["sub"]:
        raise InvalidTokenError("Token invalido.")
    return payload


def get_token_subject(token: str) -> str:
    return str(decode_access_token(token)["sub"])


def encode_jwt(
    payload: dict[str, Any],
    *,
    secret_key: str,
    algorithm: str,
) -> str:
    digestmod = SUPPORTED_ALGORITHMS.get(algorithm)
    if digestmod is None:
        raise InvalidTokenError("Algoritmo JWT nao suportado.")

    header = {"typ": "JWT", "alg": algorithm}
    signing_input = ".".join(
        [
            base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        digestmod,
    ).digest()
    return f"{signing_input}.{base64url_encode(signature)}"


def decode_jwt(
    token: str,
    *,
    secret_key: str,
    algorithm: str,
) -> dict[str, Any]:
    digestmod = SUPPORTED_ALGORITHMS.get(algorithm)
    if digestmod is None:
        raise InvalidTokenError("Algoritmo JWT nao suportado.")

    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".", 2)
        header = json.loads(base64url_decode(encoded_header))
        payload = json.loads(base64url_decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        raise InvalidTokenError("Token invalido.") from None

    if header.get("alg") != algorithm:
        raise InvalidTokenError("Token invalido.")

    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        digestmod,
    ).digest()
    received_signature = base64url_decode(encoded_signature)
    if not hmac.compare_digest(received_signature, expected_signature):
        raise InvalidTokenError("Token invalido.")

    if not isinstance(payload, dict):
        raise InvalidTokenError("Token invalido.")
    return payload


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise InvalidTokenError("Token invalido.") from None
