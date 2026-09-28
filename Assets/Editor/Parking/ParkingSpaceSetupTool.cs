using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace SmartParkingGarage.EditorTools
{
    public static class ParkingSpaceSetupTool
    {
        private const string PrefabPath = "Assets/Prefabs/Garage/SmartParkingGarage.prefab";
        private static readonly Regex SpacePattern = new Regex(@"^L[1-4]_SPACE_\d+$", RegexOptions.Compiled);
        private static readonly HashSet<string> KnownEvIds = new HashSet<string>(StringComparer.Ordinal)
        {
            "L2_SPACE_029", "L2_SPACE_030", "L2_SPACE_031", "L2_SPACE_032",
            "L2_SPACE_033", "L2_SPACE_034", "L2_SPACE_035", "L2_SPACE_036"
        };

        [MenuItem("Tools/Smart Parking Garage/Parking Space V1/Validate (Dry Run)")]
        public static void ValidateDryRun() => Debug.Log(BuildReport(false));

        [MenuItem("Tools/Smart Parking Garage/Parking Space V1/Apply Metadata + Bind Indicators")]
        public static void Apply()
        {
            SetupReport report = Analyze();
            if (report.BlockingErrors.Count > 0)
            {
                EditorUtility.DisplayDialog("Parking Space V1", string.Join("\n", report.BlockingErrors), "OK");
                return;
            }

            GameObject prefabRoot = PrefabUtility.LoadPrefabContents(PrefabPath);
            try
            {
                Transform[] all = prefabRoot.GetComponentsInChildren<Transform>(true);
                Dictionary<string, Transform> byName = all.Where(t => !string.IsNullOrEmpty(t.name)).GroupBy(t => t.name, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.First(), StringComparer.Ordinal);
                foreach (Transform spaceTransform in all.Where(t => SpacePattern.IsMatch(t.name)))
                {
                    ParkingSpace space = spaceTransform.GetComponent<ParkingSpace>() ?? spaceTransform.gameObject.AddComponent<ParkingSpace>();
                    Transform indicatorTransform = byName["PGS_LED_" + spaceTransform.name];
                    ParkingIndicator indicator = indicatorTransform.GetComponent<ParkingIndicator>() ?? indicatorTransform.gameObject.AddComponent<ParkingIndicator>();
                    Renderer renderer = indicatorTransform.GetComponent<Renderer>();
                    SetSerialized(indicator, "targetRenderer", renderer);
                    SetSerialized(indicator, "materialIndex", 0);
                    SetSerialized(space, "spaceId", spaceTransform.name);
                    SetSerialized(space, "level", int.Parse(spaceTransform.name.Substring(1, 1)));
                    SetSerialized(space, "type", KnownEvIds.Contains(spaceTransform.name) ? ParkingSpaceType.EV : ParkingSpaceType.Standard);
                    SetSerialized(space, "typeResolved", KnownEvIds.Contains(spaceTransform.name));
                    SetSerialized(space, "indicator", indicator);
                }
                EditorUtility.SetDirty(prefabRoot);
                PrefabUtility.SaveAsPrefabAsset(prefabRoot, PrefabPath);
                AssetDatabase.SaveAssets();
                Debug.Log(BuildReport(true));
            }
            finally { PrefabUtility.UnloadPrefabContents(prefabRoot); }
        }

        private static void SetSerialized(UnityEngine.Object target, string propertyName, object value)
        {
            SerializedObject serialized = new SerializedObject(target);
            SerializedProperty property = serialized.FindProperty(propertyName);
            if (property == null) throw new InvalidOperationException($"Missing serialized property {propertyName} on {target.name}.");
            if (value is string s) property.stringValue = s;
            else if (value is int i) property.intValue = i;
            else if (value is bool b) property.boolValue = b;
            else if (value is ParkingSpaceType type) property.enumValueIndex = (int)type;
            else if (value is UnityEngine.Object obj) property.objectReferenceValue = obj;
            else throw new InvalidOperationException($"Unsupported serialized value for {propertyName}.");
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static SetupReport Analyze()
        {
            GameObject prefabRoot = PrefabUtility.LoadPrefabContents(PrefabPath);
            try
            {
                Transform[] all = prefabRoot.GetComponentsInChildren<Transform>(true);
                List<Transform> spaces = all.Where(t => SpacePattern.IsMatch(t.name)).ToList();
                Dictionary<string, int> nameCounts = all.GroupBy(t => t.name, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.Count(), StringComparer.Ordinal);
                SetupReport report = new SetupReport { SpaceCount = spaces.Count, EvCount = spaces.Count(t => KnownEvIds.Contains(t.name)) };
                if (spaces.Count != 414) report.BlockingErrors.Add($"Expected 414 logical spaces; found {spaces.Count}.");
                foreach (Transform space in spaces)
                {
                    string indicatorName = "PGS_LED_" + space.name;
                    if (!nameCounts.TryGetValue(indicatorName, out int indicatorCount) || indicatorCount != 1) report.BlockingErrors.Add($"Expected one indicator named {indicatorName}; found {indicatorCount}.");
                }
                report.UnresolvedAccessible = spaces.Where(t => !KnownEvIds.Contains(t.name)).Select(t => t.name).ToList();
                return report;
            }
            finally { PrefabUtility.UnloadPrefabContents(prefabRoot); }
        }

        private static string BuildReport(bool applied)
        {
            SetupReport report = Analyze();
            return $"Parking Space V1 {(applied ? "applied" : "dry run")}: spaces={report.SpaceCount}, EV={report.EvCount}, unresolvedAccessible={report.UnresolvedAccessible.Count}, blockingErrors={report.BlockingErrors.Count}. ADA metadata remains unresolved and is represented as provisional Standard with typeResolved=false during apply.";
        }

        private sealed class SetupReport
        {
            public int SpaceCount;
            public int EvCount;
            public readonly List<string> BlockingErrors = new List<string>();
            public List<string> UnresolvedAccessible = new List<string>();
        }
    }
}
