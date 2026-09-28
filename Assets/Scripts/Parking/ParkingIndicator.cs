using UnityEngine;

namespace SmartParkingGarage
{
    public sealed class ParkingIndicator : MonoBehaviour
    {
        [SerializeField] private Renderer targetRenderer;
        [SerializeField] private int materialIndex;
        private MaterialPropertyBlock propertyBlock;
        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        private static readonly int EmissiveColorId = Shader.PropertyToID("_EmissiveColor");

        public Renderer TargetRenderer => targetRenderer;
        public int MaterialIndex => materialIndex;

        public void ApplyState(ParkingSpaceState state)
        {
            if (targetRenderer == null) return;
            if (propertyBlock == null) propertyBlock = new MaterialPropertyBlock();
            targetRenderer.GetPropertyBlock(propertyBlock, materialIndex);
            Color color = state switch
            {
                ParkingSpaceState.Occupied => new Color(0.9f, 0.03f, 0.02f, 1f),
                ParkingSpaceState.Reserved => new Color(0.05f, 0.2f, 1f, 1f),
                ParkingSpaceState.OutOfService => new Color(1f, 0.45f, 0.02f, 1f),
                _ => new Color(0.03f, 1f, 0.08f, 1f)
            };
            propertyBlock.SetColor(BaseColorId, color);
            propertyBlock.SetColor(EmissiveColorId, color * 3f);
            targetRenderer.SetPropertyBlock(propertyBlock, materialIndex);
        }
    }
}
