using UnityEngine;

namespace SmartParkingGarage
{
    /// <summary>
    /// Minimal bootstrap component for the Smart Parking Garage baseline.
    /// </summary>
    public sealed class ParkingSpace : MonoBehaviour
    {
        [SerializeField] private string spaceId;
        [SerializeField] private int level;
        [SerializeField] private ParkingSpaceType type;
        [SerializeField] private bool typeResolved;
        [SerializeField] private ParkingIndicator indicator;

        [System.NonSerialized] private ParkingSpaceRegistry registry;
        [System.NonSerialized] private ParkingSpaceState state = ParkingSpaceState.Available;

        public string SpaceId => spaceId;
        public int Level => level;
        public ParkingSpaceType Type => type;
        public bool IsTypeResolved => typeResolved;
        public ParkingSpaceState State => state;
        public ParkingIndicator Indicator => indicator;

        public bool TrySetState(ParkingSpaceState nextState)
        {
            if (registry == null)
                throw new System.InvalidOperationException("ParkingSpace is not bound to an initialized ParkingSpaceRegistry.");
            return registry.TrySetState(spaceId, nextState);
        }

        internal void Bind(ParkingSpaceRegistry owner) => registry = owner;
        internal void InitializeRuntime(ParkingSpaceState initialState)
        {
            state = initialState;
            if (indicator != null) indicator.ApplyState(state);
        }
        internal void SetRuntimeState(ParkingSpaceState nextState) => state = nextState;
    }
}
