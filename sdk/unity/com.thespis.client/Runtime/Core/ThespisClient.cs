#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Thespis.Api;

namespace Thespis
{
    /// <summary>Where Thespis runs and how the client behaves. Set in code, or by the Unity settings asset.</summary>
    public sealed class ThespisOptions
    {
        /// <summary>A Thespis server. Empty: start a sidecar on this machine. $THESPIS_URL overrides it.</summary>
        public string Url { get; set; } = "";
        /// <summary>A server's project key (tsk_...). $THESPIS_KEY overrides it.</summary>
        public string Key { get; set; } = "";
        /// <summary>The game's definition (its game.toml), sent on start so the runtime knows the game.</summary>
        public string GameToml { get; set; } = "";
        /// <summary>How to run the sidecar. $THESPIS_SIDECAR (a JSON list) overrides it.</summary>
        public IReadOnlyList<string> SidecarCommand { get; set; } = new[] { "python", "-m", "thespis" };
        /// <summary>A local model for the sidecar: auto, or an id such as gemma4-e4b. Empty: template lines.
        /// $THESPIS_MODEL overrides it.</summary>
        public string SidecarModel { get; set; } = "";
        /// <summary>Let the sidecar reach the network, for a cloud model. Off, it refuses everything off the machine.</summary>
        public bool SidecarOnline { get; set; }
        /// <summary>The SQLite file the sidecar keeps sessions in; empty, the runtime's cache folder.</summary>
        public string SidecarSessions { get; set; } = "";
        public TimeSpan SidecarStartTimeout { get; set; } = TimeSpan.FromSeconds(120);
        /// <summary>Follow provisional lines until they settle, raising LineSettled.</summary>
        public bool AutoSettle { get; set; } = true;
        /// <summary>Seconds the server holds each poll open while the model answers.</summary>
        public double PollWait { get; set; } = 2;
        /// <summary>Give up following a line after this long; its provisional text is still safe to show.</summary>
        public TimeSpan SettleTimeout { get; set; } = TimeSpan.FromSeconds(30);
        /// <summary>Requests in flight at once; more wait their turn.</summary>
        public int MaxRequests { get; set; } = 6;
    }

    /// <summary>
    /// The minds of a game's NPCs, through the Thespis /v1 protocol (docs/protocol.md).
    ///
    /// The engine owns the world. It reports what happened and who saw it (<see cref="ObserveAsync"/>), changes what
    /// it decides (<see cref="UpdateAsync"/>), and asks what an NPC does and says (<see cref="DecideAsync"/>,
    /// <see cref="ReactAsync"/>, <see cref="NarrateAsync"/>). Thespis owns the minds. What the player types is read
    /// as one of the acts the game file declares (<see cref="UnderstandAsync"/>), for the engine to carry out as it
    /// would a button.
    /// <code>
    /// await thespis.StartAsync();                // a sidecar on this machine, or the server the options name
    /// await thespis.OpenAsync("tavern");
    /// await thespis.ObserveAsync(ThespisClient.Event("insult", "player", "garrick",
    ///     ThespisClient.Claim("insulted", "player", "garrick"), "wren"));
    /// var r = await thespis.DecideAsync("garrick", "turn");
    /// if (r.Ok) Show(r.Value);                   // provisional at once; LineSettled brings the model's line
    /// </code>
    /// Every call returns a <see cref="Result{T}"/>. Awaited from Unity's main thread, every continuation and event
    /// comes back on the main thread, so nothing here uses ConfigureAwait(false).
    /// </summary>
    public sealed class ThespisClient : IDisposable
    {
        /// <summary>Decide, react or narrate gave a line: show it (it may be provisional).</summary>
        public event Action<ThespisLine>? LineArrived;
        /// <summary>A line became final (show its new text) or withdrawn (take it down).</summary>
        public event Action<ThespisLine>? LineSettled;
        /// <summary>starting, ready, failed or stopped.</summary>
        public event Action<string>? StateChanged;

