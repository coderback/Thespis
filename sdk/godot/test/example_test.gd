## The addon's gate: the Lantern example scene, driven headless. test/run.py runs it twice, with the scene unchanged:
## against a sidecar the addon starts itself, and against a server in hosted mode, with a project key. Exits 0 when
## every check passes, 1 when one fails, 2 on a timeout.
##
##   THESPIS_EXPECT=sidecar godot --headless --path sdk/godot --script res://test/example_test.gd
extends SceneTree

const TEMPLATE := "You. Say it again, to my face."

var failures: Array[String] = []
var checks := 0
var arrived := {}  # line id -> times line_arrived fired
var settled := {}  # line id -> times line_settled fired


func _initialize() -> void:
	var limit := float(OS.get_environment("THESPIS_TEST_TIMEOUT")) if OS.has_environment("THESPIS_TEST_TIMEOUT") \
			else 60.0
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
		printerr("  FAIL ", what, "" if got == null else "  (got %s)" % str(got))


func _run() -> void:
	var expect := OS.get_environment("THESPIS_EXPECT")  # sidecar or server
	var model := OS.get_environment("THESPIS_TEST_MODEL")  # a local model for the sidecar, for the offline gate
	if not model.is_empty():
		ProjectSettings.set_setting("thespis/sidecar/model", model)
	for old in ["", "-wal", "-shm"]:  # a fresh sidecar, whose reply cache hasn't heard these lines before
		DirAccess.remove_absolute(ProjectSettings.globalize_path("user://thespis/sessions.sqlite" + old))
	var thespis: ThespisClient = root.get_node("Thespis")
	thespis.line_arrived.connect(func(l: ThespisLine): arrived[l.id] = arrived.get(l.id, 0) + 1)
	thespis.line_settled.connect(func(l: ThespisLine): settled[l.id] = settled.get(l.id, 0) + 1)

	var scene: Control = load("res://example/tavern.tscn").instantiate()
	root.add_child(scene)
	var started: ThespisResult = await scene.ready_to_play
	check(started.ok, "the scene starts Thespis and opens the tavern", started)
	if not started.ok:
		return _done(thespis)
	check(thespis.is_sidecar() == (expect == "sidecar"), "it runs as a %s, with no change to the scene" % expect,
			thespis.url)
	var health: ThespisResult = await thespis.health()
	check(health.value is ThespisApi.HealthOut and health.value.offline == (expect == "sidecar"),
			"the sidecar is offline; the server is online", health)

	# Knowing nothing, Garrick leaves in silence, and no model is asked.
	var before: ThespisResult = await scene.ask_garrick()
	var quiet: ThespisLine = before.value
	check(quiet is ThespisLine and quiet.action == "leave" and quiet.is_silent() and quiet.is_final(),
			"a reply is a typed line: knowing nothing, he leaves in silence", before)

	var insult: ThespisResult = await scene.insult()
	var e = insult.value
	check(e is ThespisApi.EventOut and e.id == "e0001" and e.truth == true and typeof(e.phase) == TYPE_INT,
			"the insult is observed, as a typed event with whole numbers", insult)

	# He confronts the player: his template line at once, then the model's.
	var t0 := Time.get_ticks_msec()
	var asked: ThespisResult = await scene.ask_garrick()
	var shown := Time.get_ticks_msec() - t0
	var spoken: ThespisLine = asked.value
	check(spoken.action == "confront:player" and spoken.is_provisional() and spoken.text == TEMPLATE,
			"angry and insulted, he confronts the player, and his template line arrives provisional", asked)
	check(scene.get_node("%Garrick").modulate.a < 1.0, "the scene shows it as provisional")
	var final := await thespis.settle(spoken)
	print("  (template line after %d ms; the model's after %d ms)" % [shown, Time.get_ticks_msec() - t0])
	check(final == spoken and final.is_final() and final.source == "llm" and final.cites == ["e0001"],
			"the client follows it until the model's line settles it, citing the insult", final.to_dict())
	await process_frame
	var label: Label = scene.get_node("%Garrick")
	check(label.text.ends_with(final.words()) and label.modulate.a == 1.0, "the scene shows the final line",
			label.text)
	check(arrived.get(spoken.id) == 1 and settled.get(spoken.id) == 1, "line_arrived, then line_settled, once each",
			[arrived.get(spoken.id), settled.get(spoken.id)])

	var wren: ThespisResult = await thespis.inspect("wren")
	check(wren.value is ThespisApi.NpcOut and wren.value.beliefs.size() == 1, "Wren, who saw it, believes it", wren)
	var nobody: ThespisResult = await thespis.inspect("nobody")
	check(not nobody.ok and nobody.status == 404 and not nobody.error.is_empty(),
			"a failed call is a result, not a crash", nobody)

	var hour: ThespisResult = await scene.pass_hour()
	check(hour.value is ThespisApi.TickOut and hour.value.phase == 1 and scene.pip_at == "taproom",
			"an hour passes, and Pip walks into the taproom", hour)
	var told: ThespisResult = await scene.what_happened()
	var telling := await thespis.settle(told.value)
	check(telling.npc == "narrator" and telling.is_final() and not scene.get_node("%Narrator").text.is_empty(),
			"the narrator tells what happened", telling.to_dict())

	# More calls at once than the client has requests: they queue, and every one comes back.
	var replies := []
	for i in 8:
		var ask := func(): replies.append(await thespis.react(["garrick", "wren"][i % 2], "talk"))
		ask.call()
	while replies.size() < 8:
		await process_frame
	check(replies.all(func(r): return r.ok), "eight lines asked for at once all come back",
			replies.filter(func(r): return not r.ok))

	# The minds go into the game's own save file as text, and come back as they were.
	var path := "user://lantern_test.save"
	var choice: ThespisResult = await thespis.decide("garrick", "turn", {"wait": true})  # an hour cooled him: 3 now
	var saved: ThespisResult = await scene.save_game(path)
	check(saved.ok and saved.value is String, "the save holds the minds as text", saved)
	var loaded: ThespisResult = await scene.load_game(path)
	check(loaded.ok and loaded.value is ThespisApi.SessionOut and scene.pip_at == "taproom",
			"loading the save restores the session and the scene", loaded)
	var after_load: ThespisResult = await thespis.snapshot()
	# Against the save itself: a line still settling in the background may change the minds just before it.
	check(_world(after_load.value) == _world(saved.value), "the restored minds are the saved ones")
	var again: ThespisResult = await thespis.decide("garrick", "turn", {"wait": true})
	var why: String = again.value.reason.get_slice(";", 0)
	check(why == choice.value.reason.get_slice(";", 0) and not ".0" in why,
			"the restored mind decides as before, still in whole numbers", [why, choice.value.reason])

	if expect == "sidecar":
		var h: ThespisResult = await thespis.health()
		check(h.value.refused == 0, "the sidecar reached for nothing off this machine", h.value.refused)
	_done(thespis)


## Saves compared through their worlds, keys sorted.
func _world(text: String) -> String:
	return JSON.stringify(JSON.parse_string(text)["world"], "", true)


func _done(thespis: ThespisClient) -> void:
	var pid := thespis.sidecar.pid if thespis.sidecar else -1
	await thespis.stop()
	if pid > 0:
		await create_timer(0.5).timeout
		check(not OS.is_process_running(pid), "stopping the client stops the sidecar")
	print("%d checks, %d failed" % [checks, failures.size()])
	quit(0 if failures.is_empty() else 1)
