from pydantic import BaseModel, Field

from smart_parking_backend.models import enums


class ParkingSpace(BaseModel):
    space_id: str = Field(examples=["L1_SPACE_001"])
    level: enums.Level
    state: enums.ParkingSpaceState
    space_type: enums.ParkingSpaceType
    assigned_vehicle_id: str | None = Field(default=None, examples=["VEH_0001"])
    reserved_by: str | None = Field(default=None, examples=["SIM_VEH_0001"])


class StateCounts(BaseModel):
    total: int
    operational: int
    available: int
    occupied: int
    reserved: int
    out_of_service: int


class LevelSummary(StateCounts):
    level: enums.Level


class GarageSummary(BaseModel):
    total_physical_spaces: int
    operational_spaces: int
    available: int
    occupied: int
    reserved: int
    out_of_service: int
    levels: list[LevelSummary]
    by_space_type: dict[str, int] = Field(description="Physical stall count per space type.")
    data_source: enums.DataSource = enums.DataSource.SEEDED_BASELINE
