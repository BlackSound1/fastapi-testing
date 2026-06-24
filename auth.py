from datetime import UTC, datetime, timedelta
from typing import Any
import jwt
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from config import settings


# Create hasher with recommended settings
password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/users/token")


def hash_password(password: str) -> str:
    """
    Hash the given password.

    :param password: The password to hash.
    :return: The hashed password.
    """
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify if a password is correct by checking its plain version
    against the hashed version.

    :param plain_password: The plaintext version of the password.
    :param hashed_password: The hashed version of the password.
    :return: Whether the password is correct.
    """
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """
    Create a JWT access token.

    :param data: The dict of data.
    :param expires_delta: When from now to expire?
    :return: The access token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key.get_secret_value(), algorithm=settings.algorithm
    )
    return encoded_jwt


def verify_access_token(token: str) -> str | None:
    """
    Verifies if a given token is correct.

    :param token: The token to verify.
    :return: The user ID if the token is valid. `None` if not.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    else:
        return payload.get("sub")
