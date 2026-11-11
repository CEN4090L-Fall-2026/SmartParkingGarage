"""Hold process-local camera catalog, frames, focus ownership, and freshness metadata."""

import hashlib
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from smart_parking_backend.models import cameras as camera_models
from smart_parking_backend.services import garage_state

FOCUS_LEASE_SECONDS = 30.0


class CameraConflictError(Exception):
    """A camera operation conflicts with the current Unity session, frame, or focus lease."""


class FeedUnavailableError(Exception):
    def __init__(
        self,
        message: str,
        health: camera_models.FeedHealth,
        age_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.health = health
        self.age_ms = age_ms


@dataclass(frozen=True, slots=True)
class StoredFrame:
    """Cached JPEG plus its session, sequence, capture-age, and focused-generation identity."""
    session_id: str
    camera_id: str
    kind: camera_models.FrameKind
    sequence: int
    captured_at: datetime
    width: int
    height: int
    data: bytes
    received_mono: float
    initial_age_seconds: float
    focus_generation: str | None
    etag: str


class CCTVService:
    """Serve the current session's in-memory CCTV catalog, frames, and viewer focus lease.

    Camera state is process-local; unlike the garage projection, it is not restored from PostgreSQL.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._clock = clock
        self._utcnow = utcnow
        self._lock = threading.RLock()
        self._session_id: str | None = None
        self._catalog: dict[str, camera_models.CameraDefinition] = {}
        self._focused_interval_seconds = 0.1
        self._thumbnails: dict[str, StoredFrame] = {}
        self._focused_frame: StoredFrame | None = None
        self._sequences: dict[tuple[str, camera_models.FrameKind], int] = {}
        self._focus_camera_id: str | None = None
        self._focus_generation: str | None = None
        self._focus_lease_id: str | None = None
        self._focus_deadline_mono: float | None = None
        self._focus_expires_at: datetime | None = None

    def reset_for_session(self, session_id: str) -> None:
        """Discard camera, frame, sequence, and focus state before accepting another Unity session.

        Args:
            session_id: Unity session that will own subsequent camera reports.
        """
        with self._lock:
            self._session_id = session_id
            # Old-session images cannot be presented as current after a session boundary; this state is not persisted.
            self._catalog.clear()
            self._thumbnails.clear()
            self._focused_frame = None
            self._sequences.clear()
            self._focused_interval_seconds = 0.1
            self._clear_focus()

    def replace_catalog(self, catalog: camera_models.CameraCatalogRequest) -> None:
        """Replace camera definitions while retaining buffers only for still-enabled camera IDs.

        Args:
            catalog: Complete catalog and capture intervals reported by the current Unity session.

        Raises:
            CameraConflictError: If the catalog belongs to another Unity session.

        A zero thumbnail interval uses the existing default. Metadata changes alone do not invalidate retained frames,
        while disabled/removed cameras and invalid focus selections lose their cached state.
        """
        with self._lock:
            self._expire_focus()
            self._require_session(catalog.unity_session_id)
            next_catalog = {}
            for camera in catalog.cameras:
                if camera.thumbnail_interval_seconds == 0:
                    # Zero requests the backend's established interval instead of disabling thumbnail freshness checks.
                    camera = camera.model_copy(
                        update={
                            "thumbnail_interval_seconds": camera_models.DEFAULT_THUMBNAIL_INTERVAL_SECONDS,
                        }
                    )
                next_catalog[camera.camera_id] = camera
            # Retain pixels only for IDs enabled in the new catalog; prior catalog enablement is not required.
            retained = {
                camera_id for camera_id, camera in next_catalog.items() if camera.enabled and camera_id in self._catalog
            }
            self._thumbnails = {
                camera_id: frame for camera_id, frame in self._thumbnails.items() if camera_id in retained
            }
            if self._focused_frame is not None and self._focused_frame.camera_id not in retained:
                self._focused_frame = None
            self._sequences = {key: value for key, value in self._sequences.items() if key[0] in retained}
            self._catalog = next_catalog
            self._focused_interval_seconds = catalog.focused_interval_seconds
            focus_camera = self._focus_camera_id
            if focus_camera is not None:
                definition = self._catalog.get(focus_camera)
                # Catalog changes revoke focus when its selected camera is no longer enabled and focusable.
                if definition is None or not definition.enabled or not definition.allow_focused:
                    self._clear_focus()

    def publish_frame(
        self,
        camera_id: str,
        metadata: camera_models.FrameUpload,
        data: bytes,
    ) -> None:
        """Accept a newer frame only for the current session and camera/focus configuration.

        Args:
            camera_id: Catalog entry that produced the JPEG.
            metadata: Session, sequence, capture time, and optional focus generation.
            data: Complete JPEG bytes, bounded by the HTTP upload route.

        Raises:
            CameraConflictError: If session/focus generation/sequence identity is stale.
            FeedUnavailableError: If the camera is disabled or cannot provide the requested focused feed.
            garage_state.NotFoundError: If the camera is absent from the current catalog.
        """
        with self._lock:
            self._expire_focus()
            self._require_session(metadata.unity_session_id)
            definition = self._catalog.get(camera_id)
            if definition is None:
                raise garage_state.NotFoundError(f"Camera '{camera_id}' does not exist.")
            if not definition.enabled:
                raise FeedUnavailableError(f"Camera '{camera_id}' is disabled.", camera_models.FeedHealth.UNAVAILABLE)
            if metadata.kind == camera_models.FrameKind.FOCUSED:
                if not definition.allow_focused:
                    raise FeedUnavailableError(
                        f"Camera '{camera_id}' cannot be focused.", camera_models.FeedHealth.UNAVAILABLE
                    )
                if (
                    camera_id != self._focus_camera_id
                    or metadata.focus_generation != self._focus_generation
                    or self._focus_generation is None
                ):
                    raise CameraConflictError("Focused frame does not match the active focus generation.")
            # Reject stale frame identity before advancing sequence state or replacing the cached image.
            key = (camera_id, metadata.kind)
            if metadata.sequence <= self._sequences.get(key, 0):
                raise CameraConflictError(
                    f"Frame sequence {metadata.sequence} is not newer than the latest accepted sequence."
                )
            now_mono = self._clock()
            initial_age = max(0.0, (self._utcnow() - metadata.captured_at).total_seconds())
            # ETags track session/camera/kind/sequence/generation identity, not JPEG byte content.
            identity = (
                f"{metadata.unity_session_id}\0{camera_id}\0{metadata.kind.value}\0"
                f"{metadata.sequence}\0{metadata.focus_generation or ''}"
            )
            frame = StoredFrame(
                session_id=metadata.unity_session_id,
                camera_id=camera_id,
                kind=metadata.kind,
                sequence=metadata.sequence,
                captured_at=metadata.captured_at,
                width=metadata.width,
                height=metadata.height,
                data=data,
                received_mono=now_mono,
                initial_age_seconds=initial_age,
                focus_generation=(
                    metadata.focus_generation if metadata.kind == camera_models.FrameKind.FOCUSED else None
                ),
                etag=f'"{hashlib.sha256(identity.encode("utf-8")).hexdigest()}"',
            )
            self._sequences[key] = metadata.sequence
            if metadata.kind == camera_models.FrameKind.THUMBNAIL:
                self._thumbnails[camera_id] = frame
            else:
                self._focused_frame = frame

    def list_cameras(self) -> list[camera_models.CameraView]:
        with self._lock:
            self._expire_focus()
            return [
                camera_models.CameraView(
                    **definition.model_dump(),
                    thumbnail=self._feed_status(definition, camera_models.FrameKind.THUMBNAIL),
                    focused=self._feed_status(definition, camera_models.FrameKind.FOCUSED),
                )
                for definition in self._catalog.values()
            ]

    def get_frame(self, camera_id: str, kind: camera_models.FrameKind) -> tuple[StoredFrame, camera_models.FeedStatus]:
        """Return the retained frame and its current age/health without renewing viewer focus.

        Args:
            camera_id: Catalog camera whose image is requested.
            kind: Thumbnail or currently focused image.

        Returns:
            The cached frame and status computed at retrieval time; stale frames remain readable.

        Raises:
            garage_state.NotFoundError: If the camera is unknown.
            FeedUnavailableError: If the camera/feed is unavailable or has no cached frame.
        """
        with self._lock:
            self._expire_focus()
            definition = self._catalog.get(camera_id)
            if definition is None:
                raise garage_state.NotFoundError(f"Camera '{camera_id}' does not exist.")
            if not definition.enabled:
                raise FeedUnavailableError(f"Camera '{camera_id}' is disabled.", camera_models.FeedHealth.UNAVAILABLE)
            if kind == camera_models.FrameKind.THUMBNAIL:
                frame = self._thumbnails.get(camera_id)
            else:
                if not definition.allow_focused or camera_id != self._focus_camera_id:
                    raise FeedUnavailableError(
                        f"Focused feed for camera '{camera_id}' is unavailable.",
                        camera_models.FeedHealth.UNAVAILABLE,
                    )
                frame = self._focused_frame
                if frame is not None and frame.focus_generation != self._focus_generation:
                    frame = None
            if frame is None:
                raise FeedUnavailableError(
                    f"{kind.value.title()} feed for camera '{camera_id}' has no frame.",
                    camera_models.FeedHealth.NO_FRAME,
                )
            return frame, self._status_for_frame(definition, kind, frame)

    def acquire_focus(self, camera_id: str, lease_id: str | None) -> camera_models.FocusLease:
        """Acquire or renew a focus lease and return the focused capture generation.

        Args:
            camera_id: Enabled camera that permits focused capture.
            lease_id: Current viewer's ownership token when renewing or switching; omit for a new lease.

        Returns:
            The viewer lease and the capture generation Unity must use for focused uploads.

        Raises:
            garage_state.NotFoundError: If the camera is unknown.
            FeedUnavailableError: If the camera cannot be focused.
            CameraConflictError: If the supplied lease does not own the current focus.

        Same-camera renewal preserves generation; new leases and camera switches create a fresh generation. The viewer
        lease proves ownership, while the separate generation binds uploads to the selected capture.
        """
        with self._lock:
            self._expire_focus()
            self._camera_for_focus(camera_id)
            if self._focus_lease_id is None:
                if lease_id is not None:
                    raise CameraConflictError("Focus lease is no longer active; acquire focus without a lease id.")
                lease_id = uuid.uuid4().hex
                self._focus_generation = uuid.uuid4().hex
                self._focus_lease_id = lease_id
                self._focus_camera_id = camera_id
            else:
                if lease_id != self._focus_lease_id:
                    raise CameraConflictError("Focused camera is controlled by another viewer.")
                if camera_id != self._focus_camera_id:
                    # Switching cameras invalidates the old image and rotates the generation Unity must stamp on frames.
                    self._focused_frame = None
                    self._focus_generation = uuid.uuid4().hex
                    self._focus_camera_id = camera_id
            self._focus_deadline_mono = self._clock() + FOCUS_LEASE_SECONDS
            self._focus_expires_at = self._utcnow() + timedelta(seconds=FOCUS_LEASE_SECONDS)
            return camera_models.FocusLease(
                camera_id=camera_id,
                focus_generation=self._focus_generation,
                expires_at=self._focus_expires_at,
                lease_id=self._focus_lease_id,
            )

    def release_focus(self, lease_id: str | None) -> None:
        """Release focus only when the supplied token owns it; releasing an inactive lease is a no-op.

        Args:
            lease_id: Current viewer's focus ownership token.

        Raises:
            CameraConflictError: If another viewer owns the active focus lease.
        """
        with self._lock:
            self._expire_focus()
            if self._focus_lease_id is None:
                return
            if lease_id != self._focus_lease_id:
                raise CameraConflictError("Focused camera is controlled by another viewer.")
            self._clear_focus()

    def focus_state(self) -> camera_models.FocusState:
        with self._lock:
            self._expire_focus()
            return self._focus_state()

    def control(self, session_id: str) -> camera_models.FocusState:
        """Return capture control state for the current Unity session.

        Args:
            session_id: Unity session requesting focus-control state.

        Returns:
            The current camera and capture generation, if focus is active.

        Raises:
            CameraConflictError: If the request does not match the current session.
        """
        with self._lock:
            self._expire_focus()
            self._require_session(session_id)
            return self._focus_state()

    def _camera_for_focus(self, camera_id: str) -> camera_models.CameraDefinition:
        definition = self._catalog.get(camera_id)
        if definition is None:
            raise garage_state.NotFoundError(f"Camera '{camera_id}' does not exist.")
        if not definition.enabled or not definition.allow_focused:
            raise FeedUnavailableError(f"Camera '{camera_id}' cannot be focused.", camera_models.FeedHealth.UNAVAILABLE)
        return definition

    def _require_session(self, session_id: str) -> None:
        if self._session_id is None or session_id != self._session_id:
            raise CameraConflictError("Camera request does not match the current Unity session.")

    def _expire_focus(self) -> None:
        # Expiry is lazy: the next service operation clears the lease; there is no background timer.
        if self._focus_deadline_mono is not None and self._clock() >= self._focus_deadline_mono:
            self._clear_focus()

    def _clear_focus(self) -> None:
        self._focus_camera_id = None
        self._focus_generation = None
        self._focus_lease_id = None
        self._focus_deadline_mono = None
        self._focus_expires_at = None
        self._focused_frame = None

    def _focus_state(self) -> camera_models.FocusState:
        return camera_models.FocusState(
            camera_id=self._focus_camera_id,
            focus_generation=self._focus_generation,
            expires_at=self._focus_expires_at,
        )

    def _feed_status(
        self,
        definition: camera_models.CameraDefinition,
        kind: camera_models.FrameKind,
    ) -> camera_models.FeedStatus:
        if not definition.enabled or (
            kind == camera_models.FrameKind.FOCUSED
            and (not definition.allow_focused or definition.camera_id != self._focus_camera_id)
        ):
            return camera_models.FeedStatus(health=camera_models.FeedHealth.UNAVAILABLE)
        frame = (
            self._thumbnails.get(definition.camera_id)
            if kind == camera_models.FrameKind.THUMBNAIL
            else self._focused_frame
        )
        if frame is None or (
            kind == camera_models.FrameKind.FOCUSED and frame.focus_generation != self._focus_generation
        ):
            return camera_models.FeedStatus(health=camera_models.FeedHealth.NO_FRAME)
        return self._status_for_frame(definition, kind, frame)

    def _status_for_frame(
        self,
        definition: camera_models.CameraDefinition,
        kind: camera_models.FrameKind,
        frame: StoredFrame,
    ) -> camera_models.FeedStatus:
        # Preserve capture age but use monotonic elapsed time thereafter, avoiding wall-clock changes after receipt.
        age_seconds = max(
            0.0,
            frame.initial_age_seconds + self._clock() - frame.received_mono,
        )
        interval = (
            definition.thumbnail_interval_seconds
            if kind == camera_models.FrameKind.THUMBNAIL
            else self._focused_interval_seconds
        )
        health = camera_models.FeedHealth.FRESH if age_seconds <= interval * 3 else camera_models.FeedHealth.STALE
        return camera_models.FeedStatus(
            health=health,
            sequence=frame.sequence,
            captured_at=frame.captured_at,
            age_ms=int(age_seconds * 1000),
            width=frame.width,
            height=frame.height,
        )
