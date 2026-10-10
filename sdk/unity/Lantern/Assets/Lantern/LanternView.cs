#nullable enable
using System.Collections.Generic;
using System.Threading.Tasks;
using Thespis;
using Thespis.Api;
using UnityEngine;

namespace Lantern
{
    /// <summary>
    /// The Lantern on screen: a line for each of Garrick, Wren, Pip and the narrator, the player's choices as
    /// buttons, and a box to say something to Garrick in their own words. A reading the game isn't sure of is put
    /// back to the player as a button. The world is LanternGame's; this only shows it. A provisional line (the game's template) is drawn
    /// faded until the model's words replace it. Nothing here says where Thespis runs: that's the ThespisSettings asset.
    /// </summary>
    public sealed class LanternView : MonoBehaviour
    {
        private static readonly Dictionary<string, string> Names = new Dictionary<string, string>
        {
            ["garrick"] = "Garrick", ["wren"] = "Wren", ["pip"] = "Pip", ["narrator"] = "The Narrator",
        };
        private const string SavePath = "lantern.save";

        public LanternGame Game { get; private set; } = null!;
        /// <summary>Done when Thespis has started and the tavern is open.</summary>
        public Task<Result<SessionOut>> Ready { get; private set; } = null!;
        public string Status { get; private set; } = "Starting Thespis...";

        private readonly Dictionary<string, ThespisLine> _showing = new Dictionary<string, ThespisLine>();
        private bool _busy;
        private string _words = "";  // what the player is typing

        private void Awake()
        {
            var thespis = ThespisBehaviour.Client;
            Game = new LanternGame(thespis);
            thespis.LineArrived += line => _showing[line.Npc] = line;
            thespis.LineSettled += line =>
            {
                if (_showing.TryGetValue(line.Npc, out var shown) && shown.Id == line.Id)
                    _showing[line.Npc] = line;  // an older line settling late doesn't replace a newer one
            };
        }

        private async void Start()
        {
            Ready = Game.BeginAsync();
            var r = await Ready;
            var where = Game.Thespis.IsSidecar ? "a sidecar on this machine" : Game.Thespis.Url;
            Status = r.Ok ? $"Thespis at {where}" : $"No Thespis: {r.Reason}";
        }

        /// <summary>What the screen shows for an NPC, as the player reads it.</summary>
        public string Shown(string npc)
        {
            if (!_showing.TryGetValue(npc, out var line) || line.IsWithdrawn)
                return "";
            var doing = line.Action != null ? $" ({line.Action})" : "";
            return $"{Names[npc]}{doing}: {line.Words("...")}";
        }

        /// <summary>Whether the screen shows an NPC's line faded, as the template it is until the model's arrives.</summary>
        public bool Faded(string npc) => _showing.TryGetValue(npc, out var line) && line.IsProvisional;

        public void Clear() => _showing.Clear();

        /// <summary>A reading the game isn't sure of, as its button puts it to the player.</summary>
        public static string Question(IntentOut reading) => $"Did you mean: {reading.Reads}?";

        private void OnGUI()
        {
            var asking = Game.Asking;  // as it stood when this pass began: a click on a button below changes it
            GUILayout.BeginArea(new Rect(24, 24, Screen.width - 48, Screen.height - 48));
            GUILayout.Label("The Lantern's taproom, an hour before dusk. Garrick nurses a drink; Wren polishes the bar.");
            GUILayout.Label($"Hour {Game.Phase}. Pip is in {(Game.PipAt == "taproom" ? "the taproom" : "the " + Game.PipAt)}.");
            foreach (var npc in Names.Keys)
            {
                var colour = GUI.color;
                GUI.color = new Color(1, 1, 1, Faded(npc) ? 0.55f : 1);
                GUILayout.Label(Shown(npc));
                GUI.color = colour;
            }
            GUI.enabled = !_busy && Ready != null && Ready.IsCompleted && Ready.Result.Ok;
            GUILayout.BeginHorizontal();
            Button("Insult Garrick", () => Game.InsultAsync());
            Button("Help with his gear", () => Game.HelpAsync());
            Button("What does Garrick do?", () => Game.AskGarrickAsync());
            Button("Talk to Wren", () => Game.TalkToAsync("wren"));
            Button("An hour passes", () => Game.PassHourAsync());
            Button("What happened?", () => Game.WhatHappenedAsync());
            Button("Save", SaveAsync);
            Button("Load", LoadAsync);
            GUILayout.EndHorizontal();
            GUILayout.BeginHorizontal();
            _words = GUILayout.TextField(_words, 200);
            Button("Say to Garrick", SayAsync, GUILayout.ExpandWidth(false));
            GUILayout.EndHorizontal();
            GUILayout.Label(Game.Heard);
            GUILayout.BeginHorizontal();
            foreach (var reading in asking)
                Button(Question(reading), () => Game.CarryOutAsync(reading));
            if (asking.Count > 0)
                Button("No", () => { Game.Dismiss(); return Task.CompletedTask; });
            GUILayout.EndHorizontal();
            GUI.enabled = true;
            GUILayout.FlexibleSpace();
            GUILayout.Label(Status);
            GUILayout.EndArea();
        }

        private async void Button(string label, System.Func<Task> act, params GUILayoutOption[] layout)
        {
            if (!GUILayout.Button(label, layout))
                return;
            _busy = true;
            try
            {
                await act();
            }
            finally
            {
                _busy = false;
            }
        }

        /// <summary>What the player typed goes to Garrick, to be read as one of the game's acts or as talk.</summary>
        private Task SayAsync()
        {
            var text = _words.Trim();
            _words = "";
            return text.Length > 0 ? Game.SayAsync(text) : Task.CompletedTask;
        }

        private async Task SaveAsync()
        {
            var save = await Game.SaveAsync();
            if (save.Ok)
                System.IO.File.WriteAllText(System.IO.Path.Combine(Application.persistentDataPath, SavePath), save.Value);
        }

        private async Task LoadAsync()
        {
            var path = System.IO.Path.Combine(Application.persistentDataPath, SavePath);
            if (!System.IO.File.Exists(path))
                return;
            var r = await Game.LoadAsync(System.IO.File.ReadAllText(path));
            if (r.Ok)
                Clear();
        }
    }
}
