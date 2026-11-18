## The seed sweep: plays whole weeks headless through Thespis, a few fixed ways of playing over many seeds, and counts
## how each week ended. It answers: can every ending still be reached, and does one way of playing always win?
##
##   godot --headless --path games/before-the-ice res://tools/sweep.tscn -- --seeds=24 [--from=1]
##         [--only=alibi,confess] [--out=<file.json>]
##
## Each way of playing is a plan: where Anton goes in a phase and what he does there. An act needs its person to be
## there; one who isn't is counted as missed, not done. The world each seed makes is reported beside the ending:
## whether Martha saw his face, and the day Tamás remembers it (0, never). Thespis runs as a sidecar, started once
## ($THESPIS_SIDECAR, as for tools/week.gd); every week is a fresh session.
extends Node

const ALIBI := {"pred": "with_vera", "a": "player"}
const ASHBY_LANTERN := {"pred": "lantern", "a": "ashby"}
const ASHBY_FIRE := {"pred": "fired", "a": "ashby", "b": "otto"}
const DRUNK := {"pred": "drunk", "a": "tamas"}
const BOTTLE := {"pred": "sold_bottle", "a": "maggie", "b": "tamas"}
const LAMP := {"pred": "fired", "a": "tamas", "b": "otto"}

## The ways of playing. Each phase is "day.part" (part 0 morning, 1 afternoon, 2 evening), or "*.part" for that part
## of every day not given; its value is [place, acts], each act [verb, person, what]. A phase not given: he stays put.
const PLANS := {
	"lie low": {},
	"alibi": {
		"1.0": ["maggies", [["tell", "maggie", ALIBI]]],
		"*.0": ["mission", [["ask", "tamas", null]]],
		"*.2": ["vera", [["comfort", "vera", null]]],
	},
	"blame Ashby": {
		"1.0": ["maggies", [["tell", "maggie", ASHBY_LANTERN], ["tell", "maggie", ASHBY_FIRE]]],
		"1.2": ["police", [["tell", "gilchrist", ASHBY_LANTERN]]],
		"2.0": ["mission", [["tell", "tamas", ASHBY_LANTERN], ["tell", "sandor", ASHBY_FIRE]]],
		"*.0": ["mission", [["ask", "tamas", null]]],
		"*.2": ["vera", [["comfort", "vera", null]]],
	},
	"the true thing": {
		"1.2": ["police", [["tell", "gilchrist", DRUNK], ["tell", "gilchrist", BOTTLE]]],
		"*.0": ["mission", [["ask", "tamas", null]]],
		"*.2": ["vera", [["comfort", "vera", null]]],
	},
	"the watchman's lamp": {
		"1.0": ["maggies", [["tell", "maggie", LAMP], ["tell", "maggie", DRUNK]]],
		"1.2": ["police", [["tell", "gilchrist", LAMP], ["tell", "gilchrist", DRUNK]]],
		"*.2": ["vera", [["comfort", "vera", null]]],
	},
	"pay Billy": {
		"1.0": ["maggies", [["tell", "maggie", ALIBI]]],
		"1.1": ["store", [["pay", "billy", 5]]],
		"*.0": ["mission", [["ask", "tamas", null]]],
		"*.2": ["vera", [["comfort", "vera", null]]],
	},
	"lose Věra": {
		"1.2": ["vera", [["threaten", "vera", null]]],
		"2.2": ["police", [["tell", "gilchrist", ALIBI]]],
	},
	"confess": {
		"2.2": ["police", [["confess", "gilchrist", null]]],
	},
}

var case: Case
var ending := ""
var title := ""


