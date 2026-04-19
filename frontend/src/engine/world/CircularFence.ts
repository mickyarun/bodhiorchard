// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CircularFence — procedural wooden fence ring.
 *
 * Two styles:
 *   'solid' (default) — close-spaced posts + a continuous solid plank panel.
 *                       Used for zone property fences (dense, opaque).
 *   'rail'            — wider-spaced posts + 2 thin horizontal rails.
 *                       Used for the outer campus perimeter (light, open).
 *
 * Coordinate convention (PlayCanvas XZ plane):
 *   angle = 0  →  (cx,  cz + radius)  =  +Z from center
 *   angle = π  →  (cx,  cz - radius)  =  -Z from center
 *   angle = π/2 → (cx + radius, cz)   =  +X from center
 *
 * Tangent rotation: each panel/rail's local X aligns along the circle tangent.
 *   yaw = angle * (180 / Math.PI)  — no lookAt, no quaternion math required.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import {
  POST_HEIGHT, POST_WIDTH, PANEL_HEIGHT, PANEL_THICKNESS,
  GATE_POST_W, GATE_POST_H, GATE_WIDTH,
  SOLID_SEGMENT_WIDTH,
  RAIL_POST_HEIGHT, RAIL_POST_WIDTH, RAIL_THICKNESS, RAIL_Y_FRACTIONS,
  RAIL_SEGMENT_WIDTH,
} from './FenceConstants'

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
   * angle=0 → +Z from center.
   * Use Math.asin((pathX - cx) / radius) to align with a path.
   * Ignored when gateWidth = 0 (no gate).
   */
  gateAngle?: number
  /** World-space width of the gate opening. Set 0 for no gate (default 1.6). */
  gateWidth?: number
  /**
   * Visual style:
   *  'solid' — dense posts + continuous solid panel (default, used for zone fences)
   *  'rail'  — wider posts + 2 horizontal rails (light perimeter fence)
   */
  style?: 'solid' | 'rail'
}

// ─── CircularFence ───────────────────────────────────────────────────────────

export class CircularFence {
  private materials: MaterialFactory

  constructor(materials: MaterialFactory) {
    this.materials = materials
  }

  /**
   * Build the fence ring as children of `parent`.
   * Root entity sits at (cx, 0, cz); all posts/panels are in local space —
   * matching the BuildingFactory pattern used throughout the engine.
   */
  build(parent: pc.Entity, opts: CircularFenceOptions): pc.Entity {
    const {
      radius, cx, cz,
      gateAngle = 0,
      gateWidth = GATE_WIDTH,
      style = 'solid',
    } = opts

    const root = new pc.Entity('CircularFence')
    root.setLocalPosition(cx, 0, cz)
    parent.addChild(root)

    if (style === 'rail') {
      this._buildRailFence(root, radius, gateAngle, gateWidth)
    } else {
      this._buildSolidFence(root, radius, gateAngle, gateWidth)
    }

    return root
  }

  // ─── Solid fence (zone boundaries) ──────────────────────────────────────────

  private _buildSolidFence(
    root: pc.Entity,
    radius: number,
    gateAngle: number,
    gateWidth: number,
  ): void {
    const postMat     = this.materials.getColor('fence_post',  0.55, 0.40, 0.24)
    const panelMat    = this.materials.getColor('fence_panel', 0.64, 0.50, 0.30)
    const gatePostMat = this.materials.getColor('fence_gate',  0.42, 0.30, 0.16)

    const segmentCount = Math.max(16, Math.round((2 * Math.PI * radius) / SOLID_SEGMENT_WIDTH))
    const angleStep    = (2 * Math.PI) / segmentCount
    const panelWidth   = (2 * Math.PI * radius) / segmentCount
    const gateHalfArc  = gateWidth > 0 ? (gateWidth / radius) / 2 : 0

    for (let i = 0; i < segmentCount; i++) {
      const angle = i * angleStep
      if (gateWidth > 0 && Math.abs(this._normalizeAngle(angle - gateAngle)) < gateHalfArc) continue

      const px  = Math.sin(angle) * radius
      const pz  = Math.cos(angle) * radius
      const yaw = angle * (180 / Math.PI)

      const post = new pc.Entity('Post')
      post.addComponent('render', { type: 'box' })
      post.setLocalScale(POST_WIDTH, POST_HEIGHT, POST_WIDTH)
      post.setLocalPosition(px, POST_HEIGHT / 2, pz)
      post.render!.meshInstances[0].material = postMat
      root.addChild(post)

      const panel = new pc.Entity('Panel')
      panel.addComponent('render', { type: 'box' })
      panel.setLocalScale(panelWidth, PANEL_HEIGHT, PANEL_THICKNESS)
      panel.setLocalPosition(px, PANEL_HEIGHT / 2, pz)
      panel.setLocalEulerAngles(0, yaw, 0)
      panel.render!.meshInstances[0].material = panelMat
      root.addChild(panel)
    }

    if (gateWidth > 0) {
      this._buildGatePillars(root, radius, gateAngle, gateHalfArc, gatePostMat)
    }
  }

