from pydantic import BaseModel, Field

from smart_parking_backend.models import enums


class SimulationReport(BaseModel):
    """The SimulationManager figures Unity reports, exactly as it computes them."""

    state: enums.SimulationState
    scenario_mode: enums.ScenarioMode
    elapsed_seconds: float = Field(ge=0)
    total_spawned: int = Field(ge=0)
    total_completed: int = Field(ge=0)
    total_failed: int = Field(ge=0)
    active_vehicles: int = Field(ge=0)
    parked_vehicles: int = Field(ge=0)


class SimulationStatus(BaseModel):
    state: enums.SimulationState
    scenario_mode: enums.ScenarioMode
    elapsed_seconds: float = Field(ge=0)
    total_spawned: int = Field(ge=0)
    total_completed: int = Field(ge=0)
    total_failed: int = Field(ge=0)
    active_vehicles: int = Field(ge=0)
    parked_vehicles: int = Field(ge=0)
    available_spaces: int
    occupied_spaces: int
    reserved_spaces: int
    out_of_service_spaces: int
    pending_spawn_requests: int = Field(description="Spawn requests not yet executed by Unity.")
    data_source: enums.DataSource = enums.DataSource.SEEDED_BASELINE
