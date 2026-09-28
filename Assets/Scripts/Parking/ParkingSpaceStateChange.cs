namespace SmartParkingGarage
{
    public readonly struct ParkingSpaceStateChange
    {
        public readonly string SpaceId;
        public readonly int Level;
        public readonly ParkingSpaceType Type;
        public readonly ParkingSpaceState PreviousState;
        public readonly ParkingSpaceState CurrentState;

        public ParkingSpaceStateChange(string spaceId, int level, ParkingSpaceType type, ParkingSpaceState previousState, ParkingSpaceState currentState)
        {
            SpaceId = spaceId;
            Level = level;
            Type = type;
            PreviousState = previousState;
            CurrentState = currentState;
        }
    }
}
