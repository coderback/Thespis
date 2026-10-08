## Thespis for Godot: the minds of a game's NPCs, through the /v1 protocol (docs/protocol.md).
##
## The engine owns the world. It reports what happened and who saw it (`observe`), changes what it decides
## (`update`), and asks what an NPC does and says (`decide`, `react`, `narrate`). Thespis owns the minds: what each
## NPC believes, what it chooses among the actions the game file declares, and its words.
##
##   await Thespis.start()        # a sidecar on this machine, or the server the settings name
##   await Thespis.open("tavern")
##   await Thespis.observe(Thespis.event("insult", "player", "garrick",
##           Thespis.claim("insulted", "player", "garrick"), ["wren"]))
##   var r := await Thespis.decide("garrick", "turn")
##   if r.ok:
##       show(r.value)            # provisional at once; line_settled brings the model's line
##
## Where it runs is settings, not code: the same scene plays offline through a sidecar and online through a server.
## Every call is a coroutine returning a ThespisResult, and nothing raises.
class_name ThespisClient
extends Node

signal line_arrived(line: ThespisLine)  ## decide, react or narrate gave a line: show it (it may be provisional)
signal line_settled(line: ThespisLine)  ## a line became final (show its new text) or withdrawn (take it down)
signal state_changed(state: String)  ## starting, ready, failed or stopped

const SETTINGS := {  # [default, type, hint, hint string, what it's for]
	"thespis/connection/url": ["", TYPE_STRING, PROPERTY_HINT_NONE, "",
			"The Thespis server. Empty: start a sidecar on this machine. $THESPIS_URL overrides it."],
	"thespis/connection/key": ["", TYPE_STRING, PROPERTY_HINT_NONE, "",
			"A server's project key (tsk_...). $THESPIS_KEY overrides it. Anyone with the game can read it."],
	"thespis/game/definition": ["", TYPE_STRING, PROPERTY_HINT_FILE, "*.toml",
			"The game file to send on start, so the server or sidecar knows the game. Export *.toml with the game."],
	"thespis/sidecar/command": [[], TYPE_PACKED_STRING_ARRAY, PROPERTY_HINT_NONE, "",
			"How to run the runtime. Empty: thespis/thespis(.exe) beside the game, else python -m thespis."],
	"thespis/sidecar/model": ["", TYPE_STRING, PROPERTY_HINT_NONE, "",
			"A local model for the sidecar: auto, or an id such as gemma4-e4b. Empty: the game's template lines."],
	"thespis/sidecar/online": [false, TYPE_BOOL, PROPERTY_HINT_NONE, "",
			"Let the sidecar reach the network (a cloud model). Off, it refuses every connection off the machine."],
	"thespis/sidecar/start_timeout": [120.0, TYPE_FLOAT, PROPERTY_HINT_RANGE, "5,600,1,suffix:s",
			"Seconds to wait for the sidecar, a local model's first load included."],
}
const _METHODS := {"GET": HTTPClient.METHOD_GET, "POST": HTTPClient.METHOD_POST, "PUT": HTTPClient.METHOD_PUT,
		"DELETE": HTTPClient.METHOD_DELETE}

var url := ""  ## the server or sidecar; empty until start() finds or starts one
var key := ""  ## a server's project key, or the sidecar's token
var game_file := ""  ## a game.toml start() sends, so the runtime knows the game
var session_id := ""
var auto_settle := true  ## follow provisional lines until they settle, emitting line_settled
var poll_wait := 2.0  ## seconds the server holds each poll open while the model answers
var settle_timeout := 30.0  ## give up following a line after this long; its provisional text is still safe to show
var max_requests := 6  ## requests in flight at once; more wait their turn
var sidecar: ThespisSidecar = null  ## the runtime this client started, if it started one
var state := "stopped"

var _idle: Array[HTTPRequest] = []
var _busy := 0
var _following := {}  # line id -> ThespisLine

signal _freed


## Register the settings in Project Settings (the editor plugin does this when it's enabled).
static func register_settings() -> void:
	for name in SETTINGS:
		var s: Array = SETTINGS[name]
		var default = PackedStringArray(s[0]) if s[1] == TYPE_PACKED_STRING_ARRAY else s[0]
		if not ProjectSettings.has_setting(name):
			ProjectSettings.set_setting(name, default)
		ProjectSettings.set_initial_value(name, default)
		ProjectSettings.add_property_info({"name": name, "type": s[1], "hint": s[2], "hint_string": s[3]})


