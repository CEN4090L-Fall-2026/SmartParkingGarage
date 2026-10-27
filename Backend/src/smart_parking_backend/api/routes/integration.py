from typing import Annotated

from fastapi import APIRouter, Depends, Query

from smart_parking_backend.api import deps
from smart_parking_backend.models import integration as integration_models
from smart_parking_backend.services import integration as integration_service

router = APIRouter(prefix="/api/integration", tags=["integration"])


@router.post(
    "/state",
    response_model=integration_models.SnapshotAck,
    responses={
        409: {"description": "Stale sequence."},
        422: {"description": "Malformed snapshot."},
    },
)
def post_state(
    snapshot: integration_models.UnityStateSnapshot,
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> integration_models.SnapshotAck:
    """Unity publishes live state. A stale sequence is rejected with 409 and changes nothing."""
    return integration.accept_snapshot(snapshot)


@router.get("/status", response_model=integration_models.IntegrationStatus)
def get_status(
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> integration_models.IntegrationStatus:
    return integration.status()


@router.get(
    "/commands",
    response_model=integration_models.CommandBatch,
    responses={409: {"description": "Not the current session."}},
)
def get_commands(
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
    unity_session_id: Annotated[str, Query(min_length=1, max_length=64)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> integration_models.CommandBatch:
    """Pending commands for this Unity session, oldest first (also redelivers long-unacknowledged ones)."""
    commands = integration.fetch_commands(unity_session_id, limit)
    return integration_models.CommandBatch(
        backend_instance_id=integration.backend_instance_id,
        unity_session_id=unity_session_id,
        commands=commands,
    )


@router.get("/commands/{command_id}", response_model=integration_models.BackendCommand)
def get_command(
    command_id: str,
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> integration_models.BackendCommand:
    """Command record; OutcomeUnknown is terminal delivery without confirmed execution."""
    return integration.get_command(command_id)


@router.post("/commands/{command_id}/ack", response_model=integration_models.CommandAckResponse)
def ack_command(
    command_id: str,
    ack: integration_models.CommandAckRequest,
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> integration_models.CommandAckResponse:
    """Unity reports a command result. Idempotent: acknowledging a finished command changes nothing."""
    command, duplicate = integration.acknowledge(command_id, ack)
    message = "Command was already finished; acknowledgement ignored." if duplicate else "Acknowledgement recorded."
    return integration_models.CommandAckResponse(success=True, message=message, duplicate=duplicate, command=command)
