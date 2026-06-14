from typing import Annotated

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from database import Base, engine, get_db
from schemas import PostCreate, PostResponse, PostUpdate, UserResponse, UserCreate


# Looks at all models that inherit from Base and
# creates the tables if they don't exit. Idempotent
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Mount static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount user-generated files
app.mount("/media", StaticFiles(directory="media"), name="media")

# Set templates
templates = Jinja2Templates(directory="templates")


@app.get("/", include_in_schema=False, name="home")
@app.get("/posts", include_in_schema=False, name="posts")
def home(request: Request, db: Annotated[Session, Depends(get_db)]):
    """
    Render the home page with any posts found.

    :param request: The `Request`.
    :param db: Dependency injection for the DB.
    :return: The home page with any posts found.
    """
    result = db.execute(select(models.Post))
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request=request, name="home.html", context={"posts": posts, "title": "Home"}
    )


@app.get("/posts/{post_id}", include_in_schema=False)
def post_page(request: Request, post_id: int, db: Annotated[Session, Depends(get_db)]):
    """
    Render the page corresponding to the given `Post`.

    :param request: The `Request`.
    :param post_id: The `Post` to find.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The page corresponding to the given `Post`.
    """
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if post:
        title = post.title[:50]
        return templates.TemplateResponse(
            request, "post.html", {"post": post, "title": title}
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@app.get("/users/{user_id}/posts", include_in_schema=False, name="user_posts")
def user_posts_page(
    request: Request, user_id: int, db: Annotated[Session, Depends(get_db)]
):
    """
    Get all the `Post`s of a given `User`.

    :param request: The `Request`.
    :param user_id: The `User` to find.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The page containing all the given `User`s `Post`s.
    """
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    result = db.execute(select(models.Post).where(models.Post.user_id == user_id))
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="user_posts.html",
        context={"posts": posts, "user": user, "title": f"{user.username}'s Posts"},
    )


@app.post(
    "/api/v1/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
def create_user(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
    """
    Create a new User.

    :param user: The user to create according to the `UserCreate` model.
    :param db: Dependency injection for the DB.
    :raises HTTPException (400): A 400 error when the user's email or username is not unique.
    :returns: A new `User`.
    """

    result = db.execute(
        select(models.User).where(models.User.username == user.username)
    )

    # Get the first User object found, or None if no match
    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    result = db.execute(select(models.User).where(models.User.email == user.email))

    existing_email = result.scalars().first()

    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists"
        )

    new_user = models.User(
        username=user.username,
        email=user.email,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)  # May not be necessary

    return new_user


@app.get("/api/v1/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    """
    Get an individual `User` from the DB.

    :param user_id: The id of the `User` to get.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The found `User`.
    """
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if user:
        return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
def get_user_posts(user_id: int, db: Annotated[Session, Depends(get_db)]):
    """
    Get an individual `User's` `Post`s.

    :param user_id: The id of the `User` to get.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The found `Post`s of the `User`.
    """
    result = db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    result = db.execute(select(models.Post).where(models.Post.user_id == user_id))
    posts = result.scalars().all()
    return posts


@app.get("/api/v1/posts", response_model=list[PostResponse])
def get_posts(db: Annotated[Session, Depends(get_db)]):
    """
    Get all the `Post`s.

    :param db: Dependency injection for the DB.
    :return: All the `Post`s in the DB.
    """
    result = db.execute(select(models.Post))
    return result.scalars().all()


@app.post(
    "/api/v1/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED
)
def create_post(post: PostCreate, db: Annotated[Session, Depends(get_db)]):
    """
    Create a new `Post`.

    :param post: The new `Post` to add to the DB.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The new created `Post`.
    """

    # Verify the User exists before creating a Post in their name
    result = db.execute(select(models.User).where(models.User.id == post.user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    new_post = models.Post(title=post.title, content=post.content, user_id=post.user_id)

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    return new_post


@app.get("/api/v1/post/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    """
    Get a given `Post`.

    :param post_id: the `Post` to search for.
    :param db: Dependency injection for the DB.
    :raises HTTPException (404): A 404 error if not found.
    :return: The found `Post`.
    """
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if post:
        return post
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")


@app.put("/api/v1/posts/{post_id}", response_model=PostResponse)
def update_post_full(
    post_id: int, post_data: PostCreate, db: Annotated[Session, Depends(get_db)]
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
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    # If the client said the post should have a new User, check if the new user even exists
    if post_data.user_id != post.user_id:
        result = db.execute(
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

    db.commit()
    db.refresh(post)

    return post


@app.patch("/api/v1/posts/{post_id}", response_model=PostResponse)
def update_post_partial(
    post_id: int, post_data: PostUpdate, db: Annotated[Session, Depends(get_db)]
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
    result = db.execute(select(models.Post).where(models.Post.id == post_id))
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

    db.commit()
    db.refresh(post)

    return post


@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    """
    Handles HTTP exceptions.

    :param request: The `Request`.
    :param exception: The `HTTPException to handle.
    :return: A `JSONResponse` if this request comes from the API, an HTML `TemplateResponse` otherwise.
    """
    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    # Return JSON if this comes from the API
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=exception.status_code, content={"detail": message}
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
def validation_exception_handler(request: Request, exception: RequestValidationError):
    """
    Handles validation errors by returning a `422 UNPROCESSABLE CONTENT` error.

    :param request: The `Request`.
    :param exception: The FastAPI `RequestValidationError to handle.
    :return: A `JSONResponse` if this request comes from the API, an HTML `TemplateResponse` otherwise.
    """
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )

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
