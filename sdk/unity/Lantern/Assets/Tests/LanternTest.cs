using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using Thespis;
using Thespis.Api;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using Debug = UnityEngine.Debug;

namespace Lantern.Tests
{
    /// <summary>
    /// The package's gate in Unity: the Lantern scene, played in play mode. test/run.py runs it in batch mode twice,
    /// with the scene unchanged: against a sidecar the client starts itself (THESPIS_EXPECT=sidecar) and against a
    /// hosted-mode server with a project key (THESPIS_EXPECT=server, THESPIS_URL, THESPIS_KEY).
    /// </summary>
    public sealed class LanternTest
    {
        private const string Template = "You. Say it again, to my face.";
        private readonly List<string> _failures = new List<string>();
        private int _checks;

        private void Check(bool ok, string what, object got = null)
        {
            _checks++;
            if (ok)
                Debug.Log($"ok   {what}");
            else
            {
                _failures.Add(what);
                Debug.Log($"FAIL {what}" + (got == null ? "" : $"  (got {got})"));
            }
        }

        /// <summary>Wait for a task across frames, so its continuations run on the main thread as a game's would.</summary>
        private static IEnumerator Wait(Task task, float seconds = 120)
        {
            var until = Time.realtimeSinceStartup + seconds;
            while (!task.IsCompleted && Time.realtimeSinceStartup < until)
                yield return null;
            if (!task.IsCompleted)
                Assert.Fail($"still waiting after {seconds}s");
        }

