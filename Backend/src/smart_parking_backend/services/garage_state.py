"""
Backend projection of the garage: the seeded baseline until a Unity snapshot replaces it (cs:15).

This service owns NO simulation logic. Unity is authoritative for live state; the backend only stores what Unity
reports (plus its own spawn-request records) and serves it to clients.
"""

import threading

from smart_parking_backend.models import enums
from smart_parking_backend.models import parking as parking_models
from smart_parking_backend.models import simulation as simulation_models
from smart_parking_backend.models import vehicles as vehicle_models
from smart_parking_backend.services import seed_data


class NotFoundError(Exception):
    """Unknown space, vehicle or request (HTTP 404)."""


def _seed_spaces() -> dict[str, parking_models.ParkingSpace]:
    ev, oos = set(seed_data.EV_SPACE_IDS), set(seed_data.OUT_OF_SERVICE_SPACE_IDS)
    spaces: dict[str, parking_models.ParkingSpace] = {}
    for level, numbers in seed_data.SPACE_NUMBERS_BY_LEVEL.items():
        for number in numbers:
            space_id = f"{level}_SPACE_{number:03d}"
            spaces[space_id] = parking_models.ParkingSpace(
                space_id=space_id,
                level=enums.Level(level),
                state=enums.ParkingSpaceState.OUT_OF_SERVICE if space_id in oos else enums.ParkingSpaceState.AVAILABLE,
                space_type=enums.ParkingSpaceType.EV if space_id in ev else enums.ParkingSpaceType.STANDARD,
            )
    return spaces


def _idle_report() -> simulation_models.SimulationReport:
    return simulation_models.SimulationReport(
        state=enums.SimulationState.IDLE,
        scenario_mode=enums.ScenarioMode.NORMAL,
        elapsed_seconds=0,
        total_spawned=0,
        total_completed=0,
        total_failed=0,
        active_vehicles=0,
        parked_vehicles=0,
    )


