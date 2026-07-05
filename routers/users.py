from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from PIL import UnidentifiedImageError
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from auth import (
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)
from config import settings
from database import get_db
import models
from image_utils import delete_profile_image, process_profile_image
from schemas import (
    PaginatedPostsResponse,
    PostResponse,
    UserCreate,
    UserPublic,
    UserPrivate,
    UserUpdate,
    Token,
)

router = APIRouter()


@router.post("", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Create a new User.

    :param user: The user to create according to the `UserCreate` model.
    :param db: Dependency injection for the DB.
    :raises HTTPException (400): A 400 error when the user's email or username is not unique.
    :returns: A new `User`.
    """

    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.username) == user.username.lower()
        )
    )

    # Get the first User object found, or None if no match
    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == user.email.lower())
    )

    existing_email = result.scalars().first()

    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists"
        )

    new_user = models.User(
        username=user.username,
        email=user.email.lower(),
        password_hash=hash_password(user.password),
    )

    db.add(new_user)  # Doesn't do I/O, so no await
    await db.commit()
    await db.refresh(new_user)  # May not be necessary

    return new_user


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get an access token bt logging in.

    :param form_data: The form data.
    :param db: Dependency injection for the DB.
    :raises HTTPException (401): A 401 error when the email or password is wrong.
    :return: The new JWT access token.
    """
    # Look up user by case-insensitive email
    # Note: OAuth2PasswordRequestForm uses "username" field, but we treat is as email
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == form_data.username.lower()
        )
    )
    user = result.scalars().first()

    # Verify user exists and pw is correct. Don't reveal which one failed
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email of password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )

    return Token(access_token=access_token, token_type="Bearer")


@router.get("/me", response_model=UserPrivate)
async def get_current_user(current_user: CurrentUser):
    """
    Get the current user's info.

    :param current_user: Dependency injection for the current user.
    :return: The user.
    """
    return current_user


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Get an individual `User` from the DB.

    :param user_id: The id of the `User` to get.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The found `User`.
    """
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if user:
        return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.get("/{user_id}/posts", response_model=PaginatedPostsResponse)
async def get_user_posts(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.posts_per_page,
):
    """
    Get an individual `User's` `Post`s.

    :param user_id: The id of the `User` to get.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The found `Post`s of the `User`.
    """
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    count_result = await db.execute(
        select(func.count())
        .select_from(models.Post)
        .where(models.Post.user_id == user_id),
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.user_id == user_id)
        .order_by(models.Post.date_posted.desc())
        .offset(skip)
        .limit(limit),
    )
    posts = result.scalars().all()

    has_more = skip + len(posts) < total

    return PaginatedPostsResponse(
        posts=[PostResponse.model_validate(post) for post in posts],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.patch("/{user_id}", response_model=UserPrivate)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update a given `User`.

    :param user_id: The id of the `User` to update.
    :param user_update: The data to update the `User` with.
    :param current_user: Dependency injection for the current user.
    :param db: Dependency injection for the DB.
    :raises HTTPException (403): A 403 error if forbidden.
    :raises HTTPException (404): A 404 error if not found.
    :raises HTTPException (400): A 400 error if the user is
        trying to change their username or email to an existing one.
    :return: The updated `User`.
    """

    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user",
        )

    # Try to find the given user
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # If the user is changing their username, check if it already exists
    if (
        user_update.username is not None
        and user_update.username.lower() != user.username.lower()
    ):
        result = await db.execute(
            select(models.User).where(
                func.lower(models.User.username) == user_update.username.lower()
            )
        )
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

    # Similar for email
    if (
        user_update.email is not None
        and user_update.email.lower() != user.email.lower()
    ):
        result = await db.execute(
            select(models.User).where(
                func.lower(models.User.email) == user_update.email.lower()
            )
        )
        existing_email = result.scalars().first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Update the user
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "email":
            setattr(user, field, value.lower())
        else:
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a given `User`.

    :param user_id: The `User` to delete.
    :param current_user: Dependency injection for the current user.
    :param db: Dependency injection for the DB.
    :raises HTTPException (403): A 403 error if forbidden.
    :raises HTTPException (404): A 404 error if not found.
    :return: HTTP `204 NO CONTENT`.
    """

    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this user",
        )
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    old_filename = user.image_file

    await db.delete(user)  # Does need await
    await db.commit()

    if old_filename:
        delete_profile_image(old_filename)


@router.patch("/{user_id}/picture", response_model=UserPrivate)
async def upload_profile_picture(
    user_id: int,
    file: UploadFile,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Update the current user's profile picture.

    :param user_id: The user's ID.
    :param file: The file itself.
    :param current_user: Dependency injection for the current user.
    :param db: Dependency injection for the DB.
    :raises HTTPException (403): A 403 error if forbidden.
    :raises HTTPException (400): A 400 error if image is too big or invalid format.
    """
    # If wrong user
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user's picture",
        )

    content = await file.read()

    # If too big
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large, Maximum size is {settings.max_upload_size_bytes // (1024 * 1024)}MB",
        )

    # Since processing images is CPU-bound, not IO-bound, can't just use async/ await
    # Need to spawn a separate thread for image processing
    try:
        new_filename = await run_in_threadpool(process_profile_image, content)
    except UnidentifiedImageError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Please upload a valid image (JPEG, PNG, GIF, WebP).",
        ) from err

    # Switcheroo
    old_filename = current_user.image_file
    current_user.image_file = new_filename

    # DB before deleting old file in case DB fails
    await db.commit()
    await db.refresh(current_user)

    if old_filename:
        delete_profile_image(old_filename)

    return current_user


@router.delete("/{user_id}/picture", response_model=UserPrivate)
async def delete_user_picture(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete the current user's profile picture.

    :param user_id: The user's ID.
    :param current_user: Dependency injection for the current user.
    :param db: Dependency injection for the DB.
    :raises HTTPException (403): A 403 error if forbidden.
    :raises HTTPException (400): A 400 error if no image to delete.
    """
    # If wrong user
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this user's picture",
        )

    old_filename = current_user.image_file

    # If nothing to delete
    if old_filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile picture to delete",
        )

    # Unset image file
    current_user.image_file = None

    # DB first, in case DB fails
    await db.commit()
    await db.refresh(current_user)

    delete_profile_image(old_filename)

    return current_user
