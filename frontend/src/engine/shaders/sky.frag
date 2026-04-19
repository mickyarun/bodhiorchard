// Sky sphere fragment shader — bright gradient + sun disc
precision mediump float;

uniform float uTime;
uniform vec3 uSunPosition;

varying vec2 vUv;
varying vec3 vWorldPosition;

void main() {
    // Normalized direction from sphere center
    vec3 dir = normalize(vWorldPosition);
    float height = dir.y;

    // Bright sky gradient
    vec3 horizonColor = vec3(0.82, 0.88, 0.96);
    vec3 zenithColor = vec3(0.40, 0.60, 0.92);
    vec3 color = mix(horizonColor, zenithColor, clamp(height, 0.0, 1.0));

    // Below-horizon fade to ground color
    if (height < 0.0) {
        vec3 groundColor = vec3(0.35, 0.55, 0.30);
        color = mix(color, groundColor, clamp(-height * 3.0, 0.0, 1.0));
    }

    // Sun disc + halo
    vec3 sunDir = normalize(uSunPosition);
    float sunDot = max(dot(dir, sunDir), 0.0);
    color += vec3(1.0, 0.95, 0.85) * pow(sunDot, 128.0) * 1.5;  // hard disc
    color += vec3(1.0, 0.92, 0.75) * pow(sunDot, 8.0) * 0.2;    // soft halo

    gl_FragColor = vec4(color, 1.0);
}
