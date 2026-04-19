// Ground plane vertex shader — stub for Phase 2
attribute vec3 vertex_position;
attribute vec2 vertex_texCoord0;

uniform mat4 matrix_model;
uniform mat4 matrix_viewProjection;

varying vec2 vUv;

void main() {
    vUv = vertex_texCoord0;
    gl_Position = matrix_viewProjection * matrix_model * vec4(vertex_position, 1.0);
}