        [UnityTest, Timeout(600000)]
        public IEnumerator TheLanternPlaysWhereverThespisRuns()
        {
            var expect = Environment.GetEnvironmentVariable("THESPIS_EXPECT") ?? "sidecar";
            var sessions = Path.Combine(Application.persistentDataPath, "thespis", "sessions.sqlite");
            foreach (var suffix in new[] { "", "-wal", "-shm" })  // a fresh sidecar, whose reply cache hasn't heard these
                if (File.Exists(sessions + suffix))  // Mono throws if the folder isn't there yet
                    File.Delete(sessions + suffix);
            var thespis = ThespisBehaviour.Client;
            var arrived = new Dictionary<string, int>();
            var settled = new Dictionary<string, int>();
            var main = System.Threading.Thread.CurrentThread.ManagedThreadId;
            var offMain = 0;  // events raised on any other thread
            thespis.LineArrived += l =>
            {
                arrived[l.Id ?? ""] = arrived.TryGetValue(l.Id ?? "", out var n) ? n + 1 : 1;
                offMain += System.Threading.Thread.CurrentThread.ManagedThreadId == main ? 0 : 1;
            };
            thespis.LineSettled += l =>
            {
                settled[l.Id ?? ""] = settled.TryGetValue(l.Id ?? "", out var n) ? n + 1 : 1;
                offMain += System.Threading.Thread.CurrentThread.ManagedThreadId == main ? 0 : 1;
            };

            SceneManager.LoadScene("Lantern");
            yield return null;
            var view = UnityEngine.Object.FindAnyObjectByType<LanternView>();
            Assert.IsNotNull(view, "the scene has the Lantern in it");
            yield return null;
            yield return Wait(view.Ready, 300);
            var game = view.Game;
            var begun = view.Ready.Result;
            Check(begun.Ok, "the scene starts Thespis and opens the tavern", begun);
            if (!begun.Ok)
            {
                Assert.Fail(begun.ToString());
                yield break;
            }
            Check(thespis.IsSidecar == (expect == "sidecar"), $"it runs as a {expect}, with no change to the scene", thespis.Url);
            var health = thespis.HealthAsync();
            yield return Wait(health);
            Check(health.Result.Ok && health.Result.Value.Offline == (expect == "sidecar"),
                "the sidecar is offline; the server is online", health.Result);

            var before = game.AskGarrickAsync();
            yield return Wait(before);
            var quiet = before.Result.Value;
            Check(quiet.Action == "leave" && quiet.IsSilent && quiet.IsFinal,
                "a reply is a typed line: knowing nothing, he leaves in silence", before.Result);

            var insult = game.InsultAsync();
            yield return Wait(insult);
            Check(insult.Result.Ok && insult.Result.Value.Id == "e0001" && insult.Result.Value.Truth,
                "the insult is observed, as a typed event", insult.Result);

            var clock = Stopwatch.StartNew();
            var asked = game.AskGarrickAsync();
            yield return Wait(asked);
            var shown = clock.ElapsedMilliseconds;
            var spoken = asked.Result.Value;
            Check(spoken.Action == "confront:player" && spoken.IsProvisional && spoken.Text == Template,
                "angry and insulted, he confronts the player, and his template line arrives provisional", spoken.Text);
            Check(view.Faded("garrick") && view.Shown("garrick").EndsWith(Template), "the scene shows it, faded",
                view.Shown("garrick"));
            var settling = thespis.SettleAsync(spoken);
            yield return Wait(settling);
            var final = settling.Result;
            Debug.Log($"     (template line after {shown} ms; the model's after {clock.ElapsedMilliseconds} ms)");
            Check(ReferenceEquals(final, spoken) && final.IsFinal && final.Source == "llm" &&
                  final.Cites.SequenceEqual(new[] { "e0001" }),
                "the client follows it until the model's line settles it, citing the insult", $"{final.Status} {final.Source}");
            yield return null;
            Check(!view.Faded("garrick") && view.Shown("garrick").EndsWith(final.Words()), "the scene shows the final line",
                view.Shown("garrick"));
            Check(arrived.TryGetValue(spoken.Id, out var a) && a == 1 && settled.TryGetValue(spoken.Id, out var s) && s == 1,
                "LineArrived, then LineSettled, once each");

            var wren = thespis.InspectAsync("wren");
            yield return Wait(wren);
            Check(wren.Result.Ok && wren.Result.Value.Beliefs.Count == 1, "Wren, who saw it, believes it", wren.Result);
            var nobody = thespis.InspectAsync("nobody");
            yield return Wait(nobody);
            Check(!nobody.Result.Ok && nobody.Result.Status == 404, "a failed call is a result, not an exception", nobody.Result);

            var hour = game.PassHourAsync();
            yield return Wait(hour);
            Check(hour.Result.Ok && hour.Result.Value.Phase == 1 && game.PipAt == "taproom",
                "an hour passes, and Pip walks into the taproom", hour.Result);
            var told = game.WhatHappenedAsync();
            yield return Wait(told);
            var telling = thespis.SettleAsync(told.Result.Value);
            yield return Wait(telling);
            Check(telling.Result.IsFinal && view.Shown("narrator").Length > 0, "the narrator tells what happened",
                view.Shown("narrator"));

            var many = Task.WhenAll(Enumerable.Range(0, 8).Select(i => thespis.ReactAsync(i % 2 == 0 ? "garrick" : "wren", "talk")));
            yield return Wait(many);
            Check(many.Result.All(r => r.Ok), "eight lines asked for at once all come back");
            Check(offMain == 0 && arrived.Count > 8, "every line event came on Unity's main thread", offMain);

            var choice = thespis.DecideAsync("garrick", "turn", new DecideIn { Wait = true });
            yield return Wait(choice);
            var save = game.SaveAsync();
            yield return Wait(save);
            Check(save.Result.Ok && save.Result.Value.Contains("\"minds\":\"{"), "the save holds the minds as text");
            var loaded = game.LoadAsync(save.Result.Value);
            yield return Wait(loaded);
            Check(loaded.Result.Ok && game.PipAt == "taproom", "loading the save restores the session and the game", loaded.Result);
            var afterLoad = thespis.SnapshotAsync();
            yield return Wait(afterLoad);
            // Against the save itself: a line still settling in the background may change the minds just before it.
            var savedMinds = JObject.Parse((string)JObject.Parse(save.Result.Value)["minds"]);
            Check(JToken.DeepEquals(JObject.Parse(afterLoad.Result.Value)["world"], savedMinds["world"]),
                "the restored minds are the saved ones");
            var again = thespis.DecideAsync("garrick", "turn", new DecideIn { Wait = true });
            yield return Wait(again);
            var why = again.Result.Value.Reason.Split(';')[0];
            Check(why == choice.Result.Value.Reason.Split(';')[0] && !why.Contains(".0"),
                "the restored mind decides as before, in whole numbers", why);

            var pid = thespis.Sidecar?.Pid ?? -1;
            if (expect == "sidecar")
            {
                var h = thespis.HealthAsync();
                yield return Wait(h);
                Check(h.Result.Value.Refused == 0, "the sidecar reached for nothing off this machine", h.Result.Value.Refused);
            }
            var stop = thespis.StopAsync();
            yield return Wait(stop);
            if (pid > 0)
            {
                yield return new WaitForSecondsRealtime(0.5f);
                bool gone;
                try
                {
                    gone = Process.GetProcessById(pid).HasExited;
                }
                catch (ArgumentException)
                {
                    gone = true;
                }
                Check(gone, "stopping the client stops the sidecar");
            }
            Debug.Log($"{_checks} checks, {_failures.Count} failed");
            Assert.IsEmpty(_failures);
        }
    }
}
