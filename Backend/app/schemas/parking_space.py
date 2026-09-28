from pydantic import BaseModel, ConfigDict, Field

from ..domain.states import ParkingSpaceState, ParkingSpaceType


class ParkingSpaceSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    space_id: str = Field(alias="SpaceId")
    level: int = Field(alias="Level")
    parking_space_type: ParkingSpaceType = Field(alias="Type")
    is_type_resolved: bool = Field(alias="IsTypeResolved")
    state: ParkingSpaceState = Field(alias="State")


class ParkingSpaceStateChangeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    state: ParkingSpaceState = Field(alias="State")


class ParkingSpaceSnapshotCollection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    spaces: list[ParkingSpaceSnapshot] = Field(alias="Spaces")
