from tests import fake_unity


def post(client, path, body=None):
    url = f"/api/simulation/{path}"
    return client.post(url, json=body) if body is not None else client.post(url)


def command(client, command_id):
    return client.get(f"/api/integration/commands/{command_id}").json()


def test_queue_fetch_ack_and_snapshot(client, unity):
    response = post(client, "start")
    assert response.status_code == 202
    body = response.json()
    assert body["current_state"] == "Idle"
    queued = body["command"]
    assert queued["command_type"] == "StartSimulation" and queued["status"] == "Pending"
    assert queued["unity_session_id"] == "SESSION_A" and queued["delivery_count"] == 0
    assert client.get("/api/simulation").json()["state"] == "Idle"
    assert client.get("/api/integration/status").json()["pending_commands"] == 1

    fetched = unity.poll()
    assert [item["command_id"] for item in fetched] == [queued["command_id"]]
    assert fetched[0]["status"] == "Delivered" and fetched[0]["delivery_count"] == 1
    assert unity.poll() == []
    success, message, vehicle_id = unity.execute(fetched[0])
    assert success
    ack = unity.ack(queued["command_id"], success, message, vehicle_id)
    assert ack.status_code == 200 and ack.json()["duplicate"] is False
    assert command(client, queued["command_id"])["status"] == "Acknowledged"
    assert client.get("/api/integration/status").json()["pending_commands"] == 0
    assert client.get("/api/simulation").json()["state"] == "Idle"
    unity.snapshot()
    assert client.get("/api/simulation").json()["state"] == "Running"


def test_unity_execution_failure_is_recorded(client, unity):
    command_id = post(client, "pause-arrivals").json()["command"]["command_id"]
    assert unity.step() == [command_id]
    assert command(client, command_id)["status"] == "Failed"
    assert client.get("/api/simulation").json()["state"] == "Idle"


def test_commands_are_delivered_in_fifo_order(client, unity):
    ids = [
        post(client, "start").json()["command"]["command_id"],
        post(client, "mode", {"scenario_mode": "RushHour"}).json()["command"]["command_id"],
        post(client, "pause-arrivals").json()["command"]["command_id"],
        post(client, "resume-arrivals").json()["command"]["command_id"],
    ]
    first = unity.poll(limit=2)
    assert [item["command_id"] for item in first] == ids[:2]
    second = unity.poll(limit=10)
    assert [item["command_id"] for item in second] == ids[2:]
    for item in first + second:
        success, message, vehicle_id = unity.execute(item)
        unity.ack(item["command_id"], success, message, vehicle_id)
    unity.snapshot()
    simulation = client.get("/api/simulation").json()
    assert simulation["state"] == "Running" and simulation["scenario_mode"] == "RushHour"


def test_acknowledgement_is_idempotent_and_first_result_wins(client, unity):
    post(client, "start")
    command_id = unity.poll()[0]["command_id"]
    first = unity.ack(command_id, True, "original result")
    recorded_result = command(client, command_id)["result_message"]
    duplicate = unity.ack(command_id, True, "different duplicate result")
    conflicting = unity.ack(command_id, False, "conflicting late failure")
    assert first.json()["duplicate"] is False
    assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True
    assert conflicting.status_code == 200 and conflicting.json()["duplicate"] is True
    result = command(client, command_id)
    assert result["status"] == "Acknowledged" and result["result_message"] == recorded_result


def test_offline_commands_and_spawn_do_not_mutate_state(client):
    assert client.get("/api/integration/status").json()["connected"] is False
    for path, body in (
        ("start", None),
        ("pause-arrivals", None),
        ("resume-arrivals", None),
        ("drain", None),
        ("reset", None),
        ("mode", {"scenario_mode": "RushHour"}),
    ):
        assert post(client, path, body).status_code == 503
    assert client.post("/api/vehicles/spawn", json={"request_type": "Standard"}).status_code == 503
    assert client.get("/api/vehicles/spawn-requests").json() == []
    assert client.get("/api/integration/status").json()["pending_commands"] == 0
    simulation = client.get("/api/simulation").json()
    assert simulation["state"] == "Idle" and simulation["scenario_mode"] == "Normal"
    assert client.get("/api/garage").json()["total_physical_spaces"] == 414


