using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace SmartParkingGarage
{
    public sealed class ParkingSpaceStateDebugController : MonoBehaviour
    {
        [SerializeField] private ParkingSpaceRegistry registry;
        [SerializeField] private bool runOnStart;
        [SerializeField] private float pauseBetweenSteps = 0.15f;
        [SerializeField] private string selectedSpaceId;
        [SerializeField] private ParkingSpaceState desiredState = ParkingSpaceState.Occupied;
        private readonly List<string> failures = new List<string>();
        private readonly List<ParkingSpace> available = new List<ParkingSpace>();

        private void Start()
        {
            if (runOnStart) StartCoroutine(RunValidationRoutine());
        }

        [ContextMenu("Run Parking State V1 Validation")]
        public void RunValidation()
        {
            StopAllCoroutines();
            if (pauseBetweenSteps <= 0f) { RunValidationImmediate(); return; }
            StartCoroutine(RunValidationRoutine());
        }

        [ContextMenu("Restore Tested Spaces To Available")]
        public void RestoreTestedSpaces() { StopAllCoroutines(); if (registry != null && registry.IsInitialized) Restore(); }

        [ContextMenu("Set Selected Space State")]
        public void SetSelectedSpaceState()
        {
            if (!TryGetSelectedSpace(out ParkingSpace selected)) return;
            if (!System.Enum.IsDefined(typeof(ParkingSpaceState), desiredState))
            {
                Debug.LogWarning($"Invalid parking state '{desiredState}'. No state changed.", this);
                return;
            }

            ParkingSpaceState previous = selected.State;
            if (previous == desiredState)
            {
                Debug.Log($"Parking Space {selected.SpaceId}: {previous} -> {previous} (Level {selected.Level}, Type {selected.Type}; no change).", this);
                return;
            }

            if (!registry.TrySetState(selected.SpaceId, desiredState))
            {
                Debug.LogWarning($"Could not set parking space {selected.SpaceId} to {desiredState}. No state changed.", this);
                return;
            }

            Debug.Log($"Parking Space {selected.SpaceId}: {previous} -> {selected.State} (Level {selected.Level}, Type {selected.Type}).", this);
        }

        [ContextMenu("Cycle Selected Space State")]
        public void CycleSelectedSpaceState()
        {
            if (!TryGetSelectedSpace(out ParkingSpace selected)) return;

            ParkingSpaceState previous = selected.State;
            ParkingSpaceState next;
            switch (previous)
            {
                case ParkingSpaceState.Available: next = ParkingSpaceState.Occupied; break;
                case ParkingSpaceState.Occupied: next = ParkingSpaceState.Reserved; break;
                case ParkingSpaceState.Reserved: next = ParkingSpaceState.OutOfService; break;
                default: next = ParkingSpaceState.Available; break;
            }

            if (!registry.TrySetState(selected.SpaceId, next))
            {
                Debug.LogWarning($"Could not cycle parking space {selected.SpaceId}. No state changed.", this);
                return;
            }

            Debug.Log($"Parking Space {selected.SpaceId}: {previous} -> {selected.State} (Level {selected.Level}, Type {selected.Type}).", this);
        }

        [ContextMenu("Restore Selected Space To Available")]
        public void RestoreSelectedSpaceToAvailable()
        {
            if (!TryGetSelectedSpace(out ParkingSpace selected)) return;

            ParkingSpaceState previous = selected.State;
            if (previous == ParkingSpaceState.Available)
            {
                Debug.Log($"Parking Space {selected.SpaceId}: {previous} -> {previous} (Level {selected.Level}, Type {selected.Type}; no change).", this);
                return;
            }

            if (!registry.TrySetState(selected.SpaceId, ParkingSpaceState.Available))
            {
                Debug.LogWarning($"Could not restore parking space {selected.SpaceId}. No state changed.", this);
                return;
            }

            Debug.Log($"Parking Space {selected.SpaceId}: {previous} -> Available (Level {selected.Level}, Type {selected.Type}).", this);
        }

        private bool TryGetSelectedSpace(out ParkingSpace selected)
        {
            selected = null;
            if (registry == null || !registry.IsInitialized)
            {
                Debug.LogWarning("ParkingSpaceStateDebugController requires an initialized ParkingSpaceRegistry.", this);
                return false;
            }

            if (string.IsNullOrWhiteSpace(selectedSpaceId))
            {
                Debug.LogWarning("Select a parking Space ID in the Inspector before using this control.", this);
                return false;
            }

            if (!registry.TryGetSpace(selectedSpaceId.Trim(), out selected) || selected == null)
            {
                Debug.LogWarning($"Unknown parking Space ID '{selectedSpaceId}'. No state changed.", this);
                return false;
            }

            return true;
        }

        private void RunValidationImmediate()
        {
            failures.Clear();
            if (registry == null || !registry.IsInitialized) { failures.Add("Registry is missing or not initialized."); Finish(); return; }
            Check(registry.TotalSpaces == 414, $"Expected 414 spaces; found {registry.TotalSpaces}.");
            Check(registry.GetCounts().Available == 414, "Initial available count is not 414.");
            ParkingSpace standard = null, ev = null;
            for (int i = 0; i < registry.Spaces.Count; i++) { ParkingSpace candidate = registry.Spaces[i]; if (ev == null && candidate.Type == ParkingSpaceType.EV) ev = candidate; if (standard == null && candidate.Type == ParkingSpaceType.Standard) standard = candidate; }
            Check(standard != null, "No Standard test stall found."); Check(ev != null, "No EV test stall found.");
            if (standard != null) { TestTransition(standard, ParkingSpaceState.Occupied); TestTransition(standard, ParkingSpaceState.Reserved); TestTransition(standard, ParkingSpaceState.OutOfService); TestTransition(standard, ParkingSpaceState.Available); Check(!registry.TrySetState(standard.SpaceId, ParkingSpaceState.Available), "Unchanged state request returned true."); }
            if (ev != null) { TestTransition(ev, ParkingSpaceState.Occupied); TestTransition(ev, ParkingSpaceState.Reserved); TestTransition(ev, ParkingSpaceState.OutOfService); TestTransition(ev, ParkingSpaceState.Available); }
            Check(!registry.TrySetState("L0_SPACE_UNKNOWN", ParkingSpaceState.Occupied), "Unknown ID request returned true.");
            registry.GetAvailableSpaces(2, available); Check(available.Count > 0, "Level 2 available query returned no spaces."); Restore(); Finish();
        }

        private IEnumerator RunValidationRoutine()
        {
            failures.Clear();
            if (registry == null || !registry.IsInitialized) { failures.Add("Registry is missing or not initialized."); Finish(); yield break; }
            Check(registry.TotalSpaces == 414, $"Expected 414 spaces; found {registry.TotalSpaces}.");
            Check(registry.GetCounts().Available == 414, "Initial available count is not 414.");
            ParkingSpace standard = null;
            ParkingSpace ev = null;
            for (int i = 0; i < registry.Spaces.Count; i++)
            {
                ParkingSpace candidate = registry.Spaces[i];
                if (ev == null && candidate.Type == ParkingSpaceType.EV) ev = candidate;
                if (standard == null && candidate.Type == ParkingSpaceType.Standard) standard = candidate;
            }
            Check(standard != null, "No Standard test stall found.");
            Check(ev != null, "No EV test stall found.");
            if (standard != null)
            {
                TestTransition(standard, ParkingSpaceState.Occupied); yield return Pause();
                TestTransition(standard, ParkingSpaceState.Reserved); yield return Pause();
                TestTransition(standard, ParkingSpaceState.OutOfService); yield return Pause();
                TestTransition(standard, ParkingSpaceState.Available); yield return Pause();
                Check(!registry.TrySetState(standard.SpaceId, ParkingSpaceState.Available), "Unchanged state request returned true.");
            }
            if (ev != null)
            {
                TestTransition(ev, ParkingSpaceState.Occupied); yield return Pause();
                TestTransition(ev, ParkingSpaceState.Reserved); yield return Pause();
                TestTransition(ev, ParkingSpaceState.OutOfService); yield return Pause();
                TestTransition(ev, ParkingSpaceState.Available); yield return Pause();
            }
            Check(!registry.TrySetState("L0_SPACE_UNKNOWN", ParkingSpaceState.Occupied), "Unknown ID request returned true.");
            registry.GetAvailableSpaces(2, available);
            Check(available.Count > 0, "Level 2 available query returned no spaces.");
            Restore();
            Finish();
        }

        private void TestTransition(ParkingSpace space, ParkingSpaceState state)
        {
            bool changed = registry.TrySetState(space.SpaceId, state);
            Check(changed && space.State == state, $"Failed transition {space.SpaceId} to {state}.");
        }

        private IEnumerator Pause() { if (pauseBetweenSteps > 0f) yield return new WaitForSeconds(pauseBetweenSteps); else yield return null; }

        private void Restore()
        {
            for (int i = 0; i < registry.Spaces.Count; i++) if (registry.Spaces[i].State != ParkingSpaceState.Available) registry.TrySetState(registry.Spaces[i].SpaceId, ParkingSpaceState.Available);
        }

        private void Check(bool condition, string message) { if (!condition) failures.Add(message); }
        private void Finish() { Debug.Log(failures.Count == 0 ? "Parking Space State V1 validation PASSED." : "Parking Space State V1 validation FAILED: " + string.Join(" | ", failures), this); }
    }
}
