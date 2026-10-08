#nullable enable
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Lantern;
using Newtonsoft.Json.Linq;
using Thespis;
using Thespis.Api;

// The Lantern's game under plain .NET: the Unity package's core and the example's world, without Unity. test/run.py
// runs it against a sidecar the client starts itself (THESPIS_EXPECT=sidecar) and a hosted-mode server
// (THESPIS_EXPECT=server, with THESPIS_URL and THESPIS_KEY). Exits 0 when every check passes.

const string Template = "You. Say it again, to my face.";
var expect = Environment.GetEnvironmentVariable("THESPIS_EXPECT") ?? "sidecar";
var failures = new List<string>();
var checks = 0;

void Check(bool ok, string what, object? got = null)
{
    checks++;
    if (ok)
        Console.WriteLine($"  ok   {what}");
    else
    {
        failures.Add(what);
        Console.Error.WriteLine($"  FAIL {what}" + (got == null ? "" : $"  (got {got})"));
    }
}

var sessions = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"thespis-check-{Guid.NewGuid():N}.sqlite");
var options = new ThespisOptions
{
    GameToml = System.IO.File.ReadAllText(Environment.GetEnvironmentVariable("THESPIS_GAME")!),
    SidecarSessions = sessions,  // a fresh one, whose reply cache hasn't heard these lines before
};
using var thespis = new ThespisClient(options);
var arrived = new Dictionary<string, int>();
var settled = new Dictionary<string, int>();
thespis.LineArrived += l => arrived[l.Id ?? ""] = arrived.GetValueOrDefault(l.Id ?? "") + 1;
thespis.LineSettled += l => settled[l.Id ?? ""] = settled.GetValueOrDefault(l.Id ?? "") + 1;
var game = new LanternGame(thespis);

var begun = await game.BeginAsync();
Check(begun.Ok, "the game starts Thespis and opens the tavern", begun);
if (!begun.Ok)
    return Done();
Check(thespis.IsSidecar == (expect == "sidecar"), $"it runs as a {expect}, with no change to the game", thespis.Url);
var health = await thespis.HealthAsync();
Check(health.Ok && health.Value!.Offline == (expect == "sidecar"), "the sidecar is offline; the server is online", health);

var before = await game.AskGarrickAsync();
var quiet = before.Value!;
Check(quiet.Action == "leave" && quiet.IsSilent && quiet.IsFinal,
    "a reply is a typed line: knowing nothing, he leaves in silence", before);

var insult = await game.InsultAsync();
Check(insult.Ok && insult.Value!.Id == "e0001" && insult.Value.Truth && insult.Value.Phase == 0,
    "the insult is observed, as a typed event", insult);

var clock = Stopwatch.StartNew();
var asked = await game.AskGarrickAsync();
var shown = clock.ElapsedMilliseconds;
var spoken = asked.Value!;
Check(spoken.Action == "confront:player" && spoken.IsProvisional && spoken.Text == Template,
    "angry and insulted, he confronts the player, and his template line arrives provisional", spoken.Text);
var final = await thespis.SettleAsync(spoken);
Console.WriteLine($"  (template line after {shown} ms; the model's after {clock.ElapsedMilliseconds} ms)");
Check(ReferenceEquals(final, spoken) && final.IsFinal && final.Source == "llm" && final.Cites.SequenceEqual(new[] { "e0001" }),
    "the client follows it until the model's line settles it, citing the insult", $"{final.Status} {final.Source}");
Check(arrived.GetValueOrDefault(spoken.Id!) == 1 && settled.GetValueOrDefault(spoken.Id!) == 1,
    "LineArrived, then LineSettled, once each");

var wren = await thespis.InspectAsync("wren");
Check(wren.Ok && wren.Value!.Beliefs.Count == 1, "Wren, who saw it, believes it", wren);
var nobody = await thespis.InspectAsync("nobody");
Check(!nobody.Ok && nobody.Status == 404 && nobody.Error.Length > 0, "a failed call is a result, not an exception", nobody);

var hour = await game.PassHourAsync();
Check(hour.Ok && hour.Value!.Phase == 1 && game.PipAt == "taproom", "an hour passes, and Pip walks into the taproom", hour);
var told = await game.WhatHappenedAsync();
var telling = await thespis.SettleAsync(told.Value!);
Check(telling.Npc == "narrator" && telling.IsFinal && telling.Words().Length > 0, "the narrator tells what happened",
    telling.Text);

var many = await Task.WhenAll(Enumerable.Range(0, 8).Select(i => thespis.ReactAsync(i % 2 == 0 ? "garrick" : "wren", "talk")));
Check(many.All(r => r.Ok), "eight lines asked for at once all come back", string.Join("; ", many.Where(r => !r.Ok)));

clock.Restart();
var choice = await thespis.DecideAsync("garrick", "turn", new DecideIn { Wait = true });  // an hour cooled him
Check(choice.Ok, $"he decides again, waiting for the model's line ({clock.ElapsedMilliseconds} ms)", choice);
clock.Restart();
var beforeSave = await thespis.SnapshotAsync();
Check(beforeSave.Ok, $"a snapshot ({clock.ElapsedMilliseconds} ms)", beforeSave);
clock.Restart();
var save = await game.SaveAsync();
Check(save.Ok && save.Value!.Contains("\"minds\":\"{"), $"the save holds the minds as text ({clock.ElapsedMilliseconds} ms)",
    save);
if (!(choice.Ok && beforeSave.Ok && save.Ok))
    return Done();
var loaded = await game.LoadAsync(save.Value!);
Check(loaded.Ok && game.PipAt == "taproom" && game.Phase == 1, "loading the save restores the session and the game", loaded);
var afterLoad = await thespis.SnapshotAsync();
Check(afterLoad.Ok && JToken.DeepEquals(JObject.Parse(afterLoad.Value!)["world"], JObject.Parse(beforeSave.Value!)["world"]),
    "the restored minds are the saved ones");
var again = await thespis.DecideAsync("garrick", "turn", new DecideIn { Wait = true });
var why = again.Ok ? again.Value!.Reason.Split(';')[0] : again.ToString();
Check(why == choice.Value!.Reason.Split(';')[0] && !why.Contains(".0"), "the restored mind decides as before, in whole numbers",
    why);

if (expect == "sidecar")
{
    var h = await thespis.HealthAsync();
    Check(h.Value!.Refused == 0, "the sidecar reached for nothing off this machine", h.Value.Refused);
}
return Done();

int Done()
{
    var pid = thespis.Sidecar?.Pid ?? -1;
    if (failures.Count > 0 && thespis.Sidecar != null)
        Console.Error.WriteLine($"the sidecar's log:\n{thespis.Sidecar.Log}");
    thespis.StopAsync().GetAwaiter().GetResult();
    if (pid > 0)
    {
        System.Threading.Thread.Sleep(500);
        var gone = true;
        try
        {
            gone = Process.GetProcessById(pid).HasExited;
        }
        catch (ArgumentException)
        {
            // no such process: it's gone
        }
        Check(gone, "stopping the client stops the sidecar");
    }
    foreach (var suffix in new[] { "", "-wal", "-shm" })
        try { System.IO.File.Delete(sessions + suffix); } catch (System.IO.IOException) { }
    Console.WriteLine($"{checks} checks, {failures.Count} failed");
    return failures.Count == 0 ? 0 : 1;
}
