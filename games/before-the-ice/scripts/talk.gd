## The talk panel: a sheet of paper on the desk at whatever place Anton is. Whom he speaks to, what they say, a line
## to type in his own words, and the acts as buttons. Typed words go to Thespis `understand`, which reads them as one
## of the game's acts (coldwater.toml [intents]) or as talk; an unsure reading is put back as "Did you mean...?".
## The case (case.gd) carries out an act the same way whichever way it came.
class_name Talk
extends PanelContainer

signal finished  ## Anton is done here: the day goes on

const K := 1.5
const INK := Color("#1a1714")
const PAPER := Color("#e6dcc6")
const BROWN := Color("#4a3c2c")
const RED := Color("#a3262a")

## What Anton can tell people, as he'd put it. Some are true; most aren't.
const STORIES := [
	["I was at Věra's till late that night", {"pred": "with_vera", "a": "player"}],
	["It was Ashby's lantern in the lane", {"pred": "lantern", "a": "ashby"}],
	["Ashby set the fire", {"pred": "fired", "a": "ashby", "b": "otto"}],
	["It was the watchman's lamp", {"pred": "fired", "a": "tamas", "b": "otto"}],
	["Tamás was drunk on watch", {"pred": "drunk", "a": "tamas"}],
	["Maggie sold him the bottle", {"pred": "sold_bottle", "a": "maggie", "b": "tamas"}],
	["Otto burned his own store", {"pred": "fired", "a": "otto", "b": "otto"}],
	["Otto was dealing a crooked game that night", {"pred": "fixed_game", "a": "otto"}],
	["Ashby's wanted in Seattle", {"pred": "wanted", "a": "ashby"}],
	["Martha saw someone in the lane", {"pred": "saw_lane", "a": "martha"}],
]

var case: Case
var to := ""  ## whom Anton speaks to

var _title: Label
var _people: HBoxContainer
var _log: RichTextLabel
var _words: LineEdit
var _readings: VBoxContainer
var _acts: HFlowContainer
var _amount: SpinBox
var _end: Button
var _busy := false
var _serif := SystemFont.new()
var _italic := SystemFont.new()
var _caps := SystemFont.new()


func _init() -> void:
	_serif.font_names = PackedStringArray(["Old Standard TT", "Georgia", "Times New Roman", "serif"])
	_italic.font_names = _serif.font_names
	_italic.font_italic = true
	_caps.font_names = PackedStringArray(["IM Fell English SC", "Georgia", "Times New Roman", "serif"])


func _ready() -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = PAPER
	sb.shadow_color = Color(0, 0, 0, 0.55)
	sb.shadow_size = 14
	sb.shadow_offset = Vector2(0, 7)
	for side in [SIDE_LEFT, SIDE_RIGHT, SIDE_TOP, SIDE_BOTTOM]:
		sb.set_content_margin(side, 16 * K)
	add_theme_stylebox_override("panel", sb)
	custom_minimum_size = Vector2(430, 0) * K
	rotation = deg_to_rad(0.6)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", int(6 * K))
	add_child(v)
	_title = _label("", _caps, 20, INK)
	v.add_child(_title)
	_people = HBoxContainer.new()
	_people.add_theme_constant_override("separation", int(6 * K))
	v.add_child(_people)
	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.scroll_following = true
	_log.custom_minimum_size = Vector2(0, 170) * K
	_log.add_theme_font_override("normal_font", _serif)
	_log.add_theme_font_override("italics_font", _italic)
	_log.add_theme_font_override("bold_font", _caps)
	_log.add_theme_font_size_override("normal_font_size", int(13 * K))
	_log.add_theme_font_size_override("italics_font_size", int(13 * K))
	_log.add_theme_font_size_override("bold_font_size", int(13 * K))
	_log.add_theme_color_override("default_color", INK)
	v.add_child(_log)
	_readings = VBoxContainer.new()
	v.add_child(_readings)
	var say := HBoxContainer.new()
	_words = LineEdit.new()
	_words.placeholder_text = "Say something, in your own words"
	_words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_words.text_submitted.connect(func(_t): _typed())
	say.add_child(_words)
	say.add_child(_button("Say", _typed))
	v.add_child(say)
	_acts = HFlowContainer.new()
	_acts.add_theme_constant_override("h_separation", int(4 * K))
	v.add_child(_acts)
	_acts.add_child(_button("Ask about that night", func(): _act(func(): await case.ask(to))))
	var tell := MenuButton.new()
	tell.text = "Tell..."
	tell.flat = false
	for i in STORIES.size():
		tell.get_popup().add_item(STORIES[i][0], i)
	tell.get_popup().id_pressed.connect(func(id: int): _act(func(): await case.tell(to, STORIES[id][1])))
	_acts.add_child(tell)
	_amount = SpinBox.new()
	_amount.min_value = 1
	_amount.max_value = 50
	_amount.value = 5
	_amount.prefix = "$"
	_acts.add_child(_amount)
	_acts.add_child(_button("Give", func(): _act(func(): await case.pay(to, int(_amount.value)))))
	_acts.add_child(_button("Comfort", func(): _act(func(): await case.comfort(to))))
	_acts.add_child(_button("Threaten", func(): _act(func(): await case.threaten(to))))
	_acts.add_child(_button("Confess", func(): _act(func(): await case.confess(to))))
	_end = _button("Let the day go on", func(): finished.emit())
	v.add_child(_end)


