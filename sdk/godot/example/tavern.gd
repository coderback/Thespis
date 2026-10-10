## The Lantern: the crypt road's first act in miniature, played through the Thespis addon.
##
## Garrick, a proud sellsword, sits in the taproom; Wren keeps the bar; Pip minds the horses and wanders in and out.
## The scene owns the world: who is where, what the player does and who sees it. Thespis owns their minds
## (tavern.toml, a copy of examples/tavern/game.toml): what they believe, what Garrick chooses to do, and every line,
## shown at once from the game's own templates and replaced when the model's words arrive. What the player types to
## Garrick is read as one of the acts the game file declares, and the scene carries it out as it would the button.
##
## Nothing here says where Thespis runs. With no settings it starts a sidecar on this machine; set
## thespis/connection/url (or $THESPIS_URL) and the same scene plays through that server instead.
extends Control

signal ready_to_play(result: ThespisResult)

const GAME := "tavern"
const SAVE := "user://lantern.save"
const NAMES := {"garrick": "Garrick", "wren": "Wren", "pip": "Pip", "narrator": "The Narrator"}

var pip_at := "yard"  ## where Pip is: Thespis walks him, and each tick says where he went
var phase := 0  ## the hours passed
var told_up_to := 0  ## the phase the narrator has told the story up to
var asking: Array = []  ## what the player's words might have meant, until they say which: each a ThespisApi.IntentOut
var done: ThespisResult = null  ## what came of the player's last words: the act's event, or the line said back

var _labels := {}
var _showing := {}  # npc -> the id of the line its label shows, so an older line settling late can't replace it


func _ready() -> void:
	_labels = {"garrick": %Garrick, "wren": %Wren, "pip": %Pip, "narrator": %Narrator}
	Thespis.line_arrived.connect(_arrived)
	Thespis.line_settled.connect(_settled)
	%Insult.pressed.connect(insult)
	%Help.pressed.connect(help)
	%Ask.pressed.connect(ask_garrick)
	%TalkWren.pressed.connect(talk_to.bind("wren"))
	%Wait.pressed.connect(pass_hour)
	%Tell.pressed.connect(what_happened)
	%Save.pressed.connect(save_game)
	%Load.pressed.connect(load_game)
	%Say.pressed.connect(_say_typed)
	%Words.text_submitted.connect(func(_text): _say_typed())
	%Status.text = "Starting Thespis..."
	var r := await Thespis.start()
	if r.ok:
		r = await Thespis.open(GAME)
	var where := "a sidecar on this machine" if Thespis.is_sidecar() else Thespis.url
	%Status.text = "Thespis at %s" % where if r.ok else "No Thespis: %s" % r.reason
	ready_to_play.emit(r)


## Who in the taproom sees what the player does there, besides whoever it's done to.
func onlookers(besides: String) -> Array:
	var here := ["garrick", "wren"]
	if pip_at == "taproom":
		here.append("pip")
	return here.filter(func(npc): return npc != besides)


## The player insults Garrick. The game file says an insult angers him, so the scene reports only what happened.
func insult(whom := "garrick") -> ThespisResult:
	return await Thespis.observe(ThespisClient.event("insult", "player", whom,
			ThespisClient.claim("insulted", "player", whom), onlookers(whom)))


## The player helps Garrick with his gear. Twice, and he respects them enough to share a drink.
func help() -> ThespisResult:
	return await Thespis.observe(ThespisClient.event("help", "player", "garrick",
			ThespisClient.claim("helped", "player", "garrick"), onlookers("garrick")))


## What Garrick does now, among the choices his game file declares, and what he says. The scene carries it out.
func ask_garrick() -> ThespisResult:
	var r := await Thespis.decide("garrick", "turn")
	if r.ok and str(r.value.action).begins_with("share_drink"):
		await Thespis.update("garrick", {"flags": {"drink": true}})  # one drink is enough
	return r


func talk_to(npc: String) -> ThespisResult:
	return await Thespis.react(npc, "talk")


## The player says something in their own words. Thespis reads which of the game's acts the words do, if any
## ([intents] in tavern.toml): it only chooses among them, and fills each from the game's own lists, so nothing
## typed here can do what a button couldn't. ok with how it was read (ThespisApi.UnderstandOut); `done` holds what
## came of it.
func say(text: String, to := "garrick") -> ThespisResult:
	dismiss()
	done = null
	var r := await Thespis.understand(text, to)
	if not r.ok:
		return r
	var read: ThespisApi.UnderstandOut = r.value
	%Heard.text = 'You: "%s"' % text
	match read.status:
		"act":  # a sure reading: carry it out, as the button would
			%Heard.text += "  (%s)" % read.intent.reads
			done = await carry_out(read.intent)
		"ask":  # it may be an act with consequences: the player says whether it was
			_ask(read.readings)
		_:  # only talk
			done = await talk_to(to)
	return r


