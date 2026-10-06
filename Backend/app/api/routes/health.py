from fastapi import APIRouter
from pydantic import BaseModel

from ... import SERVICE_NAME, __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=__version__)
