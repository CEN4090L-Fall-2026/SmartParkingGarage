from pydantic import BaseModel, Field

from smart_parking_backend.models import enums


class Vehicle(BaseModel):
    """A vehicle that exists in the simulation. Only Unity (from cs:15) creates these; the backend has none yet."""

    vehicle_id: str = Field(examples=["VEH_0001"])
    requester_id: str = Field(examples=["SIM_VEH_0001"])
    request_type: enums.VehicleRequestType
    lifecycle_state: enums.VehicleLifecycleState
    assigned_space_id: str | None = None
    preferred_level: enums.Level | None = None
    failure_reason: str | None = None


class VehicleSpawnRequest(BaseModel):
    """
    A backend-side record of an intent to spawn a vehicle, tied to the SpawnVehicle command that carries it.

    AcceptedByBackend means ONLY that the backend stored it and queued the command. `forwarded_to_unity` turns true
    when Unity fetches the command, and `spawned_in_unity` (with `vehicle_id`) only when Unity acknowledges success.
    OutcomeUnknown means delivery occurred but execution was not confirmed before restart/session end. A false
    `spawned_in_unity` means no confirmed successful spawn, not proof that no vehicle exists.
    """

    request_id: str = Field(examples=["REQ_0001"])
    request_type: enums.VehicleRequestType
    preferred_level: enums.Level | None = None
    auto_depart: bool = True
    status: enums.SpawnRequestStatus = enums.SpawnRequestStatus.ACCEPTED_BY_BACKEND
    forwarded_to_unity: bool = False
    spawned_in_unity: bool = False
    vehicle_id: str | None = Field(default=None, description="Set only once Unity has spawned the vehicle.")
    command_id: str | None = Field(default=None, examples=["CMD_000001"])
    failure_reason: str | None = None
    error_code: enums.CommandErrorCode | None = None
