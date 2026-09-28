namespace SmartParkingGarage
{
    public sealed class ParkingAssignment
    {
        public string RequesterId { get; }
        public string SpaceId { get; }
        public int Level { get; }
        public ParkingSpaceType Type { get; }
        public bool IsTypeResolved { get; }

        public ParkingAssignment(string requesterId, ParkingSpace space)
        {
            RequesterId = requesterId;
            SpaceId = space.SpaceId;
            Level = space.Level;
            Type = space.Type;
            IsTypeResolved = space.IsTypeResolved;
        }
    }
}
