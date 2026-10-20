from .fake_unity import FakeUnity


def _publish_vehicle_pair(unity, first_state="Parked"):
    available = [
        space
        for space in unity.spaces
        if space["state"] == "Available" and space["space_type"] == "Standard"
    ]
    first_space, second_space = available[:2]
    first_vehicle = {
        "vehicle_id": "DRIVER_A",
        "requester_id": "REQUESTER_A",
        "request_type": "Standard",
        "lifecycle_state": first_state,
        "assigned_space_id": first_space["space_id"],
        "preferred_level": None,
        "failure_reason": None,
    }
    second_vehicle = {
        "vehicle_id": "DRIVER_B",
        "requester_id": "REQUESTER_B",
        "request_type": "Standard",
        "lifecycle_state": "Parked",
        "assigned_space_id": second_space["space_id"],
        "preferred_level": None,
        "failure_reason": None,
    }
    for space, vehicle in (
        (first_space, first_vehicle),
        (second_space, second_vehicle),
    ):
        space.update(
            state="Occupied",
            assigned_vehicle_id=vehicle["vehicle_id"],
            reserved_by=vehicle["requester_id"],
        )
    unity.vehicles = [first_vehicle, second_vehicle]
    assert unity.snapshot().status_code == 200
    return first_vehicle, second_vehicle, first_space, second_space


def test_departure_queues_target_and_projection_changes_only_from_snapshots(
    client, unity
):
    first, _, first_space, second_space = _publish_vehicle_pair(unity)
    original_vehicles = client.get("/api/vehicles").json()
    original_spaces = client.get("/api/spaces", params={"state": "Occupied"}).json()
    original_occupied = client.get("/api/garage").json()["occupied"]

    accepted = client.post("/api/vehicles/DRIVER_A/depart")
    assert accepted.status_code == 202
    body = accepted.json()
    command = body["command"]
    assert body["request"] is None
    assert body["current_state"] == "Idle"
    assert command["command_type"] == "DepartVehicle"
    assert command["payload"]["vehicle_id"] == "DRIVER_A"
    assert command["status"] == "Pending"
    assert client.get("/api/vehicles").json() == original_vehicles
    assert (
        client.get("/api/spaces", params={"state": "Occupied"}).json()
        == original_spaces
    )

    delivered = unity.poll()
    assert [item["command_id"] for item in delivered] == [command["command_id"]]
    assert (
        unity.ack(command["command_id"], True, "Departure started.").status_code == 200
    )
    assert client.get("/api/vehicles").json() == original_vehicles
    assert (
        client.get("/api/spaces", params={"state": "Occupied"}).json()
        == original_spaces
    )

    first["lifecycle_state"] = "Departing"
    assert unity.snapshot().status_code == 200
    vehicles = {
        vehicle["vehicle_id"]: vehicle for vehicle in client.get("/api/vehicles").json()
    }
    assert vehicles["DRIVER_A"]["lifecycle_state"] == "Departing"
    assert vehicles["DRIVER_B"]["lifecycle_state"] == "Parked"
    assert (
        client.get(f"/api/spaces/{first_space['space_id']}").json()["state"]
        == "Occupied"
    )
    assert (
        client.get(f"/api/spaces/{second_space['space_id']}").json()["state"]
        == "Occupied"
    )

    unity.vehicles.remove(first)
    first_space.update(state="Available", assigned_vehicle_id=None, reserved_by=None)
    unity.sim["total_completed"] += 1
    assert unity.snapshot().status_code == 200
    vehicles = {
        vehicle["vehicle_id"]: vehicle for vehicle in client.get("/api/vehicles").json()
    }
    assert list(vehicles) == ["DRIVER_B"]
    assert vehicles["DRIVER_B"]["assigned_space_id"] == second_space["space_id"]
    assert (
        client.get(f"/api/spaces/{first_space['space_id']}").json()["state"]
        == "Available"
    )
    assert (
        client.get(f"/api/spaces/{second_space['space_id']}").json()["state"]
        == "Occupied"
    )
    assert client.get("/api/garage").json()["occupied"] == original_occupied - 1


def test_unity_rejection_is_recorded_without_backend_vehicle_validation(client, unity):
    _publish_vehicle_pair(unity, first_state="DrivingToStall")
    accepted = client.post("/api/vehicles/DRIVER_A/depart")
    assert accepted.status_code == 202
    command_id = accepted.json()["command"]["command_id"]
    assert unity.poll()[0]["payload"]["vehicle_id"] == "DRIVER_A"

    failed = unity.ack(
        command_id,
        False,
        "Vehicle cannot depart in its current state.",
    )
    assert failed.status_code == 200 and failed.json()["duplicate"] is False
    result = client.get(f"/api/integration/commands/{command_id}").json()
    assert result["status"] == "Failed"
    assert result["result_message"] == "Vehicle cannot depart in its current state."
    assert result["error_code"] is None
    assert result["payload"]["vehicle_id"] == "DRIVER_A"
    original_vehicles = client.get("/api/vehicles").json()
    original_spaces = client.get("/api/spaces", params={"state": "Occupied"}).json()

    duplicate = unity.ack(command_id, True, "Conflicting late success.")
    assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True
    assert client.get(f"/api/integration/commands/{command_id}").json() == result
    assert client.get("/api/vehicles").json() == original_vehicles
    assert (
        client.get("/api/spaces", params={"state": "Occupied"}).json()
        == original_spaces
    )


def test_unknown_departure_target_is_queued_for_unity_to_reject(client, unity):
    accepted = client.post("/api/vehicles/NOT_PRESENT/depart")
    assert accepted.status_code == 202
    command_id = accepted.json()["command"]["command_id"]
    command = unity.poll()[0]
    assert command["payload"]["vehicle_id"] == "NOT_PRESENT"
    assert unity.ack(command_id, False, "Vehicle not found.").status_code == 200
    assert client.get("/api/vehicles").json() == []
    assert (
        client.get(f"/api/integration/commands/{command_id}").json()["status"]
        == "Failed"
    )


def test_departure_offline_request_does_not_queue_command(client):
    response = client.post("/api/vehicles/DRIVER_A/depart")
    assert response.status_code == 503
    assert client.get("/api/integration/status").json()["pending_commands"] == 0


def test_departure_redelivers_and_old_session_cannot_acknowledge(client, unity, clock):
    accepted = client.post("/api/vehicles/DRIVER_A/depart")
    assert accepted.status_code == 202
    command_id = accepted.json()["command"]["command_id"]
    first_delivery = unity.poll()[0]
    assert first_delivery["delivery_count"] == 1
    assert first_delivery["payload"]["vehicle_id"] == "DRIVER_A"

    clock.advance(5.1)
    second_delivery = unity.poll()[0]
    assert second_delivery["command_id"] == command_id
    assert second_delivery["delivery_count"] == 2
    assert second_delivery["payload"]["vehicle_id"] == "DRIVER_A"

    new_unity = FakeUnity(client, session="SESSION_B")
    assert new_unity.snapshot().status_code == 200
    result = client.get(f"/api/integration/commands/{command_id}").json()
    assert result["status"] == "Cancelled"
    assert result["payload"]["vehicle_id"] == "DRIVER_A"
    assert unity.ack(command_id, True, "Late old-session ack.").status_code == 409
    assert client.get(f"/api/integration/commands/{command_id}").json() == result
