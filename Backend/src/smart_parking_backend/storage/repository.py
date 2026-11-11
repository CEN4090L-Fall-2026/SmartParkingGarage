"""Persist backend request intent, command outcomes, and the latest Unity snapshot.

The stored snapshot restores dashboard knowledge, not Unity objects. Database transactions and row locks protect these
repository operations; they do not make process-local services safe to share across multiple server workers.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from smart_parking_backend.models import enums
from smart_parking_backend.models import integration as integration_models
from smart_parking_backend.models import vehicles as vehicle_models
from smart_parking_backend.storage import schema

_OPEN = (enums.CommandStatus.PENDING.value, enums.CommandStatus.DELIVERED.value)
_REQUEST_STATUSES = {
    enums.CommandStatus.PENDING: enums.SpawnRequestStatus.ACCEPTED_BY_BACKEND,
    enums.CommandStatus.DELIVERED: enums.SpawnRequestStatus.FORWARDED_TO_UNITY,
    enums.CommandStatus.ACKNOWLEDGED: enums.SpawnRequestStatus.SPAWNED_IN_UNITY,
    enums.CommandStatus.FAILED: enums.SpawnRequestStatus.FAILED,
    enums.CommandStatus.CANCELLED: enums.SpawnRequestStatus.FAILED,
    enums.CommandStatus.OUTCOME_UNKNOWN: enums.SpawnRequestStatus.OUTCOME_UNKNOWN,
}
_REQUEST_SELECT = sa.select(
    schema.parking_requests.c.request_id,
    schema.parking_requests.c.request_type,
    schema.parking_requests.c.preferred_level,
    schema.parking_requests.c.auto_depart,
    schema.commands,
).select_from(schema.parking_requests.join(schema.commands))


@dataclass(frozen=True, slots=True)
class StoredSnapshot:
    snapshot: integration_models.UnityStateSnapshot
    received_at: datetime


def _command(row: sa.RowMapping) -> integration_models.BackendCommand:
    fields = {name: row[name] for name in integration_models.BackendCommand.model_fields if name != "payload"}
    fields["payload"] = {**row["payload"], "spawn_request_id": row["spawn_request_id"]}
    return integration_models.BackendCommand.model_validate(fields)


def _request(row: sa.RowMapping) -> vehicle_models.VehicleSpawnRequest:
    # Request state is derived from its linked command so the two records cannot drift independently.
    status = enums.CommandStatus(row["status"])
    confirmed = status == enums.CommandStatus.ACKNOWLEDGED
    failed = status in (enums.CommandStatus.FAILED, enums.CommandStatus.CANCELLED)
    # Delivery means Unity received work, not that a spawn succeeded; unknown outcomes invent no ID or failure code.
    return vehicle_models.VehicleSpawnRequest(
        request_id=row["request_id"],
        request_type=row["request_type"],
        preferred_level=row["preferred_level"],
        auto_depart=row["auto_depart"],
        status=_REQUEST_STATUSES[status],
        forwarded_to_unity=row["delivery_count"] > 0 or confirmed,
        spawned_in_unity=confirmed,
        vehicle_id=row["vehicle_id"] if confirmed else None,
        command_id=row["command_id"],
        failure_reason=row["result_message"] if failed else None,
        error_code=row["error_code"] if status == enums.CommandStatus.FAILED else None,
    )


class PostgresRepository:
    """Own transaction boundaries for durable records, not Unity simulation restoration.

    Row locks coordinate database operations, but session freshness and the in-memory projection remain process-local.
    """

    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    @staticmethod
    def _end_session_commands(
        connection: sa.Connection,
        session_id: str | None,
        pending_message: str,
        delivered_message: str,
    ) -> None:
        commands = schema.commands
        scope = commands.c.unity_session_id == session_id if session_id is not None else sa.true()
        # Pending work was never delivered and can be cancelled; delivered work may already have executed.
        connection.execute(
            commands.update()
            .where(scope, commands.c.status == enums.CommandStatus.PENDING.value)
            .values(status=enums.CommandStatus.CANCELLED.value, result_message=pending_message)
        )
        # Keep delivered work explicitly uncertain instead of retrying it or inventing an acknowledgement time.
        connection.execute(
            commands.update()
            .where(scope, commands.c.status == enums.CommandStatus.DELIVERED.value)
            .values(status=enums.CommandStatus.OUTCOME_UNKNOWN.value, result_message=delivered_message)
        )

    def recover(self, now: datetime) -> StoredSnapshot | None:
        """End unfinished work and sessions, then return the last durable projection if one exists.

        Args:
            now: Backend time used to close the previously active session.

        Returns:
            The saved latest snapshot, or ``None`` if none exists. Recovery still updates unfinished commands and
            closes sessions when no snapshot is stored.
        """
        with self._engine.begin() as connection:
            self._end_session_commands(
                connection,
                None,
                "Backend restarted before this command was delivered.",
                "Execution outcome unconfirmed: backend restarted before acknowledgment.",
            )
            connection.execute(
                schema.unity_sessions.update().where(schema.unity_sessions.c.ended_at.is_(None)).values(ended_at=now)
            )
            row = (
                connection.execute(
                    sa.select(schema.latest_garage_snapshot).where(schema.latest_garage_snapshot.c.singleton_id == 1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            return StoredSnapshot(
                snapshot=integration_models.UnityStateSnapshot.model_validate(row["payload"]),
                received_at=row["received_at"],
            )

    def save_snapshot(self, snapshot: integration_models.UnityStateSnapshot, received_at: datetime) -> None:
        """Atomically close the prior session, update session metadata, and replace the latest snapshot.

        Args:
            snapshot: Full Unity report already accepted by the service layer.
            received_at: Backend receipt time, not Unity's informational timestamp.

        The row is a latest-state recovery projection, not a snapshot archive. Session/sequence validation and ordering
        are owned by ``IntegrationService``.
        """
        sessions, latest = schema.unity_sessions, schema.latest_garage_snapshot
        with self._engine.begin() as connection:
            previous_session = connection.scalar(
                sa.select(latest.c.unity_session_id).where(latest.c.singleton_id == 1).with_for_update()
            )
            if previous_session is not None and previous_session != snapshot.unity_session_id:
                self._end_session_commands(
                    connection,
                    previous_session,
                    "Unity session ended before this command completed.",
                    "Execution outcome unconfirmed: Unity session ended before acknowledgment.",
                )
                connection.execute(
                    sessions.update()
                    .where(sessions.c.unity_session_id == previous_session)
                    .values(ended_at=received_at)
                )
            session_insert = insert(sessions).values(
                unity_session_id=snapshot.unity_session_id,
                first_seen_at=received_at,
                last_seen_at=received_at,
                last_sequence=snapshot.sequence,
            )
            connection.execute(
                session_insert.on_conflict_do_update(
                    index_elements=[sessions.c.unity_session_id],
                    set_={"last_seen_at": received_at, "last_sequence": snapshot.sequence, "ended_at": None},
                )
            )
            values = {
                "unity_session_id": snapshot.unity_session_id,
                "sequence": snapshot.sequence,
                "unity_timestamp": snapshot.timestamp,
                "received_at": received_at,
                "payload": snapshot.model_dump(mode="json"),
            }
            connection.execute(
                insert(latest)
                .values(singleton_id=1, **values)
                .on_conflict_do_update(index_elements=[latest.c.singleton_id], set_=values)
            )

    @staticmethod
    def _insert_command(
        connection: sa.Connection,
        command_type: enums.CommandType,
        payload: integration_models.CommandPayload,
        unity_session_id: str,
        now: datetime,
        spawn_request_id: str | None = None,
    ) -> integration_models.BackendCommand:
        commands = schema.commands
        # Database sequences provide durable IDs/order; rollbacks may leave valid gaps.
        order = connection.scalar(sa.select(schema.command_order_seq.next_value()))
        command_id = f"CMD_{order:06d}"
        # Only older work known never delivered is cancelled here; delivered work may already have executed.
        if command_type == enums.CommandType.RESET_SIMULATION:
            connection.execute(
                commands.update()
                .where(
                    commands.c.unity_session_id == unity_session_id,
                    commands.c.command_order < order,
                    commands.c.status == enums.CommandStatus.PENDING.value,
                )
                .values(
                    status=enums.CommandStatus.CANCELLED.value,
                    result_message=f"Obsolete: superseded by reset {command_id}.",
                )
            )
        row = (
            connection.execute(
                commands.insert()
                .values(
                    command_order=order,
                    command_id=command_id,
                    unity_session_id=unity_session_id,
                    spawn_request_id=spawn_request_id,
                    command_type=command_type.value,
                    payload=payload.model_dump(mode="json", exclude={"spawn_request_id"}),
                    status=enums.CommandStatus.PENDING.value,
                    created_at=now,
                    delivery_count=0,
                )
                .returning(commands)
            )
            .mappings()
            .one()
        )
        return _command(row)

    def enqueue(
        self,
        command_type: enums.CommandType,
        payload: integration_models.CommandPayload,
        unity_session_id: str,
        now: datetime,
    ) -> integration_models.BackendCommand:
        with self._engine.begin() as connection:
            return self._insert_command(connection, command_type, payload, unity_session_id, now)

    def enqueue_spawn(
        self, payload: integration_models.CommandPayload, unity_session_id: str, now: datetime
    ) -> tuple[integration_models.BackendCommand, vehicle_models.VehicleSpawnRequest]:
        """Persist spawn intent and its Unity command in the same database transaction.

        Args:
            payload: Spawn details shared by the request record and command.
            unity_session_id: Unity session that will receive the command.
            now: Backend time for both records.

        Returns:
            The command and linked request, in that order.

        Sequence-backed identifiers persist across restarts; gaps are valid when a transaction rolls back.
        """
        with self._engine.begin() as connection:
            order = connection.scalar(sa.select(schema.parking_request_order_seq.next_value()))
            request_id = f"REQ_{order:04d}"
            connection.execute(
                schema.parking_requests.insert().values(
                    request_order=order,
                    request_id=request_id,
                    request_type=payload.request_type.value,
                    preferred_level=payload.preferred_level.value if payload.preferred_level is not None else None,
                    auto_depart=payload.auto_depart,
                    created_at=now,
                )
            )
            command = self._insert_command(
                connection, enums.CommandType.SPAWN_VEHICLE, payload, unity_session_id, now, request_id
            )
            row = (
                connection.execute(_REQUEST_SELECT.where(schema.parking_requests.c.request_id == request_id))
                .mappings()
                .one()
            )
            return command, _request(row)

    def fetch_commands(
        self, unity_session_id: str, now: datetime, redelivery_seconds: float, limit: int
    ) -> list[integration_models.BackendCommand]:
        """Mark eligible commands delivered before returning them, ordered by numeric command order.

        Args:
            unity_session_id: Session whose commands are eligible.
            now: Backend time recorded for this delivery attempt.
            redelivery_seconds: Minimum age of an unacknowledged delivery before it is eligible again.
            limit: Maximum number of eligible rows to lock and return.

        Returns:
            At-least-once work. Later pending commands can be returned while an earlier delivery awaits acknowledgement;
            Unity must deduplicate command IDs.
        """
        commands = schema.commands
        with self._engine.begin() as connection:
            rows = (
                connection.execute(
                    sa.select(commands)
                    .where(
                        commands.c.unity_session_id == unity_session_id,
                        sa.or_(
                            commands.c.status == enums.CommandStatus.PENDING.value,
                            sa.and_(
                                commands.c.status == enums.CommandStatus.DELIVERED.value,
                                commands.c.delivered_at <= now - timedelta(seconds=redelivery_seconds),
                            ),
                        ),
                    )
                    .order_by(commands.c.command_order)
                    .limit(limit)
                    .with_for_update()
                )
                .mappings()
                .all()
            )
            delivered = []
            for row in rows:
                updated = (
                    connection.execute(
                        commands.update()
                        .where(commands.c.command_order == row["command_order"])
                        .values(
                            status=enums.CommandStatus.DELIVERED.value,
                            delivery_count=row["delivery_count"] + 1,
                            delivered_at=now,
                        )
                        .returning(commands)
                    )
                    .mappings()
                    .one()
                )
                delivered.append(_command(updated))
            return delivered

    def acknowledge(
        self, command_id: str, ack: integration_models.CommandAckRequest, now: datetime
    ) -> tuple[integration_models.BackendCommand, bool]:
        """Store the first terminal Unity outcome under a row lock.

        Args:
            command_id: Command whose outcome Unity reports.
            ack: Unity's success/failure result.
            now: Backend receipt time for this acknowledgement.

        Returns:
            The stored command and whether it was already terminal. The service layer checks command existence and
            session ownership before calling this repository method.
        """
        commands = schema.commands
        with self._engine.begin() as connection:
            row = (
                connection.execute(sa.select(commands).where(commands.c.command_id == command_id).with_for_update())
                .mappings()
                .one()
            )
            if row["status"] not in _OPEN:
                return _command(row), True
            status = enums.CommandStatus.ACKNOWLEDGED if ack.success else enums.CommandStatus.FAILED
            updated = (
                connection.execute(
                    commands.update()
                    .where(commands.c.command_id == command_id)
                    .values(
                        status=status.value,
                        acknowledged_at=now,
                        result_message=ack.message or ("Executed by Unity." if ack.success else "Rejected by Unity."),
                        vehicle_id=ack.vehicle_id if ack.success else None,
                        error_code=ack.error_code.value if not ack.success and ack.error_code is not None else None,
                    )
                    .returning(commands)
                )
                .mappings()
                .one()
            )
            if ack.success and row["command_type"] == enums.CommandType.RESET_SIMULATION.value:
                # A confirmed reset supersedes older open work; commands created after it remain untouched.
                connection.execute(
                    commands.update()
                    .where(
                        commands.c.unity_session_id == row["unity_session_id"],
                        commands.c.command_order < row["command_order"],
                        commands.c.status.in_(_OPEN),
                    )
                    .values(
                        status=enums.CommandStatus.CANCELLED.value,
                        result_message=f"Obsolete: superseded by reset {command_id}.",
                    )
                )
            return _command(updated), False

    def get_command(self, command_id: str) -> integration_models.BackendCommand | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(sa.select(schema.commands).where(schema.commands.c.command_id == command_id))
                .mappings()
                .first()
            )
            return _command(row) if row is not None else None

    def get_spawn_request(self, request_id: str) -> vehicle_models.VehicleSpawnRequest | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(_REQUEST_SELECT.where(schema.parking_requests.c.request_id == request_id))
                .mappings()
                .first()
            )
            return _request(row) if row is not None else None

    def list_spawn_requests(self) -> list[vehicle_models.VehicleSpawnRequest]:
        with self._engine.connect() as connection:
            rows = connection.execute(_REQUEST_SELECT.order_by(schema.parking_requests.c.request_order)).mappings()
            return [_request(row) for row in rows]

    def pending_command_count(self, unity_session_id: str | None) -> int:
        with self._engine.connect() as connection:
            return connection.scalar(
                sa.select(sa.func.count())
                .select_from(schema.commands)
                .where(
                    schema.commands.c.unity_session_id == unity_session_id,
                    schema.commands.c.status.in_(_OPEN),
                )
            )

    def pending_spawn_request_count(self) -> int:
        with self._engine.connect() as connection:
            return connection.scalar(
                sa.select(sa.func.count())
                .select_from(schema.commands)
                .where(schema.commands.c.spawn_request_id.is_not(None), schema.commands.c.status.in_(_OPEN))
            )
