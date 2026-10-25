# Dashboard API Quick Reference

**Base URL:** `http://127.0.0.1:8000` · **Interactive schemas:** `/docs`

Backend setup: [README](../Backend/README.md).

Use JSON bodies with `Content-Type: application/json`. Field names use `snake_case`; enum values are case-sensitive. Vite origins allowed: `http://localhost:5173` and `http://127.0.0.1:5173` (port 3000 is also allowed).

## Read data

| GET endpoint | Use / response | Optional query filters |
| --- | --- | --- |
| `/health` | FastAPI status, service, version; does not indicate Unity connectivity | — |
| `/api/integration/status` | Unity `connected`, `data_source`, snapshot age, session, `backend_instance_id` | — |
| `/api/garage` | `available`, `occupied`, `reserved`, `out_of_service`, total counts, `levels` | — |
| `/api/spaces` | Array of spaces: ID, level, type, state, assigned vehicle | `level`, `state`, `space_type` |
| `/api/spaces/{space_id}` | One space | — |
| `/api/vehicles` | Array of vehicles: ID, `assigned_space_id`, `lifecycle_state` | `lifecycle_state` |
| `/api/vehicles/{vehicle_id}` | One vehicle; use for assigned stall / Find My Car | — |
| `/api/simulation` | Simulation state, scenario mode, vehicle counters | — |
| `/api/vehicles/spawn-requests/{request_id}` | Parking request status, `vehicle_id`, `failure_reason`, `error_code` | — |
| `/api/vehicles/spawn-requests` | All spawn requests; not scoped to a driver | — |
| `/api/integration/commands/{command_id}` | Command `status`, `result_message`, `error_code` | — |
| `/api/cameras` | Camera metadata with separate thumbnail and focused-feed health | — |
| `/api/cameras/{camera_id}/frame?kind=thumbnail\|focused` | Latest `image/jpeg`; ETag and age/freshness headers | `kind` defaults to `thumbnail` |
| `/api/cameras/focus` | Current focused camera and lease expiry | — |

## Send requests

| POST endpoint | JSON body | Purpose |
| --- | --- | --- |
| `/api/vehicles/spawn` | `{"request_type":"Standard","preferred_level":"L2","auto_depart":false}` | Driver parking request. Level optional; auto_depart defaults to true. |
| `/api/vehicles/{vehicle_id}/depart` | None | Request departure for the Unity vehicle ID, not a stall/request ID |
| `/api/simulation/start` | None | Start simulation |
| `/api/simulation/pause-arrivals` | None | Pause arrivals |
| `/api/simulation/resume-arrivals` | None | Resume arrivals |
| `/api/simulation/drain` | None | Drain the whole garage, not one vehicle |
| `/api/simulation/reset` | None | Reset simulation |
| `/api/simulation/mode` | `{"scenario_mode":"RushHour"}` | Set `Normal` or `RushHour` |

## CCTV

The backend exposes the CCTV transport, but Unity does not yet publish its camera catalog or frames to these endpoints,
and the dashboard does not yet consume them. The cache is in memory only; frames and focus leases are lost when the
backend restarts or Unity reports a new session.

| Endpoint | Caller | Contract |
| --- | --- | --- |
| `POST /api/integration/cameras` | Unity | Replace the current session's camera catalog. `level` is an integer from 0 to 4 (0 means not level-specific); `thumbnail_interval_seconds` 0 uses a 1-second default. |
| `POST /api/integration/cameras/{camera_id}/frames` | Unity | Send raw JPEG bytes as `image/jpeg`; query includes `unity_session_id`, `kind`, `sequence`, `captured_at`, `width`, `height`, and `focus_generation` for focused frames. |
| `GET /api/integration/cameras/control?unity_session_id=...` | Unity | Polls current focus selection and generation. |
| `POST /api/cameras/{camera_id}/focus` | Dashboard | Start a lease with no body; renew or switch cameras using `{"lease_id":"..."}`. Response includes `lease_id` and `focus_generation`. |
| `DELETE /api/cameras/focus` | Dashboard | Release with the `X-Focus-Lease-Id` header. |

Only one viewer owns focus at a time. The lease expires after 30 seconds; renew every 10 seconds while viewing.
Another viewer receives **409** until the lease is released or expires. Focus acquisition/renewal returns **200**;
release returns **204**, not a queued simulation-command response. The selection is desired capture state, not
confirmation that Unity has applied it. Unity polls the control endpoint and associates the returned generation with
focused work at capture time, then echoes it on upload; it must not relabel older frames with a newer generation.

