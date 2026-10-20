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
- State is **in memory only** (lost on restart). No database, auth, WebSockets or dashboard yet.

## Setup (Python 3.11+), run, test

From this repository's `Backend/` directory (Python 3.11+ and uv installed):

```bash
uv sync
uv run uvicorn smart_parking_backend.main:app --host 127.0.0.1 --port 8000
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
```

Run one server process: snapshots and command queues are process-local. PostgreSQL, Docker, and a `.env` file are
not required for this baseline. Stop the other backend server before using port 8000. Unity already targets
`http://127.0.0.1:8000`; no Unity code or scene changes are needed. Reloading or restarting the server clears its state.

The development dependencies (pytest, httpx, Ruff) are installed by `uv sync`. The backend tests use isolated app
instances and a controllable clock; they do not connect to Unity or a development database.

Docs: <http://127.0.0.1:8000/docs>, `/redoc`, `/openapi.json`.

## Unity <-> backend bridge: REST polling

Polling was chosen over WebSockets because it is stateless, survives either side restarting, needs nothing beyond
`UnityWebRequest`, and every message is a plain request that is easy to test. Unity does all the calling:

| Direction | Call | Cadence |
| --- | --- | --- |
| Unity -> backend | `POST /api/integration/state` (full snapshot) | 1 per second (serialized setting) |
| backend -> Unity | `GET /api/integration/commands?unity_session_id=...` | every 0.5 s |
| Unity -> backend | `POST /api/integration/commands/{command_id}/ack` | once per command |

**Sessions and sequence.** Unity generates a `unity_session_id` when Play Mode starts and numbers snapshots 1, 2, 3...
A snapshot whose sequence is not greater than the latest accepted one for that session is rejected with **409** and
changes nothing. A different session id is a new session: it is accepted, sequence tracking restarts, and commands still
open for the old session are cancelled. If the backend restarts (`backend_instance_id` changes) Unity starts a new session.

**Connectivity.** `connected` is true while the last accepted snapshot is at most `SPG_INTEGRATION_TIMEOUT_SECONDS`
(default 5) old. Query endpoints always answer and carry an `X-Data-Source` header (`SeededBaseline`, `UnityLive`,
`UnityLastKnown`); the garage and simulation bodies carry the same `data_source` field.

**Commands.** `POST /api/simulation/{start,pause-arrivals,resume-arrivals,drain,reset,mode}`, `POST /api/vehicles/spawn`,
and `POST /api/vehicles/{vehicle_id}/depart` **queue** commands and return **202** (queued, not executed). The
simulation state and vehicle projection change only when Unity executes a command and a subsequent snapshot reports the
result. Poll `GET /api/integration/commands/{command_id}` for the command outcome.

- IDs are `CMD_000001`, `CMD_000002`, ... (spawn requests are separately `REQ_0001`...).
- Status: `Pending -> Delivered -> Acknowledged | Failed`, or `Cancelled`.
- **FIFO:** commands are always returned oldest first.
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
- **Reset:** queuing a reset immediately cancels every earlier command that was never delivered ("obsolete"). Commands
  already delivered are left alone (FIFO means they finish before the reset runs); when a reset is acknowledged, any
  earlier command still open is cancelled as well. Commands created after the reset are unaffected.
- **Spawn requests** move `AcceptedByBackend -> ForwardedToUnity -> SpawnedInUnity` (with the `vehicle_id` Unity reports)
  or `Failed`. Only `SpawnedInUnity` means a vehicle exists.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | status, service, version |
| GET | `/api/garage` | totals and per-level summary (derived from the reported spaces) |
| GET | `/api/spaces`, `/api/spaces/{space_id}` | filters: `level`, `state`, `space_type`; 404 if unknown |
| GET | `/api/vehicles`, `/api/vehicles/{vehicle_id}` | active vehicles as Unity reported them |
| POST | `/api/vehicles/spawn` | 202, queues SpawnVehicle; 503 offline |
| POST | `/api/vehicles/{vehicle_id}/depart` | 202, queues DepartVehicle for Unity; 503 offline |
| GET | `/api/vehicles/spawn-requests[/{request_id}]` | spawn request records |
| GET | `/api/simulation` | status |
| POST | `/api/simulation/start`, `pause-arrivals`, `resume-arrivals`, `drain`, `reset`, `mode` | 202 queued; 503 offline |
| POST | `/api/integration/state` | Unity snapshot; 409 stale, 422 malformed |
| GET | `/api/integration/status` | connected, session, sequence, last update, age |
| GET | `/api/integration/commands` | pending commands for a session |
| GET | `/api/integration/commands/{command_id}` | one command's outcome |
| POST | `/api/integration/commands/{command_id}/ack` | Unity's result |

Status codes: 200 query, 202 command queued, 404 unknown, 409 stale snapshot / wrong session, 422 invalid input, 503 Unity offline.
CORS allows only `http://localhost:3000`, `http://localhost:5173`, `http://127.0.0.1:3000`, `http://127.0.0.1:5173`.

## Stall inventory

`src/smart_parking_backend/services/seed_data.py` holds the exact stall IDs (from the Unity garage prefab and `MainGarage` scene). IDs are **not
contiguous** (L3 and L4 run to `_125`); never generate them from a range. It is only the fallback before Unity reports.

## Testing without Unity

`tests/fake_unity.py` is an HTTP protocol stand-in for exercising sessions, sequence, FIFO, redelivery, reset, and
spawn outcomes. It is not a physics or traffic simulator; backend test results do not validate Unity vehicle movement.


## Backend cutover

This workspace adopts the handed-off application from `SmartParkingGarage/Backend` while leaving that Unity workspace
unchanged. The former database-owned `/parking-assignments` and `/parking-spaces` mutation API, SQLAlchemy bootstrap,
and PostgreSQL Compose configuration have been removed from the active implementation. They are not compatibility paths.
Unity continues to select stalls and report their resulting state. Persistence is deferred, not silently provided.

The old sibling backend was preserved locally in `Backend-before-handoff-2026-10-05.Lo9CYS.tar.gz` beside
the original sibling workspace before replacement. That archive is not included in GitHub.
No PostgreSQL database or volume was reset or deleted.
The numbered DOCX handoffs remain unchanged. Earlier Unity onboarding notes are historical; this README is the current
backend setup and ownership reference.
