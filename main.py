from typing import Annotated
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import models
from database import Base, engine, get_db
from schemas import (
    PostCreate,
    PostResponse,
    PostUpdate,
    UserResponse,
    UserCreate,
    UserUpdate,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Starts up and shuts down the DB connection.

    Loads all the models that inherit from `Base`.

    :param _app: The FastAPI app.
    """
    # Startup
    async with engine.begin() as conn:
        # Creates the DB tables if they don't exit. Idempotent
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

# Mount static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount user-generated files
app.mount("/media", StaticFiles(directory="media"), name="media")

# Set templates
templates = Jinja2Templates(directory="templates")


@app.get("/", include_in_schema=False, name="home")
@app.get("/posts", include_in_schema=False, name="posts")
async def home(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Render the home page with any posts found.

    :param request: The `Request`.
    :param db: Dependency injection for the DB.
    :return: The home page with any posts found.
    """
    result = await db.execute(
        select(models.Post).options(selectinload(models.Post.author))
    )
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request=request, name="home.html", context={"posts": posts, "title": "Home"}
    )


@app.get("/posts/{post_id}", include_in_schema=False)
async def post_page(
    request: Request, post_id: int, db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Render the page corresponding to the given `Post`.

    :param request: The `Request`.
    :param post_id: The `Post` to find.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The page corresponding to the given `Post`.
    """
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = result.scalars().first()
    if post:
        title = post.title[:50]
        return templates.TemplateResponse(
            request, "post.html", {"post": post, "title": title}
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@app.get("/users/{user_id}/posts", include_in_schema=False, name="user_posts")
async def user_posts_page(
    request: Request, user_id: int, db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Get all the `Post`s of a given `User`.

    :param request: The `Request`.
    :param user_id: The `User` to find.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The page containing all the given `User`s `Post`s.
    """
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.user_id == user_id)
    )
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="user_posts.html",
        context={"posts": posts, "user": user, "title": f"{user.username}'s Posts"},
    )


@app.post(
    "/api/v1/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Create a new User.

    :param user: The user to create according to the `UserCreate` model.
    :param db: Dependency injection for the DB.
    :raises HTTPException (400): A 400 error when the user's email or username is not unique.
    :returns: A new `User`.
    """

    result = await db.execute(
        select(models.User).where(models.User.username == user.username)
    )

    # Get the first User object found, or None if no match
    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    result = await db.execute(
        select(models.User).where(models.User.email == user.email)
    )

    existing_email = result.scalars().first()

    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists"
        )

    new_user = models.User(
        username=user.username,
        email=user.email,
    )

    db.add(new_user)  # Doesn't do I/O, so no await
    await db.commit()
    await db.refresh(new_user)  # May not be necessary

    return new_user


@app.get("/api/v1/users/{user_id}", response_model=UserResponse)
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


@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
async def get_user_posts(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
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
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.user_id == user_id)
    )
    posts = result.scalars().all()
    return posts


@app.patch("/api/v1/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int, user_update: UserUpdate, db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Update a given `User`.

    :param user_id: The id of the `User` to update.
    :param user_update: The data to update the `User` with.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :raises HTTPException (400): A 400 error if the user is
        trying to change their username or email to an existing one.
    :return: The updated `User`.
    """

    # Try to find the given user
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # If the user is changing their username, check if it already exists
    if user_update.username is not None and user_update.username != user.username:
        result = await db.execute(
            select(models.User).where(models.User.username == user_update.username)
        )
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

    # Similar for email
    if user_update.email is not None and user_update.email != user.email:
        result = await db.execute(
            select(models.User).where(models.User.email == user_update.email)
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
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Delete a given `User`.

    :param user_id: The `User` to delete.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: HTTP `204 NO CONTENT`.
    """
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    await db.delete(user)  # Does need await
    await db.commit()


@app.get("/api/v1/posts", response_model=list[PostResponse])
async def get_posts(db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Get all the `Post`s.

    :param db: Dependency injection for the DB.
    :return: All the `Post`s in the DB.
    """
    result = await db.execute(
        select(models.Post).options(selectinload(models.Post.author))
    )
    return result.scalars().all()


@app.post(
    "/api/v1/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED
)
async def create_post(post: PostCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Create a new `Post`.

    :param post: The new `Post` to add to the DB.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The new created `Post`.
    """

    # Verify the User exists before creating a Post in their name
    result = await db.execute(select(models.User).where(models.User.id == post.user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    new_post = models.Post(title=post.title, content=post.content, user_id=post.user_id)

    db.add(new_post)
    await db.commit()
    await db.refresh(new_post)

    return new_post


@app.get("/api/v1/post/{post_id}", response_model=PostResponse)
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


@app.put("/api/v1/posts/{post_id}", response_model=PostResponse)
async def update_post_full(
    post_id: int, post_data: PostCreate, db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Completely edit a `Post`.

    :param post_id: The `Post` to edit.
    :param post_data: The new data for the `Post`.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if the `Post` is not found.
    :raises HTTPException (404): A 404 error if the `User` is not found, when changing the `User`.
    :return: The updated `Post`.
    """

    # Try to get the Post
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    # If the client said the post should have a new User, check if the new user even exists
    if post_data.user_id != post.user_id:
        result = await db.execute(
            select(models.User).where(models.User.id == post_data.user_id)
        )
        user = result.scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

    post.title = post_data.title
    post.content = post_data.content
    post.user_id = post_data.user_id

    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    return post


@app.patch("/api/v1/posts/{post_id}", response_model=PostResponse)
async def update_post_partial(
    post_id: int, post_data: PostUpdate, db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Partially edit a `Post`.

    :param post_id: The `Post` to edit.
    :param post_data: The new data for the `Post`.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if the `Post` is not found.
    :return: The partially updated `Post`.
    """

    # Try to get the Post
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    # Only get the data that hasn't changed. This lets PATCH work properly
    update_data = post_data.model_dump(exclude_unset=True)

    # For each of the changed items, set the Posts version of that field to the new value
    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    return post


@app.delete("/api/v1/post/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Delete a given `Post`.

    :param post_id: the `Post` to search for.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: `HTTP 204 NO CONTENT`.
    """
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    await db.delete(post)
    await db.commit()


@app.exception_handler(StarletteHTTPException)
async def general_http_exception_handler(
    request: Request, exception: StarletteHTTPException
):
    """
    Handles HTTP exceptions.

    :param request: The `Request`.
    :param exception: The `HTTPException to handle.
    :return: JSON if this request comes from the API, an HTML `TemplateResponse` otherwise.
    """

    # Handle separately if this comes from the API
    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exception)

    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    # Return an HTML document if this comes from the web
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message,
        },
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exception: RequestValidationError
):
    """
    Handles validation errors by returning a `422 UNPROCESSABLE CONTENT` error.

    :param request: The `Request`.
    :param exception: The FastAPI `RequestValidationError to handle.
    :return: JSON if this request comes from the API, an HTML `TemplateResponse` otherwise.
    """
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, exception)

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
