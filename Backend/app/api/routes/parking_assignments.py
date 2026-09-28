from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import ParkingAssignmentModel, ParkingSpaceModel
from ...db.session import get_db_session
from ...domain.states import ParkingSpaceState, ParkingSpaceType
from ...schemas.parking_assignment import (
    ParkingAssignmentRelease,
    ParkingAssignmentRequest,
    ParkingAssignmentSnapshot,
)

router = APIRouter(prefix="/parking-assignments", tags=["parking assignments"])


def to_snapshot(
    requester_id: str,
    space: ParkingSpaceModel,
) -> ParkingAssignmentSnapshot:
    return ParkingAssignmentSnapshot(
        requester_id=requester_id,
        space_id=space.space_id,
        level=space.level,
        parking_space_type=space.parking_space_type,
        is_type_resolved=space.is_type_resolved,
    )


@router.post("", response_model=ParkingAssignmentSnapshot, status_code=201)
async def create_parking_assignment(
    request: ParkingAssignmentRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ParkingAssignmentSnapshot:
    existing_assignment = await session.get(
        ParkingAssignmentModel,
        request.requester_id,
    )
    if existing_assignment is not None:
        raise HTTPException(status_code=409, detail="Requester already assigned")

    conditions = [ParkingSpaceModel.state == ParkingSpaceState.AVAILABLE]
    if request.preferred_level is not None:
        conditions.append(ParkingSpaceModel.level == request.preferred_level)

    required_type = request.required_type or ParkingSpaceType.STANDARD
    conditions.append(ParkingSpaceModel.parking_space_type == required_type)
    if required_type in {ParkingSpaceType.EV, ParkingSpaceType.ACCESSIBLE}:
        conditions.append(ParkingSpaceModel.is_type_resolved.is_(True))

    statement = (
        select(ParkingSpaceModel)
        .where(*conditions)
        .order_by(ParkingSpaceModel.level, ParkingSpaceModel.space_id)
        .with_for_update()
    )
    space = await session.scalar(statement)
    if space is None:
        raise HTTPException(
            status_code=409,
            detail="No matching available parking space",
        )

    space.state = ParkingSpaceState.RESERVED
    session.add(
        ParkingAssignmentModel(
            requester_id=request.requester_id,
            space_id=space.space_id,
        )
    )
    await session.commit()
    return to_snapshot(request.requester_id, space)


@router.delete(
    "/{requester_id}",
    response_model=ParkingAssignmentRelease,
)
async def release_parking_assignment(
    requester_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ParkingAssignmentRelease:
    assignment = await session.get(ParkingAssignmentModel, requester_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    space = await session.get(ParkingSpaceModel, assignment.space_id)
    if space.state == ParkingSpaceState.RESERVED:
        space.state = ParkingSpaceState.AVAILABLE

    await session.delete(assignment)
    await session.commit()
    return ParkingAssignmentRelease(
        requester_id=requester_id,
        space_id=space.space_id,
        state=space.state,
    )
