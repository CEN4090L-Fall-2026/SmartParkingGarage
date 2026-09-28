using System;
using System.Collections.Generic;
using UnityEngine;

namespace SmartParkingGarage
{
    public sealed class ParkingAssignmentManager : MonoBehaviour
    {
        [SerializeField] private ParkingSpaceRegistry registry;

        private readonly List<ParkingSpace> candidates = new List<ParkingSpace>();
        private readonly Dictionary<string, ParkingAssignment> assignmentsByRequester = new Dictionary<string, ParkingAssignment>(StringComparer.Ordinal);
        private readonly Dictionary<string, ParkingAssignment> assignmentsBySpace = new Dictionary<string, ParkingAssignment>(StringComparer.Ordinal);
        private bool initialized;
        private bool operationInProgress;

        public bool IsInitialized => initialized;
        public int ActiveAssignmentCount => assignmentsByRequester.Count;
        public event Action<ParkingAssignment> AssignmentCreated;
        public event Action<ParkingAssignmentResult> AssignmentReleased;

        private void OnEnable()
        {
            if (registry == null) return;
            registry.Initialized += HandleRegistryInitialized;
            if (registry.IsInitialized) Initialize();
        }

        private void OnDisable()
        {
            if (registry != null) registry.Initialized -= HandleRegistryInitialized;
        }

        private void HandleRegistryInitialized() => Initialize();

        public void Initialize()
        {
            if (initialized || registry == null || !registry.IsInitialized) return;
            if (registry.TotalSpaces != 414)
            {
                Debug.LogError($"ParkingAssignmentManager requires 414 registry spaces; found {registry.TotalSpaces}.", this);
                return;
            }
            candidates.Clear();
            HashSet<string> ids = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < registry.Spaces.Count; i++)
            {
                ParkingSpace space = registry.Spaces[i];
                if (space == null || string.IsNullOrEmpty(space.SpaceId) || !ids.Add(space.SpaceId) || space.Level < 1 || space.Level > 4 || !Enum.IsDefined(typeof(ParkingSpaceType), space.Type))
                {
                    Debug.LogError("ParkingAssignmentManager could not validate the ParkingSpaceRegistry candidate list.", this);
                    candidates.Clear();
                    return;
                }
                candidates.Add(space);
            }
            candidates.Sort(CompareSpaces);
            initialized = true;
        }

        public ParkingAssignmentResult RequestAssignment(ParkingAssignmentRequest request)
        {
            if (!initialized || registry == null || !registry.IsInitialized) return new ParkingAssignmentResult(ParkingAssignmentStatus.NotInitialized);
            if (operationInProgress) return new ParkingAssignmentResult(ParkingAssignmentStatus.OperationInProgress);
            if (request == null) return new ParkingAssignmentResult(ParkingAssignmentStatus.InvalidRequesterId);
            string requesterId = request?.RequesterId?.Trim();
            if (string.IsNullOrEmpty(requesterId)) return new ParkingAssignmentResult(ParkingAssignmentStatus.InvalidRequesterId);
            if (request.PreferredLevel.HasValue && (request.PreferredLevel.Value < 1 || request.PreferredLevel.Value > 4)) return new ParkingAssignmentResult(ParkingAssignmentStatus.InvalidLevel);
            if (request.RequiredType.HasValue && !Enum.IsDefined(typeof(ParkingSpaceType), request.RequiredType.Value)) return new ParkingAssignmentResult(ParkingAssignmentStatus.InvalidType);
            if (assignmentsByRequester.ContainsKey(requesterId)) return new ParkingAssignmentResult(ParkingAssignmentStatus.AlreadyAssigned, assignmentsByRequester[requesterId]);

            ParkingSpace selected = SelectCandidate(request);
            if (selected == null) return new ParkingAssignmentResult(ParkingAssignmentStatus.NoMatchingAvailableSpace);

            operationInProgress = true;
            ParkingAssignment assignment = new ParkingAssignment(requesterId, selected);
            assignmentsByRequester.Add(requesterId, assignment);
            assignmentsBySpace.Add(selected.SpaceId, assignment);
            try
            {
                if (!registry.TrySetState(selected.SpaceId, ParkingSpaceState.Reserved))
                {
                    assignmentsByRequester.Remove(requesterId);
                    assignmentsBySpace.Remove(selected.SpaceId);
                    return new ParkingAssignmentResult(ParkingAssignmentStatus.StateChangeFailed, assignment, selected.State);
                }
                ParkingAssignmentCreated(assignment);
                return new ParkingAssignmentResult(ParkingAssignmentStatus.Assigned, assignment, selected.State);
            }
            finally
            {
                operationInProgress = false;
            }
        }

