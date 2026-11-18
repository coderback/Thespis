## The case: the world's side of the week, played through Thespis. The town's minds are in coldwater.toml; what
## happened the night of the fire, how Tamás remembers and who sees each way are in case.json. This node owns the
## clock, who is where, what Anton's acts do and who sees them, Gilchrist's rounds and evenings, and the steamer.
## tests/test_coldwater.py plays the same files in Python, scene by scene.
class_name Case
extends Node

signal spoke(line: ThespisLine)  ## a line Anton is there to hear
signal clock(day: int, part: int)  ## day 1 to 5; part 0 morning, 1 afternoon, 2 evening
signal news(text: String)  ## something Anton learns happened, in a sentence
signal ended(title: String, line: ThespisLine)  ## the steamer: the ending, and Gilchrist's last word
signal people_moved  ## who is where changed

const GAME := "coldwater"
const PHASES := 15
const NAMES := {"gilchrist": "Inspector Gilchrist", "vera": "Věra Holub", "tamas": "Tamás Kovács",
		"sandor": "Sándor Kovács", "billy": "Billy Tuck", "maggie": "Maggie Doyle", "otto": "Otto Brand",
		"ashby": "Jack Ashby", "martha": "Martha Matthias", "player": "you"}
## Who each is, on the name tag in a conversation.
const ROLES := {"gilchrist": "North-West Mounted Police", "vera": "your sister", "tamas": "the night watchman",
		"sandor": "the watchman's son", "billy": "the wood boy", "maggie": "keeps the roadhouse",
		"otto": "trader and lender", "ashby": "came over the pass in the fall", "martha": "sews gloves and moccasins"}
const SHE := ["vera", "maggie", "martha"]
## What Anton can tell people: as he'd say it, the claim, and how it reads on the note of what they have from him.
const STORIES := [
	["I was at Věra's till late that night.", {"pred": "with_vera", "a": "player"}, "you were at Věra's till late"],
	["It was Ashby's lantern in the lane.", {"pred": "lantern", "a": "ashby"}, "the lantern in the lane was Ashby's"],
	["Ashby set the fire.", {"pred": "fired", "a": "ashby", "b": "otto"}, "Ashby set the fire"],
	["It was the watchman's lamp.", {"pred": "fired", "a": "tamas", "b": "otto"}, "it was the watchman's lamp"],
	["Tamás was drunk on watch.", {"pred": "drunk", "a": "tamas"}, "Tamás was drunk on watch"],
	["Maggie sold him the bottle.", {"pred": "sold_bottle", "a": "maggie", "b": "tamas"}, "Maggie sold Tamás the bottle"],
	["Otto burned his own store.", {"pred": "fired", "a": "otto", "b": "otto"}, "Otto burned his own store"],
	["Otto was dealing a crooked game that night.", {"pred": "fixed_game", "a": "otto"}, "Otto was dealing a crooked game"],
	["Ashby's wanted in Seattle.", {"pred": "wanted", "a": "ashby"}, "Ashby is wanted in Seattle"],
	["Martha saw someone in the lane.", {"pred": "saw_lane", "a": "martha"}, "Martha saw someone in the lane"],
	["It was the wood boy's lantern.", {"pred": "lantern", "a": "billy"}, "the lantern in the lane was Billy's"],
	["Billy was at Brand's back door that night.", {"pred": "woodpile", "a": "billy"},
			"Billy was at Brand's back door that night"],
	["Otto was in Maggie's back room at one.", {"pred": "back_room", "a": "otto"},
			"Otto was in Maggie's back room at one"],
]
const SHORT := {"gilchrist": "Gilchrist", "vera": "Věra", "tamas": "Tamás", "sandor": "Sándor", "billy": "Billy",
		"maggie": "Maggie", "otto": "Otto", "ashby": "Ashby", "martha": "Martha"}

