## Plays a whole week headless through Thespis, as a player would, and checks it hangs together: every walk, act,
## typed line, evening, round, the steamer and the Notebook. Quits 0 if it all held, 1 if not.
##
##   godot --headless --path games/before-the-ice res://tools/week.tscn -- --seed=7
##
## Thespis runs as a sidecar, as in the game ($THESPIS_SIDECAR says how to start it, if not the packaged runtime).
extends Node

var case: Case
var failures: Array[String] = []
var heard: Array[String] = []


func check(ok: bool, what: String) -> void:
	print(("  ok    " if ok else "  FAIL  ") + what)
	if not ok:
		failures.append(what)


func _ready() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--") and "=" in a:
			args[a.get_slice("=", 0).trim_prefix("--")] = a.get_slice("=", 1)
	case = Case.new()
	add_child(case)
	case.spoke.connect(func(l: ThespisLine): heard.append("%s: %s" % [l.npc, l.words("...")]))
	case.ended.connect(func(title: String, l: ThespisLine): print("  ending: %s. %s" % [title, l.words("") if l else ""]))
	case.keep_journal = true
	var r := await case.begin(int(args.get("seed", "7")))
	check(r.ok, "Thespis started and the week opened (%s)" % ("seed %d" % case.seed_value if r.ok else r.reason))
	if not r.ok:
		_quit()
		return
	check(case.where.get("vera") == "vera" and case.where.get("tamas") == "mission", "everyone starts where the case says")
	var spec: Dictionary = case.data.week
	var fair := range(1, 501).all(func(n): return Case.keeps(spec.rules, Case.roll(spec, n)))
	check(fair and Case.roll(spec, 7) == Case.roll(spec, 7), "every week seeds 1 to 500 make keeps the rules, and a seed makes the same week")
	print("  the week: %s" % case.week)

	# Day 1, morning: the roadhouse. Anton gives Maggie his story, and types something to her.
	await case.go("maggies")
	check(case.here == "maggies", "walked to Maggie's")
	await case.tell("maggie", {"pred": "with_vera", "a": "player"})
	var u := await Thespis.understand("where were you the night of the fire", "maggie", {"offered": case.offered()})
	check(u.ok and u.value.status == "act" and u.value.intent.verb == "ask", "typed words read as an act, no model")
	if u.ok and u.value.intent != null:
		await case.carry_out(u.value.intent)
	await case.end_phase()

	# Afternoon: the landing, then the store, where Billy is.
	await case.go("store")
	if "billy" in case.at("store"):
		await case.pay("billy", 5)
		var b := await Thespis.inspect("billy")
		check(b.ok and b.value.npc.flags.get("paid_off", false), "Billy pocketed five dollars and keeps quiet")
	await case.end_phase()

	# Evening: Věra's, across the ice, then the post.
	await case.go("vera")
	await case.comfort("vera")
	heard.clear()
	await case.end_phase()
	check(heard.size() == 1 and heard[0].begins_with("gilchrist:"), "the evening at the post: Gilchrist asks (%s)" % ", ".join(heard))
	await case.end_phase()
	check(case.day() == 2 and case.part() == 0, "the night passed: day 2, morning")

	# Days 2 to 5: Anton sits with Tamás each morning and lies low; the town and Gilchrist go on without him.
	while case.playing:
		if case.part() == 0:
			await case.go("mission")
			await case.ask("tamas")
		await case.end_phase()
	check(case.done, "the ice went out after %d phases" % case.phase)
	check(case.pressures.keys() == [2, 3, 4, 5] and case.pressures.values().all(func(p): return p >= 0.0 and p <= 1.0),
			"the director measured each morning: %s; brought out: %s" % [case.pressures,
			", ".join(case.incidents.map(func(i): return "day %d %s" % [i.day, i.name]))])

	var nb := await case.notebook()
	check(nb.contains(" · ") and (nb.contains("south") or nb.contains("lamp")), "the Notebook tells his case:\n%s" % nb)

	# The playtest's record: every morning and the steamer, what Anton did, and the ending; written out as a page.
	var kinds: Array = case.journal.map(func(e): return e.kind)
	check(kinds.count("morning") == 5 and kinds.count("steamer") == 1 and "ending" in kinds and "tell" in kinds
			and "line" in kinds, "the journal kept the week (%d entries)" % case.journal.size())
	var md := Journal.save(case, nb, true, "user://playtest-check")
	var page := FileAccess.get_file_as_string(md) if not md.is_empty() else ""
	check(page.contains("**Ending:**") and page.contains("## Day 5, morning") and page.contains("Gilchrist believes")
			and FileAccess.file_exists(md.get_basename() + ".json"), "the week's record was written: %s" % md)
	_quit()


func _quit() -> void:
	print("%d failed" % failures.size() if failures.size() > 0 else "the week held")
	await Thespis.stop()
	get_tree().quit(1 if failures.size() > 0 else 0)
