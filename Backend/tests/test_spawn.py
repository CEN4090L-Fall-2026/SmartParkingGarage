from .conftest import EV_IDS


def spawn(client, body):
    return client.post("/api/vehicles/spawn", json=body)


def test_standard_and_ev_spawn_outcomes_are_truthful(client, unity):
    standard = spawn(client, {"request_type": "Standard"})
    assert standard.status_code == 202
    assert standard.json()["request"]["spawned_in_unity"] is False
    assert client.get("/api/vehicles").json() == []
    unity.step()
    vehicles = client.get("/api/vehicles").json()
    assert len(vehicles) == 1 and vehicles[0]["request_type"] == "Standard"

    ev = spawn(client, {"request_type": "EV", "preferred_level": "L2"})
    assert ev.status_code == 202
    unity.step()
    vehicles = client.get("/api/vehicles").json()
    assert [vehicle["request_type"] for vehicle in vehicles] == ["Standard", "EV"]
    assert (
        vehicles[1]["assigned_space_id"] in EV_IDS
        and vehicles[1]["preferred_level"] == "L2"
    )
    assert vehicles[0]["assigned_space_id"] not in EV_IDS
    garage = client.get("/api/garage").json()
    assert garage["reserved"] == 2 and garage["available"] == 404


def test_spawn_failure_is_recorded_without_creating_vehicle(client, unity):
    client.post("/api/simulation/start")
    spawn(client, {"request_type": "Standard"})
    unity.step()
    client.post("/api/simulation/drain")
    unity.step()
    assert client.get("/api/simulation").json()["state"] == "Draining"
    spawn(client, {"request_type": "Standard"})
    unity.step()
    failed = client.get("/api/vehicles/spawn-requests/REQ_0002").json()
    assert failed["status"] == "Failed"
    assert failed["spawned_in_unity"] is False and failed["vehicle_id"] is None
    assert len(client.get("/api/vehicles").json()) == 1


def test_exhausted_ev_capacity_reports_failed_execution(client, unity):
    ev_spaces = [space for space in unity.spaces if space["space_id"] in EV_IDS]
    assert len(ev_spaces) == 8
    for index, space in enumerate(ev_spaces, start=1):
        space.update(
            state="Reserved",
            assigned_vehicle_id=None,
            reserved_by=f"D4_EV_HOLDER_{index:02d}",
        )
    assert unity.snapshot().status_code == 200

    accepted = spawn(client, {"request_type": "EV", "preferred_level": "L2"})
    request_id = accepted.json()["request"]["request_id"]
    command_id = accepted.json()["command"]["command_id"]
    assert unity.step() == [command_id]

    request = client.get(f"/api/vehicles/spawn-requests/{request_id}").json()
    command = client.get(f"/api/integration/commands/{command_id}").json()
    assert request["status"] == "Failed"
    assert (
        request["forwarded_to_unity"] is True and request["spawned_in_unity"] is False
    )
    assert request["vehicle_id"] is None
    assert command["status"] == "Failed" and command["vehicle_id"] is None
    assert client.get("/api/vehicles").json() == []
    assert client.get("/api/garage").json()["reserved"] == 8


def test_spawn_redelivery_executes_once(client, unity, clock):
    accepted = spawn(client, {"request_type": "Standard", "preferred_level": "L1"})
    command_id = accepted.json()["command"]["command_id"]
    request_id = accepted.json()["request"]["request_id"]
    delivered = unity.poll()[0]

    result = unity.execute(delivered)
    assert result[0] is True
    unity.processed[command_id] = result
    unity.executions.append(command_id)
    clock.advance(6)
    assert [item["command_id"] for item in unity.poll()] == [command_id]
    assert unity.ack(command_id, *unity.processed[command_id]).status_code == 200
    assert len(unity.vehicles) == 1 and unity.executions == [command_id]

    request = client.get(f"/api/vehicles/spawn-requests/{request_id}").json()
    assert request["status"] == "SpawnedInUnity" and request["spawned_in_unity"] is True
    assert request["vehicle_id"] == "VEH_0001"


def test_invalid_spawn_requests_are_not_recorded_or_queued(client, unity):
    invalid = (
        {"request_type": "Truck"},
        {"request_type": "ADA"},
        {},
        {"request_type": "Standard", "preferred_level": "L7"},
        {"request_type": "Standard", "unknown": True},
    )
    for body in invalid:
        assert spawn(client, body).status_code == 422
    assert client.get("/api/vehicles/spawn-requests").json() == []
    assert client.get("/api/integration/status").json()["pending_commands"] == 0


def test_offline_spawn_is_not_recorded(client):
    response = spawn(client, {"request_type": "EV"})
    assert response.status_code == 503 and response.json()["success"] is False
    assert client.get("/api/vehicles/spawn-requests").json() == []