var data: Dictionary
var seed_value := 0
var phase := 0  ## 0 to 14: the session's phase, three a day
var here := "your_cabin"  ## where Anton is
var where := {}  ## npc -> place, from the session
var trust := {}  ## npc -> {who: trust}, from the session
var week := {}  ## what this seed made of the week: each draw in case.json's week, by name -> the option's name
var face_day := 0  ## the day Tamás sees a face again; 0, never
var face_seen := false  ## Martha saw his face in the lane (on some seeds)
var _memory: Array = []  ## what Tamás sees that day: Anton's face, or another man's
var playing := false
var done := false
var sat_with_him := false  ## tonight's evening at the post is done
var _comforted := {}  ## who Anton comforted today: once a day counts
var _sat_with_tamas := false  ## Anton was at the infirmary today
var ending_action := ""  ## what Gilchrist did at the steamer: nobody, arrest, take:<who>, ...
var pressures := {}  ## day -> the pressure on Anton that morning, 0 to 1 (the director's measure)
var incidents: Array = []  ## the incidents the director brought out, in order: each {day, name, kind}
var told := {}  ## npc -> what Anton told them, in order: each {claim, note, phase}
var keep_journal := false  ## record the week for a playtest (Journal writes it out)
var journal: Array = []  ## what happened, in order: each {phase, day, part, kind, ...}
## What the journal notes of Gilchrist each morning: his beliefs about these.
const NOTED := ["fired", "lantern", "with_vera", "left_vera", "saw_lane", "drunk", "sold_bottle", "in_bed", "back_room",
		"asleep", "woodpile", "wanted"]


## Start Thespis, open the week, and play the night of the fire into it. A seed of 0 picks one.
func begin(seed_wanted := 0) -> ThespisResult:
	data = JSON.parse_string(FileAccess.get_file_as_string("res://case.json"))
	seed_value = seed_wanted if seed_wanted != 0 else randi_range(1, 1 << 30)
	var r := await Thespis.start()
	if r.ok:
		r = await Thespis.open(GAME, seed_value)
	if not r.ok:
		return r
	var drawn := roll(data.week, seed_value)
	var see := {}
	for d in drawn:
		week[d] = str(drawn[d].name)
		for id in drawn[d].get("see", {}):
			see[id] = see.get(id, []) + drawn[d].see[id]
	for o in data.night:
		var o2: Dictionary = o.duplicate()
		o2.witnesses = o.get("witnesses", []) + see.get(o.get("id", ""), [])
		await _observe(o2)
	var heard: Array = []
	for d in drawn:
		var opt: Dictionary = drawn[d]
		for o in opt.get("observe", []):
			await _observe(o)
		for t in opt.get("tie", []):
			await Thespis.tie(t[0], t[1], t[2])
		for npc in opt.get("update", {}):
			await Thespis.update(npc, opt.update[npc])
		if opt.has("day"):
			face_day = int(opt.day)
		if opt.has("remember"):
			_memory = opt.remember
		if opt.has("news"):
			heard.append(opt.news)
	face_seen = week.get("face", "") == "seen"
	await refresh()
	playing = true
	await _morning()
	clock.emit(day(), part())
	for t in heard:
		_news(t)
	return r


## The week a seed makes: for each draw, one option by weight, drawn again (the next numbers on) until the week keeps
## the rules. draw name -> the option. The same seed makes the same week.
static func roll(spec: Dictionary, s: int) -> Dictionary:
	var rng := RandomNumberGenerator.new()
	rng.seed = s
	var drawn := {}
	for i in 100:
		drawn = {}
		for d in spec.draws:
			drawn[d.name] = _pick(rng, d.options)
		if keeps(spec.get("rules", {}), drawn):
			break
	return drawn


static func _pick(rng: RandomNumberGenerator, options: Array) -> Dictionary:
	var total := 0.0
	for o in options:
		total += float(o.weight)
	var x := rng.randf() * total
	for o in options:
		x -= float(o.weight)
		if x < 0.0:
			return o
	return options[-1]


## Whether a drawn week keeps the rules: at least one of `one_of`, and none of `never`.
static func keeps(rules: Dictionary, drawn: Dictionary) -> bool:
	for n in rules.get("never", []):
		if _is(n, drawn):
			return false
	var one_of: Array = rules.get("one_of", [])
	return one_of.is_empty() or one_of.any(func(c): return _is(c, drawn))


## Whether every draw a condition names came out as it says ("!x": anything but x).
static func _is(cond: Dictionary, drawn: Dictionary) -> bool:
	for d in cond:
		var want := str(cond[d])
		var got := str(drawn.get(d, {}).get("name", ""))
		if (got == want.substr(1)) if want.begins_with("!") else (got != want):
			return false
	return true


