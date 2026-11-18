## The town on the desk: the model exported from Blender (assets/town.glb), staged from assets/town.json:
## the toon material for every surface, the desk lamp and the small lamps, the townsfolk, the chimney smoke,
## the camera from the river, and the ink outline pass.
class_name Town
extends Node3D

const TOON := preload("res://shaders/toon.gdshader")
const OUTLINE := preload("res://shaders/outline.gdshader")
const MODEL := preload("res://assets/town.glb")
const DATA_PATH := "res://assets/town.json"
## Lamp light at the middle of the model, in the band units: flat snow there lands in the cream band, as in Blender.
const LAMP_K := 0.38

var data: Dictionary
var camera: Camera3D
var people: Dictionary = {}  ## name -> Sprite3D

var _bands: GradientTexture1D
var _materials: Dictionary = {}  ## material name -> ShaderMaterial


func _ready() -> void:
	data = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
	_bands = _band_texture()
	var model := MODEL.instantiate()
	add_child(model)
	_dress(model)
	_lamps()
	_camera()
	for who in data.people:
		_person(who, data.people[who])
	for c in data.chimneys:
		_smoke(_v(c))
	for g in data.glows:
		_glow(g)


static func _v(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])


static func _c(hex: String) -> Color:
	return Color.html(hex)


## The light bands: the ramp the Blender shading uses, cut hard (constant), in light units up to its top.
func _band_texture() -> GradientTexture1D:
	var g := Gradient.new()
	g.interpolation_mode = Gradient.GRADIENT_INTERPOLATE_CONSTANT
	var top: float = data.bands[-1][0]
	g.offsets = PackedFloat32Array()
	g.colors = PackedColorArray()
	for b in data.bands:
		g.add_point(float(b[0]) / top, _c(b[1]))
	# drop the default end points add_point left behind
	while g.get_point_count() > data.bands.size():
		g.remove_point(0)
	var t := GradientTexture1D.new()
	t.gradient = g
	t.width = 256
	return t


func _ramp_texture(stops: Array) -> GradientTexture1D:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array()
	g.colors = PackedColorArray()
	for s in stops:
		g.add_point(float(s[0]), _c(s[1]))
	while g.get_point_count() > stops.size():
		g.remove_point(0)
	var t := GradientTexture1D.new()
	t.gradient = g
	t.width = 256
	return t


func _material(name: String) -> Material:
	if _materials.has(name):
		return _materials[name]
	# every exported material was recorded by name; magenta shows one that wasn't
	var spec: Dictionary = data.materials.get(name, {"kind": "plain", "color": "#ff00ff"})
	var m := ShaderMaterial.new()
	m.shader = TOON
	m.set_shader_parameter("bands", _bands)
	m.set_shader_parameter("band_top", float(data.bands[-1][0]) * float(data.band_scale))
	m.set_shader_parameter("lamp_pos", _v(data.lamp.pos))
	m.set_shader_parameter("lamp_ref", _v(data.lamp.pos).distance_to(_v(data.lamp.target)))
	m.set_shader_parameter("lamp_k", LAMP_K)
	m.set_shader_parameter("lamp_axis", (_v(data.lamp.target) - _v(data.lamp.pos)).normalized())
	match spec.kind:
		"noise":
			m.set_shader_parameter("kind", 1)
			m.set_shader_parameter("ramp", _ramp_texture(spec.stops))
			m.set_shader_parameter("map_scale", _v(spec.map))
			m.set_shader_parameter("noise_scale", float(spec.noise))
		"snow":
			m.set_shader_parameter("kind", 2)
			m.set_shader_parameter("color", _c(spec.color))
			m.set_shader_parameter("grain", 0.08)
		"strata":
			m.set_shader_parameter("kind", 3)
			m.set_shader_parameter("ramp", _ramp_texture(spec.stops))
			m.set_shader_parameter("strata_h", float(spec.h))
		"plain":
			m.set_shader_parameter("kind", 0)
			m.set_shader_parameter("color", _c(spec.color))
			if spec.get("emit") != null:
				var glass: bool = name.begins_with("glass")
				m.set_shader_parameter("kind", 4)
				m.set_shader_parameter("emission", _c(spec.emit))
				# Blender: windows at emission 3 (clipping to lamp-yellow), the forge fire at exactly its colour
				m.set_shader_parameter("emission_strength", 3.0 if glass else float(spec.strength))
		"unlit":
			var u := StandardMaterial3D.new()
			u.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			u.albedo_color = _c(spec.color)
			_materials[name] = u
			return u
	_materials[name] = m
	return m


