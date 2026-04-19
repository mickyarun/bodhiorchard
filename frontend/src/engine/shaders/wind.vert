// Wind vertex displacement — stub for Phase 2 grass system
// Will be injected into grass blade vertex shader

// Shared wind function for grass and foliage
// vec3 applyWind(vec3 position, float time, float strength) {
//     float windX = sin(position.x * 0.5 + time * 2.0) * strength;
//     float windZ = cos(position.z * 0.3 + time * 1.5) * strength * 0.5;
//     // Only sway at the tip (y > 0.5)
//     float factor = smoothstep(0.0, 1.0, position.y);
//     return position + vec3(windX, 0.0, windZ) * factor;
// }
