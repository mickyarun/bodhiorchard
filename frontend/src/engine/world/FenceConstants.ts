/**
 * FenceConstants — shared dimensions for all fence types.
 *
 * Single source of truth consumed by:
 *   - CircularFence.ts (zone property fences + outer perimeter rail)
 *   - RectangularFence.ts (housing village compound)
 *   - TakeoverPhysicsBuilder.ts (physics collider rings for fences)
 */

// ─── Solid-fence dimensions (zone boundaries + housing compound) ─────────────

export const POST_HEIGHT     = 1.10
export const POST_WIDTH      = 0.10
export const PANEL_HEIGHT    = 0.85
export const PANEL_THICKNESS = 0.07

export const GATE_POST_W = 0.16
export const GATE_POST_H = 1.28
export const GATE_WIDTH  = 3.0   // gap width for gate openings

/** Arc length per segment for solid fences (dense post spacing). */
export const SOLID_SEGMENT_WIDTH = 0.95

// ─── Rail-fence dimensions (outer campus perimeter) ──────────────────────────

export const RAIL_POST_HEIGHT  = 1.00
export const RAIL_POST_WIDTH   = 0.12
export const RAIL_THICKNESS    = 0.06
/** Two horizontal rails at 30% and 78% of post height. */
export const RAIL_Y_FRACTIONS  = [0.30, 0.78] as const

/** Arc length per segment for rail fences (wide, open spacing). */
export const RAIL_SEGMENT_WIDTH = 4.0