        public ThespisOptions Options { get; }
        public string Url { get; private set; } = "";
        public string SessionId { get; private set; } = "";
        public Sidecar? Sidecar { get; private set; }
        public bool IsSidecar => Sidecar != null;
        public string State { get; private set; } = "stopped";

        private static readonly JsonSerializerSettings Json = new JsonSerializerSettings
        {
            ObjectCreationHandling = ObjectCreationHandling.Replace,  // a reply read into a line replaces its lists
        };
        private static readonly Regex GameId = new Regex(@"^\[game\][^\[]*?^id\s*=\s*""([^""]+)""",
            RegexOptions.Multiline | RegexOptions.Singleline);

        private readonly HttpClient _http;
        private readonly SemaphoreSlim _slots;
        private string _key = "";

        public ThespisClient(ThespisOptions? options = null, HttpMessageHandler? handler = null)
        {
            Options = options ?? new ThespisOptions();
            if (handler == null)
            {
                var own = new HttpClientHandler();
                try
                {
                    own.MaxConnectionsPerServer = Options.MaxRequests + 2;  // Mono's default is 2: polls would queue
                }
                catch (Exception e) when (e is NotImplementedException || e is PlatformNotSupportedException)
                {
                    // Unity's Mono keeps the limit per process, on its ServicePointManager: raise it, never lower it
                    var limit = System.Net.ServicePointManager.DefaultConnectionLimit;
                    System.Net.ServicePointManager.DefaultConnectionLimit = Math.Max(limit, Options.MaxRequests + 2);
                }
                handler = own;
            }
            _http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(Options.PollWait + 15) };
            _slots = new SemaphoreSlim(Options.MaxRequests);
        }

        /// <summary>A claim, for an observation: <c>Claim("insulted", "player", "garrick")</c>.</summary>
        public static ClaimIn Claim(string pred, string a, string b = "", bool neg = false) =>
            new ClaimIn { Pred = pred, A = a, B = b, Neg = neg };

        /// <summary>An event: what happened, who did it to whom, what it shows, and who else saw it.</summary>
        public static ObserveIn Event(string verb, string actor, string? target = null, ClaimIn? shows = null,
            params string[] witnesses) =>
            new ObserveIn { Verb = verb, Actor = actor, Target = target, Claim = shows, Witnesses = witnesses.ToList() };

        // ------------------------------------------------------------------------------------------ connecting

        /// <summary>
        /// Find the runtime, or start one: the server the options (or $THESPIS_URL) name, else a sidecar on this
        /// machine. Then send the game's definition, if there is one. Ok with the runtime's health, or why not.
        /// </summary>
        public async Task<Result<HealthOut>> StartAsync()
        {
            Url = Env("THESPIS_URL", Options.Url);
            _key = Env("THESPIS_KEY", Options.Key);
            SetState("starting");
            if (Url.Length == 0)
            {
                var command = Environment.GetEnvironmentVariable("THESPIS_SIDECAR");  // a JSON list: tests, tools
                Sidecar = new Sidecar
                {
                    Command = string.IsNullOrEmpty(command)
                        ? Options.SidecarCommand
                        : JsonConvert.DeserializeObject<List<string>>(command!)!,
                    Model = Env("THESPIS_MODEL", Options.SidecarModel),
                    Online = Options.SidecarOnline,
                    Sessions = Options.SidecarSessions,
                    StartTimeout = Options.SidecarStartTimeout,
                };
                var started = await Sidecar.StartAsync();
                if (!started.Ok)
                {
                    SetState("failed");
                    return started.As<HealthOut>();
                }
                Url = Sidecar.Url;
                _key = Sidecar.Token;
            }
            var health = await UntilHealthyAsync(TimeSpan.FromSeconds(10));
            if (health.Ok && Options.GameToml.Length > 0)
            {
                var sent = await PutGameAsync(Options.GameToml);
                if (!sent.Ok)
                    health = sent.As<HealthOut>();
            }
            SetState(health.Ok ? "ready" : "failed");
            return health;
        }