func day() -> int:
	return phase / 3 + 1


func part() -> int:
	return phase % 3


## Who is where, and whom each trusts, as the session has it now.
func refresh() -> void:
	var r := await Thespis.overview()
	if not r.ok:
		return
	for n in r.value.npcs:
		where[n.id] = n.loc
		trust[n.id] = n.trust_in
	people_moved.emit()


## The people at a place.
func at(place: String) -> Array:
	return where.keys().filter(func(n): return where[n] == place)


## Whoever stands where they can see Anton take a way: the street from the landing, the porch, the post and the
## infirmary windows; the lane only from the store and Maggie's kitchen window; the ice from the landing and the ice.
func onlookers(way: String, from: String, to: String) -> Array:
	var seen: Array = []
	var w: Dictionary = data.ways.get(way, {})
	for p in w.get("seen_from", []):
		seen.append_array(at(p))
	if w.get("kitchen", false) and part() == 2:
		seen.append_array(at("maggies").filter(func(n): return n in ["martha", "billy"]))
	seen.append_array(at(from))
	seen.append_array(at(to))
	var out: Array = []
	for n in seen:
		if n not in out:
			out.append(n)
	return out


## Anton goes to a place by a way. Whoever has the way in view now knows where he went, first-hand. The bend
## crossing is seen by nobody and costs him the next phase too.
func go(to: String, way := "") -> void:
	if not playing or to == here:
		return
	if way.is_empty():
		way = "ice" if to in ["vera", "ice"] or here == "vera" else "front"
	var saw := onlookers(way, here, to)
	await Thespis.observe(ThespisClient.event("walk", "player", to, {"pred": "went", "a": "player", "place": to},
			saw, {"at": here}))
	_note("walk", {"to": to, "way": way, "seen_by": saw})
	here = to
	if to == "mission":
		_sat_with_tamas = true
	await Thespis.update("player", {"loc": to})
	if int(data.ways.get(way, {}).get("cost", 0)) > 0 and part() < 2:
		await advance()


# ------------------------------------------------------------------------------------------------ Anton's acts
# Each is what its button does, and what a typed line read as that act does. Whoever else is here sees it.

func others(besides: String) -> Array:
	return at(here).filter(func(n): return n != besides)


func tell(npc: String, claim: Dictionary) -> void:
	await Thespis.observe(ThespisClient.event("tell", "player", npc, claim, others(npc), {"said": true}))
	if not told.has(npc):
		told[npc] = []
	told[npc].append({"claim": claim, "note": story_note(claim), "phase": phase})
	_note("tell", {"to": npc, "what": story_note(claim), "claim": claim})
	if npc == "gilchrist" and claim.get("pred") == "fixed_game" and claim.get("a") == "otto":
		await Thespis.update("otto", {"flags": {"found_out": true}})  # his game is out: he may as well tell
	_say(await Thespis.react(npc, "told"))


## How a claim Anton told reads on the note: the story's own words, or the claim's.
static func story_note(claim: Dictionary) -> String:
	for st in STORIES:
		var c: Dictionary = st[1]
		if c.pred == claim.get("pred") and c.a == claim.get("a") and c.get("b", "") == claim.get("b", "") 				and not claim.get("neg", false):
			return st[2]
	return "something about %s" % SHORT.get(str(claim.get("a", "")), "the fire")


func when(at_phase: int) -> String:
	var parts := ["morning", "afternoon", "evening"]
	if at_phase / 3 == phase / 3:
		return "this " + parts[at_phase % 3]
	return "day %d, %s" % [at_phase / 3 + 1, parts[at_phase % 3]]


func ask(npc: String) -> void:
	_note("ask", {"to": npc})
	match npc:
		"tamas":
			_say(await Thespis.decide("tamas", "visit"))
		"martha":
			_say(await Thespis.decide("martha", "meet", {"to": "player"}))
		"sandor":  # he goes for Anton if he believes it; otherwise he answers the question
			var r := await Thespis.decide("sandor", "meet", {"bindings": {"who": "player"}})
			if r.ok and str(r.value.action) == "greet":
				_say(await Thespis.react("sandor", "asked"))
			else:
				_say(r)
		_:
			_say(await Thespis.react(npc, "asked"))


