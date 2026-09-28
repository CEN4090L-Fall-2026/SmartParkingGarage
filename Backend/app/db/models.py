from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..domain.states import ParkingSpaceState, ParkingSpaceType


def enum_values(
    enum_type: type[ParkingSpaceState] | type[ParkingSpaceType],
) -> list[str]:
    return [member.value for member in enum_type]


class Base(DeclarativeBase):
    pass


class ParkingSpaceModel(Base):
    __tablename__ = "parking_spaces"

    space_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    parking_space_type: Mapped[ParkingSpaceType] = mapped_column(
        Enum(
            ParkingSpaceType,
            name="parking_space_type",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    is_type_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    state: Mapped[ParkingSpaceState] = mapped_column(
        Enum(
            ParkingSpaceState,
            name="parking_space_state",
            values_callable=enum_values,
        ),
        nullable=False,
    )


class ParkingAssignmentModel(Base):
    __tablename__ = "parking_assignments"

    requester_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    space_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