        public bool TryGetAssignment(string requesterId, out ParkingAssignment assignment)
        {
            assignment = null;
            if (string.IsNullOrWhiteSpace(requesterId)) return false;
            return assignmentsByRequester.TryGetValue(requesterId.Trim(), out assignment);
        }

        public ParkingAssignmentResult ReleaseAssignment(string requesterId)
        {
            if (!initialized || registry == null || !registry.IsInitialized) return new ParkingAssignmentResult(ParkingAssignmentStatus.NotInitialized);
            if (operationInProgress) return new ParkingAssignmentResult(ParkingAssignmentStatus.OperationInProgress);
            requesterId = requesterId?.Trim();
            if (string.IsNullOrEmpty(requesterId)) return new ParkingAssignmentResult(ParkingAssignmentStatus.InvalidRequesterId);
            if (!assignmentsByRequester.TryGetValue(requesterId, out ParkingAssignment assignment)) return new ParkingAssignmentResult(ParkingAssignmentStatus.UnknownRequester);
            if (!registry.TryGetSpace(assignment.SpaceId, out ParkingSpace space) || space == null) return new ParkingAssignmentResult(ParkingAssignmentStatus.AssignedSpaceMissing, assignment);

            operationInProgress = true;
            try
            {
                if (space.State == ParkingSpaceState.Reserved)
                {
                    if (!registry.TrySetState(space.SpaceId, ParkingSpaceState.Available)) return new ParkingAssignmentResult(ParkingAssignmentStatus.StateChangeFailed, assignment, space.State);
                    RemoveAssignment(assignment);
                    ParkingAssignmentResult result = new ParkingAssignmentResult(ParkingAssignmentStatus.Released, assignment, space.State);
                    AssignmentReleased?.Invoke(result);
                    return result;
                }

                RemoveAssignment(assignment);
                ParkingAssignmentResult preserved = new ParkingAssignmentResult(ParkingAssignmentStatus.ReleasedStatePreserved, assignment, space.State);
                AssignmentReleased?.Invoke(preserved);
                return preserved;
            }
            finally
            {
                operationInProgress = false;
            }
        }

        public void GetActiveAssignments(List<ParkingAssignment> results)
        {
            if (results == null) throw new ArgumentNullException(nameof(results));
            results.Clear();
            foreach (ParkingAssignment assignment in assignmentsByRequester.Values) results.Add(assignment);
            results.Sort((a, b) => string.CompareOrdinal(a.RequesterId, b.RequesterId));
        }

        private ParkingSpace SelectCandidate(ParkingAssignmentRequest request)
        {
            for (int i = 0; i < candidates.Count; i++)
            {
                ParkingSpace space = candidates[i];
                if (space.State != ParkingSpaceState.Available || assignmentsBySpace.ContainsKey(space.SpaceId)) continue;
                if (request.PreferredLevel.HasValue && space.Level != request.PreferredLevel.Value) continue;
                if (!QualifiesByType(space, request.RequiredType)) continue;
                return space;
            }
            return null;
        }

        private static bool QualifiesByType(ParkingSpace space, ParkingSpaceType? requiredType)
        {
            if (!requiredType.HasValue) return space.Type == ParkingSpaceType.Standard;
            if (requiredType.Value == ParkingSpaceType.EV) return space.Type == ParkingSpaceType.EV && space.IsTypeResolved;
            if (requiredType.Value == ParkingSpaceType.Accessible) return space.Type == ParkingSpaceType.Accessible && space.IsTypeResolved;
            return space.Type == ParkingSpaceType.Standard;
        }

        private void RemoveAssignment(ParkingAssignment assignment)
        {
            assignmentsByRequester.Remove(assignment.RequesterId);
            assignmentsBySpace.Remove(assignment.SpaceId);
        }

        private void ParkingAssignmentCreated(ParkingAssignment assignment) => AssignmentCreated?.Invoke(assignment);

        private static int CompareSpaces(ParkingSpace a, ParkingSpace b)
        {
            int level = a.Level.CompareTo(b.Level);
            return level != 0 ? level : string.CompareOrdinal(a.SpaceId, b.SpaceId);
        }
    }
}
