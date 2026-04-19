// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * ColliderDebug — immediate-mode wireframe rendering of Rapier collider boxes.
 *
 * Uses PlayCanvas `app.drawLine()` which draws for one frame. Call every
 * frame from an update handler while debug mode is enabled.
 *
 * Color coding:
 *   - static walls: green
 *   - door triggers: yellow
 *   - player capsule: cyan
 *
 * Walls are drawn from the Rapier body translation + Y-rotation quaternion,
 * so rotated KayKit houses and per-wall rotations both render correctly.
 */
import * as pc from 'playcanvas'
import type { Application as EngineApplication } from '../core/Application'
import type { PhysicsWorld } from './PhysicsWorld'

const COLOR_WALL = new pc.Color(0.2, 1.0, 0.2, 1.0)
const COLOR_DOOR = new pc.Color(1.0, 0.85, 0.0, 1.0)
const COLOR_PLAYER = new pc.Color(0.3, 0.9, 1.0, 1.0)

/** Draw every physics collider as a wireframe box this frame. */
export function drawColliderWireframes(app: EngineApplication, physics: PhysicsWorld): void {
  const pcApp = app.app
  physics.forEachColliderBox((b) => {
    const color = b.isPlayer ? COLOR_PLAYER : b.isDoor ? COLOR_DOOR : COLOR_WALL
    drawOrientedBox(pcApp, b.x, b.y, b.z, b.halfW, b.halfH, b.halfD, b.yawRad, color)
  })
}

function drawOrientedBox(
  app: pc.AppBase,
  cx: number, cy: number, cz: number,
  hx: number, hy: number, hz: number,
  yawRad: number,
  color: pc.Color,
): void {
  // 8 local corners of the box (local +X, +Y, +Z half-extents)
  // Apply Y-axis rotation, then translate to world.
  const cos = Math.cos(yawRad)
  const sin = Math.sin(yawRad)
  const corners: pc.Vec3[] = []
  for (const sx of [-1, 1]) {
    for (const sy of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const lx = sx * hx, ly = sy * hy, lz = sz * hz
        const rx = lx * cos + lz * sin
        const rz = -lx * sin + lz * cos
        corners.push(new pc.Vec3(cx + rx, cy + ly, cz + rz))
      }
    }
  }
  // Index layout: i = (sxBit<<2) | (syBit<<1) | szBit, with sxBit=(sx==1?1:0), etc.
  // 12 edges — 4 along X, 4 along Y, 4 along Z.
  const edges: Array<[number, number]> = [
    // edges along Z (sz flips): pairs differ only in last bit
    [0, 1], [2, 3], [4, 5], [6, 7],
    // edges along Y (sy flips): pairs differ only in middle bit
    [0, 2], [1, 3], [4, 6], [5, 7],
    // edges along X (sx flips): pairs differ only in high bit
    [0, 4], [1, 5], [2, 6], [3, 7],
  ]
  for (const [a, b] of edges) {
    app.drawLine(corners[a], corners[b], color)
  }
}