func pay(npc: String, amount: int) -> void:
	_note("pay", {"to": npc, "amount": amount})
	await Thespis.observe(ThespisClient.event("pay", "player", npc, ThespisClient.claim("paid", "player", npc),
			others(npc), {"amount": amount}))
	if npc == "billy":
		var r := _say(await Thespis.decide("billy", "offered", {"bindings": {"amount": amount}}))
		if r.ok and r.value.action == "pocket":
			await Thespis.update("billy", {"flags": {"paid_off": true}})
	else:
		_say(await Thespis.react(npc, "paid"))


func threaten(npc: String) -> void:
	_note("threaten", {"to": npc})
	await Thespis.observe(ThespisClient.event("threaten", "player", npc,
			ThespisClient.claim("threatened", "player", npc), others(npc)))
	await _trust(npc, -2)
	_say(await Thespis.react(npc, "threatened"))


func comfort(npc: String) -> void:
	_note("comfort", {"to": npc})
	await Thespis.observe(ThespisClient.event("comfort", "player", npc,
			ThespisClient.claim("comforted", "player", npc), others(npc)))
	if not _comforted.has(npc):
		_comforted[npc] = true
		await _trust(npc, 1)
	_say(await Thespis.react(npc, "comforted"))


func confess(npc: String) -> void:
	_note("confess", {"to": npc})
	await Thespis.observe(ThespisClient.event("confess", "player", npc,
			ThespisClient.claim("fired", "player", "otto"), others(npc), {"said": true}))
	if npc == "gilchrist":
		await Thespis.update("gilchrist", {"flags": {"confessed": true}})
	_say(await Thespis.react(npc, "confessed"))


func talk(npc: String) -> void:
	_note("talk", {"to": npc})
	_say(await Thespis.react(npc, "talk"))


## Carry out what the player's words were read as (a ThespisApi.IntentOut), as its button would.
func carry_out(intent: ThespisApi.IntentOut) -> void:
	var to := str(intent.args.get("to", ""))
	match intent.verb:
		"tell":
			await tell(to, intent.args["claim"])
		"ask":
			await ask(to)
		"pay":
			await pay(to, int(intent.args["amount"]))
		"threaten":
			await threaten(to)
		"comfort":
			await comfort(to)
		"confess":
			await confess(to)
		_:
			await talk(to)


## What the acts open now are, for understand: the people here, the money Anton has on him.
func offered() -> Array:
	var people := others("player")
	var acts: Array = []
	for verb in ["tell", "ask", "threaten", "comfort", "confess", "talk"]:
		acts.append({"verb": verb, "args": {"to": people}})
	acts.append({"verb": "pay", "args": {"to": people, "amount": {"min": 1, "max": 50}}})
	return acts


# ------------------------------------------------------------------------------------------------ time

## Anton is done here. An evening goes on to the post first, to sit with Gilchrist; then the night passes.
func end_phase() -> void:
	if part() == 2 and not sat_with_him:
		sat_with_him = true
		await evening()
	else:
		sat_with_him = false
		await advance()


## The phase is over: the evening ends at the post with Gilchrist; the minds move on a phase; Tamás remembers;
## Gilchrist makes his rounds. The last evening ends on the steamer.
func advance() -> void:
	if not playing:
		return
	_comforted = {} if part() == 2 else _comforted
	var r := await Thespis.tick()
	phase += 1
	await refresh()
	if phase >= PHASES:
		await steamer()
		return
	if part() == 0:
		await Thespis.update("gilchrist", {"flags": {"day%d" % day(): true}})
		await _waited()
		await _remember()
		await _direct()
		await _morning()
	if part() < 2:
		await rounds()
	clock.emit(day(), part())


## The evening set piece: Anton sits with Gilchrist at the post, and his question is the most pressing thing he
## believes. The lantern line names whoever he has it from.
func evening() -> ThespisResult:
	here = "police"
	await Thespis.update("player", {"loc": "police"})
	await Thespis.update("gilchrist", {"loc": "police"})
	if day() == 5:
		await Thespis.update("gilchrist", {"flags": {"last_evening": true}})
	await refresh()
	var r := _say(await Thespis.decide("gilchrist", "evening",
			{"bindings": {"teller": await _teller()}}))
	if r.ok:
		var act := str(r.value.action)
		var flag: String = {"ask_night": "asked_night", "ask_lantern": "asked_lantern", "doubt_alibi": "doubted",
				"warn": "warned", "caught_lie": "said_caught", "search": "searched"}.get(act, "")
		if act.begins_with("remark_") or act == "last_evening":  # each said once
			flag = "said_" + act
		if not flag.is_empty():
			var flags := {flag: true}
			if flag == "searched":
				flags["search_due"] = true
			await Thespis.update("gilchrist", {"flags": flags})
	return r


