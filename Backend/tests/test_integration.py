import copy

from .fake_unity import FakeUnity


def status(client):
    return client.get("/api/integration/status").json()


def test_snapshot_connectivity_timeout_and_reconnect(client, unity, clock):
    current = status(client)
    assert current["connected"] is True and current["unity_session_id"] == "SESSION_A"
    assert current["latest_sequence"] == 1
    assert current["seconds_since_last_update"] == 0
    clock.advance(5)
    assert status(client)["connected"] is True
    clock.advance(0.1)
    current = status(client)
    assert current["connected"] is False and current["data_source"] == "UnityLastKnown"
    assert current["unity_session_id"] == "SESSION_A"
    assert client.get("/api/garage").headers["x-data-source"] == "UnityLastKnown"
    unity.snapshot()
    assert status(client)["connected"] is True


def test_snapshot_projects_live_state(client, unity):
    target = next(
        space for space in unity.spaces if space["space_id"] == "L3_SPACE_001"
    )
    target.update(
        state="Occupied", assigned_vehicle_id="VEH_0001", reserved_by="SIM_VEH_0001"
    )
    unity.vehicles.append(
        {
            "vehicle_id": "VEH_0001",
            "requester_id": "SIM_VEH_0001",
            "request_type": "Standard",
            "lifecycle_state": "Parked",
            "assigned_space_id": "L3_SPACE_001",
            "preferred_level": None,
            "failure_reason": None,
        }
    )
    unity.sim.update(state="Running", elapsed_seconds=12.5, total_spawned=1)
    assert unity.snapshot().status_code == 200

    garage = client.get("/api/garage").json()
    assert (garage["available"], garage["occupied"], garage["out_of_service"]) == (
        405,
        1,
        8,
    )
    assert (
        client.get("/api/spaces/L3_SPACE_001").json()["assigned_vehicle_id"]
        == "VEH_0001"
    )
    assert len(client.get("/api/spaces", params={"state": "Occupied"}).json()) == 1
    assert client.get("/api/vehicles/VEH_0001").json()["lifecycle_state"] == "Parked"
    simulation = client.get("/api/simulation").json()
    assert simulation["state"] == "Running" and simulation["elapsed_seconds"] == 12.5
    assert simulation["total_spawned"] == 1 and simulation["active_vehicles"] == 1


def test_snapshot_replaces_full_inventory(client, unity):
    unity.spaces = unity.spaces[:10]
    assert unity.snapshot().status_code == 200
    assert len(client.get("/api/spaces").json()) == 10
    assert client.get("/api/garage").json()["total_physical_spaces"] == 10


def test_new_session_restarts_sequence(client, unity):
    unity.snapshot()
    unity.snapshot()
    assert status(client)["latest_sequence"] == 3
    other = FakeUnity(client, session="SESSION_B")
    response = other.snapshot()
    assert response.status_code == 200
    assert (
        response.json()["new_session"] is True
        and response.json()["latest_sequence"] == 1
    )
    assert status(client)["unity_session_id"] == "SESSION_B"
    assert other.snapshot().json()["latest_sequence"] == 2


def test_malformed_snapshots_do_not_change_state(client, unity):
    good = unity.body()
    cases = []
    for field in ("unity_session_id", "sequence", "timestamp", "simulation", "spaces"):
        broken = copy.deepcopy(good)
        del broken[field]
        cases.append(broken)
    for mutate in (
        lambda body: body.update(sequence=0),
        lambda body: body.update(sequence="abc"),
        lambda body: body.update(unity_session_id=""),
        lambda body: body.update(spaces=[]),
        lambda body: body.update(timestamp="yesterday"),
        lambda body: body["simulation"].update(state="Paused"),
        lambda body: body["simulation"].update(scenario_mode="Gridlock"),
        lambda body: body["simulation"].update(active_vehicles=-1),
        lambda body: body["spaces"][0].update(state="Broken"),
        lambda body: body["spaces"][0].update(level="L9"),
        lambda body: body["spaces"][0].update(space_type="Accessible"),
        lambda body: body["spaces"].append(dict(body["spaces"][0])),
        lambda body: body.update(unknown_field=1),
    ):
        broken = copy.deepcopy(good)
        mutate(broken)
        cases.append(broken)
    for broken in cases:
        assert client.post("/api/integration/state", json=broken).status_code == 422
    assert (
        client.post(
            "/api/integration/state",
            content="not json",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assert status(client)["latest_sequence"] == 1


def test_duplicate_vehicle_ids_are_rejected(client, unity):
    vehicle = {
        "vehicle_id": "VEH_0001",
        "requester_id": "SIM_VEH_0001",
        "request_type": "EV",
        "lifecycle_state": "Spawned",
        "assigned_space_id": None,
        "preferred_level": None,
        "failure_reason": None,
    }
    unity.vehicles = [vehicle, dict(vehicle)]
    assert unity.snapshot().status_code == 422


def test_stale_snapshot_is_rejected_without_regressing_state(client, unity):
    unity.sim.update(state="Running", elapsed_seconds=30.0)
    assert unity.snapshot().status_code == 200
    stale = unity.body(sequence=1)
    stale["simulation"]["state"] = "Idle"
    stale["spaces"][0]["state"] = "Occupied"
    response = client.post("/api/integration/state", json=stale)
    assert response.status_code == 409
    assert (
        response.json()["accepted"] is False and response.json()["latest_sequence"] == 2
    )
    equal = unity.body(sequence=2)
    equal["simulation"]["state"] = "Draining"
    assert client.post("/api/integration/state", json=equal).status_code == 409
    assert client.get("/api/simulation").json()["state"] == "Running"
    assert client.get("/api/garage").json()["occupied"] == 0
    assert status(client)["latest_sequence"] == 2
    assert unity.snapshot().status_code == 200
