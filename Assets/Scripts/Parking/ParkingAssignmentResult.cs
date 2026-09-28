namespace SmartParkingGarage
{
    public sealed class ParkingAssignmentResult
    {
        public ParkingAssignmentStatus Status { get; }
        public bool Succeeded => Status == ParkingAssignmentStatus.Assigned || Status == ParkingAssignmentStatus.Released || Status == ParkingAssignmentStatus.ReleasedStatePreserved;
        public ParkingAssignment Assignment { get; }
        public ParkingSpaceState? StateAfterOperation { get; }

        public ParkingAssignmentResult(ParkingAssignmentStatus status, ParkingAssignment assignment = null, ParkingSpaceState? stateAfterOperation = null)
        {
            Status = status;
            Assignment = assignment;
            StateAfterOperation = stateAfterOperation;
        }
    }
}