## Whoever Gilchrist has the lantern from, by name: the first teller of it he heard.
func _teller() -> String:
	var r := await Thespis.inspect("gilchrist")
	if r.ok:
		for b in r.value.beliefs:
			if b.claim.pred == "lantern":
				for e in b.evidence:
					if NAMES.has(e.source):
						return NAMES[e.source]
	return "Someone"


## His morning or afternoon: where he goes, if not where his walk takes him, and what comes of it.
func rounds() -> void:
	var r := await Thespis.decide("gilchrist", "rounds")
	if not r.ok:
		return
	if str(r.value.action) != "round":
		_note("round", {"action": str(r.value.action)})
	match str(r.value.action):
		"see_vera":
			await _visit("vera", {"asked_vera": true})
			_overheard(await Thespis.decide("vera", "questioned", {"to": "gilchrist"}))
			_news("Gilchrist crossed the ice to Věra's.")
		"see_martha":
			var place: String = where.get("martha", "maggies")
			await _visit(place, {"asked_martha": true})
			await _trust("martha", 2, "gilchrist")  # the first in town to ask her properly
			_overheard(await Thespis.decide("martha", "questioned", {"to": "gilchrist"}))
			_news("Gilchrist went looking for Martha.")
		"see_tamas":
			await _visit("mission", {"saw_tamas": true})
			_news("Gilchrist is sitting with Tamás at the mission.")
		"see_otto", "see_billy":  # where were you at one? They lie.
			var who := str(r.value.action).trim_prefix("see_")
			await _visit(where.get(who, "maggies"), {"asked_" + who: true})
			_overheard(await Thespis.decide(who, "questioned", {"to": "gilchrist"}))
			_news("Gilchrist went looking for %s." % SHORT[who])
		"search_cabin":
			await _visit("your_cabin", {"search_due": false})
			_news("Gilchrist's men are going through your cabin.")
	await refresh()


func _visit(place: String, flags: Dictionary) -> void:
	await Thespis.update("gilchrist", {"loc": place, "flags": flags})
	where["gilchrist"] = place


## Tamás trusts the one who sits with him: a day without Anton costs a little of that, and a day with him wins it
## back, up to what it was. Below 2 he stops keeping what he remembers of Anton to himself (it goes to Sándor), and
## the last day it may go to the Inspector.
func _waited() -> void:
	if day() >= 2:
		if not _sat_with_tamas:
			await _trust("tamas", -1)
		elif int(trust.get("tamas", {}).get("player", 0)) < 2:
			await _trust("tamas", 1)
	_sat_with_tamas = here == "mission"


# ------------------------------------------------------------------------------------------------ the director

## The pressure on Anton now, 0 to 1, by case.json's director: how far Gilchrist suspects him, whether his account
## has broken, and how many in town hold a true and damaging belief about him.
func pressure() -> float:
	var spec: Dictionary = data.director
	var w: Dictionary = spec.weights
	var g := await Thespis.inspect("gilchrist")
	var suspects := 0.0
	var alibi := 0.0
	if g.ok:
		var asked: bool = g.value.npc.get("flags", {}).get("asked_night", false)
		var vouched := false
		for b in g.value.beliefs:
			var c: Dictionary = b.claim
			if b.status != "active" or str(c.a) != "player":
				continue
			var conf := float(b.opinion.b)
			if c.pred in ["lantern", "fired"]:
				suspects = maxf(suspects, conf)
			elif c.pred == "left_vera" or (c.pred == "with_vera" and c.get("neg", false)):
				alibi = 1.0
			elif c.pred == "with_vera":
				vouched = true
		if alibi == 0.0 and asked and not vouched:
			alibi = 0.5  # asked, and never given an account
	var holders := {}
	for claim in [{"pred": "lantern", "a": "player"}, {"pred": "fired", "a": "player", "b": "otto"},
			{"pred": "left_vera", "a": "player"}, {"pred": "with_vera", "a": "player", "neg": true}]:
		var t := await Thespis.trace(claim)
		if t.ok:
			for h in t.value.holders:
				if h.npc != "gilchrist" and h.status == "active" and float(h.conf) >= 0.4:
					holders[h.npc] = true
	var town := minf(1.0, float(holders.size()) / float(spec.town_full))
	return float(w.gilchrist) * suspects + float(w.alibi) * alibi + float(w.town) * town


