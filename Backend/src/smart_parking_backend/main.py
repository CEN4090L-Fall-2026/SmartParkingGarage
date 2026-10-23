from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import smart_parking_backend
from smart_parking_backend.api.routes import (
    camera_integration,
    cameras,
    garage,
    health,
    simulation,
    spaces,
    vehicles,
)
from smart_parking_backend.api.routes import integration as integration_routes
from smart_parking_backend.services import cctv as cctv_service
from smart_parking_backend.services import garage_state
from smart_parking_backend.services import integration as integration_service

# Explicit local development origins for future React clients; deliberately not "*".
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def create_app(
    service: garage_state.GarageStateService | None = None,
    integration: integration_service.IntegrationService | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Smart Parking Garage Backend",
        version=smart_parking_backend.__version__,
        description=(
            "REST API and shared contracts. Unity is authoritative for live simulation state and reports it "
            "via /api/integration; commands are queued here and executed by Unity."
        ),
    )
    app.state.garage_service = service or garage_state.GarageStateService()
    app.state.integration_service = integration or integration_service.IntegrationService(app.state.garage_service)
    app.state.cctv_service = app.state.integration_service.cctv_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[
            "X-Data-Source",
            "ETag",
            "X-Unity-Session-Id",
            "X-Frame-Sequence",
            "X-Captured-At",
            "X-Frame-Age-Ms",
            "X-Feed-Health",
            "X-Frame-Width",
            "X-Frame-Height",
        ],
    )

    @app.exception_handler(garage_state.NotFoundError)
    def _not_found(request: Request, exc: garage_state.NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"success": False, "message": str(exc)})

    @app.exception_handler(integration_service.UnityOfflineError)
    def _offline(request: Request, exc: integration_service.UnityOfflineError) -> JSONResponse:
        source = request.app.state.integration_service.data_source().value
        state = request.app.state.garage_service.last_known_state()
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": str(exc),
                "current_state": state,
                "data_source": source,
            },
        )

    @app.exception_handler(integration_service.StaleSnapshotError)
    def _stale(request: Request, exc: integration_service.StaleSnapshotError) -> JSONResponse:
        integ = request.app.state.integration_service
        return JSONResponse(
            status_code=409,
            content={
                "accepted": False,
                "message": str(exc),
                "latest_sequence": exc.latest_sequence,
                "backend_instance_id": integ.backend_instance_id,
            },
        )

    @app.exception_handler(integration_service.SessionMismatchError)
    def _session(request: Request, exc: integration_service.SessionMismatchError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"success": False, "message": str(exc)})

    @app.exception_handler(cctv_service.CameraConflictError)
    def _camera_conflict(request: Request, exc: cctv_service.CameraConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"success": False, "message": str(exc)})

    @app.exception_handler(cctv_service.FeedUnavailableError)
    def _feed_unavailable(request: Request, exc: cctv_service.FeedUnavailableError) -> JSONResponse:
        headers = {"X-Feed-Health": exc.health.value}
        if exc.age_ms is not None:
            headers["X-Frame-Age-Ms"] = str(exc.age_ms)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": str(exc),
                "health": exc.health.value,
                "age_ms": exc.age_ms,
            },
            headers=headers,
        )

    for module in (
        health,
        garage,
        spaces,
        vehicles,
        simulation,
        integration_routes,
        cameras,
        camera_integration,
    ):
        app.include_router(module.router)
    return app


app = create_app()
