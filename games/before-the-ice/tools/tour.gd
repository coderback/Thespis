## A playthrough of the real screens: loads the game scene and plays a week through it the way a player would (a flag
## on the model, the walk, the conversation's answers and typed words, leaving, the evenings at the post, the ending
## and the Notebook), calling what each click calls. At every screen it saves a screenshot and writes down what the
## screen says, to look through before a playtest. Needs a window (screenshots), not --headless.
##
##   godot --path games/before-the-ice res://tools/tour.tscn -- --seed=19 --out=<dir> [--log=<dir>]
extends Node

## The week, phase by phase: where Anton goes, then what he does there. Each step: [whom to speak to ("" for whoever is
## first), [answers, each a piece of its words, or "type:<words>"]]. A phase not given: he goes to Věra's.
const WEEK := [
	["maggies", [["", ["What did you see", "Věra's till late"]], ["otto", ["What did you see"]]]],
	["store", [["billy", ["five dollars", "What did you see"]], ["martha", ["gloves", "What did you see"]]]],
	["dest", [["", ["sorry"]]]],
	["church", [["tamas", ["How are you today"]], ["sandor", ["What did you see"]]]],
	["landing", [["ashby", ["What did you see", "type:where were you when the fire started"]]]],
	["dest", [["", ["sorry", "What did you see"]]]],
	["church", [["tamas", ["How are you today"]]]],
	["maggies", [["", ["Ashby's lantern"]], ["martha", ["What did you see"]]]],
	["dest", [["", ["sorry"]]]],
	["church", [["tamas", ["How are you today"]]]],
	["store", [["", ["What did you see"]]]],
	["dest", [["", ["sorry"]]]],
	["church", [["tamas", ["How are you today"]]]],
	["landing", [["", ["What did you see"]]]],
	["dest", [["", ["sorry"]]]],
]

var main: Node
var out := ""
var shots := 0
var notes: Array = []


func _ready() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--") and "=" in a:
			args[a.get_slice("=", 0).trim_prefix("--")] = a.get_slice("=", 1)
	out = str(args.get("out", "user://tour"))
	DirAccess.make_dir_recursive_absolute(out)
	main = load("res://scenes/main.tscn").instantiate()
	add_child(main)
	await _until(func(): return main.case != null and main.case.playing, 90.0)
	await _settle()
	_shot("day1-morning-town")
	for i in WEEK.size():
		if not main.case.playing:
			break
		var phase_name := "day%d-%s" % [main.case.day(), ["morning", "afternoon", "evening"][main.case.part()]]
		var step: Array = WEEK[i]
		await _visit(phase_name, step[0], step[1])
	await _until(func(): return main.case.done and main.talk.visible, 120.0)
	await _settle(2.0)
	_note("ending", main.talk)
	_shot("ending")
	var path := "%s/tour.md" % out
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string("\n".join(notes) + "\n")
	f.close()
	print("The tour: %d screenshots and %s" % [shots, ProjectSettings.globalize_path(path)])
	await get_tree().create_timer(1.0).timeout
	main._notification(NOTIFICATION_WM_CLOSE_REQUEST)  # the week's record, if the steamer didn't write it
	await Thespis.stop()
	get_tree().quit()


## One phase: choose the flag, walk (skipping the walk once it's seen), sit and talk, leave; in the evening, sit with
## Gilchrist at the post too.
func _visit(phase_name: String, place: String, steps: Array) -> void:
	notes.append("\n## %s: %s" % [phase_name, place])
	var evening: bool = main.case.part() == 2
	main.paper.chosen.emit(place)
	await get_tree().create_timer(0.6).timeout
	if phase_name == "day1-morning":
		_shot(phase_name + "-walking")
	await _until(func(): return main.walk.walking or main.talk.visible, 10.0)
	while main.walk.walking:
		main.walk.skip()
		await get_tree().process_frame
	await _until(func(): return main.talk.visible and not main.talk._busy, 30.0)
	await _settle()
	_note("arrived", main.talk)
	_shot(phase_name + "-" + place)
	for st in steps:
		if not str(st[0]).is_empty() and st[0] != main.talk.to:
			if st[0] not in main.case.at(main.case.here):
				notes.append("- (%s isn't here)" % st[0])
				continue
			main.talk._speak_to(st[0])
			await _quiet()
		for want in st[1]:
			await _answer(str(want))
		_note("after " + (main.talk.to if not main.talk.to.is_empty() else "nobody"), main.talk)
	_shot(phase_name + "-" + place + "-done")
	var before: int = main.case.phase
	main.talk._go()
	if evening:  # the post: Gilchrist's question
		await _until(func(): return main.talk.visible and main.talk.to == "gilchrist" and not main.talk._busy, 60.0)
		await _settle()
		_note("the post", main.talk)
		_shot(phase_name + "-post")
		await _answer("What do you know so far")
		_note("the post, after asking", main.talk)
		main.talk._go()
	await _until(func(): return main.case.phase != before and not main.talk.visible or main.case.done, 60.0)
	await _settle()
	if main.case.part() == 0 and main.case.playing:
		_shot("day%d-morning-town" % main.case.day())


func _answer(want: String) -> void:
	if want.begins_with("type:"):
		main.talk._words.text = want.trim_prefix("type:")
		main.talk._typed()
		notes.append("- typed: \"%s\"" % want.trim_prefix("type:"))
		await _quiet()
		return
	for i in main.talk._choices.size():
		if want in str(main.talk._choices[i].say):
			notes.append("- answer %d: %s" % [i + 1, main.talk._choices[i].say])
			main.talk._answer(i)
			await _quiet()
			return
	notes.append("- (no answer like \"%s\" with %s)" % [want, main.talk.to])


## What the conversation screen shows now.
func _note(when: String, t: Node) -> void:
	notes.append("- **%s** at %s, with %s (%s): \"%s\"" % [when, t._title, t._name.text, t._role.text,
			t._speech.text.replace("\n", " ")])
	var answers: Array = t._choices.map(func(c): return "%s [%s]" % [c.say, c.hint])
	notes.append("  - answers (%d spent of %d): %s" % [t.spent, t.ANSWERS, " | ".join(answers)])
	if t._note.text.strip_edges() != "":
		notes.append("  - note: %s" % t._note.text.replace("\n", " / ").left(300))
	notes.append("  - the desk: %s" % main.paper.prompt_line.text)


func _shot(name: String) -> void:
	shots += 1
	var img := get_viewport().get_texture().get_image()
	img.save_png("%s/%02d-%s.png" % [out, shots, name])
	notes.append("- screenshot %02d-%s" % [shots, name])


func _quiet() -> void:
	await get_tree().create_timer(0.3).timeout
	await _until(func(): return not main.talk._busy, 30.0)
	await _settle(0.6)


func _settle(seconds := 1.2) -> void:
	await get_tree().create_timer(seconds).timeout
	await RenderingServer.frame_post_draw


func _until(cond: Callable, seconds: float) -> void:
	var left := seconds
	while not cond.call() and left > 0:
		await get_tree().process_frame
		left -= get_process_delta_time()
