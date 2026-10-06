"""Typed command bodies. Commands with no parameters still get an explicit (empty) model so the contract can grow."""

from pydantic import BaseModel, ConfigDict, Field

from .enums import Level, ScenarioMode, VehicleRequestType


class _Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartSimulationCommand(_Command):
    pass


class PauseArrivalsCommand(_Command):
    pass


class ResumeArrivalsCommand(_Command):
    pass


class BeginDrainCommand(_Command):
    pass


class ResetSimulationCommand(_Command):
    pass


class SetScenarioModeCommand(_Command):
    scenario_mode: ScenarioMode


class SpawnVehicleCommand(_Command):
    request_type: VehicleRequestType
    preferred_level: Level | None = Field(
        default=None, description="Optional level preference: L1-L4."
    )