## The morning's direction: below the day's target, bring out an incident latent in the night; well above it early,
## one that gives relief; on a day that's never quiet, one either way. One a morning, each once.
func _direct() -> void:
	var spec: Dictionary = data.director
	var key := str(day())
	if not spec.targets.has(key):
		return
	var now := await pressure()
	pressures[day()] = snappedf(now, 0.01)
	var target := float(spec.targets[key])
	var kind := ""
	if now < target:
		kind = "press"
	elif now > target + float(spec.relief_over) and day() <= 3:
		kind = "relieve"
	elif _quiet_day(spec):
		kind = "relieve" if now >= target else "press"
	_note("director", {"pressure": pressures[day()], "target": target, "wants": kind})
	if kind.is_empty() or not spec.get("active", true):
		return
	var done: Array = incidents.map(func(i): return i.name)
	var kinds := [kind]
	if _quiet_day(spec):  # something happens: a beat if none of this kind is left, and only last the other kind
		kinds = [kind, "beat", "relieve" if kind == "press" else "press"]
	var open: Array = []
	for k in kinds:
		for inc in spec.incidents:
			if inc.kind == k and inc.name not in done and await _requires(inc.get("requires", [])):
				open.append(inc)
		if not open.is_empty():
			kind = k
			break
	if open.is_empty():
		return
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value * 31 + day()
	var inc: Dictionary = open[rng.randi() % open.size()]
	for o in inc.get("observe", []):
		await _observe(o)
	if inc.get("remember_now", false):  # the fever breaks: what he'd have seen later, he sees now
		face_day = day()
		for o in _memory:
			await _observe(o)
	for npc in inc.get("update", {}):
		await Thespis.update(npc, inc.update[npc])
	incidents.append({"day": day(), "name": inc.name, "kind": kind})
	_note("incident", {"name": inc.name, "kind": kind})
	if inc.has("news"):
		_news(inc.news)


## Today is one the director never leaves quiet. (JSON's numbers are floats: compare as whole days.)
func _quiet_day(spec: Dictionary) -> bool:
	return spec.never_quiet.any(func(d): return int(d) == day())


## Whether every requirement of an incident holds now: a draw of the week, a flag set or not, a belief not held.
func _requires(reqs: Array) -> bool:
	for r in reqs:
		if r.has("week"):
			var drawn := {}
			for d in data.week.draws:
				for o in d.options:
					if o.name == week.get(d.name, ""):
						drawn[d.name] = o
			if not Case._is(r.week, drawn):
				return false
		elif r.has("flag") or r.has("not_flag"):
			var who: Array = r.get("flag", r.get("not_flag"))
			var i := await Thespis.inspect(str(who[0]))
			var set_: bool = i.ok and bool(i.value.npc.get("flags", {}).get(str(who[1]), false))
			if set_ != r.has("flag"):
				return false
		elif r.has("memory_ahead"):  # Tamás's face is still to come
			if not (face_day > day()):
				return false
		elif r.has("not_believes"):
			var i := await Thespis.inspect(str(r.not_believes[0]))
			if i.ok:
				for b in i.value.beliefs:
					if b.status == "active" and _same(b.claim, r.not_believes[1]):
						return false
	return true


static func _same(a: Dictionary, b: Dictionary) -> bool:
	for k in ["pred", "a"]:
		if str(a.get(k, "")) != str(b.get(k, "")):
			return false
	return str(a.get("b", "")) == str(b.get("b", "")) and bool(a.get("neg", false)) == bool(b.get("neg", false))


## Tamás's memory comes back a piece a morning: a lantern on the day the case says, a face on the seed's day.
func _remember() -> void:
	if day() == int(data.tamas.lantern.day):
		for o in data.tamas.lantern.observe:
			await _observe(o)
	if day() == face_day:
		for o in _memory:
			await _observe(o)


