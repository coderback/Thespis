// The town behind a conversation, as the canvas draws it: zoomed in on the place, darkened, washed out and softly
// blurred, so the paper in front reads. `amount` runs 0 (the town as it is) to 1 (behind a conversation).
shader_type canvas_item;

uniform float amount : hint_range(0.0, 1.0) = 0.0;
uniform vec2 center = vec2(0.34, 0.42);  // where on the picture to zoom in, 0 to 1
uniform float zoom = 2.3;
uniform float brightness = 0.4;
uniform float saturation = 0.6;
uniform float blur = 2.0;  // in pixels of the 960x540 picture

void fragment() {
	float z = mix(1.0, zoom, amount);
	vec2 uv = center + (UV - center) / z;
	vec2 px = TEXTURE_PIXEL_SIZE * blur * amount;
	vec4 c = vec4(0.0);
	for (int x = -1; x <= 1; x++) {
		for (int y = -1; y <= 1; y++) {
			c += texture(TEXTURE, uv + vec2(float(x), float(y)) * px);
		}
	}
	c /= 9.0;
	float grey = dot(c.rgb, vec3(0.299, 0.587, 0.114));
	c.rgb = mix(vec3(grey), c.rgb, mix(1.0, saturation, amount)) * mix(1.0, brightness, amount);
	COLOR = vec4(c.rgb, 1.0);
}