func _label(text: String, font: Font, size: float, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", font)
	l.add_theme_font_size_override("font_size", int(size * K))
	l.add_theme_color_override("font_color", color)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return l


func _button(text: String, pressed: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.pressed.connect(pressed)
	return b


## Show the people at a place, and whom Anton speaks to first.
func show_place(title: String, end_label := "Let the day go on") -> void:
	_title.text = title
	_end.text = end_label
	for c in _people.get_children():
		c.queue_free()
	var here: Array = case.others("player")
	if not here.has(to):
		to = here[0] if here.size() > 0 else ""
	for n in here:
		var b := Button.new()
		b.text = Case.NAMES.get(n, n)
		b.toggle_mode = true
		b.button_pressed = n == to
		b.pressed.connect(_speak_to.bind(n, title, end_label))
		_people.add_child(b)
	_acts.visible = not to.is_empty()
	if to.is_empty():
		write("[i]Nobody here.[/i]")
	visible = true


func _speak_to(n: String, title: String, end_label: String) -> void:
	to = n
	show_place(title, end_label)


func write(bbcode: String) -> void:
	_log.append_text(bbcode + "\n")


## A line someone said, followed as the model's words replace the game's own.
func hear(line: ThespisLine) -> void:
	var who: String = Case.NAMES.get(line.npc, line.npc)
	write("[b]%s:[/b] %s" % [who, line.words("...")])
	if line.is_provisional():
		var better := func(l: ThespisLine) -> void:
			if l.is_final():
				write("[b]%s:[/b] [i]%s[/i]" % [who, l.words("...")])
		line.settled.connect(better, CONNECT_ONE_SHOT)


func _act(what: Callable) -> void:
	if _busy or to.is_empty():
		return
	_busy = true
	_clear_readings()
	await what.call()
	_busy = false


## What Anton typed: read as one of the game's acts, put to him first if it's unsure, or talk.
func _typed() -> void:
	var text := _words.text.strip_edges()
	if text.is_empty() or _busy or to.is_empty():
		return
	_words.clear()
	write("[b]You:[/b] %s" % text)
	_busy = true
	_clear_readings()
	var r := await Thespis.understand(text, to, {"offered": case.offered()})
	_busy = false
	if not r.ok:
		write("[i](%s)[/i]" % r.reason)
		return
	match r.value.status:
		"act":
			await _act(func(): await case.carry_out(r.value.intent))
		"ask":
			for reading in r.value.readings:
				_readings.add_child(_button("Did you mean: %s?" % reading.reads,
						func(): _act(func(): await case.carry_out(reading))))
		_:
			await _act(func(): await case.talk(to))


func _clear_readings() -> void:
	for c in _readings.get_children():
		c.queue_free()
