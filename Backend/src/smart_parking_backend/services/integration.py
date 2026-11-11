"""Coordinate Unity reports and commands with durable records and the live backend projection.

Unity remains authoritative for simulation execution. PostgreSQL owns command delivery/results and the latest accepted
snapshot; this process owns session/sequence decisions, connectivity freshness, and the dashboard projection.
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
from smart_parking_backend.services import cctv, garage_state
from smart_parking_backend.storage.repository import PostgresRepository, StoredSnapshot

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_REDELIVERY_SECONDS = 5.0


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
    """Coordinate durable integration records with process-local connectivity and garage state.

    This service validates session and sequence ownership, but never executes simulation commands. A restored snapshot
    is last-known dashboard data until this process receives a fresh Unity report.
    """

    def __init__(
        self,
        garage: garage_state.GarageStateService,
        repository: PostgresRepository,
        timeout_seconds: float | None = None,
        redelivery_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
        *,
        cctv_service: cctv.CCTVService | None = None,
    ) -> None:
        self._garage = garage
        self._repository = repository
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
        self.cctv_service = cctv_service if cctv_service is not None else cctv.CCTVService(clock, utcnow)
        self._utcnow = utcnow
        # Nested calls reacquire this lock; it coordinates threads in this process, not multiple server workers.
        self._lock = threading.RLock()
        self.backend_instance_id = uuid.uuid4().hex[:12]
        self._session_id: str | None = None
        self._latest_sequence = 0
        self._last_update_mono: float | None = None
        self._last_update_at: datetime | None = None
        self._restored_received_at: datetime | None = None

    # ---- connectivity ----------------------------------------------------------------------------------------
    def _age(self) -> float | None:
        """Measure current age monotonically, or use UTC receipt age before this process receives a report.

        The restored UTC time supports last-known age reporting after restart; it never establishes live connectivity.
        """
        if self._last_update_mono is not None:
            return self._clock() - self._last_update_mono
        if self._restored_received_at is not None:
            return (self._utcnow() - self._restored_received_at).total_seconds()
        return None

    def is_connected(self) -> bool:
        """Return whether the current Unity session has reported within the configured timeout."""
        with self._lock:
            age = self._age()
            return self._session_id is not None and self._last_update_mono is not None and age <= self.timeout_seconds

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
                pending_commands=self._repository.pending_command_count(self._session_id),
                backend_instance_id=self.backend_instance_id,
            )

    def restore_last_known(self, saved: StoredSnapshot | None) -> None:
        """Restore dashboard knowledge and sequence identity, not Unity objects or live connectivity.

        With no saved snapshot the seeded projection remains unchanged. A restored report does not enable command
        intake; a fresh snapshot in this process is required.
        """
        with self._lock:
            if saved is None:
                return
            snapshot = saved.snapshot
            self._garage.apply_live(snapshot.simulation, snapshot.spaces, snapshot.vehicles)
            self._session_id = snapshot.unity_session_id
            self._latest_sequence = snapshot.sequence
            self._last_update_at = saved.received_at
            self._restored_received_at = saved.received_at
            self._last_update_mono = None
            self.cctv_service.reset_for_session(snapshot.unity_session_id)

    # ---- snapshots -------------------------------------------------------------------------------------------
    def accept_snapshot(self, snapshot: integration_models.UnityStateSnapshot) -> integration_models.SnapshotAck:
        """Persist a full Unity report before replacing the live projection.

        Args:
            snapshot: Full state report whose session and sequence are being accepted.

        Returns:
            The acknowledgement containing the accepted session and sequence.

        Raises:
            StaleSnapshotError: If this session has already reported this sequence or a newer one.

        A new session also clears the previous session's CCTV state. Persistence precedes in-memory publication, but
        the database write and projection update are not one atomic transaction.
        """
        with self._lock:
            new_session = snapshot.unity_session_id != self._session_id
            if not new_session and snapshot.sequence <= self._latest_sequence:
                raise StaleSnapshotError(
                    f"Stale snapshot: sequence {snapshot.sequence} <= latest accepted {self._latest_sequence}.",
                    self._latest_sequence,
                )
            received_at = self._utcnow()
            self._repository.save_snapshot(snapshot, received_at)
            if new_session:
                self.cctv_service.reset_for_session(snapshot.unity_session_id)
            self._garage.apply_live(snapshot.simulation, snapshot.spaces, snapshot.vehicles)
            self._session_id = snapshot.unity_session_id
            self._latest_sequence = snapshot.sequence
            self._last_update_mono = self._clock()
            self._last_update_at = received_at
            self._restored_received_at = None
            return integration_models.SnapshotAck(
                accepted=True,
                message="Snapshot accepted.",
                unity_session_id=self._session_id,
                latest_sequence=self._latest_sequence,
                new_session=new_session,
                backend_instance_id=self.backend_instance_id,
            )

    # ---- commands --------------------------------------------------------------------------------------------
    def enqueue(
        self, command_type: enums.CommandType, payload: integration_models.CommandPayload | None = None
    ) -> integration_models.BackendCommand:
        """Persist a command only while Unity is fresh; leave simulation validation and occupancy to Unity.

        Args:
            command_type: Unity command to enqueue.
            payload: Command-specific data, or an empty payload when omitted.

        Returns:
            The durable command record.

        Raises:
            UnityOfflineError: If Unity is not connected; no command is persisted.
        """
        with self._lock:
            if not self.is_connected():
                raise UnityOfflineError("Unity is not connected; the command was not queued.")
            return self._repository.enqueue(
                command_type, payload or integration_models.CommandPayload(), self._session_id, self._utcnow()
            )

    def enqueue_spawn(
        self, payload: integration_models.CommandPayload
    ) -> tuple[integration_models.BackendCommand, vehicle_models.VehicleSpawnRequest]:
        """Create linked spawn-request and command records atomically while Unity is fresh.

        Args:
            payload: Spawn details shared by the request and Unity command.

        Returns:
            The command and its spawn request, in that order.

        Raises:
            UnityOfflineError: If Unity is not connected; neither record is created.

        Queueing intent does not change projected occupancy or validate Unity's simulation transition.
        """
        with self._lock:
            if not self.is_connected():
                raise UnityOfflineError("Unity is not connected; the spawn request was not created.")
            return self._repository.enqueue_spawn(payload, self._session_id, self._utcnow())

    def _require_session(self, session_id: str) -> None:
        if session_id != self._session_id:
            raise SessionMismatchError(f"Session '{session_id}' is not the current Unity session '{self._session_id}'.")

    def fetch_commands(self, session_id: str, limit: int = 10) -> list[integration_models.BackendCommand]:
        """Return durable work and eligible same-session redeliveries.

        Args:
            session_id: Current Unity session requesting commands.
            limit: Maximum eligible commands to return.

        Returns:
            Commands ordered by numeric command order. Later work need not wait for earlier acknowledgements, so Unity
            must deduplicate by command ID; delivery is at least once, not exactly once.

        Raises:
            SessionMismatchError: If the requester is not the current Unity session.
        """
        with self._lock:
            self._require_session(session_id)
            return self._repository.fetch_commands(session_id, self._utcnow(), self.redelivery_seconds, limit)

    def acknowledge(
        self, command_id: str, ack: integration_models.CommandAckRequest
    ) -> tuple[integration_models.BackendCommand, bool]:
        """Record Unity's command result without revising a terminal outcome.

        Args:
            command_id: Durable command being acknowledged.
            ack: Unity session and reported command result.

        Returns:
            The command and whether the result was already terminal. The first terminal result, including
            ``OutcomeUnknown``, remains authoritative; an acknowledgement is not independent proof of physical parking
            or departure completion.

        Raises:
            garage_state.NotFoundError: If the command does not exist.
            SessionMismatchError: If Unity's session does not own the command or is not current.
        """
        with self._lock:
            command = self._repository.get_command(command_id)
            if command is None:
                raise garage_state.NotFoundError(f"Command '{command_id}' does not exist.")
            self._require_session(ack.unity_session_id)
            if ack.unity_session_id != command.unity_session_id:
                raise SessionMismatchError(
                    f"Command '{command_id}' belongs to Unity session '{command.unity_session_id}'."
                )
            return self._repository.acknowledge(command_id, ack, self._utcnow())

    def get_command(self, command_id: str) -> integration_models.BackendCommand:
        with self._lock:
            command = self._repository.get_command(command_id)
            if command is None:
                raise garage_state.NotFoundError(f"Command '{command_id}' does not exist.")
            return command
