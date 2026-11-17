## The game's screen: the town rendered small (960x540) and scaled up by whole pixels, the paper on top at full size.
## The case (case.gd) plays the week through Thespis; the talk panel is where Anton speaks.
## Run with `-- --shot=<file.png>` to save the picture after it settles and quit (tools/shot.py does this; a shot
## doesn't start Thespis). `-- --seed=<n>` plays a given week.
extends Control

const PIXELS := Vector2i(960, 540)

var view: SubViewport
var town: Town
var walk: Walk
var paper: Paper
var case: Case
var talk: Talk
var _thespis := false  ## the case is playing through Thespis


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

	var picture := TextureRect.new()
	picture.texture = view.get_texture()
	picture.set_anchors_preset(Control.PRESET_FULL_RECT)
	picture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	picture.stretch_mode = TextureRect.STRETCH_SCALE
	picture.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	picture.mouse_filter = Control.MOUSE_FILTER_IGNORE
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
	if args.has("walk"):
		_go(args.walk)
		walk.travelled = walk.curve.get_baked_length() * float(args.get("at", "0.5"))
	if args.has("shot") and not args.has("talk"):
		_shot(args.shot)
		return

	case = Case.new()
	add_child(case)
	talk = Talk.new()
	talk.case = case
	talk.visible = false
	add_child(talk)
	talk.position = Vector2(1920 - 430 * Talk.K - 60, 140)
	talk.finished.connect(_day_goes_on)
	case.spoke.connect(talk.hear)
	case.news.connect(func(t: String): talk.write("[i]%s[/i]" % t))
	case.clock.connect(_clock)
	case.people_moved.connect(_who)
	case.ended.connect(_ended)
	paper.say("Starting Thespis...", "the town's minds")
	var r := await case.begin(int(args.get("seed", "0")))
	_thespis = r.ok
	if not r.ok:
		push_warning("No Thespis: %s" % r.reason)
		paper.say("The town is quiet: no Thespis.", r.reason.left(80))
	if args.has("talk"):  # `-- --talk=maggies --shot=<file.png>`: at a place, talking, for a picture
		var key: String = args.talk
		town.people.anton.position = town.place(key)
		_arrived(key)
		await get_tree().create_timer(1.0).timeout
		await case.talk(talk.to)
		var u := await Thespis.understand("I was at my sister's till late", talk.to, {"offered": case.offered()})
		if u.ok and u.value.intent != null and u.value.status == "act":
			await case.carry_out(u.value.intent)
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
		talk.show_place(f.name)


## Anton is done here. In the evening he goes on to sit with Gilchrist at the post; then the night passes.
func _day_goes_on() -> void:
	if not case.playing:
		return
	var evening := case.part() == 2 and not case.sat_with_him
	talk.visible = false
	await case.end_phase()
	if evening and case.playing:
		paper.say("The post, with Inspector Gilchrist.", "he asked you to sit with him")
		talk.show_place("The Mounted Police post", "Good night")


func _clock(day: int, part: int) -> void:
	var d: Dictionary = case.data.days[day - 1]
	var part_name: String = case.data.phases[part]
	paper.set_clock(d.name, d.date, day, part_name)
	paper.say("%s. Where will you go?" % part_name.capitalize(), "choose a flag on the model")


## Who is at each flag's place, as the town moves.
func _who() -> void:
	for key in case.data.flags:
		var people: Array = case.at(case.data.flags[key]).map(func(n): return Case.SHORT[n])
		paper.set_who(key, ", ".join(people) if people.size() > 0 else "nobody")


func _ended(title: String, line: ThespisLine) -> void:
	paper.say(title, "the ice has gone out")
	talk.show_place(title, "The End")
	if line != null:
		talk.hear(line)
	var nb := await case.notebook()
	if nb.ok and nb.value != null:
		talk.write("[b]The Inspector's Notebook[/b]
%s" % nb.value.words(""))


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
