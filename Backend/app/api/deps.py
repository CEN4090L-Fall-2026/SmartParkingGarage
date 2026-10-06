from fastapi import Request, Response

from ..services.garage_state import GarageStateService
from ..services.integration import IntegrationService


def get_service(request: Request) -> GarageStateService:
    """The one GarageStateService (projection store) owned by the app."""
    return request.app.state.garage_service


def get_integration(request: Request) -> IntegrationService:
    return request.app.state.integration_service


def tag_data_source(response: Response, integration: IntegrationService) -> None:
    """Every query states where its data came from: SeededBaseline, UnityLive or UnityLastKnown."""
    response.headers["X-Data-Source"] = integration.data_source().value
