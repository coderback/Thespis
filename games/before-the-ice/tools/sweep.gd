## The seed sweep: plays whole weeks headless through Thespis, a few fixed ways of playing over many seeds, and counts
## how each week ended. It answers: can every ending still be reached, and does one way of playing always win?
##
##   godot --headless --path games/before-the-ice res://tools/sweep.tscn -- --seeds=24 [--from=1]
##         [--only=alibi,confess] [--out=<file.json>]
##
## Each way of playing is a plan: where Anton goes in a phase and what he does there. An act needs its person to be
## there; one who isn't is counted as missed, not done. The week each seed makes (case.json's week: who saw the
## lantern, whose face Tamás sees and when, what the town says...) is reported beside the ending, and the endings by
## each draw. Thespis runs as a sidecar, started once ($THESPIS_SIDECAR, as for tools/week.gd); every week is a fresh
## session.
extends Node

const ALIBI := {"pred": "with_vera", "a": "player"}
const ASHBY_LANTERN := {"pred": "lantern", "a": "ashby"}
const ASHBY_FIRE := {"pred": "fired", "a": "ashby", "b": "otto"}
const DRUNK := {"pred": "drunk", "a": "tamas"}
const BOTTLE := {"pred": "sold_bottle", "a": "maggie", "b": "tamas"}
const LAMP := {"pred": "fired", "a": "tamas", "b": "otto"}
const OTTO_FIRE := {"pred": "fired", "a": "otto", "b": "otto"}
const OTTO_BACK := {"pred": "back_room", "a": "otto"}
const BILLY_LANTERN := {"pred": "lantern", "a": "billy"}
const BILLY_DOOR := {"pred": "woodpile", "a": "billy"}

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
	"blame Otto": {
		"1.0": ["maggies", [["tell", "maggie", OTTO_FIRE]]],
		"1.2": ["police", [["tell", "gilchrist", OTTO_FIRE]]],
		"2.2": ["police", [["tell", "gilchrist", OTTO_BACK]]],
		"*.0": ["mission", [["ask", "tamas", null]]],
		"*.2": ["vera", [["comfort", "vera", null]]],
	},
	"blame Billy": {
		"1.0": ["maggies", [["tell", "maggie", BILLY_LANTERN]]],
		"1.2": ["police", [["tell", "gilchrist", BILLY_LANTERN]]],
		"2.2": ["police", [["tell", "gilchrist", BILLY_DOOR]]],
		"*.0": ["mission", [["ask", "tamas", null]]],
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

## What Gilchrist believed at the end, reported for these: his case, as the evidence stood.
const WATCHED := ["fired", "lantern", "with_vera", "left_vera", "saw_lane"]
## The steps of his case against Anton, counted in the report: beliefs he held, and things he'd done.
const STEPS := ["lantern(someone)", "lantern(player)", "fired(player)", "not with_vera(player)", "left_vera(player)",
		"saw_lane(martha)", "asked_vera", "asked_martha", "warned", "searched", "asked_otto", "asked_billy"]

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
			print("  seed %3d  %-20s %-12s %s%s" % [s, plan, run.ending, _drawn(run.week),
					("  (missed: %s)" % ", ".join(run.missed)) if run.missed.size() > 0 else ""])
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
			"week": {}, "knew": {}, "did": [], "pressure": {}, "incidents": []}
	var r := await case.begin(s)
	if not r.ok:
		run.reason = r.reason
		case.queue_free()
		return run
	run.week = case.week
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
	run.pressure = case.pressures
	run.incidents = case.incidents.map(func(i): return "day %d: %s" % [i.day, i.name])
	run.ok = case.done and not ending.is_empty()
	run.reason = "" if run.ok else "the week didn't reach the steamer"
	run.ending = ending
	run.title = title
	var g := await Thespis.inspect("gilchrist")  # what he went south believing, and what he'd done
	if g.ok:
		for b in g.value.beliefs:
			var c: Dictionary = b.claim
			if b.status == "active" and str(c.pred) in WATCHED:
				run.knew[_claim(c)] = snappedf(float(b.opinion.b), 0.01)
		for f in g.value.npc.get("flags", {}):
			if g.value.npc.flags[f]:
				run.did.append(f)
	await Thespis.close()
	case.queue_free()
	return run


