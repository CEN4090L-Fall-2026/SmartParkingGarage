from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import httpx
import pytest

from smart_parking_backend.models import cameras as camera_models
from smart_parking_backend.services.cctv import CameraConflictError
from tests.fake_unity import FakeUnity

JPEG = bytes.fromhex(
    """
    ffd8 ffe0 0010 4a46 4946 0001 0200 0001 0001 0000
    fffe 0010 4c61 7663 3632 2e32 382e31 3033 00 ffdb 0043
    0008 0404 0404 0405 0505 0505 0506 0606 0606 0606 0606
    0606 0606 0607 0707 0808 0807 0707 0606 0707 0808 0808
    0909 0908 0808 0809 090a 0a0a 0c0c 0b0b 0e0e 0e11 11
    14ffc4 004c 0001 0100 0000 0000 0000 0000 0000 0000 0000
    0601 0101 0000 0000 0000 0000 0000 0000 0000 0000 0006
    0710 0100 0000 0000 0000 0000 0000 0000 0000 0000 0000
    0011 0100 0000 0000 0000 0000 0000 0000 0000 0000 0000
    0000 ffc0 0011 0800 0200 0203 0122 0002 1100 0311 00ff
    da00 0c03 0100 0211 0311 003f 008b 004d 7f7f ffd9
    """
)


def camera(camera_id, *, enabled=True, allow_focused=True, interval=1.0, level=1):
    return {
        "camera_id": camera_id,
        "display_name": camera_id.replace("_", " ").title(),
        "category": "Entrance",
        "level": level,
        "enabled": enabled,
        "allow_focused": allow_focused,
        "thumbnail_interval_seconds": interval,
        "description": "Garage camera",
        "coverage": "Entry lane",
    }


def register(client, session_id, cameras, focused_interval=0.1):
    return client.post(
        "/api/integration/cameras",
        json={
            "unity_session_id": session_id,
            "focused_interval_seconds": focused_interval,
            "cameras": cameras,
        },
    )


def upload(client, session_id, camera_id, kind="thumbnail", sequence=1, **extra):

    params = {
        "unity_session_id": session_id,
        "kind": kind,
        "sequence": sequence,
        "captured_at": extra.pop("captured_at"),
        "width": 2,
        "height": 2,
        **extra,
    }
    return client.post(
        f"/api/integration/cameras/{camera_id}/frames",
        params=params,
        content=JPEG,
        headers={"Content-Type": "image/jpeg"},
    )


def post_frame(
    client, clock, session_id, camera_id, *, kind="thumbnail", sequence=1, generation=None, captured_at=None
):
    return upload(
        client,
        session_id,
        camera_id,
        kind,
        sequence,
        captured_at=(captured_at or clock.utcnow()).isoformat(),
        focus_generation=generation,
    )


@pytest.mark.parametrize("content_type", [None, "application/octet-stream", "text/plain", "application/json"])
def test_frame_upload_requires_jpeg_media_type(client, unity, clock, content_type):
    assert register(client, unity.session, [camera("CAM_A")]).status_code == 204
    assert post_frame(client, clock, unity.session, "CAM_A").status_code == 204
    original = client.get("/api/cameras/CAM_A/frame")
    params = {
        "unity_session_id": unity.session,
        "kind": "thumbnail",
        "sequence": 2,
        "captured_at": clock.utcnow().isoformat(),
        "width": 2,
        "height": 2,
    }
    headers = {} if content_type is None else {"Content-Type": content_type}
    rejected = client.post("/api/integration/cameras/CAM_A/frames", params=params, content=JPEG, headers=headers)
    assert rejected.status_code == 415
    retained = client.get("/api/cameras/CAM_A/frame")
    assert retained.content == JPEG and retained.headers["etag"] == original.headers["etag"]

    accepted = client.post(
        "/api/integration/cameras/CAM_A/frames",
        params=params,
        content=JPEG,
        headers={"Content-Type": "Image/JPEG; charset=binary"},
    )
    assert accepted.status_code == 204
    assert client.get("/api/cameras/CAM_A/frame").headers["x-frame-sequence"] == "2"


