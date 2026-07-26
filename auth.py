import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
from config import settings
from database import get_db

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


def generate_reset_token() -> str:
    """
    Create a URL-safe Base64 token (32 bytes).

    :return: The token.
    """
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """
    Hash the given password reset token.

    :param token: The token to hash.
    :return: The hashed token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


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


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:
    """
    Get the currently logged-in user.

    :param token: A JWT token.
    :param db: Dependency injection for the DB.
    :raises HTTPException (401): A 401 error if the token is invalid or expired
        or if no such user is found.
    :return: The user.
    """

    user_id = verify_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(models.User).where(models.User.id == user_id_int))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# Type alias for the current user
CurrentUser = Annotated[models.User, Depends(get_current_user)]
