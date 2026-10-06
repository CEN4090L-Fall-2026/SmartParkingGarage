from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...models import (
    BackendCommand,
    CommandAckRequest,
    CommandAckResponse,
    CommandBatch,
    IntegrationStatus,
    SnapshotAck,
    UnityStateSnapshot,
)
from ...services.integration import IntegrationService
from ..deps import get_integration

router = APIRouter(prefix="/api/integration", tags=["integration"])


@router.post(
    "/state",
    response_model=SnapshotAck,
    responses={
        409: {"description": "Stale sequence."},
        422: {"description": "Malformed snapshot."},
    },
)
def post_state(
    snapshot: UnityStateSnapshot,
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> SnapshotAck:
    """Unity publishes live state. A stale sequence is rejected with 409 and changes nothing."""
    return integration.accept_snapshot(snapshot)


@router.get("/status", response_model=IntegrationStatus)
def get_status(
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> IntegrationStatus:
    return integration.status()


@router.get(
    "/commands",
    response_model=CommandBatch,
    responses={409: {"description": "Not the current session."}},
)
def get_commands(
    integration: Annotated[IntegrationService, Depends(get_integration)],
    unity_session_id: Annotated[str, Query(min_length=1, max_length=64)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> CommandBatch:
    """Pending commands for this Unity session, oldest first (also redelivers long-unacknowledged ones)."""
    commands = integration.fetch_commands(unity_session_id, limit)
    return CommandBatch(
        backend_instance_id=integration.backend_instance_id,
        unity_session_id=unity_session_id,
        commands=commands,
    )


@router.get("/commands/{command_id}", response_model=BackendCommand)
def get_command(
    command_id: str,
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> BackendCommand:
    """Outcome of one queued command (Pending, Delivered, Acknowledged, Failed or Cancelled)."""
    return integration.get_command(command_id)


@router.post("/commands/{command_id}/ack", response_model=CommandAckResponse)
def ack_command(
    command_id: str,
    ack: CommandAckRequest,
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> CommandAckResponse:
    """Unity reports a command result. Idempotent: acknowledging a finished command changes nothing."""
    command, duplicate = integration.acknowledge(command_id, ack)
    message = (
        "Command was already finished; acknowledgement ignored."
        if duplicate
        else "Acknowledgement recorded."
    )
    return CommandAckResponse(
        success=True, message=message, duplicate=duplicate, command=command
    )
