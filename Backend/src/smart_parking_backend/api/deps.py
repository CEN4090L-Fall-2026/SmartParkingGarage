from fastapi import Request, Response

from smart_parking_backend.services import cctv, garage_state
from smart_parking_backend.services import integration as integration_service


def get_service(request: Request) -> garage_state.GarageStateService:
    """The one GarageStateService (projection store) owned by the app."""
    return request.app.state.garage_service


def get_integration(request: Request) -> integration_service.IntegrationService:
    return request.app.state.integration_service


def get_cctv(request: Request) -> cctv.CCTVService:
    return request.app.state.cctv_service


def tag_data_source(response: Response, integration: integration_service.IntegrationService) -> None:
    """Every query states where its data came from: SeededBaseline, UnityLive or UnityLastKnown."""
    response.headers["X-Data-Source"] = integration.data_source().value
