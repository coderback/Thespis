## A conversation, as the design canvas draws it (ConversationDesk): the town behind, zoomed in and dimmed; the
## place on a card; whoever Anton speaks to as a half-length portrait with a pinned name tag; what they say on a
## sheet of paper; his answers as numbered paper tags, each saying what it may cost; a ruled line to say it his own
## way; a pinned note of what they have from him, with the red string of who they told; and the way out.
##
## Typed words go to Thespis `understand`, which reads them as one of the game's acts (coldwater.toml [intents]) or
## as talk; an unsure reading comes back as "Did you mean...?" tags. The case (case.gd) carries out an act the same
## way whichever way it came. Positions are the canvas's (1280x720) times K.
class_name Talk
extends Control

signal finished  ## Anton leaves: the day goes on

const K := 1.5
const INK := Color("#1a1714")
const PAPER := Color("#e6dcc6")
const SHEET := Color("#efe6d2")
const BROWN := Color("#4a3c2c")
const AMBER := Color("#8a4f10")
const RED := Color("#b3262b")
const WARN := Color("#a82a26")
const HINT := Color("#6a5a46")
const BLUE_INK := Color("#1b2a4a")
const PALE := Color("#c9bba0")
const TILT := [-0.8, 0.5, -0.4, 0.7]
const ANSWERS := 4  ## answers a visit: each spends a little of the day
const PORTRAITS := {
	"maggie": "res://assets/portraits/maggie.png",
	"tamas": "res://assets/portraits/tamas.png",
	"otto": "res://assets/portraits/otto.png",
	"martha": "res://assets/portraits/martha.png",
}

var case: Case
var picture: TextureRect  ## the town, dimmed behind the conversation (shaders/dim.gdshader)
var to := ""  ## whom Anton speaks to
var spent := 0  ## answers given this visit

var _place: Label
var _when: Label
var _also: HBoxContainer
var _portrait: TextureRect
var _shadow: TextureRect
var _name: Label
var _role: Label
var _tag: PanelContainer
var _speaker: Label
var _speech: Label
var _answers: VBoxContainer
var _column: VBoxContainer  ## the answers, the ruled line and the fold
var _words: LineEdit
var _more: HFlowContainer
var _amount: SpinBox
var _note_title: Label
var _note: RichTextLabel
var _string: StringGraph
var _leave: Button
var _budget: Label
var _choices: Array = []  ## the answers shown: each {say, hint, warn, act}
var _busy := false
var _dimmed := 0.0  ## how far the town is dimmed now
var _title := ""
var _part := ""

var _serif: Font = Fonts.serif
var _italic: Font = Fonts.italic
var _caps: Font = Fonts.caps
var _type: Font = Fonts.type
var _hand: Font = Fonts.hand


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	_vignette()
	_place_card()
	_portrait_and_tag()
	_speech_sheet()
	_answer_column()
	_note_card()
	_way_out()
	visible = false


# ------------------------------------------------------------------------------------------------ building

func _vignette() -> void:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.55, 1.0])
	g.colors = PackedColorArray([Color(0.086, 0.059, 0.039, 0.0), Color(0.086, 0.059, 0.039, 0.35),
			Color(0.086, 0.059, 0.039, 0.85)])
	var tex := GradientTexture2D.new()
	tex.gradient = g
	tex.fill = GradientTexture2D.FILL_RADIAL
	tex.fill_from = Vector2(0.3, 0.6)
	tex.fill_to = Vector2(1.05, 1.15)
	var v := TextureRect.new()
	v.texture = tex
	v.set_anchors_preset(Control.PRESET_FULL_RECT)
	v.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	v.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(v)


