using System;
using System.Collections.Generic;
using UnityEngine;

namespace SmartParkingGarage
{
    public sealed class ParkingSpaceRegistry : MonoBehaviour
    {
        [SerializeField] private List<ParkingSpace> spaces = new List<ParkingSpace>();
        private readonly Dictionary<string, ParkingSpace> byId = new Dictionary<string, ParkingSpace>(StringComparer.Ordinal);
        private readonly int[,,] counts = new int[4, 3, 4];
        private bool initialized;

        public bool IsInitialized => initialized;
        public int TotalSpaces => spaces.Count;
        public IReadOnlyList<ParkingSpace> Spaces => spaces;
        public event Action Initialized;
        public event Action<ParkingSpaceStateChange> SpaceStateChanged;

        private void OnEnable()
        {
            if (Application.isPlaying) initialized = false;
        }

        private void Awake() => Initialize();
        private void Start() => Initialize();

        public void Initialize()
        {
            if (initialized) return;
            if (spaces == null || spaces.Count != 414) throw new InvalidOperationException($"ParkingSpaceRegistry requires 414 spaces; found {spaces?.Count ?? 0}.");
            byId.Clear();
            Array.Clear(counts, 0, counts.Length);
            for (int i = 0; i < spaces.Count; i++)
            {
                ParkingSpace space = spaces[i];
                if (space == null) throw new InvalidOperationException($"ParkingSpaceRegistry has a null entry at index {i}.");
                if (string.IsNullOrEmpty(space.SpaceId) || !byId.TryAdd(space.SpaceId, space)) throw new InvalidOperationException($"Missing or duplicate parking Space ID at index {i}.");
                if (space.Level < 1 || space.Level > 4) throw new InvalidOperationException($"Invalid level on {space.SpaceId}: {space.Level}.");
                if (space.Indicator == null) throw new InvalidOperationException($"Missing indicator on {space.SpaceId}.");
                space.Bind(this);
                space.InitializeRuntime(ParkingSpaceState.Available);
                counts[space.Level - 1, (int)space.Type, (int)ParkingSpaceState.Available]++;
            }
            initialized = true;
            Initialized?.Invoke();
        }

        public bool TryGetSpace(string spaceId, out ParkingSpace space) => byId.TryGetValue(spaceId, out space);

        public bool TrySetState(string spaceId, ParkingSpaceState nextState)
        {
            if (!initialized) throw new InvalidOperationException("ParkingSpaceRegistry is not initialized.");
            if (!Enum.IsDefined(typeof(ParkingSpaceState), nextState)) throw new ArgumentException("Invalid parking space state.", nameof(nextState));
            if (!byId.TryGetValue(spaceId, out ParkingSpace space)) return false;
            ParkingSpaceState previous = space.State;
            if (previous == nextState) return false;
            counts[space.Level - 1, (int)space.Type, (int)previous]--;
            counts[space.Level - 1, (int)space.Type, (int)nextState]++;
            space.SetRuntimeState(nextState);
            space.Indicator.ApplyState(nextState);
            SpaceStateChanged?.Invoke(new ParkingSpaceStateChange(space.SpaceId, space.Level, space.Type, previous, nextState));
            return true;
        }

        public ParkingSpaceCounts GetCounts(int? level = null, ParkingSpaceType? type = null)
        {
            int a = 0, o = 0, r = 0, x = 0;
            for (int l = 0; l < 4; l++) for (int t = 0; t < 3; t++)
            {
                if (level.HasValue && level.Value != l + 1) continue;
                if (type.HasValue && type.Value != (ParkingSpaceType)t) continue;
                a += counts[l, t, 0]; o += counts[l, t, 1]; r += counts[l, t, 2]; x += counts[l, t, 3];
            }
            return new ParkingSpaceCounts(a, o, r, x);
        }

        public int GetCount(ParkingSpaceState state, int? level = null, ParkingSpaceType? type = null)
        {
            if (!Enum.IsDefined(typeof(ParkingSpaceState), state)) throw new ArgumentException("Invalid parking space state.", nameof(state));
            ParkingSpaceCounts snapshot = GetCounts(level, type);
            return state == ParkingSpaceState.Available ? snapshot.Available : state == ParkingSpaceState.Occupied ? snapshot.Occupied : state == ParkingSpaceState.Reserved ? snapshot.Reserved : snapshot.OutOfService;
        }

        public void GetAvailableSpaces(int level, List<ParkingSpace> results, ParkingSpaceType? type = null)
        {
            if (level < 1 || level > 4) throw new ArgumentOutOfRangeException(nameof(level));
            if (results == null) throw new ArgumentNullException(nameof(results));
            results.Clear();
            for (int i = 0; i < spaces.Count; i++) if (spaces[i].Level == level && spaces[i].State == ParkingSpaceState.Available && (!type.HasValue || spaces[i].Type == type.Value)) results.Add(spaces[i]);
        }
    }
}
