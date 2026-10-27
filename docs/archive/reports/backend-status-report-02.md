# Backend — Status Report #2

Historical report. Its test counts, in-memory storage description, and planned work reflect the report's original state.
See the [backend README](../../../Backend/README.md) and [dashboard API reference](../../frontend-api.md)
for current setup and contracts, or the [archive index](../README.md) for other historical material.

## 1. Project Description

The FastAPI backend provides garage data to the dashboards and queues parking requests, individual departure requests, and simulation commands for Unity. Unity still handles vehicle movement, parking, and simulation results.

## 2. Current State of the Project

My update: This week, I reorganized the FastAPI backend into an installable `src` package and updated the application and test imports. The existing API behavior stayed the same, and the backend still supports garage, parking-space, vehicle, spawn, simulation, and individual departure requests.

I also added the fields needed for Driver Dashboard parking requests. Spawn requests now include `auto_depart`, which defaults to `true` but can be set to `false` for driver-requested vehicles. The backend accepts structured failure codes in Unity acknowledgements: `GarageFull`, `LevelFull`, `VehicleLimitReached`, and `EntranceBlocked`.

The backend test suite is passing all 45 tests. I also tested the packaged backend through the `/health` and `/api/garage` endpoints and ran an HTTP smoke test for the departure command, spawn request fields, and failure codes. Backend data is still stored in memory, so it is lost if FastAPI is restarted.

## 3. Schedule Assessment

The backend packaging, Driver Dashboard request fields, and individual departure endpoint are implemented. Unity still needs to use `auto_depart`, handle `DepartVehicle`, and send the new failure codes before we can test the full flow in the live simulation.

## 4. Planned Activities

My plan for next week:

1. Coordinate with the Unity developer to use `auto_depart`, handle `DepartVehicle`, and send the agreed failure codes.
2. Test Driver Dashboard parking requests and individual departures with the live Unity simulation.
3. Start integrating the Unity CCTV system with FastAPI, beginning with one camera frame.
4. Plan PostgreSQL storage by outlining the schema and restart-recovery requirements.
