import os
from collections.abc import AsyncGenerator
from typing import Any

# Need to set env vars here so Pydantic loads these instead of prod credentials.
# Must be before db and main imports so Pydantic loads these
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://bloguser:blogpass@localhost/test_blog"
)
os.environ["S3_BUCKET_NAME"] = "test-bucket"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["S3_ACCESS_KEY_ID"] = "testing"
os.environ["S3_SECRET_ACCESS_KEY_ID"] = "testing"
os.environ["S3_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

import boto3
import pytest
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from database import Base, get_db
from main import app

pytest_plugins = ["anyio"]


@pytest.fixture(scope="session")
def anyio_backend():
    """
    Get the backend we're using
    """
    return "asyncio"


@pytest.fixture(scope="session")
def test_engine():
    """
    Create a test async DB engine
    """
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
    )
    return engine


@pytest.fixture(scope="session")
async def setup_database(test_engine: AsyncEngine):
    """
    Create all tables. Run the tests. Delete all tables and kill the engine.

    :param test_engine: The DB engine to use.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture(scope="function")
async def db_session(
    test_engine: AsyncEngine, setup_database
) -> AsyncGenerator[AsyncSession]:
    """
    Create a DB session. On each test function, set up a new transaction,
    do the testing necessary, then rollback that transaction so the DB
    is always fresh for each test function.

    :param test_engine: The DB engine to use.
    :param setup_database: The DB
    """
    conn = await test_engine.connect()
    trans = await conn.begin()

    test_async_session = async_sessionmaker(
        bind=conn,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",  # Fake committing
    )

    async with test_async_session() as session:
        try:
            yield session  # Yield the session to the test
        finally:
            # "Undo" the test
            await session.close()
            await trans.rollback()
            await conn.close()


@pytest.fixture(scope="function")
def mocked_aws():
    """
    Yield a mocked version of S3. Uses Moto to "intercept" Boto3.

    :yield: The fake version of S3.
    """
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=os.environ["S3_BUCKET_NAME"])
        yield s3


@pytest.fixture(scope="function")
async def client(
    db_session: AsyncSession, mocked_aws: Any
) -> AsyncGenerator[AsyncClient]:
    """
    Create a function-scoped DB client.

    :param db_session: The DB session.
    :param mocked_aws: The mocked version of AWS.
    :yield: An `AsyncClient`.
    """

    async def _override_get_db():
        """Override the `get_db` function for dependency injection."""
        yield db_session

    # Swap out normal get_db with fake version
    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


async def create_test_user(
    client: AsyncClient,
    username: str = "testuser",
    email: str = "test@example.com",
    password: str = "testpassword123",
) -> dict[str, Any]:
    """
    Helper to create a test user.

    :param client: The DB client.
    :param username: The user name to use.
    :param email: The email to use.
    :param password: The password to use.
    :return: The response JSON
    """
    response = await client.post(
        "/api/v1/users",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 201, f"Failed to create user: {response.text}"
    return response.json()


async def login_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "testpassword123",
) -> str:
    """
    Helper to log in a test user.

    :param client: The DB client.
    :param email: The email to use.
    :param password: The password to use.
    :return: The access token of the logged-in user
    """
    response = await client.post(
        "/api/v1/users/token",
        data={  # Login uses form data, not JSON
            "username": email,
            "password": password,
        },
    )
    assert response.status_code == 200, f"Failed to log in: {response.text}"
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    """
    Return an auth header based on a token.

    :param token: The token to use.
    :return: JSON of the full auth header.
    """
    return {"Authorization": f"Bearer {token}"}
