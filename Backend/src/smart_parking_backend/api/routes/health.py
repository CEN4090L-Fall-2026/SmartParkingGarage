from fastapi import APIRouter
from pydantic import BaseModel

import smart_parking_backend

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok", service=smart_parking_backend.SERVICE_NAME, version=smart_parking_backend.__version__
    )
