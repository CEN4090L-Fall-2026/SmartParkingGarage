from typing import Annotated

from fastapi import APIRouter, Depends, Response

from smart_parking_backend.api import deps
from smart_parking_backend.models import parking as parking_models
from smart_parking_backend.services import garage_state
from smart_parking_backend.services import integration as integration_service

router = APIRouter(prefix="/api/garage", tags=["garage"])


@router.get("", response_model=parking_models.GarageSummary)
def get_garage(
    response: Response,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> parking_models.GarageSummary:
    deps.tag_data_source(response, integration)
    return service.garage_summary(integration.data_source())