Frame reads return the latest JPEG with `ETag`, `X-Unity-Session-Id`, `X-Frame-Sequence`, `X-Captured-At`,
`X-Frame-Age-Ms`, `X-Feed-Health`, `X-Frame-Width`, and `X-Frame-Height`. Send `If-None-Match` to receive **304**
when the frame is unchanged. A stale frame remains available as **200** with `X-Feed-Health: Stale`; check age and
health rather than HTTP success alone. Unknown cameras return **404**; unavailable feeds or feeds without frames
return **503** with a health code. CORS exposes the frame headers to the dashboard.

The catalog is limited to 32 cameras and each JPEG to 2 MiB. Uploads over that limit return **413**; missing or
non-`image/jpeg` media types return **415**. Rejected uploads leave the latest frame and sequence unchanged.
The Unity publisher should send effective positive capture intervals; the backend's interval-0 fallback is always
1 second, even if Unity's configured default changes.

Use non-overlapping JPEG polls for both thumbnails (about 1 Hz) and focused frames (about 10 Hz), updating health
headers even on **304**. There is no MJPEG/WebSocket endpoint. Keep the returned focus lease ID in the viewer, use it
to switch/release focus, and stop renewing when the viewer closes. A **409** means another owner or a stale token,
not a failed camera; do not automatically steal focus.

Dashboard clients may read camera data and acquire or release focus; only Unity should register catalogs, publish
frames, and poll camera control. See the [Unity publisher handoff](../Backend/README.md#unity-publisher-handoff) for
the adapter sequence. These APIs have no authentication and are intended for trusted local/demo use.

## Values and response handling

| Item | Values / behavior |
| --- | --- |
| Levels / vehicle and space types | `L1`, `L2`, `L3`, `L4` / `Standard`, `EV` |
| Space states | `Available`, `Occupied`, `Reserved`, `OutOfService` |
| Vehicle lifecycle | `Spawned`, `RequestingAssignment`, `DrivingToStall`, `Parking`, `Parked`, `Departing`, `DrivingToExit`, `Completed`, `Failed` |
| Simulation state | `Idle`, `Running`, `ArrivalPaused`, `Draining` |
| POST success | **202 means queued**, not executed. Response contains `command.command_id`; spawn also contains `request.request_id`. |
| Command status | `Pending` → `Delivered` → `Acknowledged` or `Failed`; can also become `Cancelled` |
| Spawn-request status | `AcceptedByBackend` → `ForwardedToUnity` → `SpawnedInUnity` or `Failed` |
| Parking confirmation | Read spawn request's `vehicle_id`, then vehicle's `assigned_space_id`. `SpawnedInUnity` does not mean parked; wait for lifecycle `Parked`. A vehicle snapshot can arrive after its acknowledgement. |
| Departure confirmation | Track command outcome, then Unity-reported vehicle/stall changes. Acknowledged does not mean exited; never free a stall optimistically. |
| Failure codes | `GarageFull`, `LevelFull`, `VehicleLimitReached`, `EntranceBlocked`, or null; use failure message if no code is supplied |
| Data freshness | `SeededBaseline` = initial layout; `UnityLive` = recent snapshot; `UnityLastKnown` = stale data. `/health` alone does not prove Unity is online. |
| HTTP errors | 404 = missing record; 422 = invalid fields (`detail`); 503 = Unity offline, nothing queued. Service errors contain `message`. |

**Refresh:** poll the visible data and integration status about once per second without overlapping refreshes. Stop command tracking at Acknowledged/Failed/Cancelled. Do not automatically retry command POSTs: another POST creates another command.

**Availability:** `by_space_type` contains physical counts, not available counts. For available EV/Standard counts, filter `/api/spaces?state=Available` and group by type/level.

**Restart:** state is in memory. If `backend_instance_id` changes, clear old command/request tracking; IDs may be reused. There is no authentication or driver-specific request ownership yet.

**Unity integration:** confirm the deployed Unity bridge consumes `auto_depart`, handles `DepartVehicle`, and sends `error_code`. Backend support is implemented; live behavior requires a matching bridge and joint testing. CCTV backend endpoints are implemented, but Unity publishing and dashboard consumption are not yet integrated. Dashboards must not send Unity snapshots, fetch commands for execution, or acknowledge commands.
