"""Unity <-> backend integration contracts (cs:15). Values reuse the exact enum strings Unity serializes."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from smart_parking_backend.models import enums
from smart_parking_backend.models import parking as parking_models
from smart_parking_backend.models import simulation as simulation_models
from smart_parking_backend.models import vehicles as vehicle_models


class UnityStateSnapshot(BaseModel):
    """
    One full report of live Unity state. The garage summary is derived by the backend from `spaces`, so there is a
    single source for the counts (no second, possibly inconsistent, set of numbers in the payload).
    """

    model_config = ConfigDict(extra="forbid")

    unity_session_id: str = Field(min_length=1, max_length=64, examples=["3f9c1a52b7d04e8a"])
    sequence: int = Field(
        ge=1,
        description="Strictly increasing within a session; <= latest accepted is stale.",
    )
    timestamp: datetime = Field(description="Unity-side UTC time of the report (informational).")
    simulation: simulation_models.SimulationReport
    spaces: list[parking_models.ParkingSpace] = Field(min_length=1)
    vehicles: list[vehicle_models.Vehicle] = Field(default_factory=list)

    @field_validator("spaces")
    @classmethod
    def _unique_spaces(cls, spaces: list[parking_models.ParkingSpace]) -> list[parking_models.ParkingSpace]:
        if len({s.space_id for s in spaces}) != len(spaces):
            raise ValueError("space_id values must be unique")
        return spaces

    @field_validator("vehicles")
    @classmethod
    def _unique_vehicles(cls, vehicles: list[vehicle_models.Vehicle]) -> list[vehicle_models.Vehicle]:
        if len({v.vehicle_id for v in vehicles}) != len(vehicles):
            raise ValueError("vehicle_id values must be unique")
        return vehicles


class SnapshotAck(BaseModel):
    accepted: bool
    message: str
    unity_session_id: str | None = None
    latest_sequence: int
    new_session: bool = False
    backend_instance_id: str = Field(description="Changes whenever the backend process restarts.")


class IntegrationStatus(BaseModel):
    connected: bool
    unity_session_id: str | None = None
    latest_sequence: int = 0
    last_update_at: datetime | None = Field(default=None, description="Backend receive time of the last snapshot.")
    seconds_since_last_update: float | None = None
    timeout_seconds: float
    data_source: enums.DataSource
    pending_commands: int = Field(description="Commands not yet acknowledged, cancelled or failed.")
    backend_instance_id: str


class CommandPayload(BaseModel):
    """Only the fields relevant to the command type are set."""

    model_config = ConfigDict(extra="forbid")

    scenario_mode: enums.ScenarioMode | None = None
    request_type: enums.VehicleRequestType | None = None
    preferred_level: enums.Level | None = None
    auto_depart: bool | None = None
    vehicle_id: str | None = Field(default=None, description="Target vehicle for a DepartVehicle command.")
    spawn_request_id: str | None = None


class BackendCommand(BaseModel):
    command_id: str = Field(examples=["CMD_000001"])
    command_type: enums.CommandType
    created_at: datetime
    payload: CommandPayload = Field(default_factory=CommandPayload)
    status: enums.CommandStatus = enums.CommandStatus.PENDING
    unity_session_id: str = Field(description="The Unity session this command was queued for.")
    delivery_count: int = 0
    delivered_at: datetime | None = None
    acknowledged_at: datetime | None = None
    result_message: str | None = None
    vehicle_id: str | None = Field(default=None, description="SpawnVehicle only: the vehicle Unity created.")
    error_code: enums.CommandErrorCode | None = None


class CommandBatch(BaseModel):
    backend_instance_id: str
    unity_session_id: str
    commands: list[BackendCommand]


class CommandAckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unity_session_id: str = Field(min_length=1, max_length=64)
    success: bool
    message: str = Field(default="", max_length=1000)
    vehicle_id: str | None = None
    error_code: enums.CommandErrorCode | None = None


class CommandAckResponse(BaseModel):
    success: bool
    message: str
    duplicate: bool = Field(description="True when the command was already finished; nothing was changed.")
    command: BackendCommand
