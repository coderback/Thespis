## The outcome of a Thespis call. GDScript has no exceptions, so every call returns one of these and nothing raises:
##
##   var r := await Thespis.decide("garrick", "turn")
##   if r.ok:
##       show(r.value)
##   else:
##       push_warning("%s: %s" % [r.error, r.reason])
class_name ThespisResult
extends RefCounted

var ok := false
var value = null  ## the reply, typed (a ThespisLine, a ThespisApi.EventOut...); a snapshot's is its text
var error := ""  ## the server's code (not_found, not_allowed, over_cap...), or unreachable, request_failed, bad_reply
var reason := ""  ## what went wrong, in words
var status := 0  ## the HTTP status; 0 when the server was never reached


static func success(reply, code := 200) -> ThespisResult:
	var r := ThespisResult.new()
	r.ok = true
	r.value = reply
	r.status = code
	return r


static func failure(code_word: String, why: String, code := 0) -> ThespisResult:
	var r := ThespisResult.new()
	r.error = code_word
	r.reason = why
	r.status = code
	return r


func _to_string() -> String:
	return "ok %s" % [value] if ok else "%s (%d): %s" % [error, status, reason]
