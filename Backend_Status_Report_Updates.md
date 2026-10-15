1. Project Description

The FastAPI backend provides garage data to the dashboards and handles parking requests and simulation commands through Unity. Unity still handles vehicle movement, parking, and the simulation results.

2. Current State of the Project

My update: This week, I reorganized the FastAPI backend into an installable `src` package and updated the application and test imports. The existing API behavior stayed the same, and the backend still supports garage, parking-space, vehicle, spawn, and simulation requests.

I also added the fields needed for Driver Dashboard parking requests. Spawn requests now include `auto_depart`, which defaults to `true` but can be set to `false` for driver-requested vehicles. Unity acknowledgements can also include the failure codes `GarageFull`, `LevelFull`, `VehicleLimitReached`, and `EntranceBlocked`.

The backend test suite is passing all 41 tests. I also tested the packaged backend separately through the `/health` and `/api/garage` endpoints. Backend data is still stored in memory, so it is lost if FastAPI is restarted.

3. Schedule Assessment

The backend packaging and Driver Dashboard request fields are finished. The Unity side still needs to use `auto_depart` and send the new failure codes during live testing. Individual vehicle departure and CCTV integration are still upcoming.

4. Planned Activities

My plan for next week:

1. Coordinate with the Unity developer to connect `auto_depart` to Unity's existing automatic-departure behavior.
2. Coordinate the `DepartVehicle` command and individual departure endpoint.
3. Test Driver Dashboard parking requests and failure messages with the live Unity simulation.
4. Start integrating the Unity CCTV system with FastAPI, beginning with one camera frame.
5. Begin to plan for postgres sql storage.
