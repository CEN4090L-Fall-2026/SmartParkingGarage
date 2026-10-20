from typing import Any

from pydantic import BaseModel, Field

from smart_parking_backend.models import enums
from smart_parking_backend.models import integration as integration_models
from smart_parking_backend.models import vehicles as vehicle_models


class CommandAccepted(BaseModel):
    """
    Returned (HTTP 202) when a command has been QUEUED for Unity. It does not mean Unity has executed it: poll
    GET /api/integration/commands/{command_id} or the simulation status for the outcome.
    """

    success: bool = True
    message: str
    current_state: str | None = Field(description="Last Unity-reported simulation state, before this command.")
    command: integration_models.BackendCommand
    request: vehicle_models.VehicleSpawnRequest | None = Field(default=None, description="SpawnVehicle only.")


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    current_state: str | None = None
    data_source: enums.DataSource | None = None
    detail: Any | None = None