func _dress(root: Node) -> void:
	for n in root.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		for i in mi.mesh.get_surface_count():
			var src := mi.mesh.surface_get_material(i)
			if src:
				mi.set_surface_override_material(i, _material(src.resource_name))


func _lamps() -> void:
	# the desk lamp: parallel light from the north-west, with shadows
	var sun := DirectionalLight3D.new()
	sun.name = "DeskLamp"
	add_child(sun)
	sun.look_at_from_position(_v(data.lamp.pos), _v(data.lamp.target), Vector3.UP)
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	sun.directional_shadow_max_distance = 140.0
	sun.shadow_bias = 0.03
	sun.shadow_normal_bias = 0.6
	sun.light_angular_distance = 0.6
	for l in data.lights:
		var o := OmniLight3D.new()
		o.position = _v(l.pos)
		o.light_color = _c(l.color)
		o.light_energy = 1.0
		o.omni_range = 0.45 * sqrt(float(l.watts))
		o.omni_attenuation = 1.4
		add_child(o)


func _camera() -> void:
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.keep_aspect = Camera3D.KEEP_WIDTH
	camera.size = float(data.camera.ortho)
	camera.far = 300.0
	add_child(camera)
	camera.look_at_from_position(_v(data.camera.pos), _v(data.camera.target), Vector3.UP)
	camera.current = true
	var quad := MeshInstance3D.new()
	var qm := QuadMesh.new()
	qm.size = Vector2(1, 1)
	quad.mesh = qm
	var om := ShaderMaterial.new()
	om.shader = OUTLINE
	om.render_priority = -100
	quad.material_override = om
	quad.extra_cull_margin = 16384.0
	quad.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	camera.add_child(quad)
	quad.position = Vector3(0, 0, -1)


func _person(who: String, p: Dictionary) -> void:
	var s := Sprite3D.new()
	s.texture = load("res://assets/sprites/%s.png" % who)
	var h: float = p.height
	s.pixel_size = h / s.texture.get_height()
	s.centered = true
	s.offset = Vector2(0, s.texture.get_height() / 2.0)
	s.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	s.shaded = false
	s.alpha_cut = SpriteBase3D.ALPHA_CUT_DISABLED
	s.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	s.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	s.position = _v(p.pos)
	s.name = who
	add_child(s)
	people[who] = s
	# a soft cold shadow on the ground beneath
	var d := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = 0.42
	cm.bottom_radius = 0.42
	cm.height = 0.004
	cm.radial_segments = 20
	cm.rings = 1
	d.mesh = cm
	d.scale = Vector3(1.2, 1, 0.85)
	d.material_override = _flat(Color("#1a2238", 0.45))
	d.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	s.add_child(d)
	d.position = Vector3(0, 0.03, 0)