func _ready() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--") and "=" in a:
			args[a.get_slice("=", 0).trim_prefix("--")] = a.get_slice("=", 1)
	var first := int(args.get("from", "1"))
	var seeds := int(args.get("seeds", "8"))
	var plans: Array = PLANS.keys() if not args.has("only") else Array(str(args.only).split(","))
	var runs: Array = []
	var started := Time.get_ticks_msec()
	for s in range(first, first + seeds):
		for plan in plans:
			var run := await _week(plan, s)
			runs.append(run)
			print("  seed %3d  %-20s %-22s face %-5s Tamás day %d%s" % [s, plan, run.ending, run.face_seen,
					run.face_day, ("  (missed: %s)" % ", ".join(run.missed)) if run.missed.size() > 0 else ""])
			if not run.ok:
				print("    stopped: %s" % run.reason)
	_report(runs, plans)
	print("%d weeks in %d s" % [runs.size(), (Time.get_ticks_msec() - started) / 1000])
	if args.has("out"):
		var f := FileAccess.open(str(args.out), FileAccess.WRITE)
		f.store_string(JSON.stringify(runs, " "))
	await Thespis.stop()
	get_tree().quit(0 if runs.all(func(r): return r.ok) else 1)


## One week, played one way on one seed.
func _week(plan: String, s: int) -> Dictionary:
	case = Case.new()
	add_child(case)
	ending = ""
	title = ""
	case.ended.connect(_ended)
	var run := {"seed": s, "plan": plan, "ok": false, "reason": "", "ending": "", "title": "", "missed": [],
			"face_seen": false, "face_day": 0}
	var r := await case.begin(s)
	if not r.ok:
		run.reason = r.reason
		case.queue_free()
		return run
	run.face_seen = case.face_seen
	run.face_day = case.face_day
	var steps: Dictionary = PLANS.get(plan, {})
	var done_at := -1
	while case.playing:
		if case.phase != done_at and not case.sat_with_him:  # once a phase, before the evening at the post
			done_at = case.phase
			var step: Variant = steps.get("%d.%d" % [case.day(), case.part()], steps.get("*.%d" % case.part()))
			if step != null:
				await case.go(step[0])
				for act in step[1]:
					if act[1] in case.at(case.here):
						await _do(act)
					else:
						run.missed.append("%s %s, day %d" % [act[0], act[1], case.day()])
		await case.end_phase()
	run.ok = case.done and not ending.is_empty()
	run.reason = "" if run.ok else "the week didn't reach the steamer"
	run.ending = ending
	run.title = title
	await Thespis.close()
	case.queue_free()
	return run


func _ended(t: String, l: ThespisLine) -> void:
	title = t
	ending = str(l.action) if l != null else ""


func _do(act: Array) -> void:
	var npc: String = act[1]
	match str(act[0]):
		"tell":
			await case.tell(npc, act[2])
		"ask":
			await case.ask(npc)
		"pay":
			await case.pay(npc, int(act[2]))
		"comfort":
			await case.comfort(npc)
		"threaten":
			await case.threaten(npc)
		"confess":
			await case.confess(npc)


## How the weeks ended: for each way of playing, how often each ending came; then each world the seeds made.
func _report(runs: Array, plans: Array) -> void:
	var endings: Array = []
	for r in runs:
		if r.ending not in endings and not r.ending.is_empty():
			endings.append(r.ending)
	endings.sort()
	print("\nHow the weeks ended, by way of playing:")
	print("  %-20s %s" % ["", "  ".join(endings.map(func(e): return "%-10s" % e))])
	for plan in plans:
		var row: Array = []
		for e in endings:
			row.append("%-10d" % runs.filter(func(r): return r.plan == plan and r.ending == e).size())
		print("  %-20s %s" % [plan, "  ".join(row)])
	print("\nBy the world the seed made (face seen by Martha / the day Tamás remembers):")
	var worlds := {}
	for r in runs:
		var w := "face %s, Tamás day %d" % ["seen" if r.face_seen else "not seen", r.face_day]
		if not worlds.has(w):
			worlds[w] = {}
		worlds[w][r.ending] = worlds[w].get(r.ending, 0) + 1
	for w in worlds:
		var parts: Array = []
		for e in worlds[w]:
			parts.append("%s %d" % [e, worlds[w][e]])
		print("  %-30s %s" % [w, ", ".join(parts)])
	var never: Array = ["nobody", "breakup", "take:ashby", "take:otto", "take:billy", "take:vera", "arrest", "mercy"].filter(
			func(e): return e not in endings)
	print("\nNever reached: %s" % (", ".join(never) if never.size() > 0 else "none"))
