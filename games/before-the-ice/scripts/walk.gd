## Anton's walk: pick a place, and he goes there along the ground in a few seconds. The way is drawn in red on the
## model, solid behind him and dashed ahead (the design: "movement is by choosing, not steering").
class_name Walk
extends Node3D

signal arrived(place: String)

const SECONDS_PER_METRE := 0.22
const WIDTH := 0.2
const DASH := 0.32

var walker: Node3D
var curve := Curve3D.new()
var travelled := 0.0
var place := ""
var walking := false

var _done := MeshInstance3D.new()
var _ahead := MeshInstance3D.new()
var _red: StandardMaterial3D


func _ready() -> void:
	_red = StandardMaterial3D.new()
	_red.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_red.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_red.albedo_color = Color("#c0262b", 0.999)
	_red.render_priority = -40
	_red.cull_mode = BaseMaterial3D.CULL_DISABLED
	for m in [_done, _ahead]:
		m.material_override = _red
		m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(m)


## Walk `walker` along `points` (on the ground) to `to`.
func go(to: String, points: PackedVector3Array) -> void:
	curve = Curve3D.new()
	curve.bake_interval = 0.05
	for i in points.size():
		var p := points[i]
		# Catmull-Rom handles, so the way bends the way a person walks it
		var prev := points[max(i - 1, 0)]
		var next := points[min(i + 1, points.size() - 1)]
		var t := (next - prev) / 6.0
		curve.add_point(p, -t, t)
	travelled = 0.0
	place = to
	walking = true


func skip() -> void:
	travelled = curve.get_baked_length()


func _process(delta: float) -> void:
	if not walking:
		return
	var total := curve.get_baked_length()
	travelled = min(travelled + delta / SECONDS_PER_METRE, total)
	walker.position = curve.sample_baked(travelled)
	_done.mesh = _ribbon(0.0, travelled, 0.0)
	_ahead.mesh = _ribbon(travelled + 0.15, total, DASH)
	if travelled >= total:
		walking = false
		arrived.emit(place)


## A flat red band along the way from `a` to `b` metres; dashed when `dash` > 0.
func _ribbon(a: float, b: float, dash: float) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var step := 0.08
	var s := a
	var any := false
	while s < b - 0.001:
		var e: float = min(s + step, b)
		if dash > 0.0 and fmod(s - a, dash * 2.0) > dash:
			s = e
			continue
		var p0 := curve.sample_baked(s) + Vector3(0, 0.02, 0)
		var p1 := curve.sample_baked(e) + Vector3(0, 0.02, 0)
		var dir := (p1 - p0).normalized()
		var side := dir.cross(Vector3.UP).normalized() * WIDTH * 0.5
		st.add_vertex(p0 - side)
		st.add_vertex(p0 + side)
		st.add_vertex(p1 + side)
		st.add_vertex(p0 - side)
		st.add_vertex(p1 + side)
		st.add_vertex(p1 - side)
		any = true
		s = e
	if not any:
		return ArrayMesh.new()
	return st.commit()
