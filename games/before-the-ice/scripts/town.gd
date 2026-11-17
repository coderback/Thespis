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
