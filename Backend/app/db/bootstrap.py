import json
from pathlib import Path

from sqlalchemy import select

from ..domain.states import ParkingSpaceState, ParkingSpaceType
from .models import Base, ParkingSpaceModel
from .session import AsyncSessionFactory, engine

INVENTORY_PATH = Path(__file__).parents[1] / "data" / "unity_inventory.json"


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    async with AsyncSessionFactory() as session:
        existing_ids = set(await session.scalars(select(ParkingSpaceModel.space_id)))
        session.add_all(
            ParkingSpaceModel(
                space_id=space["space_id"],
                level=space["level_number"],
                parking_space_type=ParkingSpaceType(space["parking_space_type"]),
                is_type_resolved=space["is_type_resolved"],
                state=ParkingSpaceState.AVAILABLE,
            )
            for space in inventory["spaces"]
            if space["space_id"] not in existing_ids
        )
        await session.commit()
