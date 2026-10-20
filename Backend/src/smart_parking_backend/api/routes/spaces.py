from typing import Annotated

from fastapi import APIRouter, Depends, Response

from smart_parking_backend.api import deps
from smart_parking_backend.models import enums
from smart_parking_backend.models import parking as parking_models
from smart_parking_backend.services import garage_state
from smart_parking_backend.services import integration as integration_service

router = APIRouter(prefix="/api/spaces", tags=["spaces"])


@router.get("", response_model=list[parking_models.ParkingSpace])
def list_spaces(
    response: Response,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
    level: enums.Level | None = None,
    state: enums.ParkingSpaceState | None = None,
    space_type: enums.ParkingSpaceType | None = None,
) -> list[parking_models.ParkingSpace]:
    deps.tag_data_source(response, integration)
    return service.list_spaces(level=level, state=state, space_type=space_type)


@router.get("/{space_id}", response_model=parking_models.ParkingSpace)
def get_space(
    space_id: str,
    response: Response,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> parking_models.ParkingSpace:
    deps.tag_data_source(response, integration)
    return service.get_space(space_id)
