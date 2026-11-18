## A playtest's record of one week, written out when the ice goes out (or the window closes): a JSON file with
## everything, and a Markdown page to read beside the player's own account of their week. The case keeps the
## journal (Case.keep_journal); this writes it. docs/before-the-ice-playtest.md says how a session runs.
class_name Journal
extends RefCounted

const DIR := "user://playtest"
const PARTS := ["morning", "afternoon", "evening"]
const PLACES := {"landing": "the landing", "maggies": "Maggie's", "store": "Brand's store", "mission": "the mission",
		"police": "the post", "ice": "the ice", "vera": "Věra's", "your_cabin": "your cabin",
		"downriver": "downriver"}


## Write the week out: <dir>/<when>-seed<N>.json and .md. The Markdown file's path, or "" if it couldn't be written.
## `notebook` is the Inspector's Notebook, if it was told; `ended` false for a week the player left early.
static func save(case: Case, notebook := "", ended := true, dir := DIR) -> String:
	DirAccess.make_dir_recursive_absolute(dir)
	var stamp := Time.get_datetime_string_from_system().replace(":", "-").replace("T", "_")
	var base := "%s/%s-seed%d" % [dir, stamp, case.seed_value]
	var record := {"seed": case.seed_value, "week": case.week, "ended": ended, "phases_played": case.phase,
			"notebook": notebook, "journal": case.journal}
	var j := FileAccess.open(base + ".json", FileAccess.WRITE)
	if j == null:
		return ""
	j.store_string(JSON.stringify(record, "  "))
	j.close()
	var m := FileAccess.open(base + ".md", FileAccess.WRITE)
	if m == null:
		return ""
	m.store_string(page(case.seed_value, case.week, case.journal, notebook, ended))
	m.close()
	return ProjectSettings.globalize_path(base + ".md")


## The week as a page: what the seed drew, then each phase (what Anton did and heard, what was said where he wasn't,
## the news), each morning what Gilchrist believed and whom the town still trusted, the ending and the Notebook.
static func page(seed_value: int, week: Dictionary, journal: Array, notebook: String, ended: bool) -> String:
	var out: Array = []
	var ending := "the player stopped before the steamer"
	for e in journal:
		if e.kind == "ending":
			ending = "%s (%s)" % [e.title, e.action]
	out.append("# Before the Ice Goes Out: seed %d\n" % seed_value)
	out.append("**Ending:** %s\n" % ending)
	out.append("## The week the seed drew (the player doesn't see this)\n")
	for d in week:
		out.append("- %s: %s" % [d, week[d]])
	var at := ""
	for e in journal:
		var when := "Day %d, %s" % [e.day, PARTS[int(e.part)]]
		if e.kind == "steamer":
			when = "The steamer"
		if when != at:
			at = when
			out.append("\n## %s\n" % when)
		var line := _line(e)
		if not line.is_empty():
			out.append(line)
	if not ended:
		out.append("\n*The player stopped here.*")
	if not notebook.is_empty():
		out.append("\n## The Inspector's Notebook\n")
		out.append(notebook)
	return "\n".join(out) + "\n"


static func _line(e: Dictionary) -> String:
	var who: String = Case.SHORT.get(str(e.get("to", "")), str(e.get("to", "")))
	match str(e.kind):
		"walk":
			var seen: Array = e.seen_by.map(func(n): return Case.SHORT.get(n, n))
			return "- You went to %s%s.%s" % [PLACES.get(e.to, e.to), (" by the " + e.way) if e.way in ["lane", "bend"] else "",
					(" Seen by %s." % ", ".join(seen)) if seen.size() > 0 else " Nobody saw."]
		"tell":
			return "- You told %s: %s." % [who, e.what]
		"ask":
			return "- You asked %s about the night." % who
		"pay":
			return "- You gave %s $%d." % [who, e.amount]
		"threaten":
			return "- You threatened %s." % who
		"comfort":
			return "- You comforted %s." % who
		"confess":
			return "- You confessed to %s." % who
		"talk":
			return "- You talked to %s." % who
		"line":
			var speaker: String = Case.SHORT.get(e.npc, e.npc)
			if e.heard:
				return "- %s: \"%s\"" % [speaker, e.words]
			return "- *(not heard by you)* %s: \"%s\" [%s]" % [speaker, e.words, e.action]
		"news":
			return "- News: %s" % e.text
		"round":
			return "- *(Gilchrist's round: %s)*" % e.action
		"morning", "steamer":
			var knew: Array = []
			for c in e.gilchrist:
				knew.append("%s %.2f" % [c, e.gilchrist[c]])
			var trusts: Array = []
			for n in e.trust:
				trusts.append("%s %d" % [Case.SHORT.get(n, n), e.trust[n]])
			return "- **Gilchrist believes:** %s\n- **He has:** %s\n- **Trust in you:** %s" % [
					", ".join(knew) if knew.size() > 0 else "nothing yet about the case",
					", ".join(e.done) if e.done.size() > 0 else "done nothing yet", ", ".join(trusts)]
		"ending":
			return "- **%s.** Gilchrist: %s" % [e.title, e.action]
		"director":
			return "- *(the pressure on you: %.2f, the day's target %.2f%s)*" % [e.pressure, e.target,
					(", so the director looks for something to " + e.wants) if not str(e.wants).is_empty() else ""]
		"incident":
			return "- *(the director brought out: %s)*" % e.name
	return ""
