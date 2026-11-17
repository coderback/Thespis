## The paper on the desk, at full resolution over the pixel town: the cartouche, the prompt, and a flag pinned to
## each place you can go. Layout follows the TownDesk screen on the design canvas (drawn at 1280x720; here 1920x1080).
class_name Paper
extends Control

signal chosen(place: String)

const K := 1.5  # canvas pixels to these
const INK := Color("#1a1714")
const PAPER := Color("#e6dcc6")
const BROWN := Color("#4a3c2c")
const AMBER := Color("#e6a54a")

## Each place's flag: what it says, how long its pin is, and any nudge off the anchor (canvas pixels) so flags clear
## each other, as on the canvas.
const FLAGS := [
	{"key": "maggies", "name": "Maggie's", "who": "Maggie, Sándor", "pin": 30},
	{"key": "store", "name": "Brand's store", "who": "burned · nobody", "pin": 50},
	{"key": "landing", "name": "The landing", "who": "Billy Tuck", "pin": 0, "nudge": Vector2(17, 42)},
	{"key": "ice", "name": "The ice", "who": "Jack Ashby", "pin": 40},
	{"key": "dest", "name": "Věra's claim", "who": "Věra", "pin": 0, "nudge": Vector2(50, -30)},
	{"key": "police", "name": "Mounted Police", "who": "Gilchrist, at the gate", "pin": 30},
	{"key": "church", "name": "The mission", "who": "Tamás, in the infirmary", "pin": 50, "nudge": Vector2(-70, 40)},
	{"key": "your_cabin", "name": "Your cabin", "who": "nobody", "pin": 0, "nudge": Vector2(0, 33)},
]

var town: Town
var flags: Dictionary = {}  ## key -> Control
var prompt: PanelContainer
var prompt_line: Label
var prompt_hint: Label
var day_line: Label
var phase_line: Label

var _serif: Font = Fonts.serif
var _italic: Font = Fonts.italic
var _caps: Font = Fonts.caps


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_cartouche()
	_prompt()
	for f in FLAGS:
		_flag(f)
	_flag({"key": "you", "name": "You", "who": "on the street", "pin": 0, "you": true, "nudge": Vector2(0, 48)})


func _box(fill: Color, shadow := 10.0) -> StyleBoxFlat:
	var b := StyleBoxFlat.new()
	b.bg_color = fill
	b.shadow_color = Color(0, 0, 0, 0.55)
	b.shadow_size = int(shadow)
	b.shadow_offset = Vector2(0, shadow * 0.5)
	return b


