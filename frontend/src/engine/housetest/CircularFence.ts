/**
 * CircularFence — procedural wooden fence ring for the exterior scene.
 *
 * Arranges box-primitive posts + tangential rail panels around a circle.
 * A gate opening is cut at a given angle, with taller gate pillars marking
 * each side of the gap.
 *
 * Coordinate convention (PlayCanvas / housetest XZ plane):
 *   angle = 0   →  point at (cx, cz + radius)  = front (+Z from center)
 *   angle = π   →  back  (-Z from center)
 *   angle = π/2 →  right (+X from center)
 *
 * Placement formula:
 *   px = Math.sin(angle) * radius
 *   pz = Math.cos(angle) * radius
 *
 * Panel rotation: each panel's local X axis lies along the tangent to the
 * circle, so setLocalEulerAngles(0, angle * RAD2DEG, 0) makes it face
 * perpendicular to the radius — no lookAt, no quaternion math required.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'

// ─── Fence geometry constants ────────────────────────────────────────────────

/** Post pillar dimensions. Box pivot is at center → lift by half height. */
const POST_HEIGHT     = 1.10
const POST_WIDTH      = 0.10

/** Solid rail panel height and depth (thickness). Width = arc length per segment. */
const PANEL_HEIGHT    = 0.85
const PANEL_THICKNESS = 0.07

/** Gate pillars: visibly thicker and taller than regular posts. */
const GATE_POST_W = 0.16
const GATE_POST_H = 1.28

/** Target arc length per segment — controls visual density of the fence. */
const TARGET_PANEL_WIDTH = 0.95

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CircularFenceOptions {
  /** Radius of the fence ring in world units. */
  radius: number
  /** World-space X of the ring center. */
  cx: number
  /** World-space Z of the ring center. */
  cz: number
  /**
   * Angle (radians) at the center of the gate gap.
   * angle=0 → +Z from center (front, toward player spawn).
   * Compute exact alignment: Math.asin((pathX - cx) / radius)
   */
  gateAngle: number
  /** World-space width of the gate opening (default 1.6). */
  gateWidth?: number
}

// ─── CircularFence ───────────────────────────────────────────────────────────

export class CircularFence {
  private materials: MaterialFactory

  constructor(materials: MaterialFactory) {
    this.materials = materials
  }

  /**
   * Build the fence ring as children of `parent`.
   * The root entity is positioned at (cx, 0, cz); all posts/panels are
   * in local space relative to that root — matching the BuildingFactory pattern.
   */
  build(parent: pc.Entity, opts: CircularFenceOptions): pc.Entity {
    const { radius, cx, cz, gateAngle, gateWidth = 1.6 } = opts

    const postMat     = this.materials.getColor('fence_post',  0.55, 0.40, 0.24)
    const panelMat    = this.materials.getColor('fence_panel', 0.64, 0.50, 0.30)
    const gatePostMat = this.materials.getColor('fence_gate',  0.42, 0.30, 0.16)

    // ── Segment count: scale with circumference so panel width stays near target
    const segmentCount = Math.max(16, Math.round((2 * Math.PI * radius) / TARGET_PANEL_WIDTH))
    const angleStep    = (2 * Math.PI) / segmentCount
    const panelWidth   = (2 * Math.PI * radius) / segmentCount   // actual arc width
    const gateHalfArc  = (gateWidth / radius) / 2                // radians to skip each side

    const root = new pc.Entity('CircularFence')
    root.setLocalPosition(cx, 0, cz)
    parent.addChild(root)

    for (let i = 0; i < segmentCount; i++) {
      const angle = i * angleStep

      // Skip segments inside the gate arc
      if (Math.abs(this._normalizeAngle(angle - gateAngle)) < gateHalfArc) continue

      // Position on ring (local to root, which sits at cx/cz)
      const px  = Math.sin(angle) * radius
      const pz  = Math.cos(angle) * radius
      // Tangent yaw: panel local-X aligns along the circle tangent
      const yaw = angle * (180 / Math.PI)

      // ── Post: square pillar, lifted so bottom sits on y=0 ──
      const post = new pc.Entity('Post')
      post.addComponent('render', { type: 'box' })
      post.setLocalScale(POST_WIDTH, POST_HEIGHT, POST_WIDTH)
      post.setLocalPosition(px, POST_HEIGHT / 2, pz)
      post.render!.meshInstances[0].material = postMat
      root.addChild(post)

      // ── Panel: flat plank tangent to the circle ──
      const panel = new pc.Entity('Panel')
      panel.addComponent('render', { type: 'box' })
      panel.setLocalScale(panelWidth, PANEL_HEIGHT, PANEL_THICKNESS)
      panel.setLocalPosition(px, PANEL_HEIGHT / 2, pz)
      panel.setLocalEulerAngles(0, yaw, 0)
      panel.render!.meshInstances[0].material = panelMat
      root.addChild(panel)
    }

    // ── Gate pillars: one on each side of the opening ──
    for (const side of [-1, 1] as const) {
      const gatePostAngle = gateAngle + side * gateHalfArc
      const gpx = Math.sin(gatePostAngle) * radius
      const gpz = Math.cos(gatePostAngle) * radius

      const gatePost = new pc.Entity('GatePost')
      gatePost.addComponent('render', { type: 'box' })
      gatePost.setLocalScale(GATE_POST_W, GATE_POST_H, GATE_POST_W)
      gatePost.setLocalPosition(gpx, GATE_POST_H / 2, gpz)
      gatePost.render!.meshInstances[0].material = gatePostMat
      root.addChild(gatePost)
    }

    return root
  }

  /** Normalize an angle to the range [-π, π]. */
  private _normalizeAngle(angle: number): number {
    let a = angle
    while (a >  Math.PI) a -= 2 * Math.PI
    while (a < -Math.PI) a += 2 * Math.PI
    return a
  }
}
