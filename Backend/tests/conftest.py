from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from smart_parking_backend.main import create_app
from smart_parking_backend.services.garage_state import GarageStateService
from smart_parking_backend.services.integration import IntegrationService

from .fake_unity import FakeUnity

OOS_IDS = {
    "L1_SPACE_029",
    "L1_SPACE_087",
    "L1_SPACE_088",
    "L1_SPACE_089",
    "L4_SPACE_017",
    "L4_SPACE_018",
    "L4_SPACE_044",
    "L4_SPACE_045",
}
EV_IDS = {f"L2_SPACE_{n:03d}" for n in range(29, 37)}


class FakeClock:
    """One controllable clock feeding both monotonic and wall-clock inputs."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def utcnow(self):
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self.t - 1000.0)

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture()
def clock():
    return FakeClock()


@pytest.fixture()
def client(clock):
    """Fresh seeded application per test, using a controllable integration clock."""
    garage = GarageStateService()
    integration = IntegrationService(
        garage,
        timeout_seconds=5.0,
        redelivery_seconds=5.0,
        clock=clock,
        utcnow=clock.utcnow,
    )
    with TestClient(create_app(garage, integration)) as test_client:
        yield test_client


@pytest.fixture()
def unity(client):
    """Fake Unity connected by an accepted initial snapshot."""
    fake = FakeUnity(client)
    assert fake.snapshot().status_code == 200
    return fake