        /// <summary>Close the session and stop the sidecar, if this client started one.</summary>
        public async Task StopAsync()
        {
            if (SessionId.Length > 0)
                await CloseAsync();
            StopSidecar();
            SetState("stopped");
        }

        /// <summary>Stop the sidecar now, without a word to the server: for a game that's quitting.</summary>
        public void StopSidecar()
        {
            if (Sidecar == null)
                return;
            Sidecar.Dispose();
            Sidecar = null;
            Url = "";
            _key = "";
        }

        public void Dispose()
        {
            StopSidecar();
            _http.Dispose();
        }

        public Task<Result<HealthOut>> HealthAsync() => CallAsync<HealthOut>(Routes.Health);

        /// <summary>Send a game's definition; its id is the one its [game] table gives.</summary>
        public Task<Result<GameOut>> PutGameAsync(string toml)
        {
            var found = GameId.Match(toml);
            if (!found.Success)
                return Task.FromResult(Result<GameOut>.Failure("no_game_id", "the definition has no id in its [game] table"));
            return CallAsync<GameOut>(Routes.PutGame, Params("gid", found.Groups[1].Value), new GameIn { Toml = toml });
        }

        // ------------------------------------------------------------------------------------------ sessions

        public async Task<Result<SessionOut>> OpenAsync(string game, int seed = 0)
        {
            var r = await CallAsync<SessionOut>(Routes.OpenSession, null, new SessionIn { Game = game, Seed = seed });
            if (r.Ok)
                SessionId = r.Value!.Session;
            return r;
        }

        /// <summary>
        /// Open a session from a save: the text <see cref="SnapshotAsync"/> gave, sent back exactly as it was written.
        /// </summary>
        public async Task<Result<SessionOut>> RestoreAsync(string game, string saved)
        {
            var body = $"{{\"game\": {JsonConvert.ToString(game)}, \"snapshot\": {saved}}}";
            var r = await CallAsync<SessionOut>(Routes.OpenSession, null, body);
            if (r.Ok)
                SessionId = r.Value!.Session;
            return r;
        }

        public async Task<Result<JToken?>> CloseAsync()
        {
            var r = await CallAsync<JToken?>(Routes.CloseSession, Session());
            SessionId = "";
            return r;
        }

        /// <summary>The session as save text, for the game's own save file.</summary>
        public Task<Result<string>> SnapshotAsync() => CallAsync<string>(Routes.Snapshot, Session());

        /// <summary>Another player, for a game with several.</summary>
        public Task<Result<JToken?>> JoinAsync(string player, string? name = null, string? at = null) =>
            CallAsync<JToken?>(Routes.Join, Session(), new JoinIn { Player = player, Name = name, At = at });

        // ------------------------------------------------------------------------------------------ the world

        /// <summary>Something happened (see <see cref="Event"/>). Ok with the event as the ledger keeps it.</summary>
        public Task<Result<EventOut>> ObserveAsync(ObserveIn what) => CallAsync<EventOut>(Routes.Observe, Session(), what);

        /// <summary>The engine changed an NPC: <c>new UpdateIn { Npc = "garrick", Loc = "road" }</c>.</summary>
        public Task<Result<JToken?>> UpdateAsync(UpdateIn change) => CallAsync<JToken?>(Routes.Update, Session(), change);

        /// <summary>Time passes: gossip spreads, NPCs walk, feelings fade.</summary>
        public Task<Result<TickOut>> TickAsync(int steps = 1) =>
            CallAsync<TickOut>(Routes.Tick, Session(), new TickIn { Steps = steps });

        /// <summary>What an NPC believes and feels.</summary>
        public Task<Result<NpcOut>> InspectAsync(string npc) => CallAsync<NpcOut>(Routes.Inspect, Session("npc", npc));

        // ------------------------------------------------------------------------------------------ lines

