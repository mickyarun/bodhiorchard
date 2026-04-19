// Ground plane fragment shader — stub for Phase 2
precision mediump float;

varying vec2 vUv;

void main() {
    // Simple grass/dirt blend - will be expanded in Phase 2
    vec3 grassColor = vec3(0.28, 0.55, 0.2);
    vec3 dirtColor = vec3(0.45, 0.35, 0.2);

    // Basic noise blend
    float n = fract(sin(dot(vUv * 50.0, vec2(12.9898, 78.233))) * 43758.5453);
    float blend = smoothstep(0.4, 0.6, n);
    vec3 color = mix(grassColor, dirtColor, blend * 0.3);

    gl_FragColor = vec4(color, 1.0);
}
