"""
Unity <-> backend integration state: the Unity session, sequence protection and the command queue.

Transport is plain REST polling: Unity POSTs snapshots and GETs pending commands; it is the only party that ever
changes simulation state. Nothing here executes a command, it only queues and tracks them.

Command lifecycle:  Pending -> Delivered -> Acknowledged | Failed,   or Cancelled (reset / session change).
Delivery is at-least-once: a Delivered command that stays unacknowledged for `redelivery_seconds` is handed out again
(delivery_count increments) and Unity de-duplicates by command_id. Commands are always returned in creation order.
"""

import os
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from smart_parking_backend.models import enums
from smart_parking_backend.models import integration as integration_models
from smart_parking_backend.models import vehicles as vehicle_models
from smart_parking_backend.services import garage_state

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_REDELIVERY_SECONDS = 5.0
_TERMINAL = (enums.CommandStatus.ACKNOWLEDGED, enums.CommandStatus.FAILED, enums.CommandStatus.CANCELLED)


class UnityOfflineError(Exception):
    """No Unity session has reported within the timeout, so commands cannot be executed (HTTP 503)."""


class StaleSnapshotError(Exception):
    """Snapshot sequence is not newer than the latest accepted one (HTTP 409)."""

    def __init__(self, message: str, latest_sequence: int) -> None:
        super().__init__(message)
        self.latest_sequence = latest_sequence


class SessionMismatchError(Exception):
    """The caller is not the current Unity session (HTTP 409)."""


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


