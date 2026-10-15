from typing import Annotated

from fastapi import APIRouter, Depends, Response

from smart_parking_backend.api.deps import get_integration, get_service, tag_data_source
from smart_parking_backend.models import (
    Level,
    ParkingSpace,
    ParkingSpaceState,
    ParkingSpaceType,
)
from smart_parking_backend.services.garage_state import GarageStateService
from smart_parking_backend.services.integration import IntegrationService

router = APIRouter(prefix="/api/spaces", tags=["spaces"])


@router.get("", response_model=list[ParkingSpace])
def list_spaces(
    response: Response,
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
    level: Level | None = None,
    state: ParkingSpaceState | None = None,
    space_type: ParkingSpaceType | None = None,
) -> list[ParkingSpace]:
    tag_data_source(response, integration)
    return service.list_spaces(level=level, state=state, space_type=space_type)


@router.get("/{space_id}", response_model=ParkingSpace)
def get_space(
    space_id: str,
    response: Response,
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> ParkingSpace:
    tag_data_source(response, integration)
    return service.get_space(space_id)