@pytest.mark.parametrize("declared_length", [False, True], ids=["streamed", "content-length"])
def test_frame_upload_size_limit_stops_reading_and_preserves_latest_frame(client, unity, clock, declared_length):
    assert register(client, unity.session, [camera("CAM_A")]).status_code == 204
    params = {
        "unity_session_id": unity.session,
        "kind": "thumbnail",
        "sequence": 1,
        "captured_at": clock.utcnow().isoformat(),
        "width": 2,
        "height": 2,
    }
    path = "/api/integration/cameras/CAM_A/frames"
    at_limit = JPEG + b"\0" * (camera_models.MAX_FRAME_BYTES - len(JPEG))
    assert client.post(path, params=params, content=at_limit, headers={"Content-Type": "image/jpeg"}).status_code == 204
    original = client.get("/api/cameras/CAM_A/frame")
    assert original.content == at_limit
    params["sequence"] = 2

    async def oversized_chunks():
        if declared_length:
            pytest.fail("Oversized Content-Length must be rejected before reading the body.")
        yield at_limit
        yield b"\0"
        pytest.fail("The upload must stop reading as soon as the size limit is exceeded.")

    async def send_oversized():
        headers = {"Content-Type": "image/jpeg"}
        if declared_length:
            headers["Content-Length"] = str(camera_models.MAX_FRAME_BYTES + 1)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="http://testserver"
        ) as sender:
            return await sender.post(path, params=params, content=oversized_chunks(), headers=headers)

    rejected = client.portal.call(send_oversized)
    assert rejected.status_code == 413
    retained = client.get("/api/cameras/CAM_A/frame")
    assert retained.content == at_limit and retained.headers["etag"] == original.headers["etag"]
    assert post_frame(client, clock, unity.session, "CAM_A", sequence=2).status_code == 204
    assert client.get("/api/cameras/CAM_A/frame").content == JPEG


def test_catalog_frames_and_conditional_reads(client, unity, clock):
    assert client.get("/api/cameras").json() == []
    assert register(client, unity.session, [camera("CAM_A"), camera("CAM_OFF", enabled=False)]).status_code == 204
    listing = {entry["camera_id"]: entry for entry in client.get("/api/cameras").json()}
    assert listing["CAM_A"]["thumbnail"]["health"] == "NoFrame"
    assert listing["CAM_A"]["focused"]["health"] == "Unavailable"
    assert client.get("/api/cameras/UNKNOWN/frame").status_code == 404
    unavailable = client.get("/api/cameras/CAM_A/frame")
    assert unavailable.status_code == 503 and unavailable.json()["health"] == "NoFrame"
    assert unavailable.headers["x-feed-health"] == "NoFrame"
    assert client.get("/api/cameras/CAM_OFF/frame").status_code == 503
    assert client.get("/api/cameras/CAM_OFF/frame").json()["health"] == "Unavailable"

    assert post_frame(client, clock, unity.session, "CAM_A").status_code == 204
    first = client.get("/api/cameras/CAM_A/frame")
    assert first.status_code == 200 and first.content == JPEG
    assert first.headers["content-type"] == "image/jpeg"
    assert first.headers["x-feed-health"] == "Fresh"
    assert first.headers["x-frame-sequence"] == "1"
    assert first.headers["x-frame-width"] == "2"
    assert first.headers["x-frame-height"] == "2"
    assert first.headers["x-unity-session-id"] == unity.session

    for validator in (first.headers["etag"], f"W/{first.headers['etag']}", f'"other", {first.headers["etag"]}', "*"):
        not_modified = client.get("/api/cameras/CAM_A/frame", headers={"If-None-Match": validator})
        assert not_modified.status_code == 304 and not not_modified.content
        assert not_modified.headers["etag"] == first.headers["etag"]

    assert post_frame(client, clock, unity.session, "CAM_A", sequence=2).status_code == 204
    newer = client.get("/api/cameras/CAM_A/frame", headers={"If-None-Match": first.headers["etag"]})
    assert newer.status_code == 200 and newer.headers["etag"] != first.headers["etag"]
    assert post_frame(client, clock, unity.session, "CAM_A", sequence=2).status_code == 409
    assert client.get("/api/cameras/CAM_A/frame").headers["x-frame-sequence"] == "2"


def test_unset_thumbnail_interval_uses_capture_default_and_numeric_level(client, unity, clock):
    assert register(client, unity.session, [camera("CAM_EXTERIOR", level=0, interval=0)]).status_code == 204
    camera_view = client.get("/api/cameras").json()[0]
    assert camera_view["level"] == 0
    assert camera_view["thumbnail_interval_seconds"] == 1.0

    capture_time = clock.utcnow() - timedelta(seconds=2.5)
    assert post_frame(client, clock, unity.session, "CAM_EXTERIOR", captured_at=capture_time).status_code == 204
    assert client.get("/api/cameras").json()[0]["thumbnail"]["health"] == "Fresh"


