## The game's screen: the town rendered small (960x540) and scaled up by whole pixels, the paper on top at full size.
## The case (case.gd) plays the week through Thespis; the talk panel is where Anton speaks.
## Run with `-- --shot=<file.png>` to save the picture after it settles and quit (tools/shot.py does this; a shot
## doesn't start Thespis, unless it's `--phases=<n>`, the town that many phases into the week, or `--talk`).
## `-- --seed=<n>` plays a given week. In a browser (the web build, served at /ice/) the link says it instead:
## /ice/?seed=19; Thespis is the server the page came from, and the week's record is sent there as it goes.
extends Control

const PIXELS := Vector2i(960, 540)

var view: SubViewport
var town: Town
var walk: Walk
var paper: Paper
var picture: TextureRect
var case: Case
var talk: Talk
var _thespis := false  ## the case is playing through Thespis
var _log_dir := Journal.DIR  ## where the week's record goes (`-- --log=<dir>`; `--log=none` for none)
var _journal_saved := false
var _web := OS.has_feature("web")
var _web_name := ""  ## in a browser, the name the week's record is sent under, the same each time


func _ready() -> void:
	view = SubViewport.new()
	view.size = PIXELS
	view.own_world_3d = true
	view.msaa_3d = Viewport.MSAA_DISABLED
	view.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED
	view.use_taa = false
	view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(view)

	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("#13203a")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var we := WorldEnvironment.new()
	we.environment = env
	view.add_child(we)

	town = Town.new()
	view.add_child(town)

	picture = TextureRect.new()
	picture.texture = view.get_texture()
	picture.set_anchors_preset(Control.PRESET_FULL_RECT)
	picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	picture.stretch_mode = TextureRect.STRETCH_SCALE
	picture.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	picture.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var dim := ShaderMaterial.new()  # dims and zooms the town behind a conversation
	dim.shader = load("res://shaders/dim.gdshader")
	picture.material = dim
	add_child(picture)

	walk = Walk.new()
	town.add_child(walk)
	walk.walker = town.people.anton
	walk.arrived.connect(_arrived)

	paper = Paper.new()
	paper.town = town
	add_child(paper)
	paper.chosen.connect(_go)

	var args := {}
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--") and "=" in a:
			args[a.get_slice("=", 0).trim_prefix("--")] = a.get_slice("=", 1)
	if _web:
		_from_page(args)
	if args.has("walk"):
		_go(args.walk)
		walk.travelled = walk.curve.get_baked_length() * float(args.get("at", "0.5"))
	if args.has("shot") and not (args.has("talk") or args.has("phases")):
		_shot(args.shot)
		return

	case = Case.new()
	add_child(case)
	talk = Talk.new()
	talk.case = case
	talk.picture = picture
	add_child(talk)
	talk.finished.connect(_day_goes_on)
	case.spoke.connect(talk.hear)
	case.news.connect(func(t: String): paper.say(t, ""))
	case.clock.connect(_clock)
	case.people_moved.connect(_who)
	case.ended.connect(_ended)
	case.keep_journal = not (args.has("shot") or args.get("log", "") == "none")  # a playtest's record of the week
	_log_dir = str(args.get("log", Journal.DIR))
	paper.say("Starting Thespis...", "the town's minds")
	var r := await case.begin(int(args.get("seed", "0")))
	_thespis = r.ok
	if not r.ok:
		push_warning("No Thespis: %s" % r.reason)
		paper.say("The town is quiet: no Thespis.", r.reason.left(80))
	if args.has("phases") and not args.has("talk"):  # `-- --phases=4 --shot=<file.png>`: the town, a few phases on
		for i in int(args.phases):
			await case.advance()
		await get_tree().create_timer(Town.LONGEST + 1.0).timeout
		if args.has("shot"):
			_shot(args.shot)
	if args.has("talk"):  # `-- --talk=maggies [--part=1] [--to=otto] [--answer=2] [--evening=1] --shot=<file.png>`
		var key: String = args.talk  # talking, for a picture
		for i in int(args.get("part", "0")):  # `--part=1`: let the morning pass first (2: the afternoon too)
			await case.end_phase()
		town.people.anton.position = town.place(key)
		_arrived(key)
		await get_tree().create_timer(1.0).timeout
		if args.has("to"):  # `--to=martha`: speak to someone else who's there
			talk._speak_to(args.to)
			await get_tree().create_timer(1.0).timeout
		if args.has("answer"):  # `--answer=2`: press that answer, as the player would
			talk._answer(int(args.answer) - 1)
			await get_tree().create_timer(1.5).timeout
		if args.has("evening"):  # `--evening=1`: leave, and leave again, to the evening at the post
			for i in 3:
				talk.close()
				await _day_goes_on()
			await get_tree().create_timer(1.0).timeout
		if args.has("shot"):
			_shot(args.shot)


