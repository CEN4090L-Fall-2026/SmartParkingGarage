from pydantic import BaseModel, ConfigDict, Field

from ..domain.states import ParkingSpaceState, ParkingSpaceType


class ParkingAssignmentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    requester_id: str = Field(alias="RequesterId")
    preferred_level: int | None = Field(default=None, alias="PreferredLevel")
    required_type: ParkingSpaceType | None = Field(
        default=None,
        alias="RequiredType",
    )


class ParkingAssignmentSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    requester_id: str = Field(alias="RequesterId")
    space_id: str = Field(alias="SpaceId")
    level: int = Field(alias="Level")
    parking_space_type: ParkingSpaceType = Field(alias="Type")
    is_type_resolved: bool = Field(alias="IsTypeResolved")


class ParkingAssignmentRelease(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    requester_id: str = Field(alias="RequesterId")
    space_id: str = Field(alias="SpaceId")
    state: ParkingSpaceState = Field(alias="State")