## A claim, for observe: `Thespis.claim("insulted", "player", "garrick")`.
static func claim(pred: String, a: String, b := "", neg := false) -> Dictionary:
	var c := {"pred": pred, "a": a, "b": b}
	if neg:
		c["neg"] = true
	return c


## An event, for observe: what happened, who did it to whom, what it shows, and who else saw it.
static func event(verb: String, actor: String, target := "", shows := {}, witnesses: Array = [],
		more := {}) -> Dictionary:
	var e := {"verb": verb, "actor": actor, "witnesses": witnesses}
	if not target.is_empty():
		e["target"] = target
	if not shows.is_empty():
		e["claim"] = shows
	e.merge(more)
	return e


# ------------------------------------------------------------------------------------------------ connecting

## Find the runtime, or start one: the server the settings (or $THESPIS_URL) name, else a sidecar on this machine.
## Then send the game file, if there is one. ok with the runtime's health (ThespisApi.HealthOut), or why not.
func start() -> ThespisResult:
	if url.is_empty():
		url = _setting("thespis/connection/url", "THESPIS_URL")
	if key.is_empty():
		key = _setting("thespis/connection/key", "THESPIS_KEY")
	if game_file.is_empty():
		game_file = _setting("thespis/game/definition", "")
	_set_state("starting")
	if url.is_empty():
		sidecar = ThespisSidecar.new()
		sidecar.name = "Sidecar"
		var cmd := OS.get_environment("THESPIS_SIDECAR")  # a JSON list, to run it some other way (tests, tools)
		sidecar.command = PackedStringArray(JSON.parse_string(cmd)) if not cmd.is_empty() else \
				PackedStringArray(ProjectSettings.get_setting("thespis/sidecar/command", PackedStringArray()))
		sidecar.model = ProjectSettings.get_setting("thespis/sidecar/model", "")
		sidecar.online = ProjectSettings.get_setting("thespis/sidecar/online", false)
		sidecar.start_timeout = ProjectSettings.get_setting("thespis/sidecar/start_timeout", 120.0)
		add_child(sidecar)
		var started := await sidecar.start()
		if not started.ok:
			_set_state("failed")
			return started
		url = sidecar.url
		key = sidecar.token
	var health := await _until_healthy(10.0)
	if health.ok and not game_file.is_empty():
		var sent := await put_game_file(game_file)
		if not sent.ok:
			health = sent
	_set_state("ready" if health.ok else "failed")
	return health


## Close the session and stop the sidecar, if this client started one.
func stop() -> void:
	if not session_id.is_empty():
		await close()
	if sidecar:
		sidecar.stop()
		sidecar.queue_free()
		sidecar = null
		url = ""
		key = ""
	_set_state("stopped")


func is_sidecar() -> bool:
	return sidecar != null


func health() -> ThespisResult:
	return await _call("health")


## Send a game's definition. Its id must be the one its [game] table gives.
func put_game(game_id: String, toml: String) -> ThespisResult:
	return await _call("put_game", {"gid": game_id}, {"toml": toml})


## Send a game file (res:// works in an exported game, if *.toml is exported with it).
func put_game_file(path: String) -> ThespisResult:
	if not FileAccess.file_exists(path):
		return ThespisResult.failure("no_game_file", "no file at %s" % path)
	var toml := FileAccess.get_file_as_string(path)
	var found := RegEx.create_from_string("(?m)^\\[game\\][^\\[]*?^id\\s*=\\s*\"([^\"]+)\"").search(toml)
	if found == null:
		return ThespisResult.failure("no_game_id", "%s has no id in its [game] table" % path)
	return await put_game(found.get_string(1), toml)


# ------------------------------------------------------------------------------------------------ sessions

func open(game: String, seed_value := 0) -> ThespisResult:
	var r := await _call("open_session", {}, {"game": game, "seed": seed_value})
	if r.ok:
		session_id = r.value.session
	return r


