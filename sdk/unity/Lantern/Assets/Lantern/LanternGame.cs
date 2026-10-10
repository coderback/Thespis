#nullable enable
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Thespis;
using Thespis.Api;

namespace Lantern
{
    /// <summary>
    /// The Lantern: the crypt road's first act in miniature. Garrick, a proud sellsword, sits in the taproom; Wren
    /// keeps the bar; Pip minds the horses and wanders in and out.
    ///
    /// This class is the scene's world, kept apart from its screen (LanternView) so the same game plays under plain
    /// .NET in a check. It owns who is where, what the player does and who sees it. Thespis owns their minds
    /// (tavern.toml, a copy of examples/tavern/game.toml): what they believe, what Garrick chooses, and every line.
    /// What the player types to Garrick is read as one of the acts the game file declares, and carried out here as
    /// its button would be. Nothing here says where Thespis runs.
    /// </summary>
    public sealed class LanternGame
    {
        public const string Game = "tavern";

        public ThespisClient Thespis { get; }
        /// <summary>Where Pip is: Thespis walks him, and each tick says where he went.</summary>
        public string PipAt { get; private set; } = "yard";
        /// <summary>The hours passed.</summary>
        public int Phase { get; private set; }
        /// <summary>The phase the narrator has told the story up to.</summary>
        public int ToldUpTo { get; private set; }
        /// <summary>What the player's words might have meant, until they say which.</summary>
        public IReadOnlyList<IntentOut> Asking { get; private set; } = System.Array.Empty<IntentOut>();
        /// <summary>The event the player's last words came to, if they did one of the game's acts.</summary>
        public EventOut? Done { get; private set; }
        /// <summary>The player's last words and, once they did something, what.</summary>
        public string Heard { get; private set; } = "";

        public LanternGame(ThespisClient thespis) => Thespis = thespis;

        public async Task<Result<SessionOut>> BeginAsync()
        {
            var started = await Thespis.StartAsync();
            return started.Ok ? await Thespis.OpenAsync(Game) : started.As<SessionOut>();
        }

        /// <summary>Who in the taproom sees what the player does there, besides whoever it's done to.</summary>
        public string[] Onlookers(string besides)
        {
            var here = new List<string> { "garrick", "wren" };
            if (PipAt == "taproom")
                here.Add("pip");
            return here.Where(npc => npc != besides).ToArray();
        }

        /// <summary>The player insults Garrick. The game file says an insult angers him, so this reports only that.</summary>
        public Task<Result<EventOut>> InsultAsync(string whom = "garrick") =>
            Thespis.ObserveAsync(ThespisClient.Event("insult", "player", whom,
                ThespisClient.Claim("insulted", "player", whom), Onlookers(whom)));

        /// <summary>The player helps Garrick with his gear. Twice, and he respects them enough to share a drink.</summary>
        public Task<Result<EventOut>> HelpAsync() =>
            Thespis.ObserveAsync(ThespisClient.Event("help", "player", "garrick",
                ThespisClient.Claim("helped", "player", "garrick"), Onlookers("garrick")));

        /// <summary>What Garrick does now, among the choices his game file declares. The scene carries it out.</summary>
        public async Task<Result<ThespisLine>> AskGarrickAsync()
        {
            var r = await Thespis.DecideAsync("garrick", "turn");
            if (r.Ok && (r.Value!.Action ?? "").StartsWith("share_drink"))
                await Thespis.UpdateAsync(new UpdateIn { Npc = "garrick", Flags = new JObject { ["drink"] = true } });
            return r;
        }

        public Task<Result<ThespisLine>> TalkToAsync(string npc) => Thespis.ReactAsync(npc, "talk");