func _paper(fill: Color, pad: Vector4, shadow := 18.0) -> StyleBoxFlat:
	var b := StyleBoxFlat.new()
	b.bg_color = fill
	b.shadow_color = Color(0, 0, 0, 0.55)
	b.shadow_size = int(shadow * K * 0.6)
	b.shadow_offset = Vector2(0, shadow * K * 0.45)
	b.content_margin_top = pad.x * K
	b.content_margin_right = pad.y * K
	b.content_margin_bottom = pad.z * K
	b.content_margin_left = pad.w * K
	return b


func _label(text: String, font: Font, size: float, color: Color, wrap := false) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", font)
	l.add_theme_font_size_override("font_size", int(size * K))
	l.add_theme_color_override("font_color", color)
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


func _put(c: Control, at: Vector2, degrees := 0.0) -> Control:
	c.position = at * K
	c.rotation = deg_to_rad(degrees)
	add_child(c)
	return c


## A brass pin, as on the canvas's notes and tags: drawn on the paper, over its top edge.
func _pin(parent: Control, at: Vector2, size := 10.0) -> void:
	var c := (at + Vector2(size, size) / 2.0) * K
	var r := size * K / 2.0
	parent.draw.connect(func() -> void:
		parent.draw_circle(c, r, Color("#4a300a"))
		parent.draw_circle(c, r * 0.8, Color("#9a6a1c"))
		parent.draw_circle(c - Vector2(r, r) * 0.25, r * 0.4, Color("#f3d58a")))


func _place_card() -> void:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", _paper(PAPER, Vector4(10, 16, 10, 16), 18))
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", int(2 * K))
	_place = _label("", _caps, 22, INK)
	_when = _label("", _type, 12, AMBER)
	v.add_child(_place)
	v.add_child(_when)
	p.add_child(v)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_put(p, Vector2(30, 24), -1.4)
	_also = HBoxContainer.new()
	_also.add_theme_constant_override("separation", int(8 * K))
	_put(_also, Vector2(34, 100))


func _portrait_and_tag() -> void:
	for i in 2:
		var t := TextureRect.new()
		t.size = Vector2(380, 430) * K
		t.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		t.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		t.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		t.mouse_filter = Control.MOUSE_FILTER_IGNORE
		if i == 0:
			t.modulate = Color(0, 0, 0, 0.5)  # its shadow on the desk
			_shadow = _put(t, Vector2(70, 304)) as TextureRect
		else:
			_portrait = _put(t, Vector2(70, 290)) as TextureRect
	_tag = PanelContainer.new()
	var sb := _paper(PAPER, Vector4(5, 12, 6, 12), 10)
	sb.border_color = INK
	sb.set_border_width_all(int(1 * K))
	_tag.add_theme_stylebox_override("panel", sb)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", int(1 * K))
	_name = _label("", _caps, 19, INK)
	_role = _label("", _italic, 13, BROWN)
	v.add_child(_name)
	v.add_child(_role)
	_tag.add_child(v)
	_tag.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_put(_tag, Vector2(64, 252), -4)
	_pin(_tag, Vector2(40, -5))


func _speech_sheet() -> void:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", _paper(SHEET, Vector4(20, 26, 22, 26), 26))
	p.custom_minimum_size = Vector2(500, 0) * K
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", int(6 * K))
	_speaker = _label("", _caps, 15, BROWN)
	_speech = _label("", _serif, 21, INK, true)
	_speech.custom_minimum_size = Vector2(448, 0) * K
	_speech.add_theme_constant_override("line_spacing", int(9 * K))
	v.add_child(_speaker)
	v.add_child(_speech)
	p.add_child(v)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_put(p, Vector2(470, 92), 0.6)
	var tail := Polygon2D.new()  # the sheet's point, towards whoever speaks
	tail.color = SHEET
	tail.polygon = PackedVector2Array([Vector2(0, 0), Vector2(-14, 12) * K, Vector2(0, 24) * K])
	tail.position = Vector2(0, 56) * K
	p.add_child(tail)