## The ice goes out. Tamás and Věra make their last choices, and Gilchrist boards the steamer with whoever he
## believes set the fire.
func steamer() -> void:
	playing = false
	done = true
	_overheard(await Thespis.decide("tamas", "decision", {"to": "gilchrist"}))
	var g := await Thespis.inspect("gilchrist")
	if g.ok and g.value.npc.get("flags", {}).get("warned", false) and g.value.npc.get("flags", {}).get("searched", false):
		await Thespis.update("vera", {"flags": {"brother_lost": true}})
	_overheard(await Thespis.decide("vera", "last_morning", {"to": "gilchrist"}))
	await _morning("steamer")
	here = "landing"
	var r := await Thespis.decide("gilchrist", "steamer")
	if not r.ok:
		ended.emit("The Ice Goes Out", null)
		return
	var act := str(r.value.action)
	ending_action = act
	var title := "The Ice Goes Out"
	if act == "breakup":
		title = "Breakup"
	elif act == "arrest":
		title = "A Hand on the Shoulder"
	elif act == "take:vera":
		title = "Věra"
	elif act == "mercy":
		title = "The Confession"
	elif act.begins_with("take:"):
		title = "Another Man's Coat"
	_note("ending", {"title": title, "action": act})
	ended.emit(title, r.value)


## The Inspector's Notebook: what Gilchrist went south believing about the night, each thing with when he first had it
## and from whom, and whom he took. His case as he'd write it up, not what happened: a lie he believed is in it.
func notebook() -> String:
	var g := await Thespis.inspect("gilchrist")
	var held: Array = []
	if g.ok:
		for b in g.value.beliefs:
			var c: Dictionary = b.claim
			if b.status != "active" or str(c.pred) not in NOTED or (c.pred == "fired" and c.a == "someone"):
				continue
			if b.evidence.is_empty():
				continue
			var first: Dictionary = b.evidence[0]
			for e in b.evidence:
				if int(e.phase) < int(first.phase):
					first = e
			held.append({"phase": int(first.phase), "from": _from(str(first.source)), "what": _wrote(c),
					"sure": float(b.opinion.b)})
	held.sort_custom(func(x, y): return x.phase < y.phase)
	var lines: Array = []
	for h in held.slice(0, 8):  # what fits the sheet: the first eight things he had, in order
		lines.append("%s · %s: %s. (%s)" % [_written(h.phase), h.from, h.what, "sure" if h.sure >= 0.8 else (
				"likely" if h.sure >= 0.5 else "not sure")])
	if held.size() > 8:
		lines.append("And %d more besides." % (held.size() - 8))
	if lines.is_empty():
		lines.append("Nothing I could use.")
	lines.append("")
	lines.append(_took())
	return "\n".join(lines)


func _written(at_phase: int) -> String:
	if at_phase >= PHASES:
		return "At the steamer"
	return "Day %d, %s" % [at_phase / 3 + 1, ["morning", "afternoon", "evening"][at_phase % 3]]


## Whom he had it from, as he'd write it.
func _from(source: String) -> String:
	match source:
		"witnessed", "self":
			return "Seen myself"
		"player":
			return "Mr Holub"
		"someone", "":
			return "Talk in town"
	return NAMES.get(source, source)


func _who(id: String) -> String:
	if id == "player":
		return "Mr Holub"
	if id == "gilchrist":
		return "I"
	if id == "someone":
		return "someone"
	return NAMES.get(id, id)


## A belief about the night, in his words.
func _wrote(c: Dictionary) -> String:
	var a := _who(str(c.a))
	var neg: bool = c.get("neg", false)
	var t := ""
	match str(c.pred):
		"fired":
			t = "%s set the fire" % a
		"lantern":
			t = "a lantern went down the back lane at one" if c.a == "someone" else "the lantern in the lane was %s's" % a
		"with_vera":
			t = "%s was %sat his sister's till late" % [a, "not " if neg else ""]
		"left_vera":
			t = "%s left his sister's at half past eleven" % a
		"saw_lane":
			t = "%s saw someone in the lane" % a
		"drunk":
			t = "%s was drunk on watch" % a
		"sold_bottle":
			t = "%s sold %s the bottle" % [a, _who(str(c.get("b", "")))]
		"in_bed":
			t = "%s was in his bed by midnight" % a
		"back_room":
			t = "%s was in Maggie's back room at one" % a
		"asleep":
			t = "%s was asleep at one" % a
		"woodpile":
			t = "%s was at Brand's back door with the cordwood" % a
		"wanted":
			t = "%s is wanted in Seattle under another name" % a
		_:
			t = claim_text(c)
	if neg and str(c.pred) != "with_vera":
		t = "not so: " + t
	return t.left(1).to_upper() + t.substr(1)