def test_freshness_uses_capture_time_and_camera_session(client, unity, clock):
    assert register(client, unity.session, [camera("CAM_A")]).status_code == 204
    capture_time = clock.utcnow() - timedelta(seconds=2.5)
    assert post_frame(client, clock, unity.session, "CAM_A", captured_at=capture_time).status_code == 204
    unity.snapshot()
    listing = client.get("/api/cameras").json()[0]
    assert listing["thumbnail"]["health"] == "Fresh"
    assert listing["thumbnail"]["age_ms"] == 2500

    before = client.get("/api/integration/status").json()["seconds_since_last_update"]
    clock.advance(0.6)
    stale = client.get("/api/cameras/CAM_A/frame")
    assert stale.status_code == 200 and stale.headers["x-feed-health"] == "Stale"
    assert stale.headers["x-frame-age-ms"] == "3100"
    assert client.get("/api/integration/status").json()["seconds_since_last_update"] > before

    assert post_frame(client, clock, unity.session, "CAM_A", sequence=2).status_code == 204
    clock.advance(0.31)
    lease = client.post("/api/cameras/CAM_A/focus")
    assert lease.status_code == 200
    generation = lease.json()["focus_generation"]
    assert post_frame(client, clock, unity.session, "CAM_A", kind="focused", generation=generation).status_code == 204
    clock.advance(0.31)
    statuses = client.get("/api/cameras").json()[0]
    assert statuses["thumbnail"]["health"] == "Fresh"
    assert statuses["focused"]["health"] == "Stale"

    changed_session = FakeUnity(client, session="SESSION_B")
    assert changed_session.snapshot().status_code == 200
    assert client.get("/api/cameras").json() == []
    assert client.get("/api/cameras/focus").json() == {
        "camera_id": None,
        "focus_generation": None,
        "expires_at": None,
    }
    assert post_frame(client, clock, unity.session, "CAM_A", sequence=3).status_code == 409
    assert register(client, changed_session.session, [camera("CAM_A")]).status_code == 204
    assert post_frame(client, clock, changed_session.session, "CAM_A").status_code == 204
    new_session_frame = client.get("/api/cameras/CAM_A/frame")
    assert new_session_frame.status_code == 200
    assert new_session_frame.headers["x-frame-sequence"] == "1"
    assert new_session_frame.headers["etag"] != stale.headers["etag"]


def test_focus_lease_exclusivity_switching_expiry_and_release(client, unity, clock):
    assert register(client, unity.session, [camera("CAM_A"), camera("CAM_B")]).status_code == 204
    first = client.post("/api/cameras/CAM_A/focus")
    assert first.status_code == 200
    token = first.json()["lease_id"]
    generation = first.json()["focus_generation"]
    assert client.get("/api/cameras/focus").json()["camera_id"] == "CAM_A"
    assert "lease_id" not in client.get("/api/cameras/focus").json()
    assert (
        client.get("/api/integration/cameras/control", params={"unity_session_id": unity.session}).json()["focus"][
            "focus_generation"
        ]
        == generation
    )
    assert (
        "lease_id"
        not in client.get("/api/integration/cameras/control", params={"unity_session_id": unity.session}).json()
    )

    assert post_frame(client, clock, unity.session, "CAM_A", kind="focused", generation=generation).status_code == 204
    renewed = client.post("/api/cameras/CAM_A/focus", json={"lease_id": token})
    assert renewed.status_code == 200 and renewed.json()["focus_generation"] == generation
    assert client.get("/api/cameras/CAM_A/frame", params={"kind": "focused"}).status_code == 200
    assert client.post("/api/cameras/CAM_B/focus").status_code == 409
    assert client.post("/api/cameras/CAM_A/focus", json={"lease_id": "wrong"}).status_code == 409

    switched = client.post("/api/cameras/CAM_B/focus", json={"lease_id": token})
    assert switched.status_code == 200
    next_generation = switched.json()["focus_generation"]
    assert next_generation != generation and switched.json()["lease_id"] == token
    assert (
        post_frame(client, clock, unity.session, "CAM_A", kind="focused", sequence=2, generation=generation).status_code
        == 409
    )
    assert client.get("/api/cameras/CAM_A/frame", params={"kind": "focused"}).status_code == 503
    assert client.get("/api/cameras/CAM_A/frame").status_code == 503  # no thumbnail uploaded
    assert (
        post_frame(client, clock, unity.session, "CAM_B", kind="focused", generation=next_generation).status_code == 204
    )

    assert client.delete("/api/cameras/focus", headers={"X-Focus-Lease-Id": "wrong"}).status_code == 409
    assert client.delete("/api/cameras/focus", headers={"X-Focus-Lease-Id": token}).status_code == 204
    assert client.get("/api/cameras/BLAH/frame", params={"kind": "focused"}).status_code == 404
    assert client.get("/api/cameras/CAM_B/frame", params={"kind": "focused"}).status_code == 503
    assert client.delete("/api/cameras/focus").status_code == 204
    assert client.post("/api/cameras/CAM_A/focus", json={"lease_id": token}).status_code == 409

    owner = client.post("/api/cameras/CAM_A/focus").json()
    clock.advance(30)
    unity.snapshot()
    replacement = client.post("/api/cameras/CAM_B/focus")
    assert replacement.status_code == 200
    assert replacement.json()["lease_id"] != owner["lease_id"]
    assert replacement.json()["focus_generation"] != owner["focus_generation"]
    assert client.post("/api/cameras/CAM_A/focus", json={"lease_id": owner["lease_id"]}).status_code == 409
    assert client.delete("/api/cameras/focus", headers={"X-Focus-Lease-Id": owner["lease_id"]}).status_code == 409


