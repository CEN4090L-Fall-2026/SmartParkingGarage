using System;

namespace SmartParkingGarage
{
    public sealed class ParkingAssignmentRequest
    {
        public string RequesterId { get; }
        public int? PreferredLevel { get; }
        public ParkingSpaceType? RequiredType { get; }

        public ParkingAssignmentRequest(string requesterId, int? preferredLevel = null, ParkingSpaceType? requiredType = null)
        {
            RequesterId = requesterId;
            PreferredLevel = preferredLevel;
            RequiredType = requiredType;
        }
    }
}