func _answer_column() -> void:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", int(10 * K))
	v.custom_minimum_size = Vector2(460, 0) * K
	_answers = VBoxContainer.new()
	_answers.add_theme_constant_override("separation", int(10 * K))
	v.add_child(_answers)
	# the ruled line, to say it your own way
	var ruled := Ruled.new()
	ruled.custom_minimum_size = Vector2(460, 44) * K
	ruled.rotation = deg_to_rad(-0.6)
	var h := HBoxContainer.new()
	h.set_anchors_preset(Control.PRESET_FULL_RECT)
	h.offset_left = 16 * K
	h.offset_right = -16 * K
	h.add_theme_constant_override("separation", int(10 * K))
	_words = LineEdit.new()
	_words.placeholder_text = "Or say it your own way..."
	_words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_words.flat = true
	_words.add_theme_font_override("font", _hand)
	_words.add_theme_font_size_override("font_size", int(19 * K))
	_words.add_theme_color_override("font_color", BLUE_INK)
	_words.add_theme_color_override("font_placeholder_color", Color("#6a6a7a"))
	_words.add_theme_color_override("caret_color", BLUE_INK)
	_words.text_submitted.connect(func(_t: String) -> void: _typed())
	h.add_child(_words)
	var enter := _label("ENTER", _type, 12, BROWN)
	enter.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	h.add_child(enter)
	ruled.add_child(h)
	v.add_child(ruled)
	# everything else Anton can do, behind a fold
	var fold := Button.new()
	fold.text = "Other things to say or do..."
	fold.flat = true
	fold.alignment = HORIZONTAL_ALIGNMENT_LEFT
	fold.add_theme_font_override("font", _italic)
	fold.add_theme_font_size_override("font_size", int(14 * K))
	fold.add_theme_color_override("font_color", PALE)
	fold.add_theme_color_override("font_hover_color", PAPER)
	fold.pressed.connect(func() -> void: _more.visible = not _more.visible)
	v.add_child(fold)
	_more = HFlowContainer.new()
	_more.add_theme_constant_override("h_separation", int(6 * K))
	_more.add_theme_constant_override("v_separation", int(6 * K))
	_more.visible = false
	var tell := MenuButton.new()
	tell.text = "Tell..."
	_style_small(tell)
	for i in Case.STORIES.size():
		tell.get_popup().add_item(Case.STORIES[i][0], i)
	tell.get_popup().id_pressed.connect(func(id: int) -> void: _do(func() -> void: await case.tell(to, Case.STORIES[id][1])))
	_more.add_child(tell)
	_amount = SpinBox.new()
	_amount.min_value = 1
	_amount.max_value = 50
	_amount.value = 5
	_amount.prefix = "$"
	_more.add_child(_amount)
	for act in [["Give", "pay"], ["Comfort", "comfort"], ["Threaten", "threaten"], ["Confess", "confess"]]:
		var b := Button.new()
		b.text = act[0]
		_style_small(b)
		var verb: String = act[1]
		b.pressed.connect(func() -> void: _do(_act_for(verb)))
		_more.add_child(b)
	v.add_child(_more)
	_column = v
	_put(v, Vector2(500, 336))


func _note_card() -> void:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", _paper(PAPER, Vector4(14, 16, 16, 16), 22))
	p.custom_minimum_size = Vector2(246, 0) * K
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", int(8 * K))
	_note_title = _label("", _caps, 17, INK, true)
	_note_title.custom_minimum_size = Vector2(214, 0) * K
	_note = RichTextLabel.new()
	_note.fit_content = true
	_note.scroll_active = false
	_note.custom_minimum_size = Vector2(214, 0) * K
	_note.add_theme_font_override("normal_font", _hand)
	_note.add_theme_font_size_override("normal_font_size", int(16 * K))
	_note.add_theme_color_override("default_color", BLUE_INK)
	_note.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_string = StringGraph.new()
	_string.font = _serif
	_string.italic = _italic
	_string.custom_minimum_size = Vector2(214, 64) * K
	v.add_child(_note_title)
	v.add_child(_note)
	v.add_child(_string)
	p.add_child(v)
	p.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_put(p, Vector2(1004, 40), 2)
	_pin(p, Vector2(116, -6), 12)


