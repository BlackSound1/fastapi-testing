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
from routers import posts, users


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

# Include routers
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(posts.router, prefix="/api/v1/posts", tags=["posts"])


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
        select(models.Post)
        .options(selectinload(models.Post.author))
        .order_by(models.Post.date_posted.desc())
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
        .order_by(models.Post.date_posted.desc())
    )
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="user_posts.html",
        context={"posts": posts, "user": user, "title": f"{user.username}'s Posts"},
    )


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"title": "Login"})


@app.get("/register", include_in_schema=False)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"title": "Register"})


@app.get("/account", include_in_schema=False)
async def account_page(request: Request):
    return templates.TemplateResponse(request, "account.html", {"title": "Account"})


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
