from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from smart_parking_backend.api import deps
from smart_parking_backend.models import cameras as camera_models
from smart_parking_backend.services import cctv
from smart_parking_backend.services import integration as integration_service

router = APIRouter(prefix="/api/integration/cameras", tags=["camera integration"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
def replace_camera_catalog(
    catalog: camera_models.CameraCatalogRequest,
    service: Annotated[cctv.CCTVService, Depends(deps.get_cctv)],
) -> Response:
    service.replace_catalog(catalog)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{camera_id}/frames",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"description": "Unknown camera."},
        409: {"description": "Wrong session or stale frame."},
        413: {"description": "JPEG exceeds the 2 MiB upload limit."},
        415: {"description": "Content-Type must be image/jpeg."},
        503: {"description": "Camera is unavailable."},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "image/jpeg": {
                    "schema": {"type": "string", "format": "binary", "maxLength": camera_models.MAX_FRAME_BYTES},
                },
            },
        },
    },
)
async def publish_frame(
    camera_id: str,
    request: Request,
    metadata: Annotated[camera_models.FrameUpload, Query()],
    service: Annotated[cctv.CCTVService, Depends(deps.get_cctv)],
) -> Response:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "image/jpeg":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Content-Type must be image/jpeg."
        )
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > camera_models.MAX_FRAME_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="JPEG exceeds the 2 MiB upload limit."
        )
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > camera_models.MAX_FRAME_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="JPEG exceeds the 2 MiB upload limit."
            )
        data.extend(chunk)
    service.publish_frame(camera_id, metadata, bytes(data))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/control", response_model=camera_models.CameraControl)
def get_camera_control(
    unity_session_id: Annotated[str, Query(min_length=1, max_length=64)],
    service: Annotated[cctv.CCTVService, Depends(deps.get_cctv)],
    integration: Annotated[integration_service.IntegrationService, Depends(deps.get_integration)],
) -> camera_models.CameraControl:
    focus = service.control(unity_session_id)
    return camera_models.CameraControl(
        unity_session_id=unity_session_id,
        backend_instance_id=integration.backend_instance_id,
        focus=focus,
    )
