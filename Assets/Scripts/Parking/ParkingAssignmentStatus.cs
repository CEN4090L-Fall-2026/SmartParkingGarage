namespace SmartParkingGarage
{
    public enum ParkingAssignmentStatus
    {
        Assigned,
        Released,
        ReleasedStatePreserved,
        NotInitialized,
        InvalidRequesterId,
        InvalidLevel,
        InvalidType,
        AlreadyAssigned,
        NoMatchingAvailableSpace,
        UnknownRequester,
        StateChangeFailed,
        OperationInProgress,
        AssignedSpaceMissing
    }
}
