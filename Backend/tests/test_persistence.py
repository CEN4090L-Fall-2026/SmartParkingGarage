from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient

from tests.conftest import FakeClock
from tests.fake_unity import FakeUnity

ClientFactory = Callable[[], AbstractContextManager[TestClient]]


def spawn(client: TestClient, request_type: str = "Standard") -> dict[str, Any]:
    response = client.post("/api/vehicles/spawn", json={"request_type": request_type, "auto_depart": False})
    assert response.status_code == 202
    return response.json()


def command(client: TestClient, command_id: str) -> dict[str, Any]:
    response = client.get(f"/api/integration/commands/{command_id}")
    assert response.status_code == 200
    return response.json()


def request(client: TestClient, request_id: str) -> dict[str, Any]:
    response = client.get(f"/api/vehicles/spawn-requests/{request_id}")
    assert response.status_code == 200
    return response.json()


def rotate_session(unity: FakeUnity) -> None:
    """Match Unity's integration-session rotation, without resetting its simulation."""
    unity.session = "SESSION_B"
    unity.sequence = 0
    unity.processed.clear()


def test_confirmed_result_and_latest_projection_survive_restart(
    client_factory: ClientFactory, clock: FakeClock
) -> None:
    with client_factory() as first:
        unity = FakeUnity(first)
        assert unity.snapshot().status_code == 200
        accepted = spawn(first)
        unity.step()
        clock.advance(2)
        assert unity.snapshot().status_code == 200
        command_id, request_id = accepted["command"]["command_id"], accepted["request"]["request_id"]
        known_command = command(first, command_id)
        known_request = request(first, request_id)
        old_status = first.get("/api/integration/status").json()
        spaces = first.get("/api/spaces").json()
        vehicles = first.get("/api/vehicles").json()
        garage = first.get("/api/garage").json()
        simulation = first.get("/api/simulation").json()

    clock.advance(37.5)
    with client_factory() as second:
        status = second.get("/api/integration/status").json()
        assert status["backend_instance_id"] != old_status["backend_instance_id"]
        assert status["connected"] is False and status["data_source"] == "UnityLastKnown"
        assert status["last_update_at"] == old_status["last_update_at"]
        assert status["seconds_since_last_update"] == 37.5
        assert status["latest_sequence"] == old_status["latest_sequence"]
        assert command(second, command_id) == known_command
        assert request(second, request_id) == known_request
        assert known_request["status"] == "SpawnedInUnity"
        assert known_request["auto_depart"] is False
        assert known_request["vehicle_id"] == vehicles[0]["vehicle_id"]
        assert second.get("/api/spaces").json() == spaces
        assert second.get("/api/vehicles").json() == vehicles
        garage["data_source"] = simulation["data_source"] = "UnityLastKnown"
        assert second.get("/api/garage").json() == garage
        assert second.get("/api/simulation").json() == simulation
        assert second.get("/api/garage").headers["X-Data-Source"] == "UnityLastKnown"
        assert second.post("/api/vehicles/spawn", json={"request_type": "Standard"}).status_code == 503
        assert second.get("/api/vehicles/spawn-requests").json() == [known_request]


def test_restart_distinguishes_uncertain_delivery_and_never_delivered_work(
    client_factory: ClientFactory, clock: FakeClock
) -> None:
    with client_factory() as first:
        unity = FakeUnity(first)
        unity.snapshot()
        known = spawn(first)
        unity.step()
        delivered = spawn(first)
        assert [item["command_id"] for item in unity.poll()] == [delivered["command"]["command_id"]]
        pending = spawn(first, "EV")
        known_result = command(first, known["command"]["command_id"])

    clock.advance(10)
    with client_factory() as second:
        unknown = command(second, delivered["command"]["command_id"])
        unknown_request = request(second, delivered["request"]["request_id"])
        assert unknown["status"] == unknown_request["status"] == "OutcomeUnknown"
        assert unknown["acknowledged_at"] is None
        assert unknown_request["forwarded_to_unity"] is True
        assert unknown_request["spawned_in_unity"] is False
        assert (
            unknown_request["vehicle_id"] is unknown_request["failure_reason"] is unknown_request["error_code"] is None
        )
        assert command(second, pending["command"]["command_id"])["status"] == "Cancelled"
        cancelled_request = request(second, pending["request"]["request_id"])
        assert cancelled_request["status"] == "Failed" and cancelled_request["forwarded_to_unity"] is False
        assert command(second, known["command"]["command_id"]) == known_result
        assert second.get("/api/integration/status").json()["pending_commands"] == 0
        assert second.get("/api/simulation").json()["pending_spawn_requests"] == 0
        unity.client = second
        duplicate = unity.ack(delivered["command"]["command_id"], True, vehicle_id="VEH_LATE").json()
        assert duplicate["duplicate"] is True and duplicate["command"] == unknown

    clock.advance(10)
    with client_factory() as third:
        assert command(third, delivered["command"]["command_id"]) == unknown
        assert request(third, delivered["request"]["request_id"]) == unknown_request
        assert command(third, known["command"]["command_id"]) == known_result
        unity.client = third
        assert unity.snapshot().status_code == 200
        rotate_session(unity)
        assert unity.snapshot().status_code == 200
        assert unity.poll() == []
        fresh = spawn(third)
        assert fresh["command"]["unity_session_id"] == unity.session
        assert fresh["command"]["command_id"] not in {
            known["command"]["command_id"],
            delivered["command"]["command_id"],
            pending["command"]["command_id"],
        }
        assert fresh["request"]["request_id"] not in {
            known["request"]["request_id"],
            delivered["request"]["request_id"],
            pending["request"]["request_id"],
        }