  // ─── Rail fence (light perimeter) ────────────────────────────────────────────

  private _buildRailFence(
    root: pc.Entity,
    radius: number,
    gateAngle: number,
    gateWidth: number,
  ): void {
    const postMat = this.materials.getColor('fence_post',  0.52, 0.38, 0.22)
    const railMat = this.materials.getColor('fence_panel', 0.60, 0.46, 0.26)

    const segmentCount = Math.max(12, Math.round((2 * Math.PI * radius) / RAIL_SEGMENT_WIDTH))
    const angleStep    = (2 * Math.PI) / segmentCount
    const railSpan     = (2 * Math.PI * radius) / segmentCount  // arc length between posts
    const gateHalfArc  = gateWidth > 0 ? (gateWidth / radius) / 2 : 0

    for (let i = 0; i < segmentCount; i++) {
      const angle = i * angleStep
      if (gateWidth > 0 && Math.abs(this._normalizeAngle(angle - gateAngle)) < gateHalfArc) continue

      const px  = Math.sin(angle) * radius
      const pz  = Math.cos(angle) * radius
      const yaw = angle * (180 / Math.PI)

      // Post
      const post = new pc.Entity('Post')
      post.addComponent('render', { type: 'box' })
      post.setLocalScale(RAIL_POST_WIDTH, RAIL_POST_HEIGHT, RAIL_POST_WIDTH)
      post.setLocalPosition(px, RAIL_POST_HEIGHT / 2, pz)
      post.render!.meshInstances[0].material = postMat
      root.addChild(post)

      // Two horizontal rails at RAIL_Y_FRACTIONS of post height
      for (const frac of RAIL_Y_FRACTIONS) {
        const rail = new pc.Entity('Rail')
        rail.addComponent('render', { type: 'box' })
        rail.setLocalScale(railSpan, RAIL_THICKNESS, RAIL_THICKNESS)
        rail.setLocalPosition(px, RAIL_POST_HEIGHT * frac, pz)
        rail.setLocalEulerAngles(0, yaw, 0)
        rail.render!.meshInstances[0].material = railMat
        root.addChild(rail)
      }
    }
  }

  // ─── Gate pillars (solid fence only) ─────────────────────────────────────────

  private _buildGatePillars(
    root: pc.Entity,
    radius: number,
    gateAngle: number,
    gateHalfArc: number,
    mat: pc.Material,
  ): void {
    for (const side of [-1, 1] as const) {
      const a   = gateAngle + side * gateHalfArc
      const gpx = Math.sin(a) * radius
      const gpz = Math.cos(a) * radius

      const post = new pc.Entity('GatePost')
      post.addComponent('render', { type: 'box' })
      post.setLocalScale(GATE_POST_W, GATE_POST_H, GATE_POST_W)
      post.setLocalPosition(gpx, GATE_POST_H / 2, gpz)
      post.render!.meshInstances[0].material = mat
      root.addChild(post)
    }
  }

  /** Normalize angle to [-π, π]. */
  private _normalizeAngle(angle: number): number {
    let a = angle
    while (a >  Math.PI) a -= 2 * Math.PI
    while (a < -Math.PI) a += 2 * Math.PI
    return a
  }
}
