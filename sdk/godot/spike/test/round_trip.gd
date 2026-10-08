## The spike's gate: the tavern scene, driven headless against a running `thespis serve` (test/run.py starts one,
## with a scripted model). Exits 0 when every check passes, 1 when one fails, 2 on a timeout.
##
##   godot --headless --path sdk/godot/spike --script res://test/round_trip.gd
extends SceneTree

const TIMEOUT := 30.0

var failures: Array[String] = []
var checks := 0


func _initialize() -> void:
	var limit := TIMEOUT
	if not OS.get_environment("THESPIS_TEST_TIMEOUT").is_empty():
		limit = float(OS.get_environment("THESPIS_TEST_TIMEOUT"))  # a local model takes longer than a script
	create_timer(limit).timeout.connect(func():
		printerr("TIMEOUT after %ss" % limit)
		quit(2))
	_run.call_deferred()


func check(ok: bool, what: String, got = null) -> void:
	checks += 1
	if ok:
		print("  ok   ", what)
	else:
		failures.append(what)
		printerr("  FAIL ", what, "" if got == null else "  (got %s)" % JSON.stringify(got))


func _run() -> void:
	var scene: Control = load("res://main.tscn").instantiate()
	var url := OS.get_environment("THESPIS_URL")
	if not url.is_empty():
		scene.server = url
	root.add_child(scene)
	var opened: bool = await scene.opened
	check(opened, "a session opens on the tavern", scene.thespis.session_id)
	if not opened:
		return _done()

	# Before anything happens, Garrick knows nothing: he rides on, and has nothing to cite, so says nothing.
	var before: Dictionary = await scene.ask()
	check(before.get("action") == "leave" and before.get("text") == null and before.get("status") == "final",
			"knowing nothing, he leaves in silence, and no model is asked", before)

	var e: Dictionary = await scene.insult()
	check(e.get("id") == "e0001" and e.get("truth") == true, "the insult is observed", e)

	# Now he confronts the player. The template line comes at once, and the model's follows.
	var thespis = scene.thespis
	var started := Time.get_ticks_msec()
	var first: Dictionary = await thespis.decide("garrick", "turn")
	var shown := Time.get_ticks_msec() - started
	check(first.get("action") == "confront:player", "angry and insulted, he confronts the player", first)
	check(first.get("status") == "provisional" and first.get("text") == "You. Say it again, to my face.",
			"his template line arrives provisional", first)
	var final: Dictionary = await thespis.settle(first)
	print("  (template line shown after %d ms; the model's after %d ms)" % [shown, Time.get_ticks_msec() - started])
	check(final.get("status") == "final" and final.get("source") == "llm", "the model's line settles it", final)
	check(final.get("cites") == ["e0001"], "it cites the insult", final.get("cites"))
	check(scene.line_label.text.ends_with(str(final.get("text"))), "the scene shows the final line",
			scene.line_label.text)

	# Wren saw it, and the minds survive a save.
	var wren: Dictionary = await thespis.inspect("wren")
	check(wren.get("beliefs", []).size() == 1, "Wren, who saw it, believes it", wren.get("beliefs"))
	var saved: Dictionary = await thespis.snapshot()
	var path := "user://tavern_save.json"
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify(saved))
	f.close()
	await thespis.close()
	var loaded = JSON.parse_string(FileAccess.get_file_as_string(path))
	var r: Dictionary = await thespis.restore("tavern", loaded)
	check(r.has("session"), "a save file restores the session", r)
	var garrick: Dictionary = await thespis.inspect("garrick")
	check(garrick.get("npc", {}).get("drives", {}).get("grudge") == 4.0, "his grudge came back with it",
			garrick.get("npc"))
	var again: Dictionary = await thespis.snapshot()
	check(_same(again["world"], saved["world"]), "the restored minds are the saved ones")
	# GDScript read the save's numbers as floats; the restored mind must still think in whole numbers.
	var after: Dictionary = await thespis.decide("garrick", "turn", {"wait": true})
	var why: String = str(after.get("reason", "")).get_slice(";", 0)
	check(why == "confront:player scores 7", "the restored mind decides as before", after.get("reason"))
	await thespis.close()
	_done()


## JSON numbers come back as floats in GDScript; compare saves through JSON text, keys sorted.
func _same(a, b) -> bool:
	return JSON.stringify(a, "", true) == JSON.stringify(b, "", true)


func _done() -> void:
	print("%d checks, %d failed" % [checks, failures.size()])
	quit(0 if failures.is_empty() else 1)
