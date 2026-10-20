from tests import inventory


def test_space_inventory_and_filters(client):
    all_spaces = client.get("/api/spaces").json()
    assert len(all_spaces) == 414
    assert len({space["space_id"] for space in all_spaces}) == 414
    assert len(client.get("/api/spaces", params={"level": "L1"}).json()) == 91
    assert len(client.get("/api/spaces", params={"level": "L2"}).json()) == 101

    out_of_service = client.get("/api/spaces", params={"state": "OutOfService"}).json()
    assert len(out_of_service) == 8
    assert {space["space_id"] for space in out_of_service} == inventory.OOS_IDS

    ev_spaces = client.get("/api/spaces", params={"space_type": "EV"}).json()
    assert {space["space_id"] for space in ev_spaces} == inventory.EV_IDS
    assert all(space["level"] == "L2" for space in ev_spaces)
    assert len(client.get("/api/spaces", params={"space_type": "Standard"}).json()) == 406

    combined = client.get("/api/spaces", params={"level": "L4", "state": "OutOfService"}).json()
    assert {space["space_id"] for space in combined} == {
        "L4_SPACE_017",
        "L4_SPACE_018",
        "L4_SPACE_044",
        "L4_SPACE_045",
    }


def test_invalid_space_filters_are_rejected(client):
    assert client.get("/api/spaces", params={"level": "L9"}).status_code == 422
    assert client.get("/api/spaces", params={"state": "Broken"}).status_code == 422
    assert client.get("/api/spaces", params={"space_type": "Accessible"}).status_code == 422


def test_single_space_lookup(client):
    response = client.get("/api/spaces/L1_SPACE_001")
    assert response.status_code == 200
    assert response.json() == {
        "space_id": "L1_SPACE_001",
        "level": "L1",
        "state": "Available",
        "space_type": "Standard",
        "assigned_vehicle_id": None,
        "reserved_by": None,
    }
    assert client.get("/api/spaces/L1_SPACE_029").json()["state"] == "OutOfService"
    assert client.get("/api/spaces/L2_SPACE_030").json()["space_type"] == "EV"
    missing = client.get("/api/spaces/L9_SPACE_999")
    assert missing.status_code == 404
    assert missing.json()["success"] is False
