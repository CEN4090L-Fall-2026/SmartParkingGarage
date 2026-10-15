from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from smart_parking_backend.api.deps import get_integration, get_service, tag_data_source
from smart_parking_backend.models import (
    CommandAccepted,
    CommandPayload,
    SpawnVehicleCommand,
    Vehicle,
    VehicleLifecycleState,
    VehicleSpawnRequest,
)
from smart_parking_backend.services.garage_state import GarageStateService
from smart_parking_backend.services.integration import IntegrationService

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.get("", response_model=list[Vehicle])
def list_vehicles(
    response: Response,
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
    lifecycle_state: VehicleLifecycleState | None = None,
) -> list[Vehicle]:
    """Active simulation vehicles as last reported by Unity (empty until Unity has reported)."""
    tag_data_source(response, integration)
    return service.list_vehicles(lifecycle_state)


@router.post(
    "/spawn",
    response_model=CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={503: {"description": "Unity is not connected."}},
)
def request_spawn(
    command: SpawnVehicleCommand,
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> CommandAccepted:
    """
    Queue a SpawnVehicle command for Unity and record a spawn request. 202 means QUEUED, not spawned: the request
    reaches SpawnedInUnity (with a vehicle_id) only after Unity acknowledges success. 503 when Unity is offline.
    """
    state = service.last_known_state()
    queued, request = integration.enqueue_spawn(
        CommandPayload(
            request_type=command.request_type,
            preferred_level=command.preferred_level,
            auto_depart=command.auto_depart,
        )
    )
    return CommandAccepted(
        message="Spawn queued for Unity. It has not been executed yet.",
        current_state=state,
        command=queued,
        request=request,
    )


# Registered before /{vehicle_id} so "spawn-requests" is never parsed as a vehicle id.
@router.get("/spawn-requests", response_model=list[VehicleSpawnRequest])
def list_spawn_requests(
    service: Annotated[GarageStateService, Depends(get_service)],
) -> list[VehicleSpawnRequest]:
    return service.list_spawn_requests()


@router.get("/spawn-requests/{request_id}", response_model=VehicleSpawnRequest)
def get_spawn_request(
    request_id: str,
    service: Annotated[GarageStateService, Depends(get_service)],
) -> VehicleSpawnRequest:
    return service.get_spawn_request(request_id)


@router.get("/{vehicle_id}", response_model=Vehicle)
def get_vehicle(
    vehicle_id: str,
    response: Response,
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> Vehicle:
    tag_data_source(response, integration)
    return service.get_vehicle(vehicle_id)
