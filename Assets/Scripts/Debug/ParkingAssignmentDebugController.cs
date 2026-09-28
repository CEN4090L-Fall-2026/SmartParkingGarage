using System;
using System.Collections.Generic;
using UnityEngine;

namespace SmartParkingGarage
{
    public sealed class ParkingAssignmentDebugController : MonoBehaviour
    {
        [SerializeField] private ParkingAssignmentManager manager;
        [SerializeField] private ParkingSpaceRegistry registry;
        [SerializeField] private string requesterId = "MANUAL_L4_01";
        [SerializeField] private bool usePreferredLevel = true;
        [SerializeField] private int preferredLevel = 4;
        [SerializeField] private bool useRequiredType;
        [SerializeField] private ParkingSpaceType requiredType = ParkingSpaceType.Standard;

        private readonly List<ParkingAssignment> active = new List<ParkingAssignment>();
        private readonly List<string> touchedSpaceIds = new List<string>();
        private readonly List<string> testRequesterIds = new List<string>();
        private readonly List<string> failures = new List<string>();
        private int createdEvents;
        private int releasedEvents;

        [ContextMenu("Request Assignment")]
        public void RequestAssignment()
        {
            if (!Ready()) return;
            ParkingAssignmentResult result = manager.RequestAssignment(BuildRequest());
            LogResult("Request", result);
            Track(result);
        }

        [ContextMenu("Release Assignment")]
        public void ReleaseAssignment()
        {
            if (!Ready()) return;
            ParkingAssignmentResult result = manager.ReleaseAssignment(requesterId);
            LogResult("Release", result);
        }

        [ContextMenu("Show Current Assignment")]
        public void ShowCurrentAssignment()
        {
            if (!Ready()) return;
            if (!manager.TryGetAssignment(requesterId, out ParkingAssignment assignment))
            {
                Debug.Log($"Parking assignment for requester '{requesterId}' not found.", this);
                return;
            }
            Debug.Log($"Parking assignment: requester={assignment.RequesterId}, SpaceId={assignment.SpaceId}, Level={assignment.Level}, Type={assignment.Type}.", FindSpace(assignment.SpaceId));
        }

        [ContextMenu("Run Parking Assignment V1 Validation")]
        public void RunValidation()
        {
            failures.Clear();
            if (!Ready() || registry.GetCounts().Available != 414 || manager.ActiveAssignmentCount != 0)
            {
                Debug.LogWarning("Parking Assignment V1 validation requires an initialized registry, 414 Available spaces, and zero active assignments.", this);
                return;
            }

            createdEvents = 0;
            releasedEvents = 0;
            manager.AssignmentCreated += OnAssignmentCreated;
            manager.AssignmentReleased += OnAssignmentReleased;
            try
            {
                ValidateCoreRequests();
                ValidateFiltering();
                ValidateFailures();
                ValidateExternalStates();
                Check(createdEvents >= 5, $"Expected assignment-created events; observed {createdEvents}.");
                Check(releasedEvents >= 5, $"Expected assignment-released events; observed {releasedEvents}.");
            }
            finally
            {
                CleanupTestState();
                manager.AssignmentCreated -= OnAssignmentCreated;
                manager.AssignmentReleased -= OnAssignmentReleased;
            }

            ParkingSpaceCounts counts = registry.GetCounts();
            Check(counts.Available == 414 && counts.Occupied == 0 && counts.Reserved == 0 && counts.OutOfService == 0, "Final parking counts were not fully restored.");
            Check(manager.ActiveAssignmentCount == 0, "Active assignments remained after cleanup.");
            Debug.Log(failures.Count == 0 ? "Parking Assignment V1 validation PASSED." : "Parking Assignment V1 validation FAILED: " + string.Join(" | ", failures), this);
        }

        [ContextMenu("Restore Assignment Test State")]
        public void RestoreAssignmentTestState() => CleanupTestState();

        private void ValidateCoreRequests()
        {
            ParkingAssignmentResult first = Request("V1_TEST_UNFILTERED", null, null);
            Check(first.Status == ParkingAssignmentStatus.Assigned && first.Assignment.Type == ParkingSpaceType.Standard, "Generic request did not assign a Standard stall.");
            Check(first.Assignment != null && FindSpace(first.Assignment.SpaceId).State == ParkingSpaceState.Reserved, "Assigned stall did not become Reserved.");
            Check(registry.GetCounts().Available == 413 && registry.GetCounts().Reserved == 1, "Counts after first assignment were incorrect.");
            ParkingAssignmentResult duplicate = manager.RequestAssignment(new ParkingAssignmentRequest("V1_TEST_UNFILTERED"));
            Check(duplicate.Status == ParkingAssignmentStatus.AlreadyAssigned, "Duplicate requester was accepted.");
            ParkingAssignmentResult second = Request("V1_TEST_SECOND", null, null);
            Check(second.Status == ParkingAssignmentStatus.Assigned && second.Assignment.SpaceId != first.Assignment.SpaceId, "Second requester received a duplicate stall or failed unexpectedly.");
            ParkingAssignmentResult release = manager.ReleaseAssignment("V1_TEST_UNFILTERED");
            Check(release.Status == ParkingAssignmentStatus.Released && FindSpace(first.Assignment.SpaceId).State == ParkingSpaceState.Available, "Normal release did not restore Available.");
            manager.ReleaseAssignment("V1_TEST_SECOND");
        }

