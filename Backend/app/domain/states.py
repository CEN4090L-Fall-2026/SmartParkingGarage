from enum import StrEnum


class ParkingSpaceState(StrEnum):
    AVAILABLE = "Available"
    OCCUPIED = "Occupied"
    RESERVED = "Reserved"
    OUT_OF_SERVICE = "OutOfService"


class ParkingSpaceType(StrEnum):
    STANDARD = "Standard"
    ACCESSIBLE = "Accessible"
    EV = "EV"
