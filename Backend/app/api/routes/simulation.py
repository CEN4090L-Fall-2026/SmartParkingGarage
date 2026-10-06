from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from ...models import (
    BeginDrainCommand,
    CommandAccepted,
    CommandPayload,
    CommandType,
    PauseArrivalsCommand,
    ResetSimulationCommand,
    ResumeArrivalsCommand,
    SetScenarioModeCommand,
    SimulationStatus,
    StartSimulationCommand,
)
from ...services.garage_state import GarageStateService
from ...services.integration import IntegrationService
from ..deps import get_integration, get_service, tag_data_source

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

_QUEUED = {503: {"description": "Unity is not connected; nothing was queued."}}


def _queue(
    service: GarageStateService,
    integration: IntegrationService,
    command_type: CommandType,
    message: str,
    payload: CommandPayload | None = None,
) -> CommandAccepted:
    """Queue for Unity. The simulation state changes only when Unity executes it and reports back."""
    state = service.last_known_state()
    command = integration.enqueue(command_type, payload)
    return CommandAccepted(
        message=f"{message} queued for Unity. It has not been executed yet.",
        current_state=state,
        command=command,
    )


@router.get("", response_model=SimulationStatus)
def get_simulation(
    response: Response,
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> SimulationStatus:
    tag_data_source(response, integration)
    return service.simulation_status(integration.data_source())


@router.post(
    "/start",
    response_model=CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def start(
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
    command: StartSimulationCommand | None = None,
) -> CommandAccepted:
    return _queue(service, integration, CommandType.START_SIMULATION, "Start")


@router.post(
    "/pause-arrivals",
    response_model=CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def pause_arrivals(
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
    command: PauseArrivalsCommand | None = None,
) -> CommandAccepted:
    return _queue(service, integration, CommandType.PAUSE_ARRIVALS, "Pause arrivals")


@router.post(
    "/resume-arrivals",
    response_model=CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def resume_arrivals(
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
    command: ResumeArrivalsCommand | None = None,
) -> CommandAccepted:
    return _queue(service, integration, CommandType.RESUME_ARRIVALS, "Resume arrivals")


@router.post(
    "/drain",
    response_model=CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def drain(
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
    command: BeginDrainCommand | None = None,
) -> CommandAccepted:
    return _queue(service, integration, CommandType.BEGIN_DRAIN, "Drain")


@router.post(
    "/reset",
    response_model=CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def reset(
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
    command: ResetSimulationCommand | None = None,
) -> CommandAccepted:
    """Queue a reset. Commands not yet delivered to Unity are cancelled as obsolete."""
    return _queue(service, integration, CommandType.RESET_SIMULATION, "Reset")


@router.post(
    "/mode",
    response_model=CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def set_mode(
    command: SetScenarioModeCommand,
    service: Annotated[GarageStateService, Depends(get_service)],
    integration: Annotated[IntegrationService, Depends(get_integration)],
) -> CommandAccepted:
    return _queue(
        service,
        integration,
        CommandType.SET_SCENARIO_MODE,
        "Scenario mode change",
        CommandPayload(scenario_mode=command.scenario_mode),
    )
