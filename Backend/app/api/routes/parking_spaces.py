from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import ParkingSpaceModel
from ...db.session import get_db_session
from ...schemas.parking_space import (
    ParkingSpaceSnapshot,
    ParkingSpaceSnapshotCollection,
    ParkingSpaceStateChangeRequest,
)

router = APIRouter(prefix="/parking-spaces", tags=["parking spaces"])


def to_snapshot(space: ParkingSpaceModel) -> ParkingSpaceSnapshot:
    return ParkingSpaceSnapshot(
        space_id=space.space_id,
        level=space.level,
        parking_space_type=space.parking_space_type,
        is_type_resolved=space.is_type_resolved,
        state=space.state,
    )


@router.get("", response_model=ParkingSpaceSnapshotCollection)
async def list_parking_spaces(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ParkingSpaceSnapshotCollection:
    spaces = await session.scalars(
        select(ParkingSpaceModel).order_by(
            ParkingSpaceModel.level,
            ParkingSpaceModel.space_id,
        )
    )
    return ParkingSpaceSnapshotCollection(
        spaces=[to_snapshot(space) for space in spaces]
    )


@router.patch(
    "/{space_id}/state",
    response_model=ParkingSpaceSnapshot,
)
async def update_parking_space_state(
    space_id: str,
    request: ParkingSpaceStateChangeRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ParkingSpaceSnapshot:
    space = await session.get(ParkingSpaceModel, space_id)
    space.state = request.state
    await session.commit()
    return to_snapshot(space)
