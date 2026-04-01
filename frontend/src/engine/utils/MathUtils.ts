/**
 * Math utilities — easing, noise, layout helpers.
 * No external dependencies.
 */

// ─── Easing Functions ───────────────────────────────

export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

export function easeInOutCubic(t: number): number {
  return t < 0.5
    ? 4 * t * t * t
    : 1 - Math.pow(-2 * t + 2, 3) / 2
}

export function easeOutQuad(t: number): number {
  return 1 - (1 - t) * (1 - t)
}

// ─── Hashing ────────────────────────────────────────

/** Simple deterministic string hash → positive integer */
export function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

// ─── Noise ──────────────────────────────────────────

/** Simple 2D simplex-ish noise for procedural placement */
export function simplexNoise2D(x: number, y: number): number {
  const dot = x * 12.9898 + y * 78.233
  const s = Math.sin(dot) * 43758.5453
  return s - Math.floor(s)
}

// ─── Range Utilities ────────────────────────────────

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function randRange(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

// ─── Exclusion Zone Check ──────────────────────────

export interface ExclusionZone {
  x: number
  z: number
  radius: number
}

/** Check if a point is inside any circular exclusion zone. */
export function isInsideAnyZone(px: number, pz: number, zones: readonly ExclusionZone[]): boolean {
  for (const zone of zones) {
    const dx = px - zone.x
    const dz = pz - zone.z
    if (dx * dx + dz * dz < zone.radius * zone.radius) return true
  }
  return false
}

// ─── Layout ─────────────────────────────────────────

/** Compute grid position for index i in a grid with given columns and spacing. */
export function gridPosition(
  i: number,
  cols: number,
  spacingX: number,
  spacingZ: number,
): { x: number; z: number } {
  const row = Math.floor(i / cols)
  const col = i % cols
  const totalWidth = (cols - 1) * spacingX
  const x = col * spacingX - totalWidth / 2
  const z = row * spacingZ
  return { x, z }
}
