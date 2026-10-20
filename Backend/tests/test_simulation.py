def post(client, path, body=None):
    url = f"/api/simulation/{path}"
    return client.post(url, json=body) if body is not None else client.post(url)


def test_simulation_state_machine_via_unity(client, unity):
    def transition(path, body=None):
        assert post(client, path, body).status_code == 202
        unity.step()
        return client.get("/api/simulation").json()["state"]

    assert transition("start") == "Running"
    assert transition("pause-arrivals") == "ArrivalPaused"
    assert transition("resume-arrivals") == "Running"
    assert transition("drain") == "Idle"
    assert transition("start") == "Running"
    assert transition("reset") == "Idle"


def test_invalid_transitions_fail_at_unity(client, unity):
    for path in ("pause-arrivals", "resume-arrivals", "drain"):
        command_id = post(client, path).json()["command"]["command_id"]
        unity.step()
        assert client.get(f"/api/integration/commands/{command_id}").json()["status"] == "Failed"
    post(client, "start")
    unity.step()
    command_id = post(client, "start").json()["command"]["command_id"]
    unity.step()
    assert client.get(f"/api/integration/commands/{command_id}").json()["status"] == "Failed"
    assert client.get("/api/simulation").json()["state"] == "Running"


def test_scenario_mode_changes_only_after_unity_executes(client, unity):
    response = post(client, "mode", {"scenario_mode": "RushHour"})
    assert response.status_code == 202
    assert client.get("/api/simulation").json()["scenario_mode"] == "Normal"
    unity.step()
    assert client.get("/api/simulation").json()["scenario_mode"] == "RushHour"
    post(client, "mode", {"scenario_mode": "Normal"})
    unity.step()
    assert client.get("/api/simulation").json()["scenario_mode"] == "Normal"


def test_invalid_scenario_mode_is_rejected(client, unity):
    assert post(client, "mode", {"scenario_mode": "Gridlock"}).status_code == 422
    assert post(client, "mode", {}).status_code == 422
    assert post(client, "mode", {"scenario_mode": "Normal", "extra": 1}).status_code == 422


def test_reset_restores_baseline_inventory(client, unity):
    post(client, "start")
    client.post("/api/vehicles/spawn", json={"request_type": "Standard"})
    client.post("/api/vehicles/spawn", json={"request_type": "EV"})
    unity.step()
    assert client.get("/api/garage").json()["reserved"] == 2
    post(client, "reset")
    unity.step()
    garage = client.get("/api/garage").json()
    assert (
        garage["available"],
        garage["occupied"],
        garage["reserved"],
        garage["out_of_service"],
    ) == (406, 0, 0, 8)
    simulation = client.get("/api/simulation").json()
    assert simulation["state"] == "Idle" and simulation["active_vehicles"] == 0
    assert client.get("/api/vehicles").json() == []
