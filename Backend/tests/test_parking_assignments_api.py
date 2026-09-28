from uuid import uuid4

from fastapi.testclient import TestClient


def test_assignment_reserves_and_releases_parking_space(
    client: TestClient,
) -> None:
    requester_id = f"assignment-test-{uuid4()}"
    assignment_response = client.post(
        "/parking-assignments",
        json={
            "RequesterId": requester_id,
            "PreferredLevel": 1,
            "RequiredType": "Standard",
        },
    )
    assert assignment_response.status_code == 201
    assignment = assignment_response.json()
    assert assignment["RequesterId"] == requester_id
    assert assignment["Level"] == 1
    assert assignment["Type"] == "Standard"

    assigned_space_id = assignment["SpaceId"]
    reserved_spaces = client.get("/parking-spaces").json()["Spaces"]
    reserved_space = next(
        space for space in reserved_spaces if space["SpaceId"] == assigned_space_id
    )
    assert reserved_space["State"] == "Reserved"

    release_response = client.delete(f"/parking-assignments/{requester_id}")
    assert release_response.status_code == 200
    assert release_response.json() == {
        "RequesterId": requester_id,
        "SpaceId": assigned_space_id,
        "State": "Available",
    }

    occupied_requester_id = f"{requester_id}-occupied"
    occupied_assignment_response = client.post(
        "/parking-assignments",
        json={
            "RequesterId": occupied_requester_id,
            "PreferredLevel": 1,
            "RequiredType": "Standard",
        },
    )
    assert occupied_assignment_response.status_code == 201
    occupied_assignment = occupied_assignment_response.json()
    occupied_space_id = occupied_assignment["SpaceId"]

    update_response = client.patch(
        f"/parking-spaces/{occupied_space_id}/state",
        json={"State": "Occupied"},
    )
    assert update_response.status_code == 200

    occupied_release_response = client.delete(
        f"/parking-assignments/{occupied_requester_id}"
    )
    assert occupied_release_response.status_code == 200
    assert occupied_release_response.json()["State"] == "Occupied"

    reset_response = client.patch(
        f"/parking-spaces/{occupied_space_id}/state",
        json={"State": "Available"},
    )
    assert reset_response.status_code == 200
