#nullable enable
using UnityEngine;

namespace Thespis
{
    /// <summary>
    /// Thespis in a scene: holds the game's one <see cref="ThespisClient"/>, lives across scene loads, and stops the
    /// sidecar when the game quits.
    /// <code>
    /// var thespis = ThespisBehaviour.Client;
    /// var started = await thespis.StartAsync();
    /// </code>
    /// Awaited from a MonoBehaviour, the client's calls continue on Unity's main thread, and its events (LineArrived,
    /// LineSettled) are raised there, so they can touch the scene directly.
    /// </summary>
    [DisallowMultipleComponent]
    [DefaultExecutionOrder(-1000)]  // before any script that asks for the client in its own Awake
    public sealed class ThespisBehaviour : MonoBehaviour
    {
        [Tooltip("Where Thespis runs. Left empty: the ThespisSettings asset in a Resources folder, else the defaults.")]
        [SerializeField] private ThespisSettings? settings;

        private static ThespisBehaviour? _instance;
        private ThespisClient? _client;

        /// <summary>The scene's client, made from the settings the first time it's asked for.</summary>
        public static ThespisClient Client
        {
            get
            {
                if (_instance == null)
                    _instance = new GameObject("Thespis").AddComponent<ThespisBehaviour>();
                return _instance._client ??= new ThespisClient(_instance.Settings().ToOptions());
            }
        }

        private ThespisSettings Settings()
        {
            if (settings == null)
                settings = Resources.Load<ThespisSettings>("ThespisSettings");
            return settings != null ? settings : ScriptableObject.CreateInstance<ThespisSettings>();
        }

        private void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);  // the first one carries on across scenes
                return;
            }
            _instance = this;
            DontDestroyOnLoad(gameObject);
        }

        private void OnApplicationQuit() => Shut();

        private void OnDestroy()
        {
            if (_instance == this)
                Shut();
        }

        private void Shut()
        {
            _client?.Dispose();  // stops the sidecar, if the client started one
            _client = null;
            if (_instance == this)
                _instance = null;
        }
    }
}