## Open a session from a save: the text snapshot() gave, sent back exactly as it was written. Keep it as text in your
## own save file; parsed into a Dictionary, its whole numbers would come back as floats.
func restore(game: String, saved: String) -> ThespisResult:
	var body := '{"game": %s, "snapshot": %s}' % [JSON.stringify(game), saved]
	var r := await _call("open_session", {}, body)
	if r.ok:
		session_id = r.value.session
	return r


func close() -> ThespisResult:
	var r := await _call("close_session", {"sid": session_id})
	session_id = ""
	_following.clear()
	return r


## The session as save text, for the game's own save file. ok with a String.
func snapshot() -> ThespisResult:
	return await _call("snapshot", {"sid": session_id})


## Another player, for a game with several: `join("bram", "Bram", "green")`.
func join(player: String, display_name := "", at := "") -> ThespisResult:
	var body := {"player": player}
	if not display_name.is_empty():
		body["name"] = display_name
	if not at.is_empty():
		body["at"] = at
	return await _call("join", {"sid": session_id}, body)


# ------------------------------------------------------------------------------------------------ the world

## Something happened: a Dictionary (see event()) or a ThespisApi.ObserveIn. ok with a ThespisApi.EventOut.
func observe(what) -> ThespisResult:
	return await _call("observe", {"sid": session_id}, what)


## The engine changed an NPC: `update("garrick", {"loc": "road", "flags": {"gone": true}})`.
func update(npc: String, change: Dictionary) -> ThespisResult:
	var body := change.duplicate()
	body["npc"] = npc
	return await _call("update", {"sid": session_id}, body)


## Time passes: gossip spreads, NPCs walk, feelings fade. ok with a ThespisApi.TickOut.
func tick(steps := 1) -> ThespisResult:
	return await _call("tick", {"sid": session_id}, {"steps": steps})


## What an NPC believes and feels. ok with a ThespisApi.NpcOut.
func inspect(npc: String) -> ThespisResult:
	return await _call("inspect", {"sid": session_id, "npc": npc})


# ------------------------------------------------------------------------------------------------ lines

## What `npc` does at `moment`, among the actions the game declares, and what it says. ok with a ThespisLine whose
## `action` is the choice. options: situation, bindings, to, wait (true waits for the model's line).
func decide(npc: String, moment: String, options := {}) -> ThespisResult:
	return await _line("decide", _with({"npc": npc, "moment": moment}, options))


## What `npc` says about `trigger`, one of its [npc.x.lines]. options: situation, cites, fill, wait.
func react(npc: String, trigger: String, options := {}) -> ThespisResult:
	return await _line("react", _with({"npc": npc, "trigger": trigger}, options))


## The narrator's telling of what happened. options: since (a phase), to (a player), wait.
func narrate(options := {}) -> ThespisResult:
	return await _line("narrate", options.duplicate())


## A line as it stands now, holding the poll open up to `wait` seconds while it's provisional.
func line(id: String, wait := 0.0) -> ThespisResult:
	var query := "?wait=%s" % wait if wait > 0 else ""
	return await _call("line", {"sid": session_id, "lid": id}, null, query)


## Wait until a line is final or withdrawn, and return it. If it can't be followed that far (the server went away,
## or settle_timeout passed), it comes back still provisional, with settle_error saying why: its text is the game's
## own template line, so it is still safe to show.
func settle(spoken: ThespisLine) -> ThespisLine:
	if spoken.is_settled() or spoken.id == null:
		return spoken
	if _following.has(spoken.id):
		await spoken._followed
		return spoken
	await _follow(spoken)
	return spoken


func _line(route: String, body: Dictionary) -> ThespisResult:
	var r := await _call(route, {"sid": session_id}, body)
	if not r.ok:
		return r
	var spoken: ThespisLine = r.value
	line_arrived.emit(spoken)
	if spoken.is_settled():
		line_settled.emit(spoken)
	elif auto_settle and spoken.id != null:
		_follow(spoken)  # not awaited: the game carries on while the model answers
	return r


