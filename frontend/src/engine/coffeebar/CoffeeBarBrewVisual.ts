// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CoffeeBarBrewVisual — small ceramic cup beside the espresso machine plus
 * a thin "pour" stream during the server's `brewing` phase.
 *
 * Why not animate liquid INSIDE the cup? The cup is rendered as a solid
 * cylinder primitive (no hollow interior), so a sub-cylinder placed inside
 * is invisible. Instead we render the coffee as a flat disc on the cup
 * rim ("coffee surface") that grows in radius as it fills, plus a thin
 * vertical cylinder above the rim representing the pouring stream.
 *
 * Phases (driven entirely by snapshot.active.phase + phaseStartMs):
 *   - idle / approaching → everything hidden
 *   - brewing            → cup + pour stream visible; surface disc grows 0→1
 *   - dispensed          → cup + full surface disc; stream hidden
 *
 * Server time is the source of truth: fill ratio = elapsed / brewing_ms,
 * so every observer sees the same animation regardless of when they joined.
 */
import * as pc from 'playcanvas'
import type { BuildingFactory } from '../buildings/BuildingFactory'
import type { CoffeeBarSnapshot } from './CoffeeBarRoomClient'
import { COUNTER, COUNTER_FRONT_Z, S } from './CoffeeBarLayout'
import { COFFEE_MACHINE_POS } from './SceneConfig'

/** ms — mirrors COFFEE_PHASE_MS.brewing on the server (multiplayer/src/sim/CoffeeMenu.ts).
 *  Kept as a local constant rather than imported because the frontend does
 *  not depend on the multiplayer package — same pattern used elsewhere. */
const BREWING_MS = 3000

/** Cup geometry (metres). */
const CUP_RADIUS = 0.05
const CUP_HEIGHT = 0.09
const CUP_INNER_RADIUS = 0.042  // visible coffee surface radius when full

/** Pour stream — thin vertical cylinder, machine spout → cup rim. */
const STREAM_RADIUS = 0.006
const SURFACE_THICKNESS = 0.003  // very thin disc on rim

/** Approximate machine spout height above the counter. The coffee machine
 *  is `S.SMALL` tall and the spout sits at roughly half that height. */
const SPOUT_Y = COUNTER.topY + S.SMALL * 0.5

/** Cup is positioned directly under the machine spout. Using
 *  COFFEE_MACHINE_POS as the x source means moving the machine in
 *  SceneConfig automatically repositions the cup. The small forward `z`
 *  offset places it just outside the GLB's front face. */
const CUP_X = COFFEE_MACHINE_POS.x
const CUP_Z = COUNTER_FRONT_Z + 0.05

export class CoffeeBarBrewVisual {
  private factory: BuildingFactory
  private root: pc.Entity | null = null
  private cupBody: pc.Entity | null = null
  private surface: pc.Entity | null = null
  private stream: pc.Entity | null = null

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  /** Build cup + surface disc + pour stream. All hidden until `brewing`. */
  attach(parent: pc.Entity): void {
    const materials = this.factory.materialFactory
    if (!materials) return

    const cupMat = materials.getColor('cup_ceramic', 0.95, 0.93, 0.88, {
      metalness: 0.0, gloss: 0.6,
    })
    const coffeeMat = materials.getColor('cup_coffee', 0.18, 0.09, 0.04, {
      metalness: 0.0, gloss: 0.85,
    })

    const root = new pc.Entity('BrewCup')
    root.setLocalPosition(CUP_X, 0, CUP_Z)
    root.enabled = false

    // Cup body — solid cylinder, base sits on counter top.
    const cup = new pc.Entity('CupBody')
    cup.addComponent('render', { type: 'cylinder' })
    cup.setLocalScale(CUP_RADIUS * 2, CUP_HEIGHT, CUP_RADIUS * 2)
    cup.setLocalPosition(0, COUNTER.topY + CUP_HEIGHT / 2, 0)
    cup.render!.meshInstances[0].material = cupMat
    root.addChild(cup)

    // Coffee surface — flat disc just above the cup rim. Scales 0→1 in
    // X/Z to grow from a dot to a full disc as it fills.
    const surface = new pc.Entity('CoffeeSurface')
    surface.addComponent('render', { type: 'cylinder' })
    surface.setLocalScale(0.001, SURFACE_THICKNESS, 0.001)
    surface.setLocalPosition(0, COUNTER.topY + CUP_HEIGHT - SURFACE_THICKNESS / 2, 0)
    surface.render!.meshInstances[0].material = coffeeMat
    root.addChild(surface)

    // Pour stream — thin dark vertical cylinder from "spout" down to cup
    // rim. Scaled in Y to span from STREAM_TOP_Y down to the cup's top.
    const stream = new pc.Entity('PourStream')
    const streamHeight = SPOUT_Y - (COUNTER.topY + CUP_HEIGHT)
    stream.addComponent('render', { type: 'cylinder' })
    stream.setLocalScale(STREAM_RADIUS * 2, streamHeight, STREAM_RADIUS * 2)
    stream.setLocalPosition(0, COUNTER.topY + CUP_HEIGHT + streamHeight / 2, 0)
    stream.render!.meshInstances[0].material = coffeeMat
    stream.enabled = false
    root.addChild(stream)

    parent.addChild(root)
    this.root = root
    this.cupBody = cup
    this.surface = surface
    this.stream = stream
  }

  /** Per-frame update — drives visibility and fill from server phase. */
  update(snapshot: CoffeeBarSnapshot, nowMs: number): void {
    if (!this.root || !this.surface || !this.stream || !this.cupBody) return
    const phase = snapshot.active.phase

    if (phase === 'brewing') {
      const elapsed = Math.max(0, nowMs - snapshot.active.phaseStartMs)
      const t = Math.min(1, elapsed / BREWING_MS)
      this.setSurfaceFill(t)
      this.stream.enabled = true
      this.root.enabled = true
      return
    }

    if (phase === 'dispensed') {
      this.setSurfaceFill(1)
      this.stream.enabled = false
      this.root.enabled = true
      return
    }

    this.root.enabled = false
  }

  destroy(): void {
    this.root?.destroy()
    this.root = null
    this.cupBody = null
    this.surface = null
    this.stream = null
  }

  /** Scale the coffee-surface disc from a dot (t=0) to full rim (t=1). */
  private setSurfaceFill(t: number): void {
    if (!this.surface) return
    const r = Math.max(0.001, CUP_INNER_RADIUS * t)
    this.surface.setLocalScale(r * 2, SURFACE_THICKNESS, r * 2)
  }
}