        /// <summary>
        /// What <paramref name="npc"/> does at <paramref name="moment"/>, among the actions the game declares, and
        /// what it says. <paramref name="options"/> carries the rest: Situation, Bindings, To, Wait.
        /// </summary>
        public Task<Result<ThespisLine>> DecideAsync(string npc, string moment, DecideIn? options = null)
        {
            var body = options ?? new DecideIn();
            body.Npc = npc;
            body.Moment = moment;
            return LineCallAsync(Routes.Decide, body);
        }

        /// <summary>What <paramref name="npc"/> says about <paramref name="trigger"/>, one of its [npc.x.lines].</summary>
        public Task<Result<ThespisLine>> ReactAsync(string npc, string trigger, ReactIn? options = null)
        {
            var body = options ?? new ReactIn();
            body.Npc = npc;
            body.Trigger = trigger;
            return LineCallAsync(Routes.React, body);
        }

        /// <summary>The narrator's telling of what happened: Since (a phase), To (a player), Wait.</summary>
        public Task<Result<ThespisLine>> NarrateAsync(NarrateIn? options = null) =>
            LineCallAsync(Routes.Narrate, options ?? new NarrateIn());

        /// <summary>A line as it stands now, holding the poll open up to <paramref name="wait"/> seconds.</summary>
        public Task<Result<ThespisLine>> LineAsync(string id, double wait = 0) =>
            CallAsync<ThespisLine>(Routes.Line, Session("lid", id), null, wait > 0 ? $"?wait={wait}" : "");

        /// <summary>
        /// Wait until a line is final or withdrawn, and return it. If it can't be followed that far, it comes back
        /// still provisional, with SettleError saying why: its text is the game's own template line, safe to show.
        /// </summary>
        public async Task<ThespisLine> SettleAsync(ThespisLine line)
        {
            if (line.IsSettled || line.Id == null)
                return line;
            var following = line.Following;
            if (following != null)
            {
                await following.Task;
                return line;
            }
            await FollowAsync(line);
            return line;
        }

        private async Task<Result<ThespisLine>> LineCallAsync(Route route, object body)
        {
            var r = await CallAsync<ThespisLine>(route, Session(), body);
            if (!r.Ok)
                return r;
            var line = r.Value!;
            LineArrived?.Invoke(line);
            if (line.IsSettled)
                LineSettled?.Invoke(line);
            else if (Options.AutoSettle && line.Id != null)
                _ = FollowAsync(line);  // not awaited: the game carries on while the model answers
            return r;
        }

        private async Task FollowAsync(ThespisLine line)
        {
            var done = new TaskCompletionSource<bool>();
            line.Following = done;
            try
            {
                var deadline = DateTime.UtcNow + Options.SettleTimeout;
                while (line.IsProvisional)
                {
                    if (DateTime.UtcNow > deadline)
                    {
                        line.SettleError = $"not settled after {Options.SettleTimeout.TotalSeconds}s";
                        break;
                    }
                    var r = await CallAsync<ThespisLine>(Routes.Line, Session("lid", line.Id!), null,
                        $"?wait={Options.PollWait}", line);
                    if (!r.Ok)
                    {
                        line.SettleError = $"{r.Error}: {r.Reason}";
                        break;
                    }
                }
            }
            catch (Exception e)
            {
                line.SettleError = e.Message;
            }
            finally
            {
                line.Following = null;
            }
            if (line.IsSettled)
            {
                LineSettled?.Invoke(line);
                line.RaiseSettled();
            }
            done.TrySetResult(true);
        }

        // ------------------------------------------------------------------------------------------ the player's words

        /// <summary>
        /// What the player's own words do, among the acts the game file declares ([intents]). The reply's Status says
        /// what to do with it: <c>act</c>, carry out Intent as its button would and report what happened with
        /// <see cref="ObserveAsync"/>; <c>ask</c>, put Readings to the player first ("Did you mean: Insult
        /// Garrick?") and carry out the one they pick; <c>talk</c>, the words do none of the game's acts.
        /// Reading changes nothing, and an intent's arguments come only from the game's own lists: Args holds ids,
        /// whole numbers and claims to hand back to observe as they came.
        /// <paramref name="to"/> is the NPC spoken to. <paramref name="options"/> carries the rest: Offered (the acts
        /// open now, narrowing the game's; left out, every act the game declares) and Player (who typed it).
        /// </summary>
        public Task<Result<UnderstandOut>> UnderstandAsync(string text, string? to = null, UnderstandIn? options = null)
        {
            var body = options ?? new UnderstandIn();
            body.Text = text;
            body.To = to ?? body.To;
            return CallAsync<UnderstandOut>(Routes.Understand, Session(), body);
        }