        /// <summary>
        /// The player says something in their own words. Thespis reads which of the game's acts the words do, if any
        /// ([intents] in tavern.toml): it only chooses among them, and fills each from the game's own lists, so
        /// nothing typed here can do what a button couldn't. Ok with how it was read; <see cref="Done"/> holds the
        /// event it came to, if it came to one.
        /// </summary>
        public async Task<Result<UnderstandOut>> SayAsync(string text, string to = "garrick")
        {
            Dismiss();
            Done = null;
            var r = await Thespis.UnderstandAsync(text, to);
            if (!r.Ok)
                return r;
            var read = r.Value!;
            Heard = $"You: \"{text}\"";
            if (read.Status == "act")  // a sure reading: carry it out, as the button would
                await CarryOutAsync(read.Intent!);
            else if (read.Status == "ask")  // it may be an act with consequences: the player says whether it was
                Asking = read.Readings;
            else  // only talk
                await TalkToAsync(to);
            return r;
        }

        /// <summary>
        /// Carry out an act the player's words did, as its button would: one observe, seen by whoever is in the
        /// taproom. It is also the player's yes to a reading they were asked about.
        /// </summary>
        public async Task<Result<EventOut>> CarryOutAsync(IntentOut intent)
        {
            Dismiss();
            var to = (string?)intent.Args["to"] ?? "garrick";
            Result<EventOut> r;
            switch (intent.Verb)
            {
                case "insult":
                    r = await InsultAsync(to);
                    break;
                case "tell":  // the claim goes back as it came. True or not, the ledger knows: a lie is logged as one
                    var telling = ThespisClient.Event("tell", "player", to, intent.Args["claim"]!.ToObject<ClaimIn>(),
                        Onlookers(to));
                    telling.Said = true;
                    r = await Thespis.ObserveAsync(telling);
                    break;
                case "pay":
                    var paying = ThespisClient.Event("pay", "player", to, ThespisClient.Claim("paid", "player", to),
                        Onlookers(to));
                    paying.Amount = (int)intent.Args["amount"]!;
                    r = await Thespis.ObserveAsync(paying);
                    break;
                default:
                    return Result<EventOut>.Failure("no_such_act", $"the Lantern has no act called {intent.Verb}");
            }
            if (r.Ok)
            {
                Done = r.Value;
                Heard += $"  ({intent.Reads})";
            }
            return r;
        }

        /// <summary>The player meant none of the readings: nothing happens.</summary>
        public void Dismiss() => Asking = System.Array.Empty<IntentOut>();

        /// <summary>An hour passes: Pip walks his round, and the gossips pass on what they've heard.</summary>
        public async Task<Result<TickOut>> PassHourAsync()
        {
            var r = await Thespis.TickAsync();
            if (r.Ok)
            {
                Phase = r.Value!.Phase;
                foreach (var move in r.Value.Moves)
                    if (move.TryGetValue("who", out var who) && who == "pip")
                        PipAt = move["to"];
            }
            return r;
        }

        public async Task<Result<ThespisLine>> WhatHappenedAsync()
        {
            var r = await Thespis.NarrateAsync(new NarrateIn { Since = ToldUpTo });
            if (r.Ok)
                ToldUpTo = Phase;
            return r;
        }

        /// <summary>The game's save: the scene's own state and the minds, kept as the text Thespis wrote.</summary>
        public async Task<Result<string>> SaveAsync()
        {
            var minds = await Thespis.SnapshotAsync();
            if (!minds.Ok)
                return minds;
            var save = new JObject
            {
                ["pip_at"] = PipAt, ["phase"] = Phase, ["told_up_to"] = ToldUpTo, ["minds"] = minds.Value,
            };
            return Result<string>.Success(save.ToString(Formatting.None));
        }

        public async Task<Result<SessionOut>> LoadAsync(string save)
        {
            var saved = JObject.Parse(save);
            await Thespis.CloseAsync();
            var r = await Thespis.RestoreAsync(Game, (string)saved["minds"]!);
            if (r.Ok)
            {
                PipAt = (string)saved["pip_at"]!;
                Phase = (int)saved["phase"]!;
                ToldUpTo = (int)saved["told_up_to"]!;
                Dismiss();
                Done = null;
                Heard = "";
            }
            return r;
        }
    }
}
