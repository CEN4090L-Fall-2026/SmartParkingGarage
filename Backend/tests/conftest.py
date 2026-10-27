import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from smart_parking_backend import main
from tests import fake_unity


class FakeClock:
    """One controllable clock feeding both monotonic and wall-clock inputs."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def utcnow(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self.t - 1000.0)

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture()
def database_url() -> Iterator[str]:
    """Migrate an isolated PostgreSQL schema; never reset the configured database."""
    base_url = sa.make_url(os.environ["SPG_TEST_DATABASE_URL"])
    root = sa.create_engine(base_url)
    name = f"spg_test_{uuid4().hex}"
    with root.begin() as connection:
        connection.execute(sa.schema.CreateSchema(name))
    scoped_url = base_url.update_query_dict({"options": f"-csearch_path={name}"})
    engine = sa.create_engine(scoped_url)
    try:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        engine.dispose()
        yield scoped_url.render_as_string(hide_password=False)
    finally:
        engine.dispose()
        with root.begin() as connection:
            connection.execute(sa.schema.DropSchema(name, cascade=True))
        root.dispose()


@pytest.fixture()
def client_factory(database_url: str, clock: FakeClock) -> Callable[[], AbstractContextManager[TestClient]]:
    @contextmanager
    def open_client() -> Iterator[TestClient]:
        app = main.create_app(
            database_url=database_url,
            timeout_seconds=5.0,
            redelivery_seconds=5.0,
            clock=clock,
            utcnow=clock.utcnow,
        )
        with TestClient(app) as test_client:
            yield test_client

    return open_client


@pytest.fixture()
def client(client_factory: Callable[[], AbstractContextManager[TestClient]]) -> Iterator[TestClient]:
    with client_factory() as test_client:
        yield test_client


@pytest.fixture()
def unity(client: TestClient) -> fake_unity.FakeUnity:
    """Fake Unity connected by an accepted initial snapshot."""
    fake = fake_unity.FakeUnity(client)
    assert fake.snapshot().status_code == 200
    return fake
