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
]
const SHORT := {"gilchrist": "Gilchrist", "vera": "Věra", "tamas": "Tamás", "sandor": "Sándor", "billy": "Billy",
		"maggie": "Maggie", "otto": "Otto", "ashby": "Ashby", "martha": "Martha"}

var data: Dictionary
var seed_value := 0
var phase := 0  ## 0 to 14: the session's phase, three a day
var here := "your_cabin"  ## where Anton is
var where := {}  ## npc -> place, from the session
var trust := {}  ## npc -> {who: trust}, from the session
var face_day := 0  ## the day Tamás sees the face again; 0, never
var face_seen := false  ## Martha saw his face in the lane (on some seeds)
var playing := false
var done := false
var sat_with_him := false  ## tonight's evening at the post is done
var _comforted := {}  ## who Anton comforted today: once a day counts
var _sat_with_tamas := false  ## Anton was at the infirmary today
var told := {}  ## npc -> what Anton told them, in order: each {claim, note, phase}


## Start Thespis, open the week, and play the night of the fire into it. A seed of 0 picks one.
func begin(seed_wanted := 0) -> ThespisResult:
	data = JSON.parse_string(FileAccess.get_file_as_string("res://case.json"))
	seed_value = seed_wanted if seed_wanted != 0 else randi_range(1, 1 << 30)
	var r := await Thespis.start()
	if r.ok:
		r = await Thespis.open(GAME, seed_value)
	if not r.ok:
		return r
	for o in data.night:
		await _observe(o)
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	face_seen = rng.randf() < float(data.face.chance)
	if face_seen:
		for o in data.face.observe:
			await _observe(o)
	var days: Array = data.tamas.face.days
	face_day = int(days[rng.randi() % days.size()])
	await refresh()
	playing = true
	clock.emit(day(), part())
	return r


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
	match npc:
		"tamas":
			_say(await Thespis.decide("tamas", "visit"))
		"martha":
			_say(await Thespis.decide("martha", "meet", {"to": "player"}))
		"sandor":
			_say(await Thespis.decide("sandor", "meet", {"bindings": {"who": "player"}}))
		_:
			_say(await Thespis.react(npc, "asked"))


func pay(npc: String, amount: int) -> void:
	await Thespis.observe(ThespisClient.event("pay", "player", npc, ThespisClient.claim("paid", "player", npc),
			others(npc), {"amount": amount}))
	if npc == "billy":
		var r := _say(await Thespis.decide("billy", "offered", {"bindings": {"amount": amount}}))
		if r.ok and r.value.action == "pocket":
			await Thespis.update("billy", {"flags": {"paid_off": true}})
	else:
		_say(await Thespis.react(npc, "paid"))


func threaten(npc: String) -> void:
	await Thespis.observe(ThespisClient.event("threaten", "player", npc,
			ThespisClient.claim("threatened", "player", npc), others(npc)))
	await _trust(npc, -2)
	_say(await Thespis.react(npc, "threatened"))


func comfort(npc: String) -> void:
	await Thespis.observe(ThespisClient.event("comfort", "player", npc,
			ThespisClient.claim("comforted", "player", npc), others(npc)))
	if not _comforted.has(npc):
		_comforted[npc] = true
		await _trust(npc, 1)
	_say(await Thespis.react(npc, "comforted"))


func confess(npc: String) -> void:
	await Thespis.observe(ThespisClient.event("confess", "player", npc,
			ThespisClient.claim("fired", "player", "otto"), others(npc), {"said": true}))
	if npc == "gilchrist":
		await Thespis.update("gilchrist", {"flags": {"confessed": true}})
	_say(await Thespis.react(npc, "confessed"))


func talk(npc: String) -> void:
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
		await _waited()
		await _remember()
	if part() < 2:
		await rounds()
	clock.emit(day(), part())


## The evening set piece: Anton sits with Gilchrist at the post, and his question is the most pressing thing he
## believes. The lantern line names whoever he has it from.
func evening() -> ThespisResult:
	here = "police"
	await Thespis.update("player", {"loc": "police"})
	await Thespis.update("gilchrist", {"loc": "police"})
	await refresh()
	var r := _say(await Thespis.decide("gilchrist", "evening",
			{"bindings": {"teller": await _teller()}}))
	if r.ok:
		var flag: String = {"ask_night": "asked_night", "ask_lantern": "asked_lantern", "doubt_alibi": "doubted",
				"warn": "warned", "caught_lie": "said_caught", "search": "searched"}.get(str(r.value.action), "")
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
	match str(r.value.action):
		"see_vera":
			await _visit("vera", {"asked_vera": true})
			_overheard(await Thespis.decide("vera", "questioned", {"to": "gilchrist"}))
			news.emit("Gilchrist crossed the ice to Věra's.")
		"see_martha":
			var place: String = where.get("martha", "maggies")
			await _visit(place, {"asked_martha": true})
			await _trust("martha", 2, "gilchrist")  # the first in town to ask her properly
			_overheard(await Thespis.decide("martha", "questioned", {"to": "gilchrist"}))
			news.emit("Gilchrist went looking for Martha.")
		"see_tamas":
			await _visit("mission", {"saw_tamas": true})
			news.emit("Gilchrist is sitting with Tamás at the mission.")
		"search_cabin":
			await _visit("your_cabin", {"search_due": false})
			news.emit("Gilchrist's men are going through your cabin.")
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


## Tamás's memory comes back a piece a morning: a lantern on the day the case says, the face on the seed's day.
func _remember() -> void:
	if day() == int(data.tamas.lantern.day):
		for o in data.tamas.lantern.observe:
			await _observe(o)
	if day() == face_day:
		for o in data.tamas.face.observe:
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
	here = "landing"
	var r := await Thespis.decide("gilchrist", "steamer")
	if not r.ok:
		ended.emit("The Ice Goes Out", null)
		return
	var act := str(r.value.action)
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
	ended.emit(title, r.value)


## The Inspector's Notebook: the week as he'd write it up.
func notebook() -> ThespisResult:
	return await Thespis.narrate({"since": 0})


# ------------------------------------------------------------------------------------------------ plumbing

func _observe(o: Dictionary) -> ThespisResult:
	var more := {}
	if o.has("at"):
		more["at"] = o.at
	return await Thespis.observe(ThespisClient.event(o.verb, o.actor, o.get("target", ""), o.get("claim", {}),
			o.get("witnesses", []), more))


## A line Anton hears: shown if he's there.
func _say(r: ThespisResult) -> ThespisResult:
	if r.ok and r.value != null and not r.value.is_silent():
		spoke.emit(r.value)
	return r


## A line said where Anton isn't: it happens, and he doesn't hear it.
func _overheard(r: ThespisResult) -> ThespisResult:
	if r.ok and where.get(r.value.npc, "") == here:
		spoke.emit(r.value)
	return r


## Move `npc`'s trust in `who` (Anton, unless said) by `by`, within -5 to 5.
func _trust(npc: String, by: int, who := "player") -> void:
	var now: int = int(trust.get(npc, {}).get(who, 0))
	var to: int = clampi(now + by, -5, 5)
	await Thespis.update(npc, {"trust_in": {who: to}})
	if not trust.has(npc):
		trust[npc] = {}
	trust[npc][who] = to
