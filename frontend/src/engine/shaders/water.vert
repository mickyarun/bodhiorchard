// Water surface vertex shader — dual sine wave displacement
attribute vec3 vertex_position;
attribute vec2 vertex_texCoord0;

uniform mat4 matrix_model;
uniform mat4 matrix_viewProjection;
uniform float uTime;
uniform float uAmplitude;
uniform float uFrequency;

varying vec2 vUv;
varying float vWaveHeight;

void main() {
    vUv = vertex_texCoord0;

    vec3 pos = vertex_position;

    // Dual sine wave Y displacement
    float wave1 = sin(pos.x * uFrequency + uTime * 1.5) * uAmplitude;
    float wave2 = sin(pos.z * uFrequency * 0.7 + uTime * 1.1) * uAmplitude * 0.6;
    pos.y += wave1 + wave2;

    vWaveHeight = (wave1 + wave2) / (uAmplitude * 1.6);

    gl_Position = matrix_viewProjection * matrix_model * vec4(pos, 1.0);
}
