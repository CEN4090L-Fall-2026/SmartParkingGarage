from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from smart_parking_backend.api import deps
from smart_parking_backend.models import commands as command_models
from smart_parking_backend.models import enums
from smart_parking_backend.models import integration as integration_models
from smart_parking_backend.models import responses as response_models
from smart_parking_backend.models import vehicles as vehicle_models
from smart_parking_backend.services import garage_state
from smart_parking_backend.services import integration as integration_service

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.get("", response_model=list[vehicle_models.Vehicle])
def list_vehicles(
    response: Response,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
    lifecycle_state: enums.VehicleLifecycleState | None = None,
) -> list[vehicle_models.Vehicle]:
    """Active simulation vehicles as last reported by Unity (empty until Unity has reported)."""
    deps.tag_data_source(response, integration)
    return service.list_vehicles(lifecycle_state)


@router.post(
    "/spawn",
    response_model=response_models.CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={503: {"description": "Unity is not connected."}},
)
def request_spawn(
    command: command_models.SpawnVehicleCommand,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> response_models.CommandAccepted:
    """
    Queue a SpawnVehicle command for Unity and record a spawn request. 202 means QUEUED, not spawned: the request
    reaches SpawnedInUnity (with a vehicle_id) only after Unity acknowledges success. 503 when Unity is offline.
    """
    state = service.last_known_state()
    queued, request = integration.enqueue_spawn(
        integration_models.CommandPayload(
            request_type=command.request_type,
            preferred_level=command.preferred_level,
            auto_depart=command.auto_depart,
        )
    )
    return response_models.CommandAccepted(
        message="Spawn queued for Unity. It has not been executed yet.",
        current_state=state,
        command=queued,
        request=request,
    )


# Registered before /{vehicle_id} so "spawn-requests" is never parsed as a vehicle id.
@router.get("/spawn-requests", response_model=list[vehicle_models.VehicleSpawnRequest])
def list_spawn_requests(
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
) -> list[vehicle_models.VehicleSpawnRequest]:
    return service.list_spawn_requests()


@router.get("/spawn-requests/{request_id}", response_model=vehicle_models.VehicleSpawnRequest)
def get_spawn_request(
    request_id: str,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
) -> vehicle_models.VehicleSpawnRequest:
    return service.get_spawn_request(request_id)


@router.post(
    "/{vehicle_id}/depart",
    response_model=response_models.CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={503: {"description": "Unity is not connected."}},
)
def request_departure(
    vehicle_id: str,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> response_models.CommandAccepted:
    """Queue a departure request for Unity; Unity validates and performs the departure."""
    state = service.last_known_state()
    queued = integration.enqueue(
        enums.CommandType.DEPART_VEHICLE, integration_models.CommandPayload(vehicle_id=vehicle_id)
    )
    return response_models.CommandAccepted(
        message="Departure queued for Unity. It has not been executed yet.",
        current_state=state,
        command=queued,
    )


@router.get("/{vehicle_id}", response_model=vehicle_models.Vehicle)
def get_vehicle(
    vehicle_id: str,
    response: Response,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> vehicle_models.Vehicle:
    deps.tag_data_source(response, integration)
    return service.get_vehicle(vehicle_id)
