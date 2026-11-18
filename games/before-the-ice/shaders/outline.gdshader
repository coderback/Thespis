// One-pixel ink outlines, as Freestyle draws them in the Blender renders: on silhouettes (a step in depth) and on
// creases (a turn in the surface), drawn on the nearer side so the line belongs to the object in front.
// A full-screen quad on the camera; sprites and smoke are transparent, so they draw after it and carry no line.
// The browser's renderer (Compatibility) has no normal buffer, so there the surface's facing is worked out from the
// depth of the pixels around it, and its depth runs -1 to 1 rather than 0 to 1.
shader_type spatial;
render_mode unshaded, depth_test_disabled, depth_draw_never, cull_disabled, blend_mix, fog_disabled;

uniform sampler2D depth_tex : hint_depth_texture, filter_nearest;
#if CURRENT_RENDERER != RENDERER_COMPATIBILITY
uniform sampler2D normal_tex : hint_normal_roughness_texture, filter_nearest;
#endif
uniform vec3 ink : source_color = vec3(0.102, 0.071, 0.047);
uniform float depth_step = 0.35;   // world units: a gap this big in depth is a silhouette
uniform float crease = 0.72;       // cosine: surfaces turning more sharply than this get a line

void vertex() {
	POSITION = vec4(VERTEX.xy * 2.0, 1.0, 1.0);
}

vec3 view_pos(vec2 uv, mat4 inv_proj) {
	float d = texture(depth_tex, uv).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	d = d * 2.0 - 1.0;
#endif
	vec4 v = inv_proj * vec4(uv * 2.0 - 1.0, d, 1.0);
	return v.xyz / v.w;
}

float view_z(vec2 uv, mat4 inv_proj) {
	return -view_pos(uv, inv_proj).z;
}

vec3 view_n(vec2 uv, mat4 inv_proj, vec2 px) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	// the facing from the depth around: of the two neighbours on each axis, the one on the same surface (nearer in
	// depth), so a silhouette doesn't bend the normal
	vec3 p = view_pos(uv, inv_proj);
	vec3 r = view_pos(uv + vec2(px.x, 0.0), inv_proj) - p;
	vec3 l = p - view_pos(uv - vec2(px.x, 0.0), inv_proj);
	vec3 u = view_pos(uv + vec2(0.0, px.y), inv_proj) - p;
	vec3 d = p - view_pos(uv - vec2(0.0, px.y), inv_proj);
	vec3 dx = abs(r.z) < abs(l.z) ? r : l;
	vec3 dy = abs(u.z) < abs(d.z) ? u : d;
	return normalize(cross(dy, dx));
#else
	return normalize(texture(normal_tex, uv).xyz * 2.0 - 1.0);
#endif
}

void fragment() {
	vec2 px = 1.0 / VIEWPORT_SIZE;
	float z = view_z(SCREEN_UV, INV_PROJECTION_MATRIX);
	vec3 nrm = view_n(SCREEN_UV, INV_PROJECTION_MATRIX, px);
	float edge = 0.0;
	vec2 dirs[4] = vec2[](vec2(1, 0), vec2(-1, 0), vec2(0, 1), vec2(0, -1));
	for (int k = 0; k < 4; k++) {
		vec2 uv = SCREEN_UV + dirs[k] * px;
		float zn = view_z(uv, INV_PROJECTION_MATRIX);
		// silhouette: the neighbour is well behind me
		if (zn - z > depth_step) {
			edge = 1.0;
		}
		// crease: same depth, sharply different facing; only one side draws it
		if (k < 2 && abs(zn - z) < depth_step && dot(nrm, view_n(uv, INV_PROJECTION_MATRIX, px)) < crease && dirs[k].x > 0.0) {
			edge = 1.0;
		}
		if (k >= 2 && abs(zn - z) < depth_step && dot(nrm, view_n(uv, INV_PROJECTION_MATRIX, px)) < crease && dirs[k].y > 0.0) {
			edge = 1.0;
		}
	}
	ALBEDO = ink;
	ALPHA = edge;
}