func _follow(spoken: ThespisLine) -> void:
	_following[spoken.id] = spoken
	var deadline := Time.get_ticks_msec() + int(settle_timeout * 1000)
	while spoken.is_provisional():
		if Time.get_ticks_msec() > deadline:
			spoken.settle_error = "not settled after %ss" % settle_timeout
			break
		var r := await _call("line", {"sid": session_id, "lid": spoken.id}, null, "?wait=%s" % poll_wait, spoken)
		if not r.ok:
			spoken.settle_error = "%s: %s" % [r.error, r.reason]
			break
	_following.erase(spoken.id)
	if spoken.is_settled():
		line_settled.emit(spoken)
		spoken.settled.emit(spoken)
	spoken._followed.emit()


# ------------------------------------------------------------------------------------------------ plumbing

func _setting(name: String, env: String) -> String:
	if not env.is_empty() and not OS.get_environment(env).is_empty():
		return OS.get_environment(env)
	return str(ProjectSettings.get_setting(name, ""))


func _set_state(now: String) -> void:
	if now != state:
		state = now
		state_changed.emit(now)


func _until_healthy(seconds: float) -> ThespisResult:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000)
	while true:
		var r := await health()
		if r.ok or Time.get_ticks_msec() > deadline:
			return r
		await get_tree().create_timer(0.1).timeout
	return null


func _with(body: Dictionary, options: Dictionary) -> Dictionary:
	var out := body.duplicate()
	out.merge(options)
	return out


## One call by its route in the generated table (ThespisApi.ROUTES). `body` is a Dictionary, a generated class, or
## text sent as it is. `into` is an object to read the reply into, in place of a new one.
func _call(route: String, params := {}, body = null, query := "", into: Object = null) -> ThespisResult:
	if url.is_empty():
		return ThespisResult.failure("not_started", "call start() first")
	var spec: Array = ThespisApi.ROUTES[route]
	var path: String = spec[1]
	for p in params:
		path = path.replace("{%s}" % p, str(params[p]).uri_encode())
	var text := ""
	if body is String:
		text = body
	elif body is Object:
		text = JSON.stringify(body.to_dict())
	elif body != null:
		text = JSON.stringify(body)
	var headers := PackedStringArray(["Content-Type: application/json", "Accept: application/json"])
	if not key.is_empty():
		headers.append("Authorization: Bearer " + key)
	var http := await _take()
	http.timeout = poll_wait + 15.0
	var err := http.request(url + path + query, headers, _METHODS[spec[0]], text)
	if err != OK:
		_give(http)
		return ThespisResult.failure("request_failed", error_string(err))
	var res: Array = await http.request_completed
	_give(http)
	if res[0] != HTTPRequest.RESULT_SUCCESS:
		return ThespisResult.failure("unreachable", "couldn't reach %s (HTTPRequest result %d)" % [url, res[0]])
	var code: int = res[1]
	var reply: String = (res[3] as PackedByteArray).get_string_from_utf8()
	var data = JSON.parse_string(reply) if not reply.is_empty() else null
	if code >= 400:
		if data is Dictionary and data.has("error"):
			return ThespisResult.failure(str(data["error"]), str(data.get("reason", "")), code)
		return ThespisResult.failure("http_%d" % code, reply.left(300), code)
	if route == "snapshot":
		return ThespisResult.success(reply, code)  # as text, so a save keeps its whole numbers whole
	var kind: String = spec[3]
	if kind.is_empty() or data == null:
		return ThespisResult.success(data, code)
	if data is Array:
		return ThespisResult.success(data.map(func(x): return _typed(kind, x)), code)
	if not data is Dictionary:
		return ThespisResult.failure("bad_reply", reply.left(300), code)
	return ThespisResult.success(into.read(data) if into else _typed(kind, data), code)


func _typed(kind: String, data: Dictionary):
	var made = ThespisLine.new() if kind == "LineOut" else ThespisApi.make(kind)
	return made.read(data)


## A free HTTPRequest node, or a new one, waiting while max_requests are in flight. One node carries one request at
## a time, so a poll held open can't block the player's next call.
func _take() -> HTTPRequest:
	while _idle.is_empty() and _busy >= max_requests:
		await _freed
	_busy += 1
	if not _idle.is_empty():
		return _idle.pop_back()
	var http := HTTPRequest.new()
	add_child(http)
	return http


func _give(http: HTTPRequest) -> void:
	_busy -= 1
	_idle.append(http)
	_freed.emit()
