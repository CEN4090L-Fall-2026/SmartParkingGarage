# Dashboard API Quick Reference

**Base URL:** `http://127.0.0.1:8000` · **Interactive schemas:** `/docs`

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

**Unity handoff still required:** the inspected Unity bridge does not yet consume `auto_depart`, handle `DepartVehicle`, or send `error_code`. Backend support is implemented; live behavior requires those Unity changes and joint testing. CCTV endpoints are not implemented. Dashboards must not send Unity snapshots, fetch commands for execution, or acknowledge commands.