func _label(text: String, font: Font, size: float, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", font)
	l.add_theme_font_size_override("font_size", int(size * K))
	l.add_theme_color_override("font_color", color)
	return l


func _cartouche() -> void:
	var p := PanelContainer.new()
	var sb := _box(PAPER, 16)
	sb.content_margin_left = 20 * K
	sb.content_margin_right = 20 * K
	sb.content_margin_top = 16 * K
	sb.content_margin_bottom = 14 * K
	p.add_theme_stylebox_override("panel", sb)
	p.position = Vector2(34, 30) * K
	p.custom_minimum_size = Vector2(300, 0) * K
	p.rotation = deg_to_rad(-1.6)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", int(4 * K))
	v.add_child(_label("Coldwater Landing", _caps, 32, INK))
	day_line = _label("Yukon District · Tuesday, April 26, 1898", _italic, 14, BROWN)
	v.add_child(day_line)
	phase_line = _label("DAY 1 · MORNING", _serif, 14, Color("#8a4f10"))
	v.add_child(phase_line)
	p.add_child(v)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(p)


func _prompt() -> void:
	var p := PanelContainer.new()
	var sb := _box(Color(0.086, 0.059, 0.039, 0.82), 0)
	sb.border_color = Color("#5a4636")
	sb.set_border_width_all(1)
	sb.content_margin_left = 20 * K
	sb.content_margin_right = 20 * K
	sb.content_margin_top = 10 * K
	sb.content_margin_bottom = 10 * K
	p.add_theme_stylebox_override("panel", sb)
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", int(12 * K))
	h.alignment = BoxContainer.ALIGNMENT_CENTER
	h.add_child(_label("Anton Holub", _caps, 20, AMBER))
	prompt_line = _label("Evening. Where will you go?", _serif, 17, PAPER)
	h.add_child(prompt_line)
	prompt_hint = _label("choose a flag on the model", _italic, 13, Color("#c9bba0"))
	h.add_child(prompt_hint)
	p.add_child(h)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(p)
	prompt = p


## The day on the cartouche.
func set_clock(day_name: String, date: String, day: int, part: String) -> void:
	day_line.text = "Yukon District · %s, %s" % [day_name, date]
	phase_line.text = "DAY %d · %s" % [day, part]


## Who is at a flag's place now.
func set_who(key: String, who: String) -> void:
	if not flags.has(key):
		return
	var b: Button = flags[key]
	var f: Dictionary = b.get_meta("flag")
	f.who = who
	b.tooltip_text = "Go to %s. Here: %s" % [f.name, who]
	var words: VBoxContainer = b.get_child(0).get_child(0).get_child(0)
	(words.get_child(1) as Label).text = who


func say(line: String, hint := "") -> void:
	prompt_line.text = line
	prompt_hint.text = hint


func _flag(f: Dictionary) -> void:
	var you: bool = f.get("you", false)
	var b := Button.new()
	b.flat = true
	b.focus_mode = Control.FOCUS_ALL
	b.tooltip_text = "" if you else "Go to %s. Here: %s" % [f.name, f.who]
	b.disabled = you
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 0)
	col.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var tag := PanelContainer.new()
	var sb := _box(Color("#f3d58a") if you else PAPER, 6)
	sb.border_color = INK
	sb.set_border_width_all(1)
	sb.content_margin_left = 8 * K
	sb.content_margin_right = 8 * K
	sb.content_margin_top = 4 * K
	sb.content_margin_bottom = 5 * K
	tag.add_theme_stylebox_override("panel", sb)
	tag.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var words := VBoxContainer.new()
	words.add_theme_constant_override("separation", int(1 * K))
	words.mouse_filter = Control.MOUSE_FILTER_IGNORE
	words.add_child(_label(f.name, _caps, 14, INK))
	words.add_child(_label(f.who, _italic, 12, BROWN))
	tag.add_child(words)
	col.add_child(tag)
	var pin := ColorRect.new()
	pin.color = Color("#2a1d12")
	pin.custom_minimum_size = Vector2(2 * K, max(f.pin, 0) * K)
	pin.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	pin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var pinrow := MarginContainer.new()
	pinrow.add_theme_constant_override("margin_left", int(10 * K))
	pinrow.mouse_filter = Control.MOUSE_FILTER_IGNORE
	pinrow.add_child(pin)
	col.add_child(pinrow)
	var head := ColorRect.new()
	head.color = Color("#c9a14a")
	head.custom_minimum_size = Vector2(6, 6) * K
	head.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	head.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var headrow := MarginContainer.new()
	headrow.add_theme_constant_override("margin_left", int(8 * K))
	headrow.mouse_filter = Control.MOUSE_FILTER_IGNORE
	headrow.add_child(head)
	col.add_child(headrow)
	b.add_child(col)
	b.set_meta("flag", f.duplicate())  # its own copy: who is there changes
	if not you:
		b.pressed.connect(func() -> void: chosen.emit(f.key))
	add_child(b)
	flags[f.key] = b


## Pin each flag's point onto its place on the model (the town is drawn at half this size).
func _process(_delta: float) -> void:
	if town == null or town.camera == null:
		return
	var page := get_viewport_rect().size
	# the prompt: centred at the foot of the screen
	prompt.size = prompt.get_combined_minimum_size()
	prompt.position = Vector2((page.x - prompt.size.x) / 2.0, page.y - prompt.size.y - 26 * K)
	var to_paper := page / Vector2(960, 540)
	for key in flags:
		var b: Button = flags[key]
		var f: Dictionary = b.get_meta("flag")
		var p3: Vector3 = town.anton_feet() if key == "you" else town.place(key)
		var nudge: Vector2 = f.get("nudge", Vector2.ZERO)
		var tip: Vector2 = town.to_screen(p3) * to_paper + nudge * K
		var col: Control = b.get_child(0)
		b.size = col.get_combined_minimum_size()
		# the pin's point is 11 canvas px in from the left and at the foot of the flag
		b.position = tip - Vector2(11 * K, b.size.y - 3 * K)
