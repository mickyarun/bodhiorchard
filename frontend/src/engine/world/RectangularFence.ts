// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * RectangularFence — procedural wooden fence rectangle with a gate.
 *
 * Builds 4 straight walls from posts + panels, with an optional gate gap
 * on the south side (-Z). Tighter than CircularFence for rectangular layouts
 * like the housing village.
 *
 * Uses the same material keys as CircularFence for visual consistency.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { FenceBounds } from '@shared/world/VillageLayout'
import {
  POST_HEIGHT, POST_WIDTH, PANEL_HEIGHT, PANEL_THICKNESS,
  GATE_POST_W, GATE_POST_H, GATE_WIDTH,
  SOLID_SEGMENT_WIDTH,
} from './FenceConstants'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface RectFenceOptions {
  bounds: FenceBounds
  /** Which side gets the gate: 'south' (default), 'north', 'east', 'west'. */
  gateSide?: 'south' | 'north' | 'east' | 'west'
}

// ─── RectangularFence ───────────────────────────────────────────────────────

export class RectangularFence {
  private materials: MaterialFactory

  constructor(materials: MaterialFactory) {
    this.materials = materials
  }

  build(parent: pc.Entity, opts: RectFenceOptions): pc.Entity {
    const { bounds, gateSide = 'south' } = opts
    const root = new pc.Entity('RectFence')
    root.setLocalPosition(0, 0, 0)
    parent.addChild(root)

    const postMat  = this.materials.getColor('fence_post',  0.55, 0.40, 0.24)
    const panelMat = this.materials.getColor('fence_panel', 0.64, 0.50, 0.30)
    const gateMat  = this.materials.getColor('fence_gate',  0.42, 0.30, 0.16)

    // Define 4 walls as line segments
    const walls: Array<{ sx: number; sz: number; ex: number; ez: number; yaw: number; side: string }> = [
      { sx: bounds.minX, sz: bounds.minZ, ex: bounds.maxX, ez: bounds.minZ, yaw: 0,   side: 'north' },
      { sx: bounds.minX, sz: bounds.maxZ, ex: bounds.maxX, ez: bounds.maxZ, yaw: 0,   side: 'south' },
      { sx: bounds.minX, sz: bounds.minZ, ex: bounds.minX, ez: bounds.maxZ, yaw: 90,  side: 'west'  },
      { sx: bounds.maxX, sz: bounds.minZ, ex: bounds.maxX, ez: bounds.maxZ, yaw: 90,  side: 'east'  },
    ]

    for (const wall of walls) {
      const isGateSide = wall.side === gateSide
      this._buildWall(root, wall.sx, wall.sz, wall.ex, wall.ez, wall.yaw, postMat, panelMat, isGateSide ? GATE_WIDTH : 0)

      // Gate pillars
      if (isGateSide) {
        this._buildGatePillars(root, wall, gateMat)
      }
    }

    return root
  }

  private _buildWall(
    root: pc.Entity,
    sx: number, sz: number,
    ex: number, ez: number,
    yaw: number,
    postMat: pc.Material,
    panelMat: pc.Material,
    gateGap: number,
  ): void {
    const dx = ex - sx
    const dz = ez - sz
    const wallLen = Math.sqrt(dx * dx + dz * dz)
    if (wallLen < 0.1) return

    const segments = Math.max(1, Math.round(wallLen / SOLID_SEGMENT_WIDTH))
    const panelWidth = wallLen / segments

    // Gate center is at the midpoint of the wall
    const gateCenterT = 0.5
    const gateHalfT = wallLen > 0 ? (gateGap / 2) / wallLen : 0

    for (let i = 0; i < segments; i++) {
      const t = (i + 0.5) / segments  // midpoint of this segment along the wall

      // Skip segments inside the gate gap
      if (gateGap > 0 && Math.abs(t - gateCenterT) < gateHalfT) continue

      const px = sx + dx * t
      const pz = sz + dz * t

      // Post
      const post = new pc.Entity('Post')
      post.addComponent('render', { type: 'box' })
      post.setLocalScale(POST_WIDTH, POST_HEIGHT, POST_WIDTH)
      post.setLocalPosition(px, POST_HEIGHT / 2, pz)
      post.render!.meshInstances[0].material = postMat
      root.addChild(post)

      // Panel
      const panel = new pc.Entity('Panel')
      panel.addComponent('render', { type: 'box' })
      panel.setLocalScale(panelWidth, PANEL_HEIGHT, PANEL_THICKNESS)
      panel.setLocalPosition(px, PANEL_HEIGHT / 2, pz)
      panel.setLocalEulerAngles(0, yaw, 0)
      panel.render!.meshInstances[0].material = panelMat
      root.addChild(panel)
    }
  }

  private _buildGatePillars(
    root: pc.Entity,
    wall: { sx: number; sz: number; ex: number; ez: number },
    mat: pc.Material,
  ): void {
    const dx = wall.ex - wall.sx
    const dz = wall.ez - wall.sz
    const wallLen = Math.sqrt(dx * dx + dz * dz)
    if (wallLen < 0.1) return

    const midT = 0.5
    const halfGapT = (GATE_WIDTH / 2) / wallLen

    for (const side of [-1, 1] as const) {
      const t = midT + side * halfGapT
      const px = wall.sx + dx * t
      const pz = wall.sz + dz * t

      const post = new pc.Entity('GatePost')
      post.addComponent('render', { type: 'box' })
      post.setLocalScale(GATE_POST_W, GATE_POST_H, GATE_POST_W)
      post.setLocalPosition(px, GATE_POST_H / 2, pz)
      post.render!.meshInstances[0].material = mat
      root.addChild(post)
    }
  }
}
