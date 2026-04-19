// Water surface fragment shader — translucent blue-teal + caustic shimmer
precision highp float;

uniform float uTime;

varying vec2 vUv;
varying float vWaveHeight;

// Caustic shimmer pattern
float caustic(vec2 uv, float t) {
    vec2 p = uv * 8.0;
    float c = 0.0;
    c += sin(p.x * 3.1 + t * 1.3) * 0.15;
    c += sin(p.y * 2.7 + t * 0.9) * 0.15;
    c += sin((p.x + p.y) * 2.3 + t * 1.7) * 0.1;
    return c;
}

void main() {
    // Base water color: blue-teal gradient (brightened)
    vec3 shallowColor = vec3(0.3, 0.75, 0.8);
    vec3 deepColor = vec3(0.1, 0.4, 0.6);
    vec3 baseColor = mix(deepColor, shallowColor, vWaveHeight * 0.5 + 0.5);

    // Caustic shimmer
    float c = caustic(vUv, uTime);
    baseColor += vec3(c * 0.3, c * 0.35, c * 0.2);

    // Foam at wave peaks
    float foam = smoothstep(0.5, 0.9, vWaveHeight);
    baseColor = mix(baseColor, vec3(0.9, 0.95, 1.0), foam * 0.3);

    // Transparency: deeper = more opaque (slightly more visible)
    float alpha = mix(0.55, 0.8, 1.0 - vWaveHeight * 0.5);

    gl_FragColor = vec4(baseColor, alpha);
}