## The last line: whom he took south.
func _took() -> String:
	match ending_action:
		"nobody":
			return "I went south with no one."
		"arrest":
			return "I took Mr Holub south."
		"mercy":
			return "I took Mr Holub south, and I'll tell the judge why he did it."
		"breakup":
			return "I wrote it down as the watchman's lamp."
	if ending_action.begins_with("take:"):
		return "I took %s south." % NAMES.get(ending_action.trim_prefix("take:"), "")
	return ""


# ------------------------------------------------------------------------------------------------ plumbing

func _observe(o: Dictionary) -> ThespisResult:
	var more := {}
	for k in ["at", "said", "conf", "true"]:
		if o.has(k):
			more[k] = o[k]
	return await Thespis.observe(ThespisClient.event(o.verb, o.actor, o.get("target", ""), o.get("claim", {}),
			o.get("witnesses", []), more))


## A line Anton hears: shown if he's there.
func _say(r: ThespisResult) -> ThespisResult:
	if r.ok and r.value != null and not r.value.is_silent():
		_note_line(r.value, true)
		spoke.emit(r.value)
	return r


## A line said where Anton isn't: it happens, and he doesn't hear it.
func _overheard(r: ThespisResult) -> ThespisResult:
	if r.ok and r.value != null and not r.value.is_silent():
		_note_line(r.value, where.get(r.value.npc, "") == here)
	if r.ok and where.get(r.value.npc, "") == here:
		spoke.emit(r.value)
	return r


# ------------------------------------------------------------------------------------------------ the journal
# A playtest's record of the week (keep_journal): what Anton did, what he heard, what was said where he wasn't, the
# news, and each morning what Gilchrist believed and whom the town still trusted. Journal writes it out.

func _note(kind: String, more := {}) -> void:
	if keep_journal:
		var e := {"phase": phase, "day": day(), "part": part(), "kind": kind}
		e.merge(more)
		journal.append(e)


func _note_line(l: ThespisLine, heard: bool) -> void:
	_note("line", {"npc": l.npc, "action": str(l.action), "words": l.words(""), "heard": heard})


func _news(text: String) -> void:
	_note("news", {"text": text})
	news.emit(text)


## The morning's state: Gilchrist's beliefs about the case, what he has done, and each person's trust in Anton.
func _morning(kind := "morning") -> void:
	if not keep_journal:
		return
	var g := await Thespis.inspect("gilchrist")
	var knew := {}
	var did: Array = []
	if g.ok:
		for b in g.value.beliefs:
			var c: Dictionary = b.claim
			if b.status == "active" and str(c.pred) in NOTED:
				knew[claim_text(c)] = snappedf(float(b.opinion.b), 0.01)
		for f in g.value.npc.get("flags", {}):
			if g.value.npc.flags[f] and not str(f).ends_with("_due"):
				did.append(f)
	var trusts := {}
	for n in trust:
		if trust[n].has("player"):
			trusts[n] = int(trust[n].player)
	_note(kind, {"gilchrist": knew, "done": did, "trust": trusts})


## A claim, short: pred(who), "not " first for a denial; the fire's object (always Brand's store) left out.
static func claim_text(c: Dictionary) -> String:
	var who := str(c.a)
	if c.has("b") and not str(c.b).is_empty() and str(c.pred) != "fired":
		who = "%s, %s" % [c.a, c.b]
	return "%s%s(%s)" % ["not " if c.get("neg", false) else "", c.pred, who]


## Move `npc`'s trust in `who` (Anton, unless said) by `by`, within -5 to 5.
func _trust(npc: String, by: int, who := "player") -> void:
	var now: int = int(trust.get(npc, {}).get(who, 0))
	var to: int = clampi(now + by, -5, 5)
	await Thespis.update(npc, {"trust_in": {who: to}})
	if not trust.has(npc):
		trust[npc] = {}
	trust[npc][who] = to
