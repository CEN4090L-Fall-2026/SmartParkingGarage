from typing import Any

from pydantic import BaseModel, Field

from smart_parking_backend.models.enums import DataSource
from smart_parking_backend.models.integration import BackendCommand
from smart_parking_backend.models.vehicles import VehicleSpawnRequest


class CommandAccepted(BaseModel):
    """
    Returned (HTTP 202) when a command has been QUEUED for Unity. It does not mean Unity has executed it: poll
    GET /api/integration/commands/{command_id} or the simulation status for the outcome.
    """

    success: bool = True
    message: str
    current_state: str | None = Field(
        description="Last Unity-reported simulation state, before this command."
    )
    command: BackendCommand
    request: VehicleSpawnRequest | None = Field(
        default=None, description="SpawnVehicle only."
    )


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    current_state: str | None = None
    data_source: DataSource | None = None
    detail: Any | None = None
