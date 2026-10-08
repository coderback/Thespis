## The Lantern, in Godot: Garrick sits in the taproom. Insult him, then ask what he does.
##
## The engine owns the world: this scene decides what an insult is, who saw it and what it does to Garrick, and
## tells Thespis. Thespis owns his mind: what he believes, what he chooses among the actions examples/tavern/game.toml
## declares, and what he says. His line shows at once (provisional) and is replaced when the model's arrives.
extends Control

signal opened(ok: bool)

const Thespis := preload("res://thespis.gd")
const INSULT := {"pred": "insulted", "a": "player", "b": "garrick"}

@export var server := "http://127.0.0.1:7878"

var thespis: Node

@onready var line_label: Label = $Box/Line
@onready var status_label: Label = $Box/Status


func _ready() -> void:
	thespis = Thespis.new()
	thespis.base_url = server
	add_child(thespis)
	thespis.line_changed.connect(_show)
	$Box/Buttons/Insult.pressed.connect(insult)
	$Box/Buttons/Ask.pressed.connect(ask)
	var r: Dictionary = await thespis.open("tavern")
	status_label.text = "Session %s" % thespis.session_id if r.has("session") else "No Thespis: %s" % r.get("reason")
	opened.emit(r.has("session"))


## The player insults Garrick in front of Wren. The game file says an insult angers him ([npc.garrick.feels]), so
## the engine reports only the event.
func insult() -> Dictionary:
	return await thespis.observe({"verb": "insult", "actor": "player", "target": "garrick",
			"claim": INSULT, "witnesses": ["wren"]})


## What Garrick does now, and what he says: shown at once, then settled.
func ask() -> Dictionary:
	var line: Dictionary = await thespis.decide("garrick", "turn")
	return await thespis.settle(line)


func _show(line: Dictionary) -> void:
	if line.get("status") == "withdrawn":
		line_label.text = ""
		return
	var text = line.get("text")
	line_label.text = "Garrick (%s): %s" % [line.get("action", "?"), text if text != null else "..."]
	status_label.text = "%s, from %s" % [line.get("status", "?"), line.get("source", "?")]
