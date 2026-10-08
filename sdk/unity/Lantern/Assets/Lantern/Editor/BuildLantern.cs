using Thespis;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Lantern.Editor
{
    /// <summary>
    /// Makes the Lantern's scene and its ThespisSettings asset, as they're committed. Run it from the menu
    /// (Thespis → Rebuild the Lantern) or in batch mode:
    /// <c>Unity -batchmode -projectPath sdk/unity/Lantern -executeMethod Lantern.Editor.BuildLantern.Build -quit</c>
    /// </summary>
    public static class BuildLantern
    {
        private const string Scene = "Assets/Lantern/Lantern.unity";
        private const string Settings = "Assets/Lantern/Resources/ThespisSettings.asset";

        [MenuItem("Thespis/Rebuild the Lantern")]
        public static void Build()
        {
            if (!AssetDatabase.IsValidFolder("Assets/Lantern/Resources"))
                AssetDatabase.CreateFolder("Assets/Lantern", "Resources");
            var settings = AssetDatabase.LoadAssetAtPath<ThespisSettings>(Settings);
            if (settings == null)
            {
                settings = ScriptableObject.CreateInstance<ThespisSettings>();
                AssetDatabase.CreateAsset(settings, Settings);
            }
            settings.game = AssetDatabase.LoadAssetAtPath<TextAsset>("Assets/Lantern/tavern.toml");
            EditorUtility.SetDirty(settings);

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var camera = new GameObject("Camera", typeof(Camera));
            camera.GetComponent<Camera>().clearFlags = CameraClearFlags.SolidColor;
            camera.GetComponent<Camera>().backgroundColor = new Color(0.12f, 0.1f, 0.09f);
            new GameObject("Thespis", typeof(ThespisBehaviour));
            new GameObject("Lantern", typeof(LanternView));
            EditorSceneManager.SaveScene(scene, Scene);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(Scene, true) };
            AssetDatabase.SaveAssets();
            Debug.Log($"Built {Scene} and {Settings}");
        }
    }
}
