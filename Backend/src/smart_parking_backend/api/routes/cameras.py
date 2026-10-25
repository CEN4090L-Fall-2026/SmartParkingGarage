import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from smart_parking_backend.api import deps
from smart_parking_backend.models import cameras as camera_models
from smart_parking_backend.services import cctv, garage_state
from smart_parking_backend.services import integration as integration_service

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

_STREAM_BOUNDARY = "frame"
_STREAM_POLL_SECONDS = 0.05


@router.get("", response_model=list[camera_models.CameraView])
def list_cameras(
    service: Annotated[cctv.CCTVService, Depends(deps.get_cctv)],
) -> list[camera_models.CameraView]:
    return service.list_cameras()


@router.get("/focus", response_model=camera_models.FocusState)
def get_focus(
    service: Annotated[cctv.CCTVService, Depends(deps.get_cctv)],
) -> camera_models.FocusState:
    return service.focus_state()


@router.post(
    "/{camera_id}/focus",
    response_model=camera_models.FocusLease,
    responses={
        404: {"description": "Unknown camera."},
        409: {"description": "Focus is owned by another viewer."},
        503: {"description": "Unity or the requested feed is unavailable."},
    },
)
def acquire_focus(
    camera_id: str,
    service: Annotated[cctv.CCTVService, Depends(deps.get_cctv)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
    request: Annotated[camera_models.FocusRequest | None, Body()] = None,
) -> camera_models.FocusLease:
    if not integration.is_connected():
        raise integration_service.UnityOfflineError("Unity is not connected; camera focus was not changed.")
    return service.acquire_focus(camera_id, request.lease_id if request is not None else None)


@router.delete("/focus", status_code=status.HTTP_204_NO_CONTENT)
def release_focus(
    service: Annotated[cctv.CCTVService, Depends(deps.get_cctv)],
    lease_id: Annotated[str | None, Header(alias="X-Focus-Lease-Id")] = None,
) -> Response:
    service.release_focus(lease_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _etag_matches(header: str | None, etag: str) -> bool:
    if header is None:
        return False
    for candidate in header.split(","):
        candidate = candidate.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:].strip()
        if candidate == etag:
            return True
    return False


def _frame_headers(frame: cctv.StoredFrame, feed: camera_models.FeedStatus) -> dict[str, str]:
    return {
        "ETag": frame.etag,
        "X-Unity-Session-Id": frame.session_id,
        "X-Frame-Sequence": str(frame.sequence),
        "X-Captured-At": frame.captured_at.isoformat().replace("+00:00", "Z"),
        "X-Frame-Age-Ms": str(feed.age_ms),
        "X-Feed-Health": feed.health.value,
        "X-Frame-Width": str(frame.width),
        "X-Frame-Height": str(frame.height),
    }


@router.get("/{camera_id}/frame")
def get_frame(
    camera_id: str,
    request: Request,
    service: Annotated[cctv.CCTVService, Depends(deps.get_cctv)],
    kind: Annotated[camera_models.FrameKind, Query()] = camera_models.FrameKind.THUMBNAIL,
) -> Response:
    frame, feed = service.get_frame(camera_id, kind)
    headers = _frame_headers(frame, feed)
    headers["Cache-Control"] = "private, no-cache"
    if _etag_matches(request.headers.get("if-none-match"), frame.etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=frame.data, media_type="image/jpeg", headers=headers)


async def _focused_frames(
    service: cctv.CCTVService,
    camera_id: str,
    session_id: str,
    focus_generation: str | None,
) -> AsyncIterator[bytes]:
    last_etag = None
    while True:
        try:
            frame, feed = service.get_frame(camera_id, camera_models.FrameKind.FOCUSED)
        except (garage_state.NotFoundError, cctv.FeedUnavailableError):
            break
        if frame.session_id != session_id or frame.focus_generation != focus_generation:
            break
        if frame.etag != last_etag:
            headers = {
                "Content-Type": "image/jpeg",
                "Content-Length": str(len(frame.data)),
                **_frame_headers(frame, feed),
            }
            part_headers = "\r\n".join(f"{key}: {value}" for key, value in headers.items())
            yield f"--{_STREAM_BOUNDARY}\r\n{part_headers}\r\n\r\n".encode("ascii")
            yield frame.data
            yield b"\r\n"
            last_etag = frame.etag
        await asyncio.sleep(_STREAM_POLL_SECONDS)
    yield f"--{_STREAM_BOUNDARY}--\r\n".encode("ascii")


@router.get(
    "/{camera_id}/stream",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"multipart/x-mixed-replace": {}}, "description": "Focused MJPEG stream."},
        404: {"description": "Unknown camera."},
        503: {"description": "Focused feed is unavailable or has no frame."},
    },
)
def stream_focused(
    camera_id: str,
    service: Annotated[cctv.CCTVService, Depends(deps.get_cctv)],
) -> StreamingResponse:
    frame, _ = service.get_frame(camera_id, camera_models.FrameKind.FOCUSED)
    return StreamingResponse(
        _focused_frames(service, camera_id, frame.session_id, frame.focus_generation),
        media_type=f"multipart/x-mixed-replace; boundary={_STREAM_BOUNDARY}",
        headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"},
    )