        private void ValidateFiltering()
        {
            ParkingAssignmentResult level = Request("V1_TEST_LEVEL_3", 3, null);
            Check(level.Status == ParkingAssignmentStatus.Assigned && level.Assignment.Level == 3, "Preferred level filtering failed.");
            manager.ReleaseAssignment("V1_TEST_LEVEL_3");
            ParkingAssignmentResult ev = Request("V1_TEST_EV", null, ParkingSpaceType.EV);
            Check(ev.Status == ParkingAssignmentStatus.Assigned && ev.Assignment.Type == ParkingSpaceType.EV && ev.Assignment.Level == 2 && ev.Assignment.IsTypeResolved, "EV-only request did not return a confirmed Level 2 EV stall.");
            manager.ReleaseAssignment("V1_TEST_EV");
            ParkingAssignmentResult accessible = Request("V1_TEST_ACCESSIBLE", null, ParkingSpaceType.Accessible);
            Check(accessible.Status == ParkingAssignmentStatus.NoMatchingAvailableSpace, "Accessible-only request did not fail safely.");
            ParkingAssignmentResult impossible = Request("V1_TEST_IMPOSSIBLE", 1, ParkingSpaceType.EV);
            Check(impossible.Status == ParkingAssignmentStatus.NoMatchingAvailableSpace, "Impossible level/type filter unexpectedly assigned a stall.");
        }

        private void ValidateFailures()
        {
            Check(manager.RequestAssignment(new ParkingAssignmentRequest("", null, null)).Status == ParkingAssignmentStatus.InvalidRequesterId, "Blank requester was accepted.");
            Check(manager.RequestAssignment(new ParkingAssignmentRequest("V1_TEST_BAD_LEVEL", 5, null)).Status == ParkingAssignmentStatus.InvalidLevel, "Invalid level was accepted.");
            Check(manager.RequestAssignment(new ParkingAssignmentRequest("V1_TEST_BAD_TYPE", null, (ParkingSpaceType)99)).Status == ParkingAssignmentStatus.InvalidType, "Invalid type was accepted.");
            Check(manager.ReleaseAssignment("V1_TEST_UNKNOWN").Status == ParkingAssignmentStatus.UnknownRequester, "Unknown release was not rejected.");
        }

        private void ValidateExternalStates()
        {
            ValidateExternalState("V1_TEST_OCCUPIED", ParkingSpaceState.Occupied);
            ValidateExternalState("V1_TEST_OUT_OF_SERVICE", ParkingSpaceState.OutOfService);
            ValidateExternalState("V1_TEST_AVAILABLE", ParkingSpaceState.Available);
        }

        private void ValidateExternalState(string id, ParkingSpaceState externalState)
        {
            ParkingAssignmentResult result = Request(id, null, null);
            Check(result.Status == ParkingAssignmentStatus.Assigned, $"External-state setup request failed for {externalState}.");
            if (result.Assignment == null) return;
            ParkingSpace space = FindSpace(result.Assignment.SpaceId);
            touchedSpaceIds.Add(space.SpaceId);
            if (space.State != externalState) registry.TrySetState(space.SpaceId, externalState);
            ParkingAssignmentResult release = manager.ReleaseAssignment(id);
            Check(release.Status == ParkingAssignmentStatus.ReleasedStatePreserved && space.State == externalState, $"Release did not preserve external state {externalState}.");
        }

        private ParkingAssignmentResult Request(string id, int? level, ParkingSpaceType? type)
        {
            testRequesterIds.Add(id);
            ParkingAssignmentResult result = manager.RequestAssignment(new ParkingAssignmentRequest(id, level, type));
            Track(result);
            return result;
        }

        private ParkingAssignmentRequest BuildRequest() => new ParkingAssignmentRequest(requesterId, usePreferredLevel ? preferredLevel : (int?)null, useRequiredType ? requiredType : (ParkingSpaceType?)null);

        private bool Ready() => manager != null && registry != null && manager.IsInitialized && registry.IsInitialized;

        private void Track(ParkingAssignmentResult result)
        {
            if (result.Assignment != null)
            {
                if (!touchedSpaceIds.Contains(result.Assignment.SpaceId)) touchedSpaceIds.Add(result.Assignment.SpaceId);
                if (!testRequesterIds.Contains(result.Assignment.RequesterId)) testRequesterIds.Add(result.Assignment.RequesterId);
            }
        }

        private void CleanupTestState()
        {
            if (manager == null || registry == null || !manager.IsInitialized || !registry.IsInitialized) return;
            manager.GetActiveAssignments(active);
            for (int i = 0; i < active.Count; i++) manager.ReleaseAssignment(active[i].RequesterId);
            for (int i = 0; i < touchedSpaceIds.Count; i++)
            {
                ParkingSpace space = FindSpace(touchedSpaceIds[i]);
                if (space != null && space.State != ParkingSpaceState.Available) registry.TrySetState(space.SpaceId, ParkingSpaceState.Available);
            }
            active.Clear();
            touchedSpaceIds.Clear();
            testRequesterIds.Clear();
        }

        private ParkingSpace FindSpace(string spaceId)
        {
            if (registry == null) return null;
            return registry.TryGetSpace(spaceId, out ParkingSpace space) ? space : null;
        }

        private void LogResult(string operation, ParkingAssignmentResult result)
        {
            if (result.Assignment != null)
            {
                Debug.Log($"{operation} assignment: requester={result.Assignment.RequesterId}, SpaceId={result.Assignment.SpaceId}, Level={result.Assignment.Level}, Type={result.Assignment.Type}, Result={result.Status}, State={result.StateAfterOperation}.", FindSpace(result.Assignment.SpaceId));
            }
            else Debug.Log($"{operation} assignment: requester={requesterId}, Result={result.Status}.", this);
        }

        private void OnAssignmentCreated(ParkingAssignment assignment) => createdEvents++;
        private void OnAssignmentReleased(ParkingAssignmentResult result) => releasedEvents++;
        private void Check(bool condition, string message) { if (!condition) failures.Add(message); }
    }
}