func _way_out() -> void:
	_leave = Button.new()
	_leave.custom_minimum_size = Vector2(0, 44) * K
	var sb := _paper(PAPER, Vector4(0, 18, 0, 18), 14)
	sb.border_color = INK
	sb.set_border_width_all(int(1 * K))
	var hover := sb.duplicate() as StyleBoxFlat
	hover.bg_color = Color("#f3ead6")
	_leave.add_theme_stylebox_override("normal", sb)
	_leave.add_theme_stylebox_override("hover", hover)
	_leave.add_theme_stylebox_override("pressed", hover)
	_leave.add_theme_stylebox_override("focus", hover)
	_leave.add_theme_font_override("font", _caps)
	_leave.add_theme_font_size_override("font_size", int(17 * K))
	_leave.add_theme_color_override("font_color", INK)
	_leave.add_theme_color_override("font_hover_color", INK)
	_leave.add_theme_color_override("font_pressed_color", INK)
	_leave.add_theme_color_override("font_focus_color", INK)
	_leave.pressed.connect(_go)
	add_child(_leave)
	_budget = _label("", _italic, 14, PALE)
	add_child(_budget)


func _style_small(b: Button) -> void:
	var sb := _paper(PAPER, Vector4(4, 10, 4, 10), 8)
	sb.border_color = INK
	sb.set_border_width_all(int(1 * K))
	var hover := sb.duplicate() as StyleBoxFlat
	hover.bg_color = Color("#f3ead6")
	b.add_theme_stylebox_override("normal", sb)
	b.add_theme_stylebox_override("hover", hover)
	b.add_theme_stylebox_override("pressed", hover)
	b.add_theme_font_override("font", _serif)
	b.add_theme_font_size_override("font_size", int(14 * K))
	b.add_theme_color_override("font_color", INK)
	b.add_theme_color_override("font_hover_color", INK)


## Keep the way out at the foot of the screen, right, whatever its words.
func _process(_delta: float) -> void:
	if not visible:
		return
	var page := get_viewport_rect().size
	_leave.size = _leave.get_combined_minimum_size()
	_leave.position = Vector2(page.x - _leave.size.x - 52 * K, page.y - _leave.size.y - 26 * K)
	_budget.size = _budget.get_combined_minimum_size()
	_budget.position = Vector2(_leave.position.x - _budget.size.x - 24 * K, page.y - _budget.size.y - 36 * K)


# ------------------------------------------------------------------------------------------------ playing

## Sit down at a place: the town dims behind, and whoever is here first speaks.
func open(title: String, part_name: String, leave_label: String, first := "") -> void:
	_title = title
	_part = part_name
	spent = 0
	_place.text = title
	_when.text = "DAY %d · %s" % [case.day(), part_name]
	_leave.text = leave_label
	if first.is_empty():  # with someone first, what they just said stays on the sheet
		_speech.text = ""
		_speaker.text = ""
	_more.visible = false
	_column.visible = true
	_also.visible = true
	var here: Array = case.others("player")
	to = first if not first.is_empty() else (here[0] if here.size() > 0 else "")
	if _speaker.text == Case.NAMES.get(to, ""):  # what they said before the sheet knew whose it was
		_speaker.text = ""
		_speaker.visible = false
	visible = true
	_dim(1.0)
	_show_person()
	if not to.is_empty() and first.is_empty():
		_busy = true
		await case.talk(to)
		_busy = false


func close() -> void:
	visible = false
	_dim(0.0)


func _go() -> void:
	if _busy:
		return
	close()
	finished.emit()


func _dim(amount: float) -> void:
	if picture == null or picture.material == null:
		return
	var m := picture.material as ShaderMaterial
	create_tween().tween_method(func(x: float) -> void: m.set_shader_parameter("amount", x), _dimmed, amount, 0.35)
	_dimmed = amount


