## The game's screen: the town rendered small (960x540) and scaled up by whole pixels, the paper on top at full size.
## Run with `-- --shot=<file.png>` to save the picture after it settles and quit (tools/shot.py does this).
extends Control

const PIXELS := Vector2i(960, 540)

var view: SubViewport
var town: Town
var walk: Walk
var paper: Paper


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
	if args.has("shot"):
		_shot(args.shot)


func _go(place: String) -> void:
	if walk.walking:
		return
	var f: Dictionary = paper.flags[place].get_meta("flag")
	paper.say("Walking to %s." % f.name, "a few seconds · click to skip")
	paper.flags.you.visible = false
	walk.go(place, town.route_to(place, town.anton_feet()))


func _arrived(place: String) -> void:
	var f: Dictionary = paper.flags[place].get_meta("flag")
	paper.say("At %s." % f.name, f.who)
	paper.flags.you.visible = true


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
