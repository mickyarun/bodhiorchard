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
 * StringLightEffect — Decorative warm lights strung between wooden poles.
 *
 * Each string has:
 * - Wooden poles at start and end (thin brown cylinders, ground to string height)
 * - A wire following a catenary curve (thin dark cylinder segments)
 * - Emissive bulbs spaced along the wire
 *
 * Placed at coffee bar and cafeteria zones. Simple geometry, no GLBs.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { MaterialFactory } from '../rendering/MaterialFactory'

export interface LightString {
  start: { x: number; y: number; z: number }
  end: { x: number; y: number; z: number }
  bulbCount: number
}

const BULB_SIZE = 0.25
const MAX_SAG = 1.5
const SAG_RATIO = 0.12 // sag = min(span * SAG_RATIO, MAX_SAG)
const WIRE_THICKNESS = 0.025
const POLE_DIAMETER = 0.07
const WIRE_SEGMENTS_PER_BULB = 3

export class StringLightEffect {
  private root: pc.Entity | null = null
  private bulbMat: pc.StandardMaterial | null = null
  private wireMat: pc.StandardMaterial | null = null
  private poleMat: pc.StandardMaterial | null = null

  build(
    app: Application,
    materials: MaterialFactory,
  ): pc.Entity {
    this.root = new pc.Entity('StringLights')
    this.bulbMat = materials.getColor('string_light_bulb', 1, 0.9, 0.5, {
      emissive: [1, 0.85, 0.4],
    })
    this.wireMat = materials.getColor('string_light_wire', 0.2, 0.15, 0.1)
    this.poleMat = materials.getColor('string_light_pole', 0.35, 0.25, 0.15)
    app.root.addChild(this.root)
    return this.root
  }

  addStrings(strings: LightString[]): void {
    if (!this.root || !this.bulbMat) return

    for (const str of strings) {
      // Compute sag proportional to string span (short strings sag less)
      const spanX = str.end.x - str.start.x
      const spanZ = str.end.z - str.start.z
      const span = Math.sqrt(spanX * spanX + spanZ * spanZ)
      const sag = Math.min(span * SAG_RATIO, MAX_SAG)

      // ─── Poles at each end ───
      this.addPole(str.start.x, str.start.y, str.start.z)
      this.addPole(str.end.x, str.end.y, str.end.z)

      // ─── Wire along catenary curve ───
      const totalSegments = str.bulbCount * WIRE_SEGMENTS_PER_BULB
      let prev = { x: str.start.x, y: str.start.y, z: str.start.z }

      for (let i = 1; i <= totalSegments; i++) {
        const t = i / totalSegments
        const drop = Math.sin(t * Math.PI) * sag
        const cur = {
          x: str.start.x + (str.end.x - str.start.x) * t,
          y: str.start.y + (str.end.y - str.start.y) * t - drop,
          z: str.start.z + (str.end.z - str.start.z) * t,
        }
        this.addWireSegment(prev, cur)
        prev = cur
      }

      // ─── Bulbs at regular intervals ───
      for (let i = 0; i < str.bulbCount; i++) {
        const t = (i + 0.5) / str.bulbCount
        const drop = Math.sin(t * Math.PI) * sag

        const bulb = new pc.Entity(`Bulb_${i}`)
        bulb.addComponent('render', { type: 'sphere' })
        bulb.setLocalScale(BULB_SIZE, BULB_SIZE, BULB_SIZE)
        bulb.setLocalPosition(
          str.start.x + (str.end.x - str.start.x) * t,
          str.start.y + (str.end.y - str.start.y) * t - drop,
          str.start.z + (str.end.z - str.start.z) * t,
        )

        bulb.render!.meshInstances[0].material = this.bulbMat
        this.root.addChild(bulb)
      }
    }
  }

  /** Vertical pole from ground to the string attachment point. */
  private addPole(x: number, topY: number, z: number): void {
    const pole = new pc.Entity('Pole')
    pole.addComponent('render', { type: 'cylinder' })
    // PlayCanvas cylinder: default height=2, so scaleY = desiredHeight/2
    pole.setLocalPosition(x, topY / 2, z)
    pole.setLocalScale(POLE_DIAMETER, topY / 2, POLE_DIAMETER)
    pole.render!.meshInstances[0].material = this.poleMat!
    this.root!.addChild(pole)
  }

  /** Thin cylinder between two catenary points. */
  private addWireSegment(
    p1: { x: number; y: number; z: number },
    p2: { x: number; y: number; z: number },
  ): void {
    const dx = p2.x - p1.x
    const dy = p2.y - p1.y
    const dz = p2.z - p1.z
    const len = Math.sqrt(dx * dx + dy * dy + dz * dz)
    if (len < 0.001) return

    const wire = new pc.Entity('Wire')
    wire.addComponent('render', { type: 'cylinder' })

    // Position at midpoint
    wire.setLocalPosition(
      (p1.x + p2.x) / 2,
      (p1.y + p2.y) / 2,
      (p1.z + p2.z) / 2,
    )

    // Scale: thin wire, height = segment length
    wire.setLocalScale(WIRE_THICKNESS, len / 2, WIRE_THICKNESS)

    // Rotate default Y-axis to align with segment direction.
    // Quaternion from (0,1,0) to normalized direction:
    //   cross((0,1,0), dir) = (dir.z, 0, -dir.x)
    //   dot = dir.y
    //   q = (cross, 1 + dot) then normalize
    const nx = dx / len
    const ny = dy / len
    const nz = dz / len

    if (ny < -0.999) {
      // Nearly straight down — rotate 180° around X
      wire.setLocalEulerAngles(180, 0, 0)
    } else {
      const qx = nz
      const qz = -nx
      const qw = 1 + ny
      const invLen = 1 / Math.sqrt(qx * qx + qz * qz + qw * qw)
      wire.setLocalRotation(qx * invLen, 0, qz * invLen, qw * invLen)
    }

    wire.render!.meshInstances[0].material = this.wireMat!
    this.root!.addChild(wire)
  }

  destroy(): void {
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
    this.bulbMat = null
    this.wireMat = null
    this.poleMat = null
  }
}