class GarageStateService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._spaces: dict[str, parking_models.ParkingSpace] = _seed_spaces()
        self._vehicles: dict[str, vehicle_models.Vehicle] = {}
        self._report: simulation_models.SimulationReport = _idle_report()
        self._spawn_requests: dict[str, vehicle_models.VehicleSpawnRequest] = {}
        self._request_sequence = 0

    # ---- projection updates (called by IntegrationService) ---------------------------------------------------
    def apply_live(
        self,
        report: simulation_models.SimulationReport,
        spaces: list[parking_models.ParkingSpace],
        vehicles: list[vehicle_models.Vehicle],
    ) -> None:
        """Replace the whole projection with what Unity reported. There is deliberately no merge with the seed."""
        with self._lock:
            self._spaces = {s.space_id: s.model_copy() for s in spaces}
            self._vehicles = {v.vehicle_id: v.model_copy() for v in vehicles}
            self._report = report.model_copy()

    # ---- queries ---------------------------------------------------------------------------------------------
    @staticmethod
    def _counts(spaces: list[parking_models.ParkingSpace]) -> dict:
        def n(state: enums.ParkingSpaceState) -> int:
            return sum(1 for s in spaces if s.state == state)

        oos = n(enums.ParkingSpaceState.OUT_OF_SERVICE)
        return {
            "total": len(spaces),
            "operational": len(spaces) - oos,
            "available": n(enums.ParkingSpaceState.AVAILABLE),
            "occupied": n(enums.ParkingSpaceState.OCCUPIED),
            "reserved": n(enums.ParkingSpaceState.RESERVED),
            "out_of_service": oos,
        }

    def garage_summary(
        self, data_source: enums.DataSource = enums.DataSource.SEEDED_BASELINE
    ) -> parking_models.GarageSummary:
        with self._lock:
            spaces = list(self._spaces.values())
            total = parking_models.StateCounts(**self._counts(spaces))
            levels = [
                parking_models.LevelSummary(level=level, **self._counts([s for s in spaces if s.level == level]))
                for level in enums.Level
            ]
            by_type = {t.value: sum(1 for s in spaces if s.space_type == t) for t in enums.ParkingSpaceType}
            return parking_models.GarageSummary(
                total_physical_spaces=total.total,
                operational_spaces=total.operational,
                available=total.available,
                occupied=total.occupied,
                reserved=total.reserved,
                out_of_service=total.out_of_service,
                levels=levels,
                by_space_type=by_type,
                data_source=data_source,
            )

    def list_spaces(
        self,
        level: enums.Level | None = None,
        state: enums.ParkingSpaceState | None = None,
        space_type: enums.ParkingSpaceType | None = None,
    ) -> list[parking_models.ParkingSpace]:
        with self._lock:
            return [
                s.model_copy()
                for s in self._spaces.values()
                if (level is None or s.level == level)
                and (state is None or s.state == state)
                and (space_type is None or s.space_type == space_type)
            ]

    def get_space(self, space_id: str) -> parking_models.ParkingSpace:
        with self._lock:
            space = self._spaces.get(space_id)
            if space is None:
                raise NotFoundError(f"Parking space '{space_id}' does not exist.")
            return space.model_copy()

    def list_vehicles(self, lifecycle_state: enums.VehicleLifecycleState | None = None) -> list[vehicle_models.Vehicle]:
        with self._lock:
            return [
                v.model_copy()
                for v in self._vehicles.values()
                if lifecycle_state is None or v.lifecycle_state == lifecycle_state
            ]

    def get_vehicle(self, vehicle_id: str) -> vehicle_models.Vehicle:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            if vehicle is None:
                raise NotFoundError(f"Vehicle '{vehicle_id}' does not exist in the backend.")
            return vehicle.model_copy()

    def simulation_status(
        self, data_source: enums.DataSource = enums.DataSource.SEEDED_BASELINE
    ) -> simulation_models.SimulationStatus:
        with self._lock:
            counts = self._counts(list(self._spaces.values()))
            r = self._report
            open_states = (
                enums.SpawnRequestStatus.ACCEPTED_BY_BACKEND,
                enums.SpawnRequestStatus.FORWARDED_TO_UNITY,
            )
            return simulation_models.SimulationStatus(
                state=r.state,
                scenario_mode=r.scenario_mode,
                elapsed_seconds=r.elapsed_seconds,
                total_spawned=r.total_spawned,
                total_completed=r.total_completed,
                total_failed=r.total_failed,
                active_vehicles=r.active_vehicles,
                parked_vehicles=r.parked_vehicles,
                available_spaces=counts["available"],
                occupied_spaces=counts["occupied"],
                reserved_spaces=counts["reserved"],
                out_of_service_spaces=counts["out_of_service"],
                pending_spawn_requests=sum(1 for q in self._spawn_requests.values() if q.status in open_states),
                data_source=data_source,
            )

    def last_known_state(self) -> str:
        with self._lock:
            return self._report.state.value

    # ---- spawn-request records -------------------------------------------------------------------------------
    def create_spawn_request(
        self,
        request_type: enums.VehicleRequestType,
        preferred_level: enums.Level | None,
        command_id: str | None = None,
        *,
        auto_depart: bool = True,
    ) -> vehicle_models.VehicleSpawnRequest:
        with self._lock:
            self._request_sequence += 1
            request = vehicle_models.VehicleSpawnRequest(
                request_id=f"REQ_{self._request_sequence:04d}",
                request_type=request_type,
                preferred_level=preferred_level,
                auto_depart=auto_depart,
                command_id=command_id,
            )
            self._spawn_requests[request.request_id] = request
            return request.model_copy()

    def update_spawn_request(self, request_id: str, **fields) -> None:
        with self._lock:
            request = self._spawn_requests.get(request_id)
            if request is not None:
                self._spawn_requests[request_id] = request.model_copy(update=fields)

    def list_spawn_requests(self) -> list[vehicle_models.VehicleSpawnRequest]:
        with self._lock:
            return [r.model_copy() for r in self._spawn_requests.values()]

    def get_spawn_request(self, request_id: str) -> vehicle_models.VehicleSpawnRequest:
        with self._lock:
            request = self._spawn_requests.get(request_id)
            if request is None:
                raise NotFoundError(f"Spawn request '{request_id}' does not exist.")
            return request.model_copy()