## Whom Anton speaks to: the portrait, the tag, the note of what they have from him, the answers, the others here.
func _show_person() -> void:
	for c in _also.get_children():
		c.queue_free()
	for n in case.others("player"):
		if n == to:
			continue
		var b := Button.new()
		b.text = "Speak to %s" % Case.SHORT[n]
		_style_small(b)
		b.pressed.connect(_speak_to.bind(n))
		_also.add_child(b)
	var tex: Texture2D = null
	if not to.is_empty():
		var path: String = PORTRAITS.get(to, "res://assets/sprites/%s.png" % to)
		if ResourceLoader.exists(path):
			tex = load(path)
	_portrait.texture = tex
	_shadow.texture = tex
	_tag.visible = not to.is_empty()
	_name.text = Case.NAMES.get(to, "")
	_role.text = Case.ROLES.get(to, "")
	if to.is_empty():
		_speech.text = "Nobody's here."
	_refresh_note()
	_refresh_answers()


func _speak_to(n: String) -> void:
	if _busy:
		return
	to = n
	_show_person()
	_busy = true
	await case.talk(to)
	_busy = false


## A line someone said. Whoever Anton speaks to is on the sheet; anyone else is named over it.
func hear(line: ThespisLine) -> void:
	_speaker.text = "" if line.npc == to else Case.NAMES.get(line.npc, line.npc)
	_speaker.visible = not _speaker.text.is_empty()
	_speech.text = "\"%s\"" % line.words("...")
	if line.is_provisional():
		var better := func(l: ThespisLine) -> void:
			if l.is_final() and _speech.text == "\"%s\"" % line.words("..."):
				_speech.text = "\"%s\"" % l.words("...")
		line.settled.connect(better, CONNECT_ONE_SHOT)


## The end: the Inspector's Notebook on the pinned note, and nothing left to answer.
func notebook(text: String) -> void:
	_column.visible = false
	_also.visible = false
	_budget.text = ""
	_note_title.text = "The Inspector's Notebook"
	_note.clear()
	_note.append_text(text)
	_string.chain = []
	_string.visible = false


## Something Anton learns happened, said over the sheet.
func write(text: String) -> void:
	_speaker.text = text
	_speaker.visible = true


## The note: what this person has from Anton, and the red string of who they told.
func _refresh_note() -> void:
	var short: String = Case.SHORT.get(to, "")
	_note_title.text = "What %s has from you" % short if not short.is_empty() else "Nobody to tell"
	_note.clear()
	var said: Array = case.told.get(to, [])
	if said.is_empty():
		_note.append_text("Nothing yet.")
		_string.chain = []
		_string.visible = false
		return
	for t in said:
		var at: int = t.phase
		_note.append_text("Day %d, %s: %s.\n" % [at / 3 + 1, ["morning", "afternoon", "evening"][at % 3], t.note])
	var r := await Thespis.trace(said[-1].claim)
	var chain := [["You", ""], [short, ""]]
	if r.ok:
		for h in r.value.holders:
			for e in h.get("from", []):
				if e.get("source") == to and chain.size() < 3:
					chain.append([Case.SHORT.get(h.npc, h.npc), case.when(int(e.get("phase", 0)))])
	_string.chain = chain
	_string.visible = true
	_string.queue_redraw()


