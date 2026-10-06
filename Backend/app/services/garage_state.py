"""
Backend projection of the garage: the seeded baseline until a Unity snapshot replaces it (cs:15).

This service owns NO simulation logic. Unity is authoritative for live state; the backend only stores what Unity
reports (plus its own spawn-request records) and serves it to clients.
"""

import threading

from ..models import (
    DataSource,
    GarageSummary,
    Level,
    LevelSummary,
    ParkingSpace,
    ParkingSpaceState,
    ParkingSpaceType,
    ScenarioMode,
    SimulationReport,
    SimulationState,
    SimulationStatus,
    SpawnRequestStatus,
    StateCounts,
    Vehicle,
    VehicleLifecycleState,
    VehicleRequestType,
    VehicleSpawnRequest,
)
from .seed_data import EV_SPACE_IDS, OUT_OF_SERVICE_SPACE_IDS, SPACE_NUMBERS_BY_LEVEL


class NotFoundError(Exception):
    """Unknown space, vehicle or request (HTTP 404)."""


def _seed_spaces() -> dict[str, ParkingSpace]:
    ev, oos = set(EV_SPACE_IDS), set(OUT_OF_SERVICE_SPACE_IDS)
    spaces: dict[str, ParkingSpace] = {}
    for level, numbers in SPACE_NUMBERS_BY_LEVEL.items():
        for number in numbers:
            space_id = f"{level}_SPACE_{number:03d}"
            spaces[space_id] = ParkingSpace(
                space_id=space_id,
                level=Level(level),
                state=ParkingSpaceState.OUT_OF_SERVICE
                if space_id in oos
                else ParkingSpaceState.AVAILABLE,
                space_type=ParkingSpaceType.EV
                if space_id in ev
                else ParkingSpaceType.STANDARD,
            )
    return spaces


def _idle_report() -> SimulationReport:
    return SimulationReport(
        state=SimulationState.IDLE,
        scenario_mode=ScenarioMode.NORMAL,
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
        self._spaces: dict[str, ParkingSpace] = _seed_spaces()
        self._vehicles: dict[str, Vehicle] = {}
        self._report: SimulationReport = _idle_report()
        self._spawn_requests: dict[str, VehicleSpawnRequest] = {}
        self._request_sequence = 0

    # ---- projection updates (called by IntegrationService) ---------------------------------------------------
    def apply_live(
        self,
        report: SimulationReport,
        spaces: list[ParkingSpace],
        vehicles: list[Vehicle],
    ) -> None:
        """Replace the whole projection with what Unity reported. There is deliberately no merge with the seed."""
        with self._lock:
            self._spaces = {s.space_id: s.model_copy() for s in spaces}
            self._vehicles = {v.vehicle_id: v.model_copy() for v in vehicles}
            self._report = report.model_copy()

    # ---- queries ---------------------------------------------------------------------------------------------
    @staticmethod
    def _counts(spaces: list[ParkingSpace]) -> dict:
        def n(state: ParkingSpaceState) -> int:
            return sum(1 for s in spaces if s.state == state)

        oos = n(ParkingSpaceState.OUT_OF_SERVICE)
        return {
            "total": len(spaces),
            "operational": len(spaces) - oos,
            "available": n(ParkingSpaceState.AVAILABLE),
            "occupied": n(ParkingSpaceState.OCCUPIED),
            "reserved": n(ParkingSpaceState.RESERVED),
            "out_of_service": oos,
        }

    def garage_summary(
        self, data_source: DataSource = DataSource.SEEDED_BASELINE
    ) -> GarageSummary:
        with self._lock:
            spaces = list(self._spaces.values())
            total = StateCounts(**self._counts(spaces))
            levels = [
                LevelSummary(
                    level=level, **self._counts([s for s in spaces if s.level == level])
                )
                for level in Level
            ]
            by_type = {
                t.value: sum(1 for s in spaces if s.space_type == t)
                for t in ParkingSpaceType
            }
            return GarageSummary(
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
        level: Level | None = None,
        state: ParkingSpaceState | None = None,
        space_type: ParkingSpaceType | None = None,
    ) -> list[ParkingSpace]:
        with self._lock:
            return [
                s.model_copy()
                for s in self._spaces.values()
                if (level is None or s.level == level)
                and (state is None or s.state == state)
                and (space_type is None or s.space_type == space_type)
            ]

    def get_space(self, space_id: str) -> ParkingSpace:
        with self._lock:
            space = self._spaces.get(space_id)
            if space is None:
                raise NotFoundError(f"Parking space '{space_id}' does not exist.")
            return space.model_copy()

    def list_vehicles(
        self, lifecycle_state: VehicleLifecycleState | None = None
    ) -> list[Vehicle]:
        with self._lock:
            return [
                v.model_copy()
                for v in self._vehicles.values()
                if lifecycle_state is None or v.lifecycle_state == lifecycle_state
            ]

    def get_vehicle(self, vehicle_id: str) -> Vehicle:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            if vehicle is None:
                raise NotFoundError(
                    f"Vehicle '{vehicle_id}' does not exist in the backend."
                )
            return vehicle.model_copy()

    def simulation_status(
        self, data_source: DataSource = DataSource.SEEDED_BASELINE
    ) -> SimulationStatus:
        with self._lock:
            counts = self._counts(list(self._spaces.values()))
            r = self._report
            open_states = (
                SpawnRequestStatus.ACCEPTED_BY_BACKEND,
                SpawnRequestStatus.FORWARDED_TO_UNITY,
            )
            return SimulationStatus(
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
                pending_spawn_requests=sum(
                    1 for q in self._spawn_requests.values() if q.status in open_states
                ),
                data_source=data_source,
            )

    def last_known_state(self) -> str:
        with self._lock:
            return self._report.state.value

    # ---- spawn-request records -------------------------------------------------------------------------------
    def create_spawn_request(
        self,
        request_type: VehicleRequestType,
        preferred_level: Level | None,
        command_id: str | None = None,
    ) -> VehicleSpawnRequest:
        with self._lock:
            self._request_sequence += 1
            request = VehicleSpawnRequest(
                request_id=f"REQ_{self._request_sequence:04d}",
                request_type=request_type,
                preferred_level=preferred_level,
                command_id=command_id,
            )
            self._spawn_requests[request.request_id] = request
            return request.model_copy()

    def update_spawn_request(self, request_id: str, **fields) -> None:
        with self._lock:
            request = self._spawn_requests.get(request_id)
            if request is not None:
                self._spawn_requests[request_id] = request.model_copy(update=fields)

    def list_spawn_requests(self) -> list[VehicleSpawnRequest]:
        with self._lock:
            return [r.model_copy() for r in self._spawn_requests.values()]

    def get_spawn_request(self, request_id: str) -> VehicleSpawnRequest:
        with self._lock:
            request = self._spawn_requests.get(request_id)
            if request is None:
                raise NotFoundError(f"Spawn request '{request_id}' does not exist.")
            return request.model_copy()