## The director: the pressure each morning by way of playing (the mean over seeds, against the target), and what it
## brought out, with how those weeks ended.
func _director(runs: Array, plans: Array) -> void:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://case.json"))
	var targets: Dictionary = data.director.targets
	print("\nThe pressure on Anton each morning (mean over seeds; the target in brackets):")
	print("  %-20s %s" % ["", "  ".join([2, 3, 4, 5].map(func(d): return ("day %d (%s)" % [d, targets[str(d)]]).rpad(14)))])
	for plan in plans:
		var mine: Array = runs.filter(func(r): return r.plan == plan)
		var row: Array = []
		for d in [2, 3, 4, 5]:
			var total := 0.0
			for r in mine:
				total += float(r.pressure.get(d, 0.0))
			row.append(("%.2f" % (total / maxf(1.0, mine.size()))).rpad(14))
		print("  %-20s %s" % [plan, "  ".join(row)])
	print("\nWhat the director brought out (weeks), and how those weeks ended:")
	var seen := {}
	for r in runs:
		for i in r.incidents:
			var name: String = i.get_slice(": ", 1)
			if not seen.has(name):
				seen[name] = {}
			seen[name][r.ending] = seen[name].get(r.ending, 0) + 1
	for name in seen:
		var parts: Array = []
		for e in seen[name]:
			parts.append("%s %d" % [e, seen[name][e]])
		print("  %-30s %s" % [name, ", ".join(parts)])
	print("  %-30s %d weeks" % ["(nothing brought out)", runs.filter(func(r): return r.incidents.is_empty()).size()])


## A week, short: each draw's option, the usual ones left out.
static func _drawn(w: Dictionary) -> String:
	var usual := {"lantern": "Billy and Otto", "face": "not seen", "whose face": "Anton's", "talk": "nothing yet",
			"sister": "he left at half past eleven", "kitchen": "Věra", "woodpile": "Otto",
			"back room": "she says so"}
	var parts: Array = []
	for d in w:
		if usual.get(d, "") != w[d]:
			parts.append("%s: %s" % [d, w[d]])
	return "; ".join(parts)


## A claim as the report writes it: pred(who), "not " first for a denial; the fire's object (always Brand's store)
## left out.
static func _claim(c: Dictionary) -> String:
	var who := str(c.a)
	if c.has("b") and str(c.pred) != "fired":
		who = "%s, %s" % [c.a, c.b]
	return "%s%s(%s)" % ["not " if c.get("neg", false) else "", c.pred, who]


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
	print("\nHow far his case against Anton got (weeks, of each way of playing):")
	print("  %-20s %s" % ["", "  ".join(STEPS.map(func(st): return st.left(12).rpad(12)))])
	for plan in plans:
		var row: Array = []
		for st in STEPS:
			row.append(str(runs.filter(func(r): return r.plan == plan and (r.knew.has(st) or st in r.did)).size()).rpad(12))
		print("  %-20s %s" % [plan, "  ".join(row)])
	_director(runs, plans)
	print("\nDoes the seed move the ending? (for each way of playing: how many endings, and the commonest's share)")
	for plan in plans:
		var mine: Array = runs.filter(func(r): return r.plan == plan)
		var counts := {}
		for r in mine:
			counts[r.ending] = counts.get(r.ending, 0) + 1
		var top: int = counts.values().max() if counts.size() > 0 else 0
		print("  %-20s %d endings, the commonest %d of %d" % [plan, counts.size(), top, mine.size()])
	print("\nBy what the seed drew (every way of playing together):")
	var draws := {}
	for r in runs:
		for d in r.week:
			var key := "%s: %s" % [d, r.week[d]]
			if not draws.has(key):
				draws[key] = {}
			draws[key][r.ending] = draws[key].get(r.ending, 0) + 1
	var keys: Array = draws.keys()
	keys.sort()
	for k in keys:
		var parts: Array = []
		for e in draws[k]:
			parts.append("%s %d" % [e, draws[k][e]])
		print("  %-40s %s" % [k, ", ".join(parts)])
	var never: Array = ["nobody", "breakup", "take:ashby", "take:otto", "take:billy", "take:vera", "arrest", "mercy"].filter(
			func(e): return e not in endings)
	print("\nNever reached: %s" % (", ".join(never) if never.size() > 0 else "none"))
