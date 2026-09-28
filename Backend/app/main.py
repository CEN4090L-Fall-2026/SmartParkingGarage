from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes.health import router as health_router
from .api.routes.parking_assignments import router as parking_assignments_router
from .api.routes.parking_spaces import router as parking_spaces_router
from .db.bootstrap import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await initialize_database()
    yield


app = FastAPI(
    title="Smart Parking Garage API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(parking_spaces_router)
app.include_router(parking_assignments_router)
app.include_router(health_router)
