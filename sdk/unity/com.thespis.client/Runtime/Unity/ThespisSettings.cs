#nullable enable
using System;
using System.IO;
using UnityEngine;

namespace Thespis
{
    /// <summary>
    /// Where Thespis runs, as an asset (Create → Thespis → Settings). Put it in a Resources folder named
    /// ThespisSettings, or give it to the ThespisBehaviour. Which way it runs is settings, never code: leave the
    /// server empty and the game starts a sidecar on the player's machine.
    /// </summary>
    [CreateAssetMenu(menuName = "Thespis/Settings", fileName = "ThespisSettings")]
    public sealed class ThespisSettings : ScriptableObject
    {
        [Tooltip("A Thespis server. Empty: start a sidecar on this machine. $THESPIS_URL overrides it.")]
        public string server = "";

        [Tooltip("The server's project key (tsk_...). $THESPIS_KEY overrides it. Anyone with the game can read it.")]
        public string key = "";

        [Tooltip("The game's definition: its game.toml, imported as a text asset. Sent on start.")]
        public TextAsset? game;

        [Tooltip("How to run the sidecar: the executable, then its arguments. Empty: thespis/thespis(.exe) beside " +
                 "the game's executable in a build, python -m thespis in the editor.")]
        public string[] sidecarCommand = Array.Empty<string>();

        [Tooltip("A local model for the sidecar: auto, or an id such as gemma4-e4b. Empty: the game's template lines.")]
        public string sidecarModel = "";

        [Tooltip("Let the sidecar reach the network, for a cloud model. Off, it refuses every connection off the machine.")]
        public bool sidecarOnline;

        [Tooltip("Seconds to wait for the sidecar, a local model's first load included.")]
        public float sidecarStartTimeout = 120;

        /// <summary>The client's options from these settings.</summary>
        public ThespisOptions ToOptions() => new ThespisOptions
        {
            Url = server,
            Key = key,
            GameToml = game != null ? game.text : "",
            SidecarCommand = sidecarCommand.Length > 0 ? sidecarCommand : DefaultSidecarCommand(),
            SidecarModel = sidecarModel,
            SidecarOnline = sidecarOnline,
            SidecarSessions = Path.Combine(Application.persistentDataPath, "thespis", "sessions.sqlite"),
            SidecarStartTimeout = TimeSpan.FromSeconds(sidecarStartTimeout),
        };

        /// <summary>
        /// The runtime a build ships with (tools/package.py's folder, as thespis/ beside the game's executable), or
        /// Python while in the editor.
        /// </summary>
        public static string[] DefaultSidecarCommand()
        {
            if (!Application.isEditor)
            {
                var exe = Application.platform == RuntimePlatform.WindowsPlayer ? "thespis.exe" : "thespis";
                // dataPath is Game_Data beside the executable, or Game.app/Contents on macOS.
                var here = Application.platform == RuntimePlatform.OSXPlayer
                    ? Path.GetFullPath(Path.Combine(Application.dataPath, "..", ".."))
                    : Path.GetDirectoryName(Application.dataPath) ?? ".";
                var packaged = Path.Combine(here, "thespis", exe);
                if (File.Exists(packaged))
                    return new[] { packaged };
            }
            return new[] { "python", "-m", "thespis" };
        }
    }
}