def test_commands_are_rejected_while_disconnected_and_resume_after_snapshot(client, unity, clock):
    clock.advance(6)
    assert post(client, "start").status_code == 503
    unity.snapshot()
    assert post(client, "start").status_code == 202


def test_invalid_commands_are_not_queued(client, unity):
    assert post(client, "mode", {"scenario_mode": "Gridlock"}).status_code == 422
    assert client.post("/api/vehicles/spawn", json={"request_type": "Truck"}).status_code == 422
    assert client.get("/api/integration/status").json()["pending_commands"] == 0


def test_redelivery_and_unity_deduplication(client, unity, clock):
    command_id = post(client, "start").json()["command"]["command_id"]
    first = unity.poll()
    assert [item["delivery_count"] for item in first] == [1]
    clock.advance(4.9)
    assert unity.poll() == []
    clock.advance(0.2)
    assert unity.poll()[0]["delivery_count"] == 2
    unity.processed.clear()
    clock.advance(6)
    assert unity.step() == [command_id]
    clock.advance(6)
    assert unity.step() == []
    assert unity.executions == [command_id]
    assert client.get("/api/simulation").json()["state"] == "Running"


def test_redelivered_command_retains_fifo_position(client, unity, clock):
    first = post(client, "start").json()["command"]["command_id"]
    unity.poll()
    second = post(client, "mode", {"scenario_mode": "RushHour"}).json()["command"]["command_id"]
    clock.advance(6)
    assert [item["command_id"] for item in unity.poll()] == [first, second]


def test_reset_cancels_undelivered_commands(client, unity):
    first = post(client, "start").json()["command"]["command_id"]
    second = post(client, "mode", {"scenario_mode": "RushHour"}).json()["command"]["command_id"]
    reset = post(client, "reset").json()["command"]["command_id"]
    later = post(client, "start").json()["command"]["command_id"]
    assert command(client, first)["status"] == "Cancelled"
    assert command(client, second)["status"] == "Cancelled"
    assert [item["command_id"] for item in unity.poll()] == [reset, later]


def test_reset_preserves_delivered_command_until_reset_ack(client, unity):
    earlier = post(client, "start").json()["command"]["command_id"]
    unity.poll()
    reset = post(client, "reset").json()["command"]["command_id"]
    assert command(client, earlier)["status"] == "Delivered"
    unity.poll()
    unity.ack(reset, True, "Reset.")
    assert command(client, earlier)["status"] == "Cancelled"
    assert command(client, reset)["status"] == "Acknowledged"


def test_new_session_leaves_delivered_execution_unknown(client, unity):
    command_id = post(client, "start").json()["command"]["command_id"]
    unity.poll()
    new_unity = fake_unity.FakeUnity(client, session="SESSION_B")
    assert new_unity.snapshot().json()["new_session"] is True
    assert command(client, command_id)["status"] == "OutcomeUnknown"
    assert client.get("/api/integration/status").json()["pending_commands"] == 0
    assert client.get("/api/integration/commands", params={"unity_session_id": "SESSION_A"}).status_code == 409
    assert unity.ack(command_id, True).status_code == 409
    assert post(client, "start").json()["command"]["unity_session_id"] == "SESSION_B"


def test_cors_allows_configured_origin_and_rejects_other_origin(client):
    allowed = "http://localhost:3000"
    preflight = client.options(
        "/api/garage",
        headers={"Origin": allowed, "Access-Control-Request-Method": "GET"},
    )
    assert preflight.headers["access-control-allow-origin"] == allowed
    response = client.get("/api/garage", headers={"Origin": allowed})
    assert response.headers["access-control-allow-origin"] == allowed

    rejected = "http://evil.example"
    preflight = client.options(
        "/api/garage",
        headers={"Origin": rejected, "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in preflight.headers
    response = client.get("/api/garage", headers={"Origin": rejected})
    assert "access-control-allow-origin" not in response.headers


def test_obsolete_state_authority_routes_are_absent(client):
    assert client.get("/parking-assignments").status_code == 404
    assert client.patch("/parking-spaces/L1_SPACE_001/state", json={"State": "Occupied"}).status_code == 404
