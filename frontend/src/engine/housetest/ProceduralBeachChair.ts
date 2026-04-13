/**
 * ProceduralBeachChair — low-poly folding beach/deck chair from primitives.
 *
 * Built from PlayCanvas box primitives so there are zero GLB compatibility
 * issues. The seat height is a compile-time constant — no SeatProber needed.
 *
 * Side view:
 *        ╱│  backrest (angled)
 *       ╱ │
 *      ╱──┤  seat surface (flat) → SEAT_HEIGHT
 *     │   │
 *     ┴   ┴  legs
 *   ──────── ground
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'

// ─── Dimensions (world units) ───────────────────────────────────────────────
// Elongated seat makes it look like a pool sun lounger, not a dining chair.
const WIDTH = 0.5
const SEAT_DEPTH = 0.9     // doubled for lounger proportions
const SEAT_THICK = 0.03
const LEG_THICK = 0.025
const BACK_HEIGHT = 0.3
const BACK_ANGLE = 55  // degrees from horizontal (more reclined)

/** Known seat surface Y — use this for InteractionPoint.y */
export const SEAT_HEIGHT = 0.25

// ─── Fabric colors — one per chair instance ─────────────────────────────────
const FABRIC_COLORS: Array<[number, number, number]> = [
  [0.9, 0.25, 0.2],   // red
  [0.2, 0.55, 0.9],   // blue
  [0.3, 0.8, 0.35],   // green
  [0.95, 0.8, 0.2],   // yellow
  [0.85, 0.45, 0.1],  // orange
  [0.7, 0.3, 0.8],    // purple
]

let colorIndex = 0

/**
 * Build a single procedural beach chair entity.
 *
 * The entity's local origin is at the center-bottom of the chair
 * (feet on ground, center of seat width). Caller places it with
 * `setLocalPosition(x, 0, z)` and rotates with `setLocalEulerAngles(0, yaw, 0)`.
 *
 * @param materials MaterialFactory for PBR-correct colors (uses `getColor`)
 */
export function buildBeachChair(materials: MaterialFactory): pc.Entity {
  const root = new pc.Entity('BeachChair')

  // Pick a fabric color (cycles through the palette)
  const [fr, fg, fb] = FABRIC_COLORS[colorIndex % FABRIC_COLORS.length]!
  colorIndex++

  const wood = materials.getColor('beach_wood', 0.55, 0.35, 0.2, { metalness: 0, gloss: 0.2 })
  const fabric = materials.getColor(`beach_fabric_${colorIndex}`, fr, fg, fb, { metalness: 0, gloss: 0.1 })

  const hw = WIDTH / 2  // half width

  // ─── 4 Legs ───────────────────────────────────────────────────────────────
  const legPositions = [
    { x: -hw + LEG_THICK, z: -SEAT_DEPTH / 2 + LEG_THICK },   // front-left
    { x:  hw - LEG_THICK, z: -SEAT_DEPTH / 2 + LEG_THICK },   // front-right
    { x: -hw + LEG_THICK, z:  SEAT_DEPTH / 2 - LEG_THICK },   // back-left
    { x:  hw - LEG_THICK, z:  SEAT_DEPTH / 2 - LEG_THICK },   // back-right
  ]

  for (const lp of legPositions) {
    const leg = new pc.Entity('Leg')
    leg.addComponent('render', { type: 'box' })
    leg.setLocalScale(LEG_THICK, SEAT_HEIGHT, LEG_THICK)
    leg.setLocalPosition(lp.x, SEAT_HEIGHT / 2, lp.z)
    leg.render!.meshInstances[0].material = wood
    leg.render!.castShadows = true
    root.addChild(leg)
  }

  // ─── Seat surface ─────────────────────────────────────────────────────────
  const seat = new pc.Entity('Seat')
  seat.addComponent('render', { type: 'box' })
  seat.setLocalScale(WIDTH, SEAT_THICK, SEAT_DEPTH)
  seat.setLocalPosition(0, SEAT_HEIGHT, 0)
  seat.render!.meshInstances[0].material = fabric
  seat.render!.castShadows = true
  root.addChild(seat)

  // ─── Backrest (angled, at -Z = behind the sitter) ─────────────────────────
  // The sitter faces +Z (toward the pool when yaw points at it).
  // The backrest goes at -Z so it's behind them.
  const back = new pc.Entity('Backrest')
  back.addComponent('render', { type: 'box' })
  back.setLocalScale(WIDTH, BACK_HEIGHT, SEAT_THICK)
  const backRad = BACK_ANGLE * Math.PI / 180
  const backCenterY = SEAT_HEIGHT + Math.sin(backRad) * BACK_HEIGHT / 2
  const backCenterZ = -SEAT_DEPTH / 2 + Math.cos(backRad) * BACK_HEIGHT / 2
  back.setLocalPosition(0, backCenterY, backCenterZ)
  back.setLocalEulerAngles(-(BACK_ANGLE - 90), 0, 0)
  back.render!.meshInstances[0].material = fabric
  back.render!.castShadows = true
  root.addChild(back)

  // ─── Armrests (thin wood bars on each side) ───────────────────────────────
  for (const side of [-1, 1]) {
    const arm = new pc.Entity('Armrest')
    arm.addComponent('render', { type: 'box' })
    arm.setLocalScale(LEG_THICK, LEG_THICK, SEAT_DEPTH * 0.7)
    arm.setLocalPosition(side * hw, SEAT_HEIGHT + 0.08, 0)
    arm.render!.meshInstances[0].material = wood
    arm.render!.castShadows = true
    root.addChild(arm)
  }

  return root
}
