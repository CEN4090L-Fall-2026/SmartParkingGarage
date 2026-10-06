from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api.routes import garage, health, simulation, spaces, vehicles
from .api.routes import integration as integration_routes
from .services.garage_state import GarageStateService, NotFoundError
from .services.integration import (
    IntegrationService,
    SessionMismatchError,
    StaleSnapshotError,
    UnityOfflineError,
)

# Explicit local development origins for future React clients; deliberately not "*".
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def create_app(
    service: GarageStateService | None = None,
    integration: IntegrationService | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Smart Parking Garage Backend",
        version=__version__,
        description=(
            "REST API and shared contracts. Unity is authoritative for live simulation state and reports it "
            "via /api/integration; commands are queued here and executed by Unity."
        ),
    )
    app.state.garage_service = service or GarageStateService()
    app.state.integration_service = integration or IntegrationService(
        app.state.garage_service
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Data-Source"],
    )

    @app.exception_handler(NotFoundError)
    def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"success": False, "message": str(exc)}
        )

    @app.exception_handler(UnityOfflineError)
    def _offline(request: Request, exc: UnityOfflineError) -> JSONResponse:
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

    @app.exception_handler(StaleSnapshotError)
    def _stale(request: Request, exc: StaleSnapshotError) -> JSONResponse:
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

    @app.exception_handler(SessionMismatchError)
    def _session(request: Request, exc: SessionMismatchError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"success": False, "message": str(exc)}
        )

    for module in (health, garage, spaces, vehicles, simulation, integration_routes):
        app.include_router(module.router)
    return app


app = create_app()
