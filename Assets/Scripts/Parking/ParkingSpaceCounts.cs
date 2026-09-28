namespace SmartParkingGarage
{
    public readonly struct ParkingSpaceCounts
    {
        public readonly int Available;
        public readonly int Occupied;
        public readonly int Reserved;
        public readonly int OutOfService;
        public int Total => Available + Occupied + Reserved + OutOfService;

        public ParkingSpaceCounts(int available, int occupied, int reserved, int outOfService)
        {
            Available = available;
            Occupied = occupied;
            Reserved = reserved;
            OutOfService = outOfService;
        }
    }
}
