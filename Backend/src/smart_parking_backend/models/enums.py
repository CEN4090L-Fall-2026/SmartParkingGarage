"""Shared vocabulary. Member values are the exact strings used by the Unity project and on the wire."""

from enum import Enum


class ParkingSpaceState(str, Enum):
    AVAILABLE = "Available"
    OCCUPIED = "Occupied"
    RESERVED = "Reserved"
    OUT_OF_SERVICE = "OutOfService"


class ParkingSpaceType(str, Enum):
    # ADA/Accessible is intentionally absent: authoritative accessible-stall metadata is not established.
    STANDARD = "Standard"
    EV = "EV"


class Level(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class VehicleRequestType(str, Enum):
    STANDARD = "Standard"
    EV = "EV"


class VehicleLifecycleState(str, Enum):
    SPAWNED = "Spawned"
    REQUESTING_ASSIGNMENT = "RequestingAssignment"
    DRIVING_TO_STALL = "DrivingToStall"
    PARKING = "Parking"
    PARKED = "Parked"
    DEPARTING = "Departing"
    DRIVING_TO_EXIT = "DrivingToExit"
    COMPLETED = "Completed"
    FAILED = "Failed"


class SimulationState(str, Enum):
    IDLE = "Idle"
    RUNNING = "Running"
    ARRIVAL_PAUSED = "ArrivalPaused"
    DRAINING = "Draining"


class ScenarioMode(str, Enum):
    NORMAL = "Normal"
    RUSH_HOUR = "RushHour"


class SpawnRequestStatus(str, Enum):
    """Lifecycle of a spawn request. Only SpawnedInUnity means Unity actually created the vehicle."""

    ACCEPTED_BY_BACKEND = "AcceptedByBackend"  # stored and queued as a command; Unity has not received it
    FORWARDED_TO_UNITY = "ForwardedToUnity"  # Unity has fetched the command
    SPAWNED_IN_UNITY = "SpawnedInUnity"  # Unity acknowledged that it spawned the vehicle
    FAILED = "Failed"  # Unity rejected it, or it was cancelled before execution
    OUTCOME_UNKNOWN = "OutcomeUnknown"  # delivered, but session ended before execution was confirmed


class DataSource(str, Enum):
    """Where the backend's current garage/simulation projection came from."""

    SEEDED_BASELINE = "SeededBaseline"  # no Unity session has ever reported
    UNITY_LIVE = "UnityLive"  # Unity reported within the integration timeout
    UNITY_LAST_KNOWN = "UnityLastKnown"  # Unity has gone quiet; this is its last report


class CommandType(str, Enum):
    START_SIMULATION = "StartSimulation"
    PAUSE_ARRIVALS = "PauseArrivals"
    RESUME_ARRIVALS = "ResumeArrivals"
    BEGIN_DRAIN = "BeginDrain"
    RESET_SIMULATION = "ResetSimulation"
    SET_SCENARIO_MODE = "SetScenarioMode"
    SPAWN_VEHICLE = "SpawnVehicle"
    DEPART_VEHICLE = "DepartVehicle"


class CommandErrorCode(str, Enum):
    GARAGE_FULL = "GarageFull"
    LEVEL_FULL = "LevelFull"
    VEHICLE_LIMIT_REACHED = "VehicleLimitReached"
    ENTRANCE_BLOCKED = "EntranceBlocked"


class CommandStatus(str, Enum):
    PENDING = "Pending"  # queued, not yet handed to Unity
    DELIVERED = "Delivered"  # handed to Unity, no acknowledgement yet
    ACKNOWLEDGED = "Acknowledged"  # Unity executed it successfully
    FAILED = "Failed"  # Unity rejected it or could not execute it
    CANCELLED = "Cancelled"  # made obsolete by a reset or by the Unity session ending
    OUTCOME_UNKNOWN = "OutcomeUnknown"  # delivered without an acknowledgement before restart/session end