def test_session_end_classification_is_durable_and_acks_cannot_cross_sessions(client_factory: ClientFactory) -> None:
    with client_factory() as first:
        unity = FakeUnity(first)
        unity.snapshot()
        delivered = spawn(first)
        unity.poll()
        pending = spawn(first)
        old_session = unity.session
        rotate_session(unity)
        assert unity.snapshot().json()["new_session"] is True
        unknown = command(first, delivered["command"]["command_id"])
        cancelled = command(first, pending["command"]["command_id"])
        assert unknown["status"] == "OutcomeUnknown" and cancelled["status"] == "Cancelled"
        assert unity.poll() == []
        assert first.get("/api/integration/commands", params={"unity_session_id": old_session}).status_code == 409
        for session in (old_session, unity.session):
            assert (
                first.post(
                    f"/api/integration/commands/{delivered['command']['command_id']}/ack",
                    json={"unity_session_id": session, "success": True},
                ).status_code
                == 409
            )

    with client_factory() as second:
        assert command(second, delivered["command"]["command_id"]) == unknown
        assert command(second, pending["command"]["command_id"]) == cancelled
        assert request(second, delivered["request"]["request_id"])["status"] == "OutcomeUnknown"


def test_restored_sequence_protection_and_unity_handshake_replace_snapshot(client_factory: ClientFactory) -> None:
    with client_factory() as first:
        unity = FakeUnity(first)
        unity.snapshot()
        previous = spawn(first)
        old_status = first.get("/api/integration/status").json()
        spaces = first.get("/api/spaces").json()

    with client_factory() as second:
        unity.client = second
        stale = unity.snapshot(sequence=old_status["latest_sequence"])
        assert stale.status_code == 409
        assert second.get("/api/spaces").json() == spaces
        assert second.get("/api/integration/status").json()["connected"] is False
        resumed = unity.snapshot()
        assert resumed.status_code == 200
        assert resumed.json()["backend_instance_id"] != old_status["backend_instance_id"]
        assert second.get("/api/integration/status").json()["data_source"] == "UnityLive"
        rotate_session(unity)
        unity.spaces = unity.spaces[:1]
        assert unity.snapshot().json()["latest_sequence"] == 1
        assert second.get("/api/spaces").json() == unity.spaces
        assert unity.poll() == []
        fresh = spawn(second)
        assert fresh["command"]["unity_session_id"] == unity.session
        assert fresh["command"]["command_id"] != previous["command"]["command_id"]
        assert fresh["request"]["request_id"] != previous["request"]["request_id"]


def test_reset_uses_numeric_creation_order_across_id_padding_boundary(
    client: TestClient, unity: FakeUnity, clock: FakeClock, database_url: str
) -> None:
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("SELECT setval('command_order_seq', 999998)"))
    finally:
        engine.dispose()
    earlier = client.post("/api/simulation/start").json()["command"]["command_id"]
    assert [item["command_id"] for item in unity.poll()] == [earlier]
    reset = client.post("/api/simulation/reset").json()["command"]["command_id"]
    later = client.post("/api/simulation/start").json()["command"]["command_id"]
    assert [item["command_id"] for item in unity.poll()] == [reset, later]
    assert unity.ack(reset, True, "Reset.").status_code == 200
    assert command(client, earlier)["status"] == "Cancelled"
    assert command(client, reset)["status"] == "Acknowledged"
    assert command(client, later)["status"] == "Delivered"
    clock.advance(5.1)
    assert [item["command_id"] for item in unity.poll()] == [later]
