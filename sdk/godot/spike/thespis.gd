## A thin client for the Thespis /v1 protocol (docs/protocol.md), in plain GDScript over HTTPRequest.
##
## The spike's job is to find out what's awkward about /v1 from an engine, so this wraps each route and nothing more.
## Every call is a coroutine: `var line = await thespis.decide("garrick", "turn")`. A failed call returns
## {"error": ..., "reason": ...} instead of raising, since GDScript has no exceptions.
extends Node

signal line_changed(line: Dictionary)  ## a line arrived, or settled from provisional to final or withdrawn

var base_url := "http://127.0.0.1:7878"
var session_id := ""
var poll_wait := 2.0  ## seconds the server holds each poll open while the model answers
var max_polls := 10


func open(game: String, seed_value := 0) -> Dictionary:
	var r := await _call(HTTPClient.METHOD_POST, "/v1/sessions", {"game": game, "seed": seed_value})
	session_id = r.get("session", "")
	return r


func restore(game: String, saved: Dictionary) -> Dictionary:
	var r := await _call(HTTPClient.METHOD_POST, "/v1/sessions", {"game": game, "snapshot": saved})
	session_id = r.get("session", "")
	return r


func observe(event: Dictionary) -> Dictionary:
	return await _call(HTTPClient.METHOD_POST, _in("observe"), event)


func update(change: Dictionary) -> Dictionary:
	return await _call(HTTPClient.METHOD_POST, _in("update"), change)


## What `npc` does at `moment`, and its line, which may still be provisional: see settle().
func decide(npc: String, moment: String, extra := {}) -> Dictionary:
	var line := await _call(HTTPClient.METHOD_POST, _in("decide"), _with({"npc": npc, "moment": moment}, extra))
	line_changed.emit(line)
	return line


func react(npc: String, trigger: String, extra := {}) -> Dictionary:
	var line := await _call(HTTPClient.METHOD_POST, _in("react"), _with({"npc": npc, "trigger": trigger}, extra))
	line_changed.emit(line)
	return line


func tick(steps := 1) -> Dictionary:
	return await _call(HTTPClient.METHOD_POST, _in("tick"), {"steps": steps})


## Poll a provisional line until it settles (final or withdrawn), emitting line_changed when it does.
func settle(line: Dictionary) -> Dictionary:
	var polls := 0
	while line.get("status") == "provisional" and polls < max_polls:
		polls += 1
		line = await _call(HTTPClient.METHOD_GET, _in("lines/%s?wait=%s" % [line["id"], poll_wait]))
	if line.get("status") != "provisional":
		line_changed.emit(line)
	return line


func inspect(npc: String) -> Dictionary:
	return await _call(HTTPClient.METHOD_GET, _in("npcs/" + npc))


func snapshot() -> Dictionary:
	return await _call(HTTPClient.METHOD_GET, _in("snapshot"))


func close() -> Dictionary:
	var r := await _call(HTTPClient.METHOD_DELETE, "/v1/sessions/" + session_id)
	session_id = ""
	return r


func _in(route: String) -> String:
	return "/v1/sessions/%s/%s" % [session_id, route]


func _with(body: Dictionary, extra: Dictionary) -> Dictionary:
	var out := body.duplicate()
	out.merge(extra)
	return out


## One request on its own HTTPRequest node, so calls can overlap (a poll while the player acts).
func _call(method: int, path: String, body = null) -> Dictionary:
	var http := HTTPRequest.new()
	http.timeout = poll_wait + 10.0
	add_child(http)
	var headers := PackedStringArray(["Content-Type: application/json"])
	var err := http.request(base_url + path, headers, method, "" if body == null else JSON.stringify(body))
	if err != OK:
		http.queue_free()
		return {"error": "request_failed", "reason": error_string(err)}
	var res: Array = await http.request_completed
	http.queue_free()
	var result: int = res[0]
	var code: int = res[1]
	if result != HTTPRequest.RESULT_SUCCESS:
		return {"error": "unreachable", "reason": "HTTPRequest result %d" % result}
	var text: String = (res[3] as PackedByteArray).get_string_from_utf8()
	if text.is_empty():
		return {"status_code": code}
	var data = JSON.parse_string(text)
	if typeof(data) != TYPE_DICTIONARY:
		return {"error": "bad_reply", "reason": text.left(200), "status_code": code}
	return data
