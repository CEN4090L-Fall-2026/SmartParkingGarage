from fastapi.testclient import TestClient


def test_parking_space_state_persists_between_requests(client: TestClient) -> None:
    spaces_response = client.get("/parking-spaces")
    assert spaces_response.status_code == 200
    spaces = spaces_response.json()["Spaces"]
    assert len(spaces) == 414
    assert spaces[0]["SpaceId"] == "L1_SPACE_001"
    assert spaces[0]["State"] in {"Available", "Occupied"}

    update_response = client.patch(
        "/parking-spaces/L1_SPACE_001/state",
        json={"State": "Occupied"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["State"] == "Occupied"

    reread_spaces = client.get("/parking-spaces").json()["Spaces"]
    first_space = next(
        space for space in reread_spaces if space["SpaceId"] == "L1_SPACE_001"
    )
    assert first_space["State"] == "Occupied"

    reset_response = client.patch(
        "/parking-spaces/L1_SPACE_001/state",
        json={"State": "Available"},
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["State"] == "Available"