def test_catalog_replacement_prunes_removed_or_disabled_frames(client, unity, clock):
    assert register(client, unity.session, [camera("CAM_A"), camera("CAM_B")]).status_code == 204
    assert post_frame(client, clock, unity.session, "CAM_A").status_code == 204
    lease = client.post("/api/cameras/CAM_A/focus").json()
    assert (
        post_frame(
            client, clock, unity.session, "CAM_A", kind="focused", generation=lease["focus_generation"]
        ).status_code
        == 204
    )

    assert register(client, unity.session, [camera("CAM_A", enabled=False), camera("CAM_C")]).status_code == 204
    listing = {item["camera_id"]: item for item in client.get("/api/cameras").json()}
    assert list(listing) == ["CAM_A", "CAM_C"]
    assert listing["CAM_A"]["thumbnail"]["health"] == "Unavailable"
    assert client.get("/api/cameras/CAM_A/frame").status_code == 503
    assert client.get("/api/cameras/focus").json()["camera_id"] is None
    assert client.get("/api/cameras/CAM_C/frame").status_code == 503


def test_snapshot_freshness_is_independent_from_camera_frames(client, unity, clock):
    assert register(client, unity.session, [camera("CAM_A")]).status_code == 204
    assert post_frame(client, clock, unity.session, "CAM_A").status_code == 204
    clock.advance(6)
    assert client.get("/api/integration/status").json()["connected"] is False
    stale = client.get("/api/cameras/CAM_A/frame")
    assert stale.status_code == 200 and stale.headers["x-feed-health"] == "Stale"
    assert post_frame(client, clock, unity.session, "CAM_A", sequence=2).status_code == 204
    assert client.get("/api/integration/status").json()["connected"] is False
    assert client.get("/api/cameras/CAM_A/frame").headers["x-feed-health"] == "Fresh"
    clock.advance(0.25)
    unity.snapshot()
    assert client.get("/api/integration/status").json()["connected"] is True
    assert client.get("/api/cameras/CAM_A/frame").headers["x-frame-age-ms"] == "250"


def test_focus_lease_is_atomic_and_session_or_simulation_snapshot_lifecycle_is_clear(client, unity):
    assert register(client, unity.session, [camera("CAM_A")]).status_code == 204
    service = client.app.state.cctv_service
    first_snapshot = client.post("/api/integration/state", json=unity.body())
    assert first_snapshot.status_code == 200
    barrier = Barrier(2)

    def acquire():
        barrier.wait()
        try:
            return service.acquire_focus("CAM_A", None)
        except CameraConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: acquire(), range(2)))
    assert sum(result is not None for result in results) == 1
    active = next(result for result in results if result is not None)

    unity.sim["state"] = "Running"
    assert unity.snapshot().status_code == 200
    assert service.focus_state().camera_id == "CAM_A"
    service.release_focus(active.lease_id)


def test_camera_cors(client, unity, clock):
    assert register(client, unity.session, [camera("CAM_A")]).status_code == 204
    assert post_frame(client, clock, unity.session, "CAM_A").status_code == 204
    preflight = client.options(
        "/api/cameras/focus",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "x-focus-lease-id,if-none-match",
        },
    )
    assert preflight.status_code == 200
    assert "DELETE" in preflight.headers["access-control-allow-methods"]
    frame = client.get("/api/cameras/CAM_A/frame", headers={"Origin": "http://localhost:5173"})
    assert frame.headers["access-control-allow-origin"] == "http://localhost:5173"
    exposed = frame.headers["access-control-expose-headers"].lower()
    assert "etag" in exposed and "x-frame-age-ms" in exposed and "x-feed-health" in exposed