        // ------------------------------------------------------------------------------------------ plumbing

        private static string Env(string name, string otherwise)
        {
            var v = Environment.GetEnvironmentVariable(name);
            return string.IsNullOrEmpty(v) ? otherwise : v!;
        }

        private void SetState(string now)
        {
            if (now == State)
                return;
            State = now;
            StateChanged?.Invoke(now);
        }

        private async Task<Result<HealthOut>> UntilHealthyAsync(TimeSpan within)
        {
            var deadline = DateTime.UtcNow + within;
            while (true)
            {
                var r = await HealthAsync();
                if (r.Ok || DateTime.UtcNow > deadline)
                    return r;
                await Task.Delay(100);
            }
        }

        private Dictionary<string, string> Session(string? name = null, string? value = null)
        {
            var p = new Dictionary<string, string> { ["sid"] = SessionId };
            if (name != null)
                p[name] = value!;
            return p;
        }

        private static Dictionary<string, string> Params(string name, string value) =>
            new Dictionary<string, string> { [name] = value };

        /// <summary>
        /// One call by its route in the generated table. <paramref name="body"/> is a generated class, or text sent
        /// as it is. <paramref name="into"/> is an object to read the reply into, in place of a new one.
        /// </summary>
        private async Task<Result<T>> CallAsync<T>(Route route, Dictionary<string, string>? parameters = null,
            object? body = null, string query = "", object? into = null)
        {
            if (Url.Length == 0)
                return Result<T>.Failure("not_started", "call StartAsync first");
            var path = route.Path;
            if (parameters != null)
                foreach (var p in parameters)
                    path = path.Replace("{" + p.Key + "}", Uri.EscapeDataString(p.Value));
            using var request = new HttpRequestMessage(new HttpMethod(route.Method), Url + path + query);
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            if (_key.Length > 0)
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _key);
            if (body != null)
            {
                var text = body as string ?? JsonConvert.SerializeObject(body);
                request.Content = new StringContent(text, Encoding.UTF8, "application/json");
            }
            string reply;
            int status;
            await _slots.WaitAsync();
            try
            {
                using var response = await _http.SendAsync(request);
                status = (int)response.StatusCode;
                reply = await response.Content.ReadAsStringAsync();
            }
            catch (Exception e) when (e is HttpRequestException || e is TaskCanceledException)
            {
                return Result<T>.Failure("unreachable", $"couldn't reach {Url}: {e.Message}");
            }
            finally
            {
                _slots.Release();
            }
            if (status >= 400)
            {
                try
                {
                    var error = JObject.Parse(reply);
                    if (error["error"] != null)
                        return Result<T>.Failure((string)error["error"]!, (string?)error["reason"] ?? "", status);
                }
                catch (JsonException)
                {
                    // not one of ours: say what came back
                }
                return Result<T>.Failure($"http_{status}", reply.Length > 300 ? reply.Substring(0, 300) : reply, status);
            }
            if (typeof(T) == typeof(string))
                return Result<T>.Success((T)(object)reply, status);  // a snapshot, as text: its numbers stay whole
            if (reply.Length == 0)
                return Result<T>.Success(default!, status);
            try
            {
                if (into != null)
                {
                    JsonConvert.PopulateObject(reply, into, Json);
                    return Result<T>.Success((T)into, status);
                }
                return Result<T>.Success(JsonConvert.DeserializeObject<T>(reply, Json)!, status);
            }
            catch (JsonException e)
            {
                return Result<T>.Failure("bad_reply", e.Message, status);
            }
        }
    }
}