func _go(place: String) -> void:
	if walk.walking or (_thespis and (talk.visible or not case.playing)):
		return  # one place a phase: let the day go on first
	var f: Dictionary = paper.flags[place].get_meta("flag")
	paper.say("Walking to %s." % f.name, "a few seconds · click to skip")
	paper.flags.you.visible = false
	walk.go(place, town.route_to(place, town.anton_feet()))


func _arrived(place: String) -> void:
	var f: Dictionary = paper.flags[place].get_meta("flag")
	paper.say("At %s." % f.name, f.who)
	paper.flags.you.visible = true
	if _thespis and case.playing:
		await case.go(case.data.flags.get(place, place))
		_sit(place, f.name, "Leave %s" % f.name)


## Sit down to talk at a place: the town zooms in on it and dims, and the paper on the desk gives way to the
## conversation.
func _sit(place: String, title: String, leave: String, first := "") -> void:
	var m := picture.material as ShaderMaterial
	m.set_shader_parameter("center", town.to_screen(town.place(place)) / Vector2(PIXELS))
	paper.visible = false
	talk.open(title, case.data.phases[case.part()], leave, first)


## Anton is done here. In the evening he goes on to sit with Gilchrist at the post; then the night passes.
func _day_goes_on() -> void:
	if not case.playing:
		return
	var evening := case.part() == 2 and not case.sat_with_him
	paper.visible = true
	await case.end_phase()
	if evening and case.playing:  # he asked Anton to sit with him, and his question is on the sheet
		_sit("police", "The Mounted Police post", "Good night", "gilchrist")


func _clock(day: int, part: int) -> void:
	var d: Dictionary = case.data.days[day - 1]
	var part_name: String = case.data.phases[part]
	paper.set_clock(d.name, d.date, day, part_name)
	paper.say("%s. Where will you go?" % part_name.capitalize(), "choose a flag on the model")
	_send_record("", false)  # in a browser, the week so far: a closed tab can't send it


## Who is at each flag's place, as the town moves: on the flags, and the figures walking there.
func _who() -> void:
	town.stand(case.where)
	for key in case.data.flags:
		var people: Array = case.at(case.data.flags[key]).map(func(n): return Case.SHORT[n])
		paper.set_who(key, ", ".join(people) if people.size() > 0 else "nobody")


func _ended(title: String, line: ThespisLine) -> void:
	_sit("landing", title, "The End", "gilchrist")
	if line != null:
		talk.hear(line)
	var told := await case.notebook()
	talk.notebook(told)
	_save_journal(told, true)


## Write the playtest's record of the week, once: at the steamer, or when the window closes on a week not done.
func _save_journal(notebook: String, ended: bool) -> void:
	if case == null or not case.keep_journal or _journal_saved or case.journal.is_empty():
		return
	_journal_saved = true
	if _web:
		_send_record(notebook, ended)
		return
	var path := Journal.save(case, notebook, ended, _log_dir)
	print("The week's record: %s" % (path if not path.is_empty() else "couldn't be written to " + _log_dir))


## In a browser: the seed from the page's link (?seed=19), and Thespis at the server the page came from.
func _from_page(args: Dictionary) -> void:
	var query := str(JavaScriptBridge.eval("location.search", true)).trim_prefix("?")
	for pair in query.split("&", false):
		if pair.get_slice("=", 0) == "seed" and pair.get_slice("=", 1).is_valid_int():
			args["seed"] = pair.get_slice("=", 1)
	Thespis.url = str(JavaScriptBridge.eval("location.origin", true)) + "/thespis"


## In a browser: the week's record to the server it came from, under one name for the week, replacing the last send.
func _send_record(notebook: String, ended: bool) -> void:
	if not _web or case == null or not case.keep_journal or case.journal.is_empty():
		return
	if _web_name.is_empty():
		_web_name = "%s-seed%d-%04d" % [Journal.stamp(), case.seed_value, randi() % 10000]
	var r := Journal.record(case, notebook, ended)
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(_res, code, _h, _b):
		if code != 200:
			push_warning("the week's record wasn't taken (%d)" % code)
		http.queue_free())
	var origin := str(JavaScriptBridge.eval("location.origin", true))
	http.request(origin + "/ice/record", ["Content-Type: application/json"], HTTPClient.METHOD_POST,
			JSON.stringify({"name": _web_name, "md": r.md, "json": r.json}))


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_save_journal("", false)


func _unhandled_input(event: InputEvent) -> void:
	if walk.walking and event is InputEventMouseButton and event.pressed:
		walk.skip()


func _shot(path: String) -> void:
	for i in 30:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	view.get_texture().get_image().save_png(path)
	get_viewport().get_texture().get_image().save_png(path.get_basename() + "-screen.png")
	get_tree().quit()