## Unlit, and transparent so it draws after the outlines and carries none (smoke, glows, shadows).
func _flat(c: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.albedo_color = Color(c, min(c.a, 0.999))
	m.render_priority = -50
	return m


func _smoke(at: Vector3) -> void:
	var m := _flat(Color("#c3cad4"))
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(at)
	for i in 7:
		var u := i / 7.0
		var r := 0.09 + u * 0.2
		var b := MeshInstance3D.new()
		var sm := SphereMesh.new()
		sm.radius = r
		sm.height = r * 1.6
		sm.radial_segments = 12
		sm.rings = 6
		b.mesh = sm
		b.material_override = m
		b.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		# Blender: drift west (-x) and a little north (-z here), rising
		b.position = at + Vector3(-u * 0.9 + rng.randf_range(-0.04, 0.04), 0.08 + u * 1.15, -u * 0.2)
		add_child(b)


func _glow(g: Dictionary) -> void:
	var d := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = 1.0
	cm.bottom_radius = 1.0
	cm.height = 0.004
	cm.radial_segments = 10
	cm.rings = 1
	d.mesh = cm
	d.scale = Vector3(g.radii[0], 1, g.radii[1])
	d.rotation.y = -0.2
	d.position = _v(g.pos)
	d.material_override = _flat(_c(g.color))
	d.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(d)


## Where a point in the town falls on the 960x540 picture.
func to_screen(p: Vector3) -> Vector2:
	return camera.unproject_position(p)


func place(key: String) -> Vector3:
	return _v(data.places[key])


func anton_feet() -> Vector3:
	return people.anton.position


## The way from where Anton stands to a place, on the ground: out to the street, along it, and in (the landing and
## the ice by the dock; Věra's by the way across the ice the Blender walk draws).
func route_to(key: String, from: Vector3) -> PackedVector3Array:
	const STREET := -0.4      # Godot z of the middle of Front Street (Blender y 0.4)
	const BOARDWALK := 0.55   # in front of the doors
	var pts := PackedVector3Array([from, Vector3(from.x, 0.07, STREET)])
	match key:
		"dest":
			var taken: Array = data.routes.taken
			for i in range(4, taken.size()):
				pts.append(_v(taken[i]))
		"landing", "ice":
			pts.append(Vector3(0.8, 0.07, STREET))
			pts.append(Vector3(1.0, 0.2, -1.6))
			pts.append(Vector3(1.0, 0.2, -2.9))
			if key == "ice":
				pts.append(Vector3(1.4, 0.08, -3.6))
				pts.append(Vector3(3.9, 0.08, -4.1))
		_:
			var x := place(key).x
			pts.append(Vector3(x, 0.07, STREET))
			pts.append(Vector3(x, 0.16, BOARDWALK))
	return pts


# ------------------------------------------------------------------------------------------------ the town moves
## Where the townsfolk stand at each place, in the open street or out on the ice: by a wall the eaves hide a
## figure's head from the camera, and east of Maggie's the laid-up steamer hides the front of the street. Whoever is already at a place keeps their spot; a newcomer takes the first free
## one. A place with no spots (downriver, where Martha's people are building) is off the model.
const SPOTS := {
	"maggies": [Vector3(-6.1, 0.03, -0.25), Vector3(-7.9, 0.03, -0.3), Vector3(-7.0, 0.03, -1.1),
			Vector3(-8.8, 0.03, -1.1), Vector3(-9.6, 0.03, -0.3), Vector3(-4.6, 0.03, -0.3), Vector3(-10.4, 0.03, -1.1)],
	"store": [Vector3(1.1, 0.03, 0.4), Vector3(0.2, 0.03, -0.6), Vector3(1.9, 0.03, -0.6), Vector3(-0.6, 0.03, 0.4)],
	"landing": [Vector3(0.0, 0.03, -1.8), Vector3(2.0, 0.03, -1.8), Vector3(-1.0, 0.03, -1.2)],
	"ice": [Vector3(5.5, 0.06, -3.9), Vector3(4.3, 0.08, -4.1), Vector3(6.7, 0.06, -3.7)],
	"police": [Vector3(9.6, 0.03, 0.45), Vector3(8.4, 0.03, -0.3), Vector3(10.8, 0.03, -0.3)],
	"mission": [Vector3(15.1, 0.03, -0.3), Vector3(13.9, 0.03, -0.3), Vector3(14.5, 0.03, -1.1)],
	"vera": [Vector3(-2.55, 0.03, -7.15), Vector3(-1.6, 0.03, -6.6), Vector3(-1.5, 0.03, -7.5)],
	"your_cabin": [Vector3(-13.4, 0.03, -0.3), Vector3(-12.2, 0.03, -0.3)],
}
const STREET_Z := -0.4  ## Godot z of the middle of Front Street
const BANK_Z := -2.0  ## past this, the ice and the far side of it
const PACE := 0.22  ## seconds a metre, as Anton walks
const LONGEST := 4.0  ## seconds: a long way is walked faster

var _standing := {}  ## who -> [place, spot]
var _walks := {}  ## who -> Tween


## Put the townsfolk where the case says they are (`where`: who -> place). The first time they're simply there;
## after that each one who moved walks to the new place along the street, and over the landing to the ice.
func stand(where: Dictionary) -> void:
	var first := _standing.is_empty()
	var taken := {}
	for who in _standing:  # those who stay where they were keep their spots
		if where.get(who, "") == _standing[who][0]:
			taken["%s/%d" % _standing[who]] = true
	for who in where:
		if who not in people or who == "anton":
			continue
		var at: String = where[who]
		if _standing.has(who) and _standing[who][0] == at:
			continue
		var spots: Array = SPOTS.get(at, [])
		var i := 0
		while taken.has("%s/%d" % [at, i]):
			i += 1
		taken["%s/%d" % [at, i]] = true
		_standing[who] = [at, i]
		var s: Sprite3D = people[who]
		if spots.is_empty():
			_fade(who, false, first)
			continue
		var to: Vector3 = spots[i] if i < spots.size() else spots[-1] + Vector3(0.9 * (i - spots.size() + 1), 0, 0)
		if first or not s.visible:
			s.position = to
			_fade(who, true, first)
		else:
			_walk(who, to)


func _walk(who: String, to: Vector3) -> void:
	var s: Sprite3D = people[who]
	if _walks.has(who):  # still walking, or still coming into sight: carry on from here, in full view
		_walks[who].kill()
	s.modulate.a = 1.0
	var curve := Curve3D.new()
	curve.bake_interval = 0.05
	var pts := _way(s.position, to)
	for i in pts.size():
		var t := (pts[min(i + 1, pts.size() - 1)] - pts[max(i - 1, 0)]) / 6.0
		curve.add_point(pts[i], -t, t)
	var length := curve.get_baked_length()
	var tw := create_tween()
	tw.tween_method(func(d: float): s.position = curve.sample_baked(d), 0.0, length, min(length * PACE, LONGEST))
	_walks[who] = tw


## The way between two spots on the ground: out to the street and along it, and down the landing to the ice.
func _way(a: Vector3, b: Vector3) -> PackedVector3Array:
	var pts := PackedVector3Array([a])
	var a_ice := a.z < BANK_Z
	var b_ice := b.z < BANK_Z
	if not a_ice:
		pts.append(Vector3(a.x, 0.07, STREET_Z))
	if a_ice != b_ice:  # by the landing, down to the ice or up from it
		var down := [Vector3(1.0, 0.07, STREET_Z), Vector3(1.0, 0.2, -1.6), Vector3(1.0, 0.2, -2.9)]
		if a_ice:
			down.reverse()
		for p in down:
			pts.append(p)
	if not b_ice:
		pts.append(Vector3(b.x, 0.07, STREET_Z))
	pts.append(b)
	return pts


## Come into sight or go out of it: off the model, or back from there.
func _fade(who: String, show: bool, at_once: bool) -> void:
	var s: Sprite3D = people[who]
	if _walks.has(who):
		_walks[who].kill()
		_walks.erase(who)
	if at_once:
		s.visible = show
		s.modulate.a = 1.0
		return
	if show:
		s.modulate.a = 0.0
		s.visible = true
	var tw := create_tween()
	tw.tween_property(s, "modulate:a", 1.0 if show else 0.0, 0.6)
	if not show:
		tw.tween_callback(func(): s.visible = false)
	_walks[who] = tw