## Carry out an act the player's words did, as its button would: one observe, seen by whoever is in the taproom.
func carry_out(intent: ThespisApi.IntentOut) -> ThespisResult:
	var to: String = intent.args.get("to", "garrick")
	match intent.verb:
		"insult":
			return await insult(to)
		"tell":  # the claim goes back as it came. True or not, the ledger knows: a lie is logged as one
			return await Thespis.observe(ThespisClient.event("tell", "player", to, intent.args["claim"],
					onlookers(to), {"said": true}))
		"pay":
			return await Thespis.observe(ThespisClient.event("pay", "player", to,
					ThespisClient.claim("paid", "player", to), onlookers(to), {"amount": int(intent.args["amount"])}))
	return await talk_to(to)


## The player says yes to one of the readings they were asked about.
func confirm(reading: ThespisApi.IntentOut) -> ThespisResult:
	dismiss()
	%Heard.text += "  (%s)" % reading.reads
	done = await carry_out(reading)
	return done


## The player meant none of them: nothing happens.
func dismiss() -> void:
	_ask([])


## An hour passes: Pip walks his round, and the gossips pass on what they've heard.
func pass_hour() -> ThespisResult:
	var r := await Thespis.tick()
	if r.ok:
		phase = r.value.phase
		for move in r.value.moves:
			if move.get("who") == "pip":
				pip_at = move["to"]
		%Where.text = "Hour %d. Pip is in %s." % [phase, "the taproom" if pip_at == "taproom" else "the " + pip_at]
	return r


func what_happened() -> ThespisResult:
	var r := await Thespis.narrate({"since": told_up_to})
	if r.ok:
		told_up_to = phase
	return r


## The game's save holds the scene's own state and the minds, kept as the text Thespis wrote.
func save_game(path := SAVE) -> ThespisResult:
	var minds := await Thespis.snapshot()
	if minds.ok:
		var f := FileAccess.open(path, FileAccess.WRITE)
		f.store_string(JSON.stringify({"pip_at": pip_at, "phase": phase, "told_up_to": told_up_to,
				"minds": minds.value}))
		f.close()
	return minds


func load_game(path := SAVE) -> ThespisResult:
	if not FileAccess.file_exists(path):
		return ThespisResult.failure("no_save", "nothing saved yet")
	var saved: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	await Thespis.close()
	var r := await Thespis.restore(GAME, saved["minds"])
	if r.ok:
		pip_at = saved["pip_at"]
		phase = int(saved["phase"])
		told_up_to = int(saved["told_up_to"])
		_showing.clear()
		dismiss()
		%Heard.text = ""
		for label in _labels.values():
			label.text = ""
	return r


func _say_typed() -> void:
	var text: String = %Words.text.strip_edges()
	if not text.is_empty():
		%Words.clear()
		await say(text)


## Each reading as a button, "Did you mean: Insult Garrick?", and one to say it was none of them.
func _ask(readings: Array) -> void:
	asking = readings
	for old in %Asking.get_children():
		%Asking.remove_child(old)
		old.queue_free()
	for reading in readings:
		var yes := Button.new()
		yes.text = "Did you mean: %s?" % reading.reads
		yes.pressed.connect(confirm.bind(reading))
		%Asking.add_child(yes)
	if not readings.is_empty():
		var no := Button.new()
		no.text = "No"
		no.pressed.connect(dismiss)
		%Asking.add_child(no)


func _arrived(line: ThespisLine) -> void:
	_showing[line.npc] = line.id
	_show(line)


func _settled(line: ThespisLine) -> void:
	if _showing.get(line.npc) == line.id:
		_show(line)


func _show(line: ThespisLine) -> void:
	var label: Label = _labels.get(line.npc)
	if label == null:
		return
	if line.is_withdrawn():
		label.text = ""
		return
	var doing := " (%s)" % line.action if line.action != null else ""
	label.text = "%s%s: %s" % [NAMES.get(line.npc, line.npc), doing, line.words("...")]
	label.modulate.a = 0.55 if line.is_provisional() else 1.0  # the template line, until the model's arrives