## The answers here: ask, the stories not yet told this person, and what suits them (money for Billy, gloves from
## Martha, comfort for the rest). Each says what it may cost.
func _refresh_answers() -> void:
	_choices = []
	if not to.is_empty():
		var who := "she" if to in Case.SHE else "he"
		var ask: Array = {"gilchrist": ["What do you know so far, Inspector?", "asks"],
				"tamas": ["How are you today? Do you remember any more?", "sits with him"]}.get(to,
				["What did you see that night?", "asks"])
		_choices.append({"say": ask[0], "hint": ask[1], "warn": false, "act": func() -> void: await case.ask(to)})
		var told_here: Array = case.told.get(to, []).map(func(t): return Case.story_note(t.claim))
		var gossip := "%s'll tell the town" % who if to == "maggie" else (
				"he'll write it down" if to == "gilchrist" else "%s may repeat it" % who)
		var n := 0
		for st in Case.STORIES:
			if n == 2:
				break
			if st[2] in told_here:
				continue
			var claim: Dictionary = st[1]
			_choices.append({"say": st[0], "hint": gossip, "warn": true,
					"act": func() -> void: await case.tell(to, claim)})
			n += 1
		if to == "billy":
			_choices.append({"say": "Here's five dollars. You didn't see anything.", "hint": "buys his silence?",
					"warn": true, "act": func() -> void: await case.pay(to, 5)})
		elif to == "martha":
			_choices.append({"say": "I'll take a pair of gloves.", "hint": "four dollars", "warn": false,
					"act": func() -> void: await case.pay(to, 4)})
		else:
			_choices.append({"say": "I'm sorry for all of it.", "hint": "comforts", "warn": false,
					"act": func() -> void: await case.comfort(to)})
	_draw_answers()


func _draw_answers() -> void:
	for c in _answers.get_children():
		c.queue_free()
	var left := ANSWERS - spent
	for i in _choices.size():
		var a: Dictionary = _choices[i]
		var b := Button.new()
		b.custom_minimum_size = Vector2(460, 44) * K
		b.rotation = deg_to_rad(TILT[i % TILT.size()])
		var sb := _paper(PAPER, Vector4(8, 14, 8, 14), 12)
		sb.border_color = INK
		sb.set_border_width_all(int(1 * K))
		var hover := sb.duplicate() as StyleBoxFlat
		hover.bg_color = Color("#f3ead6")
		b.add_theme_stylebox_override("normal", sb)
		b.add_theme_stylebox_override("hover", hover)
		b.add_theme_stylebox_override("pressed", hover)
		b.add_theme_stylebox_override("focus", hover)
		b.add_theme_stylebox_override("disabled", sb)
		var h := HBoxContainer.new()
		h.set_anchors_preset(Control.PRESET_FULL_RECT)
		h.offset_left = 14 * K
		h.offset_right = -14 * K
		h.add_theme_constant_override("separation", int(10 * K))
		h.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var dot := Panel.new()
		var ds := StyleBoxFlat.new()
		ds.bg_color = Color("#3a2a1e")
		ds.set_corner_radius_all(int(5 * K))
		dot.add_theme_stylebox_override("panel", ds)
		dot.custom_minimum_size = Vector2(10, 10) * K
		dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		dot.mouse_filter = Control.MOUSE_FILTER_IGNORE
		h.add_child(dot)
		var num := _label(str(i + 1), _type, 13, AMBER)
		num.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		h.add_child(num)
		var say := _label(a.say, _serif, 18, INK, true)
		say.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		say.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		h.add_child(say)
		var hint := _label(a.hint, _italic, 13, WARN if a.warn else HINT)
		hint.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		h.add_child(hint)
		b.add_child(h)
		b.disabled = left <= 0
		b.pressed.connect(_answer.bind(i))
		_answers.add_child(b)
	_budget.text = ("Each answer spends a little of the %s." % _part.to_lower()) if left > 0 \
			else "It's getting late. Time to go."


func _answer(i: int) -> void:
	if i < _choices.size():
		_do(_choices[i].act)


## Carry out an act and count it against the visit.
func _do(what: Callable) -> void:
	if _busy or to.is_empty() or spent >= ANSWERS:
		return
	_busy = true
	spent += 1
	await what.call()
	_busy = false
	_refresh_note()
	_refresh_answers()


func _act_for(verb: String) -> Callable:
	match verb:
		"pay":
			return func() -> void: await case.pay(to, int(_amount.value))
		"comfort":
			return func() -> void: await case.comfort(to)
		"threaten":
			return func() -> void: await case.threaten(to)
		_:
			return func() -> void: await case.confess(to)