class IntegrationService:
    def __init__(
        self,
        garage: garage_state.GarageStateService,
        timeout_seconds: float | None = None,
        redelivery_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._garage = garage
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _env_float("SPG_INTEGRATION_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        self.redelivery_seconds = (
            redelivery_seconds
            if redelivery_seconds is not None
            else _env_float("SPG_COMMAND_REDELIVERY_SECONDS", DEFAULT_REDELIVERY_SECONDS)
        )
        self._clock = clock
        self._utcnow = utcnow
        self._lock = threading.RLock()
        self.backend_instance_id = uuid.uuid4().hex[:12]
        self._session_id: str | None = None
        self._latest_sequence = 0
        self._last_update_mono: float | None = None
        self._last_update_at: datetime | None = None
        self._commands: dict[str, integration_models.BackendCommand] = {}  # insertion order == creation order == FIFO
        self._delivered_mono: dict[str, float] = {}
        self._command_sequence = 0

    # ---- connectivity ----------------------------------------------------------------------------------------
    def _age(self) -> float | None:
        return None if self._last_update_mono is None else self._clock() - self._last_update_mono

    def is_connected(self) -> bool:
        with self._lock:
            age = self._age()
            return self._session_id is not None and age is not None and age <= self.timeout_seconds

    def data_source(self) -> enums.DataSource:
        with self._lock:
            if self._session_id is None:
                return enums.DataSource.SEEDED_BASELINE
            return enums.DataSource.UNITY_LIVE if self.is_connected() else enums.DataSource.UNITY_LAST_KNOWN

    def status(self) -> integration_models.IntegrationStatus:
        with self._lock:
            age = self._age()
            return integration_models.IntegrationStatus(
                connected=self.is_connected(),
                unity_session_id=self._session_id,
                latest_sequence=self._latest_sequence,
                last_update_at=self._last_update_at,
                seconds_since_last_update=None if age is None else round(age, 3),
                timeout_seconds=self.timeout_seconds,
                data_source=self.data_source(),
                pending_commands=sum(1 for c in self._commands.values() if c.status not in _TERMINAL),
                backend_instance_id=self.backend_instance_id,
            )

    # ---- snapshots -------------------------------------------------------------------------------------------
    def accept_snapshot(self, snapshot: integration_models.UnityStateSnapshot) -> integration_models.SnapshotAck:
        """
        A different session id is a NEW Unity session: it is accepted, sequence tracking restarts, and commands still
        open for the previous session are cancelled. A repeated session id must advance the sequence.
        An old session that reappears after a newer one therefore starts yet another session; only the latest
        reporter is tracked.
        """
        with self._lock:
            new_session = snapshot.unity_session_id != self._session_id
            if new_session:
                self._cancel_open("Unity session ended before this command completed.")
                self._session_id = snapshot.unity_session_id
                self._latest_sequence = 0
            elif snapshot.sequence <= self._latest_sequence:
                raise StaleSnapshotError(
                    f"Stale snapshot: sequence {snapshot.sequence} <= latest accepted {self._latest_sequence}.",
                    self._latest_sequence,
                )
            self._garage.apply_live(snapshot.simulation, snapshot.spaces, snapshot.vehicles)
            self._latest_sequence = snapshot.sequence
            self._last_update_mono = self._clock()
            self._last_update_at = self._utcnow()
            return integration_models.SnapshotAck(
                accepted=True,
                message="Snapshot accepted.",
                unity_session_id=self._session_id,
                latest_sequence=self._latest_sequence,
                new_session=new_session,
                backend_instance_id=self.backend_instance_id,
            )

    # ---- commands --------------------------------------------------------------------------------------------
    def _cancel_open(self, reason: str, before: str | None = None) -> None:
        """Cancel commands that are not finished; `before` limits this to commands created earlier than that id."""
        for command in self._commands.values():
            if before is not None and command.command_id >= before:
                break
            if command.status in (enums.CommandStatus.PENDING, enums.CommandStatus.DELIVERED):
                self._finish(command, enums.CommandStatus.CANCELLED, reason)

    def _finish(
        self,
        command: integration_models.BackendCommand,
        status: enums.CommandStatus,
        message: str,
        vehicle_id: str | None = None,
        error_code: enums.CommandErrorCode | None = None,
    ) -> None:
        command.status = status
        command.result_message = message
        command.acknowledged_at = self._utcnow()
        if vehicle_id is not None:
            command.vehicle_id = vehicle_id
        if status == enums.CommandStatus.FAILED:
            command.error_code = error_code
        request_id = command.payload.spawn_request_id
        if command.command_type == enums.CommandType.SPAWN_VEHICLE and request_id:
            if status == enums.CommandStatus.ACKNOWLEDGED:
                self._garage.update_spawn_request(
                    request_id,
                    status=enums.SpawnRequestStatus.SPAWNED_IN_UNITY,
                    forwarded_to_unity=True,
                    spawned_in_unity=True,
                    vehicle_id=vehicle_id,
                )
            else:
                self._garage.update_spawn_request(
                    request_id,
                    status=enums.SpawnRequestStatus.FAILED,
                    failure_reason=message,
                    error_code=error_code if status == enums.CommandStatus.FAILED else None,
                )

    def enqueue(
        self, command_type: enums.CommandType, payload: integration_models.CommandPayload | None = None
    ) -> integration_models.BackendCommand:
        with self._lock:
            if not self.is_connected():
                raise UnityOfflineError("Unity is not connected; the command was not queued.")
            self._command_sequence += 1
            command = integration_models.BackendCommand(
                command_id=f"CMD_{self._command_sequence:06d}",
                command_type=command_type,
                created_at=self._utcnow(),
                payload=payload or integration_models.CommandPayload(),
                unity_session_id=self._session_id,
            )
            if command_type == enums.CommandType.RESET_SIMULATION:
                # Commands never handed to Unity are obsolete once a reset is queued. Delivered ones stay: Unity may
                # be running them, and FIFO order guarantees they finish before the reset executes.
                for earlier in self._commands.values():
                    if earlier.status == enums.CommandStatus.PENDING:
                        self._finish(
                            earlier,
                            enums.CommandStatus.CANCELLED,
                            f"Obsolete: superseded by reset {command.command_id}.",
                        )
            self._commands[command.command_id] = command
            return command.model_copy(deep=True)

    def enqueue_spawn(
        self, payload: integration_models.CommandPayload
    ) -> tuple[integration_models.BackendCommand, vehicle_models.VehicleSpawnRequest]:
        """Create a linked spawn request and command as one step.

        Args:
            payload: Accepted spawn parameters to forward to Unity.

        Returns:
            The queued command and its linked spawn-request record.

        Raises:
            UnityOfflineError: No live Unity session; no request or command is created.
        """
        with self._lock:
            if not self.is_connected():
                raise UnityOfflineError("Unity is not connected; the spawn request was not created.")
            request = self._garage.create_spawn_request(
                payload.request_type,
                payload.preferred_level,
                auto_depart=payload.auto_depart,
            )
            payload = payload.model_copy(update={"spawn_request_id": request.request_id})
            command = self.enqueue(enums.CommandType.SPAWN_VEHICLE, payload)
            self._garage.update_spawn_request(request.request_id, command_id=command.command_id)
            return command, self._garage.get_spawn_request(request.request_id)

    def _require_session(self, session_id: str) -> None:
        if session_id != self._session_id:
            raise SessionMismatchError(f"Session '{session_id}' is not the current Unity session '{self._session_id}'.")

    def fetch_commands(self, session_id: str, limit: int = 10) -> list[integration_models.BackendCommand]:
        """Commands for Unity to run, oldest first: never-delivered ones and Delivered ones awaiting redelivery."""
        with self._lock:
            self._require_session(session_id)
            now = self._clock()
            due: list[integration_models.BackendCommand] = []
            for command in self._commands.values():
                if len(due) >= limit:
                    break
                if command.status == enums.CommandStatus.PENDING or (
                    command.status == enums.CommandStatus.DELIVERED
                    and now - self._delivered_mono.get(command.command_id, now) >= self.redelivery_seconds
                ):
                    due.append(command)
            for command in due:
                command.status = enums.CommandStatus.DELIVERED
                command.delivery_count += 1
                command.delivered_at = self._utcnow()
                self._delivered_mono[command.command_id] = now
                request_id = command.payload.spawn_request_id
                if command.command_type == enums.CommandType.SPAWN_VEHICLE and request_id:
                    self._garage.update_spawn_request(
                        request_id,
                        status=enums.SpawnRequestStatus.FORWARDED_TO_UNITY,
                        forwarded_to_unity=True,
                    )
            return [c.model_copy(deep=True) for c in due]

    def acknowledge(
        self, command_id: str, ack: integration_models.CommandAckRequest
    ) -> tuple[integration_models.BackendCommand, bool]:
        """Record Unity's result, preserving the first terminal outcome.

        Args:
            command_id: ID of the queued command.
            ack: Unity's acknowledgement for its current session.

        Returns:
            The command and a duplicate flag. A finished command is unchanged.

        Raises:
            garage_state.NotFoundError: The command ID is unknown.
            SessionMismatchError: The acknowledgement is for a different session.
        """
        with self._lock:
            command = self._commands.get(command_id)
            if command is None:
                raise garage_state.NotFoundError(f"Command '{command_id}' does not exist.")
            self._require_session(ack.unity_session_id)
            if command.status in _TERMINAL:
                return command.model_copy(deep=True), True
            if ack.success:
                self._finish(
                    command,
                    enums.CommandStatus.ACKNOWLEDGED,
                    ack.message or "Executed by Unity.",
                    ack.vehicle_id,
                )
                if command.command_type == enums.CommandType.RESET_SIMULATION:
                    self._cancel_open(
                        f"Obsolete: superseded by reset {command_id}.",
                        before=command_id,
                    )
            else:
                self._finish(
                    command,
                    enums.CommandStatus.FAILED,
                    ack.message or "Rejected by Unity.",
                    error_code=ack.error_code,
                )
            return command.model_copy(deep=True), False

    def get_command(self, command_id: str) -> integration_models.BackendCommand:
        with self._lock:
            command = self._commands.get(command_id)
            if command is None:
                raise garage_state.NotFoundError(f"Command '{command_id}' does not exist.")
            return command.model_copy(deep=True)
