// The town's one material: the Blender look, live. The desk lamp's light is cut into bands (cold blue shadow up to
// warm lamplight) and multiplied by the surface colour; the surface colour is a noise ramp in object space, as the
// Blender materials are, so wood, ice and walnut keep their grain. Local lamps add a warm band of their own.
shader_type spatial;
render_mode diffuse_lambert, specular_disabled, ambient_light_disabled;

const int PLAIN = 0;
const int NOISE = 1;
const int SNOW = 2;
const int STRATA = 3;
const int EMISSIVE = 4;

uniform int kind = 0;
uniform vec3 color : source_color = vec3(0.8);
uniform sampler2D ramp : source_color, filter_linear, repeat_disable;
uniform vec3 map_scale = vec3(1.0);   // the Blender mapping scale, in Blender's axes
uniform float noise_scale = 4.0;
uniform float strata_h = 4.6;
uniform float grain = 0.12;           // how much the noise shakes the light (the Blender bump)
uniform vec3 emission : source_color = vec3(0.0);
uniform float emission_strength = 0.0;

// the bands, shared by every material
uniform sampler2D bands : source_color, filter_nearest, repeat_disable;
uniform float band_top = 0.72;        // the ramp's top in light units (1.6 x band scale in Blender)
uniform float lamp_k = 1.0;           // desk lamp light to Blender light units
uniform float omni_k = 1.0;
uniform vec3 omni_warm : source_color = vec3(1.0, 0.86, 0.62);
// the desk lamp is a lamp, not the sun: its light falls off with distance (Blender's spot, by inverse square)
uniform vec3 lamp_pos = vec3(-24.0, 34.0, -18.0);
uniform float lamp_ref = 45.3;          // distance at which lamp_k holds
uniform vec3 lamp_axis = vec3(0.52, -0.76, 0.39);  // where the lamp points
uniform float cone_cos = 0.857;         // cos of half the 62 degree cone
uniform float cone_blend = 0.6;         // Blender's spot blend: the soft part of the cone

varying vec3 obj;

// The browser's renderer (Compatibility) hands these generated gradients back as stored, in sRGB, where Forward+
// hands them back linear: the same colour either way.
vec3 lin(vec3 c) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
#else
	return c;
#endif
}

varying vec3 world;
varying float shake;

vec3 hash3(vec3 p) {
	p = vec3(dot(p, vec3(127.1, 311.7, 74.7)), dot(p, vec3(269.5, 183.3, 246.1)), dot(p, vec3(113.5, 271.9, 124.6)));
	return -1.0 + 2.0 * fract(sin(p) * 43758.5453123);
}

float gnoise(vec3 p) {
	vec3 i = floor(p);
	vec3 f = fract(p);
	vec3 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(dot(hash3(i + vec3(0, 0, 0)), f - vec3(0, 0, 0)), dot(hash3(i + vec3(1, 0, 0)), f - vec3(1, 0, 0)), u.x),
	               mix(dot(hash3(i + vec3(0, 1, 0)), f - vec3(0, 1, 0)), dot(hash3(i + vec3(1, 1, 0)), f - vec3(1, 1, 0)), u.x), u.y),
	           mix(mix(dot(hash3(i + vec3(0, 0, 1)), f - vec3(0, 0, 1)), dot(hash3(i + vec3(1, 0, 1)), f - vec3(1, 0, 1)), u.x),
	               mix(dot(hash3(i + vec3(0, 1, 1)), f - vec3(0, 1, 1)), dot(hash3(i + vec3(1, 1, 1)), f - vec3(1, 1, 1)), u.x), u.y), u.z);
}

// Blender's Noise texture, near enough: fractal gradient noise, 0.5 in the middle
float fbm(vec3 p, int octaves) {
	float s = 0.0;
	float a = 0.5;
	float n = 0.0;
	for (int k = 0; k < octaves; k++) {
		s += a * gnoise(p);
		n += a;
		p *= 2.0;
		a *= 0.5;
	}
	return 0.5 + 0.75 * s / n;
}

void vertex() {
	// Blender's object coordinates: Godot (x, y, z) is Blender (x, -z, y)
	obj = vec3(VERTEX.x, -VERTEX.z, VERTEX.y);
	world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec3 c = color;
	float n = 0.5;
	if (kind == NOISE) {
		n = fbm(obj * map_scale * noise_scale, 5);
		c = texture(ramp, vec2(clamp(n, 0.0, 1.0), 0.0)).rgb;
	} else if (kind == STRATA) {
		float f = obj.z / strata_h + 0.5 + 0.08 * fbm(obj * 3.0, 4);
		c = texture(ramp, vec2(clamp(f, 0.0, 1.0), 0.0)).rgb;
		n = fbm(obj * 14.0, 2);
	} else if (kind == SNOW) {
		n = fbm(obj * 45.0, 3);
	}
	vec3 to = world - lamp_pos;
	float d = lamp_ref / length(to);
	float cone = smoothstep(0.0, 1.0, (dot(normalize(to), lamp_axis) - cone_cos) / ((1.0 - cone_cos) * cone_blend));
	shake = (1.0 + grain * (n - 0.5) * 2.0) * d * d * cone;
	if (kind == EMISSIVE) {
		ALBEDO = vec3(0.0);
		EMISSION = lin(emission) * emission_strength;
	} else {
		ALBEDO = c;
		EMISSION = lin(emission) * emission_strength;
	}
}

void light() {
	float ndl = max(dot(NORMAL, LIGHT), 0.0);
	float e = ndl * ATTENUATION;
	if (LIGHT_IS_DIRECTIONAL) {
		// the desk lamp: the whole ramp, shadow colour included, comes from it
		float f = e * lamp_k * shake;
		DIFFUSE_LIGHT += lin(texture(bands, vec2(clamp(f / band_top, 0.0, 0.999), 0.5)).rgb);
	} else {
		// window spill, lanterns, the forge: a warm band, stepped
		float f = e * omni_k * dot(LIGHT_COLOR, vec3(0.333));
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
		f /= PI;  // its local lights arrive a factor of pi stronger than Forward+'s
#endif
		float b = f > 0.6 ? 0.55 : (f > 0.2 ? 0.3 : (f > 0.05 ? 0.12 : 0.0));
		DIFFUSE_LIGHT += b * lin(omni_warm);
	}
}