## What Anton typed: read as one of the game's acts, put to him first if it's unsure, or talk.
func _typed() -> void:
	var text := _words.text.strip_edges()
	if text.is_empty() or _busy or to.is_empty() or spent >= ANSWERS:
		return
	_words.clear()
	_busy = true
	var r := await Thespis.understand(text, to, {"offered": case.offered()})
	_busy = false
	if not r.ok:
		write("(%s)" % r.reason)
		return
	match r.value.status:
		"act":
			_do(func() -> void: await case.carry_out(r.value.intent))
		"ask":
			_choices = []
			for reading in r.value.readings:
				_choices.append({"say": "Did you mean: %s?" % reading.reads, "hint": "your words", "warn": false,
						"act": func() -> void: await case.carry_out(reading)})
			_draw_answers()
		_:
			_do(func() -> void: await case.talk(to))


## 1 to 4 answer, as the tags are numbered.
func _unhandled_key_input(event: InputEvent) -> void:
	if not visible or _words.has_focus() or not event.is_pressed():
		return
	var k := (event as InputEventKey).keycode
	if k >= KEY_1 and k <= KEY_4:
		_answer(k - KEY_1)
		get_viewport().set_input_as_handled()


# ------------------------------------------------------------------------------------------------ pieces

## Ruled notebook paper, blue lines every 31 canvas pixels, for the line Anton writes in his own words.
class Ruled extends Control:
	func _draw() -> void:
		draw_rect(Rect2(Vector2(0, 6) * K, Vector2(size.x, size.y)), Color(0, 0, 0, 0.35))  # its shadow
		draw_rect(Rect2(Vector2.ZERO, size), Color("#ece4d2"))
		var y := 30.0 * K
		while y < size.y:
			draw_line(Vector2(0, y), Vector2(size.x, y), Color("#9fb6cc"), 1.0 * K)
			y += 31.0 * K


## The red string of who has it: from Anton, through whoever he told, to whoever they told, with when.
class StringGraph extends Control:
	var chain: Array = []  ## each [name, when]
	var font: Font
	var italic: Font

	func _draw() -> void:
		if chain.size() < 2:
			return
		var w := size.x
		var xs: Array[float] = []
		for i in chain.size():
			xs.append(lerpf(28.0 * K, w - 28.0 * K, float(i) / float(max(chain.size() - 1, 1))))
		for i in chain.size() - 1:
			var a := Vector2(xs[i], 22.0 * K)
			var b := Vector2(xs[i + 1], 22.0 * K)
			var mid := (a + b) / 2.0 - Vector2(0, 18.0 * K)
			var pts := PackedVector2Array()
			for s in 17:
				var t := float(s) / 16.0
				pts.append(a.lerp(mid, t).lerp(mid.lerp(b, t), t))
			draw_polyline(pts, RED, 2.5 * K, true)
		for i in chain.size():
			var last := i == chain.size() - 1 and i > 1
			draw_circle(Vector2(xs[i], 22.0 * K), 5.0 * K, RED if last else INK)
			var who: String = chain[i][0]
			var ns := font.get_string_size(who, HORIZONTAL_ALIGNMENT_CENTER, -1, int(13 * K))
			draw_string(font, Vector2(xs[i] - ns.x / 2.0, 44.0 * K), who, HORIZONTAL_ALIGNMENT_LEFT, -1,
					int(13 * K), INK)
			var when: String = chain[i][1]
			if not when.is_empty():
				var ws := italic.get_string_size(when, HORIZONTAL_ALIGNMENT_CENTER, -1, int(11 * K))
				draw_string(italic, Vector2(xs[i] - ws.x / 2.0, 60.0 * K), when, HORIZONTAL_ALIGNMENT_LEFT, -1,
						int(11 * K), BROWN)
