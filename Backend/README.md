# Smart Parking Garage Backend

REST API and shared contracts for the Smart Parking Garage product (Python, FastAPI, Pydantic).

Canonical GitHub repository: <https://github.com/CEN4090L-Fall-2026/SmartParkingGarage>, under `Backend/`.
Clone the team repository outside the Unity UVCS workspace and make backend changes in this directory.
The personal `CrashHermit/SmartParkingGarage-Backend` repository is not the team's source of truth.

## Ownership model

- **Unity is authoritative for live simulation state** (assignments, movement, maneuvers, traffic, departures).
- The backend is authoritative for **accepted external commands**, the normalized API contracts, and a **client-facing
  projection** of what Unity last reported. It never decides simulation outcomes.
- Until a Unity session reports, queries return the **seeded baseline** (414 stalls, 406 operational, 8 OutOfService,
  8 EV on L2). Once Unity reports, its snapshot **replaces** the projection completely; nothing is merged with the seed.
- PostgreSQL persists parking-request intent, command delivery/results, Unity session metadata, and the latest complete
  snapshot. Restart restores that snapshot as **UnityLastKnown**, not live simulation state. CCTV remains in memory.
- No authentication or WebSockets; dashboards consume this API from separate projects.

## Setup (Python 3.11+), run, test

From this repository's `Backend/` directory (Python 3.11+, uv, and Docker with Compose installed):

```bash
uv sync
docker compose up -d --wait postgres
export SPG_DATABASE_URL='postgresql+psycopg://smart_parking:smart_parking_dev@127.0.0.1:5432/smart_parking'
uv run alembic upgrade head
uv run uvicorn smart_parking_backend.main:app --host 127.0.0.1 --port 8000
```

Compose provisions PostgreSQL 17 with a persistent named volume. The password above is for local development only.
Set `SPG_POSTGRES_PORT` before running Compose to change the host port, and change the URL to match.
An existing PostgreSQL database can be used instead: skip Compose and provide its driver-qualified URL.
`SPG_DATABASE_URL` and an explicitly migrated schema are required; startup does not migrate, load `.env`, or fall
back to memory. Run `uv run alembic upgrade head` when deploying schema changes. Do not delete the database volume
unless intentionally discarding all durable records.

In another terminal, run tests and quality checks:

```bash
export SPG_TEST_DATABASE_URL='postgresql+psycopg://smart_parking:smart_parking_dev@127.0.0.1:5432/smart_parking'
uv run pytest -q
uv run ruff format --check src tests migrations
uv run ruff check src tests migrations
```

The test URL is required explicitly and must permit creating/dropping schemas. Each test creates a uniquely named
schema, applies the real Alembic migrations, and drops only that schema afterward; it never resets shared application
tables. Tests use a controllable clock and a simulated Unity publisher, not the Unity editor. Development dependencies
(pytest, httpx, Ruff) are installed by `uv sync`.

