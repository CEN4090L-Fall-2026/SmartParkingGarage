from typing import Annotated

from fastapi import APIRouter, Depends, Response

from smart_parking_backend.api.deps import get_integration, get_service, tag_data_source
from smart_parking_backend.models import GarageSummary
from smart_parking_backend.services.garage_state import GarageStateService
from smart_parking_backend.services.integration import IntegrationService

router = APIRouter(prefix="/api/garage", tags=["garage"])


@router.get("", response_model=GarageSummary)
def get_garage(
    response: Response,
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> GarageSummary:
    tag_data_source(response, integration)
    return service.garage_summary(integration.data_source())
