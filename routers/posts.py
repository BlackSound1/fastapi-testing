from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import CurrentUser
from database import get_db
import models
from schemas import PostCreate, PostResponse, PostUpdate


router = APIRouter()


@router.get("", response_model=list[PostResponse])
async def get_posts(db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Get all the `Post`s.

    :param db: Dependency injection for the DB.
    :return: All the `Post`s in the DB.
    """
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .order_by(models.Post.date_posted.desc())
    )
    return result.scalars().all()


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post: PostCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Create a new `Post`.

    :param post: The new `Post` to add to the DB.
    :param current_user: Dependency injection for the current user.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The new created `Post`.
    """
    new_post = models.Post(
        title=post.title, content=post.content, user_id=current_user.id
    )

    db.add(new_post)
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])

    return new_post


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Get a given `Post`.

    :param post_id: the `Post` to search for.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The found `Post`.
    """
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = result.scalars().first()
    if post:
        return post
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@router.put("/{post_id}", response_model=PostResponse)
async def update_post_full(
    post_id: int,
    post_data: PostCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Completely edit a `Post`.

    :param post_id: The `Post` to edit.
    :param post_data: The new data for the `Post`.
    :param current_user: Dependency injection for the current user.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if the `Post` is not found.
    :raises HTTPException (403): A 403 error if forbidden.
    :return: The updated `Post`.
    """

    # Try to get the Post
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this post",
        )

    post.title = post_data.title
    post.content = post_data.content

    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    return post


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post_partial(
    post_id: int,
    post_data: PostUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Partially edit a `Post`.

    :param post_id: The `Post` to edit.
    :param post_data: The new data for the `Post`.
    :param current_user: Dependency injection for the current user.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if the `Post` is not found.
    :raises HTTPException (403): A 403 error if forbidden.
    :return: The partially updated `Post`.
    """

    # Try to get the Post
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this post",
        )

    # Only get the data that hasn't changed. This lets PATCH work properly
    update_data = post_data.model_dump(exclude_unset=True)

    # For each of the changed items, set the Posts version of that field to the new value
    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Delete a given `Post`.

    :param post_id: the `Post` to search for.
    :param current_user: Dependency injection for the current user.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :raises HTTPException (403): A 403 error if forbidden.
    :return: `HTTP 204 NO CONTENT`.
    """
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this post",
        )

    await db.delete(post)
    await db.commit()
