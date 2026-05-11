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
 * LanternSystem — Glowing lantern posts along garden paths.
 *
 * Places a thin pole + emissive sphere at intervals along path routes.
 * No actual point lights — emissive material creates the glow illusion.
 *
 * Performance: ~20 posts + 20 spheres, shared materials, no shadows.
 */
import * as pc from 'playcanvas'
import { evalRouteAt, type PathRoute } from '@shared/world/paths'

const LANTERN_SPACING = 6      // world units between lanterns along each path
const POLE_WIDTH = 0.06
const POLE_HEIGHT = 1.5
const LAMP_RADIUS = 0.12
const PATH_OFFSET = 0.8        // offset perpendicular to path direction (left side)

export class LanternSystem {
  private root: pc.Entity
  private poleMat: pc.StandardMaterial
  private lampMat: pc.StandardMaterial

  constructor(app: pc.AppBase) {
    this.root = new pc.Entity('LanternSystem')
    app.root.addChild(this.root)

    // Dark wood pole material
    this.poleMat = new pc.StandardMaterial()
    this.poleMat.diffuse = new pc.Color(0.3, 0.2, 0.12)
    this.poleMat.metalness = 0
    this.poleMat.gloss = 0.15
    this.poleMat.update()

    // Warm emissive lamp material — no point light, just glow
    this.lampMat = new pc.StandardMaterial()
    this.lampMat.diffuse = new pc.Color(1.0, 0.85, 0.4)
    this.lampMat.emissive = new pc.Color(1.0, 0.85, 0.4)
    this.lampMat.metalness = 0
    this.lampMat.gloss = 0.5
    this.lampMat.update()
  }

  /**
   * Place lanterns along path routes, skipping any positions inside exclusion zones.
   * @param routes — array of PathRoute (supports curved routes via Bezier control points)
   * @param exclusionZones — circular zones where lanterns should NOT be placed (e.g., housing village)
   */
  buildAlongRoutes(
    routes: PathRoute[],
    exclusionZones: ReadonlyArray<{ x: number; z: number; radius: number }> = [],
  ): void {
    for (const route of routes) {
      // Chord length — the Bezier arc length is within a few % of this for
      // our gentle 12% curves. Close enough for lantern count estimation.
      const chordDx = route.toX - route.fromX
      const chordDz = route.toZ - route.fromZ
      const chordDist = Math.sqrt(chordDx * chordDx + chordDz * chordDz)
      if (chordDist < LANTERN_SPACING * 2) continue

      const count = Math.floor(chordDist / LANTERN_SPACING)
      for (let i = 1; i < count; i++) {
        const t = i / count
        const p = evalRouteAt(route, t)
        // Approximate perpendicular via finite difference on the curve —
        // correct for both straight and curved routes.
        const pNext = evalRouteAt(route, Math.min(1, t + 0.01))
        const tdx = pNext.x - p.x
        const tdz = pNext.z - p.z
        const tlen = Math.sqrt(tdx * tdx + tdz * tdz) || 1
        const px = -tdz / tlen
        const pz = tdx / tlen
        const x = p.x + px * PATH_OFFSET
        const z = p.z + pz * PATH_OFFSET

        // Skip if inside an exclusion zone (housing compound, etc.)
        const excluded = exclusionZones.some(zone => {
          const ex = x - zone.x, ez = z - zone.z
          return ex * ex + ez * ez < zone.radius * zone.radius
        })
        if (excluded) continue

        this.createLantern(x, z)
      }
    }
  }

  destroy(): void {
    this.root.destroy()
    this.poleMat.destroy()
    this.lampMat.destroy()
  }

  private createLantern(x: number, z: number): void {
    // Pole
    const pole = new pc.Entity('LPole')
    pole.addComponent('render', { type: 'box' })
    pole.setLocalScale(POLE_WIDTH, POLE_HEIGHT, POLE_WIDTH)
    pole.setPosition(x, POLE_HEIGHT / 2, z)
    pole.render!.meshInstances[0].material = this.poleMat
    pole.render!.castShadows = false
    this.root.addChild(pole)

    // Lamp (sphere at top of pole)
    const lamp = new pc.Entity('LLamp')
    lamp.addComponent('render', { type: 'sphere' })
    const s = LAMP_RADIUS * 2
    lamp.setLocalScale(s, s, s)
    lamp.setPosition(x, POLE_HEIGHT + LAMP_RADIUS, z)
    lamp.render!.meshInstances[0].material = this.lampMat
    lamp.render!.castShadows = false
    this.root.addChild(lamp)
  }
}
