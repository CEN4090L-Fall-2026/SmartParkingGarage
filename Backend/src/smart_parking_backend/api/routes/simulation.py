from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from smart_parking_backend.api import deps
from smart_parking_backend.models import commands as command_models
from smart_parking_backend.models import enums
from smart_parking_backend.models import integration as integration_models
from smart_parking_backend.models import responses as response_models
from smart_parking_backend.models import simulation as simulation_models
from smart_parking_backend.services import garage_state
from smart_parking_backend.services import integration as integration_service

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

_QUEUED = {503: {"description": "Unity is not connected; nothing was queued."}}


def _queue(
    service: garage_state.GarageStateService,
    integration: integration_service.IntegrationService,
    command_type: enums.CommandType,
    message: str,
    payload: integration_models.CommandPayload | None = None,
) -> response_models.CommandAccepted:
    """Queue for Unity. The simulation state changes only when Unity executes it and reports back."""
    state = service.last_known_state()
    command = integration.enqueue(command_type, payload)
    return response_models.CommandAccepted(
        message=f"{message} queued for Unity. It has not been executed yet.",
        current_state=state,
        command=command,
    )


@router.get("", response_model=simulation_models.SimulationStatus)
def get_simulation(
    response: Response,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> simulation_models.SimulationStatus:
    deps.tag_data_source(response, integration)
    return service.simulation_status(integration.data_source())


@router.post(
    "/start",
    response_model=response_models.CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def start(
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
    command: command_models.StartSimulationCommand | None = None,
) -> response_models.CommandAccepted:
    return _queue(service, integration, enums.CommandType.START_SIMULATION, "Start")


@router.post(
    "/pause-arrivals",
    response_model=response_models.CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def pause_arrivals(
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
    command: command_models.PauseArrivalsCommand | None = None,
) -> response_models.CommandAccepted:
    return _queue(service, integration, enums.CommandType.PAUSE_ARRIVALS, "Pause arrivals")


@router.post(
    "/resume-arrivals",
    response_model=response_models.CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def resume_arrivals(
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
    command: command_models.ResumeArrivalsCommand | None = None,
) -> response_models.CommandAccepted:
    return _queue(service, integration, enums.CommandType.RESUME_ARRIVALS, "Resume arrivals")


@router.post(
    "/drain",
    response_model=response_models.CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def drain(
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
    command: command_models.BeginDrainCommand | None = None,
) -> response_models.CommandAccepted:
    return _queue(service, integration, enums.CommandType.BEGIN_DRAIN, "Drain")


@router.post(
    "/reset",
    response_model=response_models.CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def reset(
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
    command: command_models.ResetSimulationCommand | None = None,
) -> response_models.CommandAccepted:
    """Queue a reset. Commands not yet delivered to Unity are cancelled as obsolete."""
    return _queue(service, integration, enums.CommandType.RESET_SIMULATION, "Reset")


@router.post(
    "/mode",
    response_model=response_models.CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_QUEUED,
)
def set_mode(
    command: command_models.SetScenarioModeCommand,
    service: Annotated[garage_state.GarageStateService, Depends(deps.get_service)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> response_models.CommandAccepted:
    return _queue(
        service,
        integration,
        enums.CommandType.SET_SCENARIO_MODE,
        "Scenario mode change",
        integration_models.CommandPayload(scenario_mode=command.scenario_mode),
    )
