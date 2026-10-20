from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from smart_parking_backend import main
from smart_parking_backend.services import garage_state
from smart_parking_backend.services import integration as integration_service
from tests import fake_unity


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
    garage = garage_state.GarageStateService()
    integration = integration_service.IntegrationService(
        garage,
        timeout_seconds=5.0,
        redelivery_seconds=5.0,
        clock=clock,
        utcnow=clock.utcnow,
    )
    with TestClient(main.create_app(garage, integration)) as test_client:
        yield test_client


@pytest.fixture()
def unity(client):
    """Fake Unity connected by an accepted initial snapshot."""
    fake = fake_unity.FakeUnity(client)
    assert fake.snapshot().status_code == 200
    return fake