Run one server process: the live projection, connectivity clocks, camera frames, and focus leases remain process-local.
PostgreSQL makes records durable, not the entire backend multi-worker-safe. Use an available port; the existing Unity
bridge targets `http://127.0.0.1:8000`. Driver-specific fields and commands require a matching Unity bridge.
Unity Plastic main changeset 4824 includes `CCTVBackendPublisher`, which publishes the camera catalog and JPEG frames
and polls focus control. Dashboard consumption is a separate integration; see [CCTV](../docs/frontend-api.md#cctv).

Reloading/restarting preserves request/command IDs and known results. Startup cancels commands never delivered and
marks delivered-but-unacknowledged commands **OutcomeUnknown**; neither is replayed. The latest snapshot is replaced
on each accepted report, not archived. Its original receipt time is preserved, and command intake stays offline until
a fresh Unity report arrives. This restores backend knowledge, not Unity vehicles. Records are retained indefinitely;
there is no accounts/booking system, historical snapshot archive, or CCTV recording. Frames and focus leases are lost.

Docs: <http://127.0.0.1:8000/docs>, `/redoc`, `/openapi.json`.

Dashboard developers: [API quick reference](../docs/frontend-api.md).
Previous handoff: [backend status report #2](../docs/reports/backend-status-report-02.md) (historical).

## Unity <-> backend bridge: REST polling

Polling was chosen over WebSockets because it is stateless, survives either side restarting, needs nothing beyond
`UnityWebRequest`, and every message is a plain request that is easy to test. Unity does all the calling:

| Direction | Call | Cadence |
| --- | --- | --- |
| Unity -> backend | `POST /api/integration/state` (full snapshot) | 1 per second (serialized setting) |
| backend -> Unity | `GET /api/integration/commands?unity_session_id=...` | every 0.5 s |
| Unity -> backend | `POST /api/integration/commands/{command_id}/ack` | once per command |
| Unity -> backend | `POST /api/integration/cameras` (catalog) | Once per established integration session; again after backend restart |
| Unity -> backend | `POST /api/integration/cameras/{camera_id}/frames` (raw JPEG) | New captures only; default thumbnails 1 fps per camera, focused 10 fps |
| backend -> Unity | `GET /api/integration/cameras/control?unity_session_id=...` | every 0.5 s |

**CCTV startup.** Update the separate Unity workspace to Plastic main changeset 4824 or newer, open
`Assets/Scenes/Main/MainGarage.unity` with Unity 6000.6.0f1, and enter Play Mode with this backend running.
`BackendIntegrationClient` automatically adds `CCTVBackendPublisher` when `publishCctv` is enabled (the default)
and a `CCTVCaptureService` exists. After the integration session and catalog are accepted, the publisher starts capture.
The backend URL comes from the existing bridge (`http://127.0.0.1:8000` by default); there is no separate camera URL.
Check `/api/integration/status` for `connected: true` and `/api/cameras` for the catalog and fresh thumbnails.
Acquire a focus lease to start focused capture; merely opening the stream does not select a camera.
Camera publishing does not move the Unity operator's on-screen view.

**Sessions and sequence.** Unity generates a `unity_session_id` when Play Mode starts and numbers snapshots 1, 2, 3...
A snapshot whose sequence is not greater than the latest accepted one for that session is rejected with **409** and
changes nothing. A different session id is accepted with new sequence tracking: old Pending commands become Cancelled,
and old Delivered commands without results become OutcomeUnknown. If the backend restarts (`backend_instance_id`
changes) Unity starts a new integration session without resetting its simulation. The returning client's first fresh
old-session snapshot may be accepted so it can learn the new backend ID; completed/unknown commands never revive.

**Connectivity.** `connected` requires an accepted snapshot in this process within `SPG_INTEGRATION_TIMEOUT_SECONDS`
(default 5). A restored snapshot is always disconnected until a fresh report, even if its saved timestamp is recent.
Garage, space, vehicle, and simulation projection responses carry `X-Data-Source`:
`SeededBaseline`, `UnityLive`, or `UnityLastKnown`. Garage and simulation also include `data_source` in their bodies.
Integration status reports freshness in its body; command and spawn-request queries are records, not freshness indicators.

**Commands.** `POST /api/simulation/{start,pause-arrivals,resume-arrivals,drain,reset,mode}`, `POST /api/vehicles/spawn`,
and `POST /api/vehicles/{vehicle_id}/depart` **queue** commands and return **202** (queued, not executed). The
simulation state and vehicle projection change only when Unity executes a command and a subsequent snapshot reports the
result. Poll `GET /api/integration/commands/{command_id}` for the command outcome.

- IDs retain the `CMD_000001` / `REQ_0001` format, allocated by durable PostgreSQL sequences. They are not reused on
  backend restart; gaps are valid. Command order uses the numeric sequence, not a string comparison.
- Status: `Pending -> Delivered -> Acknowledged | Failed`, or `Cancelled` / `OutcomeUnknown`.
- **FIFO:** eligible commands are always returned oldest first, within their owning Unity session.
- **Offline:** with no Unity session reporting within the timeout, every command endpoint returns **503** and queues
  nothing; backend state is never changed as if Unity had executed it.
- **Validation of transitions belongs to Unity.** An invalid command (for example `pause-arrivals` while Idle) is queued
  and Unity acknowledges it as failed (`status: Failed`, with Unity's message).
- **Individual departure:** the path vehicle ID is sent to Unity as `payload.vehicle_id`. The backend does not check
  whether that vehicle exists or is ready to depart, and does not change its vehicle or parking-space projection.
  Unity validates and starts the departure; snapshots report its progress and completion.
- **Driver parking requests:** SpawnVehicle accepts `payload.auto_depart` (default `true`). Setting it to `false` is
  forwarded to Unity, which must consume the field to keep the driver-requested vehicle parked. Until that Unity bridge
  change is made, the backend field alone does not change simulation behavior.
- **Structured spawn failures:** Unity may include `error_code` in a failed acknowledgement: `GarageFull`, `LevelFull`,
  `VehicleLimitReached`, or `EntranceBlocked`. The backend records the code on the command and spawn-request result; it
  does not infer codes from message text.
- **Delivery is at-least-once.** A delivered command with no ack after `SPG_COMMAND_REDELIVERY_SECONDS` (default 5) is handed
  out again (`delivery_count` increments). Unity remembers processed ids and only re-acknowledges them, never re-executes.
- **Acks are idempotent:** acknowledging a finished command returns `duplicate: true` and changes nothing; the first result wins.
- **Unknown outcomes:** `OutcomeUnknown` is terminal, not failed or successful, and is excluded from pending counts.
  Do not automatically retry it: a vehicle may have been created before its acknowledgement was lost. It has no
  confirmed vehicle/error code and is not reconciled from snapshots. Acknowledgements cannot cross session ownership.
- **Acknowledgement time:** `acknowledged_at` records an actual Unity success/failure response, not cancellation or
  unknown-outcome classification; it remains null for the latter two.
- **Reset:** queuing a reset immediately cancels every earlier command that was never delivered ("obsolete"). Commands
  already delivered are left alone (FIFO means they finish before the reset runs); when a reset is acknowledged, any
  earlier command still open is cancelled as well. Commands created after the reset are unaffected.
- **Spawn requests** move `AcceptedByBackend -> ForwardedToUnity -> SpawnedInUnity` (with the reported `vehicle_id`),
  `Failed`, or `OutcomeUnknown`. A cancelled command retains the existing request-level Failed mapping. Request status
  and flags are derived from the linked command, not separately mutable records. Unknown is forwarded but not confirmed
  spawned, with null vehicle/failure/error fields. Only `SpawnedInUnity` confirms successful creation.

## Integration endpoints

The [dashboard API quick reference](../docs/frontend-api.md) lists client-facing endpoints and request fields.
These endpoints are for the Unity bridge, not dashboard execution:

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/api/integration/state` | Full Unity snapshot; 409 stale |
| GET | `/api/integration/commands?unity_session_id=...` | Commands for execution; may redeliver |
| POST | `/api/integration/commands/{command_id}/ack` | Unity's result; first terminal result wins |

Status codes: 200 query, 202 command queued, 404 unknown, 409 stale snapshot / wrong session, 422 invalid input, 503 Unity offline.
CORS allows only `http://localhost:3000`, `http://localhost:5173`, `http://127.0.0.1:3000`, `http://127.0.0.1:5173`.

## CCTV endpoints

The backend keeps a bounded, process-local latest-frame cache. It neither stores video history nor starts Unity capture.
Unity must register the current camera catalog and publish JPEG frames; the backend endpoints are implemented, but
the Unity HTTP publisher and dashboard client are not connected yet. Camera and frame state resets when Unity reports a
new session or the backend restarts.

| Method | Path | Caller | Contract |
| --- | --- | --- | --- |
| POST | `/api/integration/cameras` | Unity | Replace the catalog for the current `unity_session_id`; JSON includes `focused_interval_seconds` and camera metadata (`level` is 0-4; 0 means not level-specific; a thumbnail interval of 0 uses the 1-second default). |
| POST | `/api/integration/cameras/{camera_id}/frames` | Unity | Query carries `unity_session_id`, `kind`, `sequence`, `captured_at`, `width`, `height`, and focused `focus_generation`; raw request body is `image/jpeg`. |
| GET | `/api/integration/cameras/control?unity_session_id=...` | Unity | Returns the current focused camera and `focus_generation`, plus the backend instance ID. |
| GET | `/api/cameras` | Dashboard | Camera metadata and separate thumbnail/focused feed status. |
| GET | `/api/cameras/{camera_id}/frame?kind=thumbnail\|focused` | Dashboard | Latest JPEG; `kind` defaults to `thumbnail`. Supports `If-None-Match` / **304**. |
| GET | `/api/cameras/{camera_id}/stream` | Dashboard | Focused MJPEG stream (`multipart/x-mixed-replace; boundary=frame`); requires a selected camera with an existing focused frame. |
| GET | `/api/cameras/focus` | Dashboard | Current focused camera, generation, and lease expiry. |
| POST | `/api/cameras/{camera_id}/focus` | Dashboard | Acquire focus without a body, or renew/switch by sending `{"lease_id":"..."}`. Returns the lease ID and focus generation. |
| DELETE | `/api/cameras/focus` | Dashboard | Release focus with `X-Focus-Lease-Id`. |

There is one exclusive focus lease for the whole backend, expiring after 30 seconds. Renew it with the same lease ID
while viewing; another viewer receives **409** until it is released or expires. Unity polls the control endpoint and
publishes focused frames with the returned generation. A stale frame remains fetchable with `X-Feed-Health: Stale`;
consumers should check `X-Frame-Age-Ms` and feed health rather than treating HTTP 200 as proof of freshness.

Unknown cameras return **404**. Disabled feeds, feeds without a frame, and focused feeds that are not selected return
**503** with `X-Feed-Health` (`Unavailable` or `NoFrame`). Wrong sessions, non-increasing sequences, and focus lease
conflicts return **409**. `ETag` identifies the Unity session, camera, frame kind, sequence, and focus generation.
Uploads are limited to 2 MiB per JPEG and 32 cameras per catalog. Oversized uploads return **413**, checked against
`Content-Length` before reading when supplied and against received bytes while streaming. Missing or non-`image/jpeg`
content types return **415**; MIME parameters are allowed. Rejected uploads do not replace the latest frame or advance
its sequence. The backend does not decode or validate JPEG content.

`/api/cameras` is read-only for dashboards except for the explicit focus endpoints. Dashboards must not send Unity
catalogs, publish camera frames, or poll the Unity control endpoint.

### Unity publisher handoff

These backend APIs are implemented; the missing integration is the Unity HTTP publisher/control adapter. Browse
`/docs` or fetch `/openapi.json` for the public request/response schemas. They are trusted local/demo APIs without
authentication, not endpoints to expose directly to the internet.

1. Publish an ordinary garage snapshot to establish `unity_session_id`, then register the catalog. Send numeric
   camera levels 0-4 and category names (`Exterior`, `City`, `Entrance`, `Exit`, `ParkingLevel`, `Ramp`, `EV`).
   Send effective positive capture intervals: thumbnail interval 0 uses the backend's fixed 1-second default,
   which will not follow a changed Unity capture setting automatically.
2. Start Unity capture. The current scene has `captureOnStart` off; accepting a catalog does not start capture.
   Upload each latest JPEG independently of garage snapshots, using `kind=thumbnail` or `kind=focused`, per-camera/kind
   increasing sequences, render-time UTC `captured_at`, and the frame's actual dimensions. Map Unity's
   `Thumbnail`/`Focused` enum names to the lowercase wire values. Keep at most one upload in flight per camera/kind;
   skip superseded frames rather than building a backlog.
3. Poll camera control about every 0.5 seconds. Apply a non-null selection with `SetFocusedCamera`; clear it with
   `ClearFocusedCamera` when null. Tag focused capture work with the returned `focus_generation` at capture time and
   echo it on upload. Never relabel old frames using the generation current at upload time, even for the same camera.
   Unity's current `CCTVFrame` has no generation field, so capture-time association is part of the Unity integration.
4. On a session change or backend restart, re-establish the ordinary snapshot session and republish the catalog.
   A **409** for an obsolete focus generation requires reading current control, not retrying the old frame.

CCTV control/ingest is synchronous: focus acquisition returns **200**, and catalog/frame acceptance or release returns
**204**. It does not queue a simulation command or return **202**. A focus response is desired capture state, not proof
that Unity has applied it.

Dashboard clients poll thumbnail JPEGs about once per second and use `/api/cameras/{camera_id}/stream` for the focused
view. Unity still uploads individual JPEGs; it does not upload multipart video. WebSocket/WebRTC transport is not
implemented. The JPEG endpoint remains available for single-frame reads of either kind.

### Focused MJPEG viewing

1. Acquire focus, retain the returned `lease_id`, and renew it every 10 seconds while viewing.
2. Poll `/api/cameras` until that camera has a focused frame (`Fresh` or `Stale`, not `NoFrame`/`Unavailable`).
   Then set the viewer's `<img>` source to `/api/cameras/{camera_id}/stream`. The stream returns **200** with
   `multipart/x-mixed-replace; boundary=frame`; each part has `Content-Type: image/jpeg`, `Content-Length`, and the
   same ETag/session/sequence/capture-time/age/health/dimension metadata as a single-frame response.
3. Continue polling camera status about once per second for health badges. A native `<img>` cannot expose multipart
   headers to JavaScript, and an open connection is not proof of freshness. The stream sends only newer frames;
   capture stopping leaves the last image displayed without repeatedly sending the same JPEG.
4. Switching camera or losing the focus lease ends the old stream. Open a new stream after the new generation's first
   frame arrives. Remove the image source when the viewer closes, stop lease renewal, and explicitly release focus.

Any viewer may read the selected focused feed without the owner's token. Opening/closing a stream neither acquires,
renews, nor releases focus. Same-camera lease renewal keeps the stream open. Before streaming starts, unknown cameras
return **404** and unavailable/no-frame focused feeds return **503** with the existing health response.
After headers have been sent, lease expiry/release, focus-generation or Unity-session change, and catalog
removal/disable/focus revocation end the stream rather than returning a new HTTP error. A frame already in flight
may finish before closure. Normal closure sends the final multipart boundary; client disconnect cancels its reader.

Each reader checks the shared latest-frame cache every 50 ms without holding a lock while sending. Slow readers skip
superseded frames instead of building a per-viewer frame queue; transport buffers and in-flight images are additional
to the retained-cache bound. Streaming responses use `Cache-Control: private, no-store` and `X-Accel-Buffering: no`;
reverse proxies must allow long-lived, unbuffered responses. The stream does not use conditional **304** responses.

This implements the Unity document's JPEG-grid/MJPEG-focused recommendation. Live Unity CCTV/dashboard integration
still requires the separate publisher and dashboard consumer and has not been verified.

## Stall inventory

`src/smart_parking_backend/services/seed_data.py` holds the exact stall IDs (from the Unity garage prefab and `MainGarage` scene). IDs are **not
contiguous** (L3 and L4 run to `_125`); never generate them from a range. It is only the fallback before Unity reports.

## Testing without Unity

`tests/fake_unity.py` is an HTTP protocol stand-in for exercising sessions, sequence, FIFO, redelivery, reset, and
spawn outcomes. It is not a physics or traffic simulator; backend test results do not validate Unity vehicle movement.


## Code organization and style

- `api/routes/` defines HTTP handlers; `api/deps.py` resolves the application services.
- `models/` owns typed wire contracts and enum values; `services/` owns the projection and command lifecycle.
- Project-local imports use absolute module paths and qualified names, following adapted [Google Python conventions](https://google.github.io/styleguide/pyguide.html#22-imports). Models are imported from their owning modules, not re-exported by `models/__init__.py`.
- Nontrivial service contracts use explicit return types and concise Google-style `Args`, `Returns`, and `Raises` docstrings. Standard-library and third-party imports retain existing FastAPI/Pydantic conventions.
- Ruff is the formatter and linter, with a 120-column line length rather than Google's 80-column wrapping.
- `tests/conftest.py` provides fixtures; `tests/inventory.py` holds independent inventory expectations; `tests/fake_unity.py` exercises the HTTP protocol.

The numbered DOCX handoffs are historical. This README and the dashboard API reference describe the current backend.
