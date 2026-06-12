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
 * VillageDressing — life between the houses.
 *
 * The housing village read as "identical houses in an empty pen". This
 * module dresses the zone-LOCAL space with the CC0 props already shipped
 * with the app (Kenney garden/furniture GLBs):
 *
 *   - a campfire gathering circle (stones + logs + stump seats)
 *   - benches along the street ends
 *   - per-house yard props (log stacks, potted plants, mushrooms),
 *     deterministic per house index so rebuilds don't reshuffle yards
 *   - a washing line with hanging towels behind one house row
 *
 * Everything is parented to the village root (inherits zone yaw) and is
 * purely visual — no seats, no physics, no shared/world changes, so the
 * multiplayer sim is untouched.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { VillageLayoutResult } from '@shared/world/VillageLayout'
import { BUILDING, DECOR, GARDEN_PROPS } from '../assets/AssetManifest'
import { Theme } from '../rendering/Theme'

/** Deterministic per-index jitter — yards keep their look across rebuilds. */
function jitter(index: number, salt: number): number {
  const x = Math.sin(index * 127.1 + salt * 311.7) * 43758.5453
  return x - Math.floor(x)
}

const TOWEL_COLORS: ReadonlyArray<[number, number, number]> = [
  [0.90, 0.45, 0.40],
  [0.45, 0.62, 0.85],
  [0.92, 0.85, 0.55],
]

export class VillageDressing {
  async build(
    root: pc.Entity,
    loader: AssetLoader,
    layout: VillageLayoutResult,
    materials?: MaterialFactory,
  ): Promise<void> {
    const dressing = new pc.Entity('VillageDressing')
    root.addChild(dressing)

    if (materials) {
      this.buildFloor(dressing, materials, layout)
      this.buildWashingLine(dressing, materials, layout)
    }
    await Promise.all([
      this.buildCampfire(dressing, loader, layout),
      this.buildStreetBenches(dressing, loader, layout),
      this.buildYards(dressing, loader, layout),
    ])
  }

  /**
   * Packed-earth floor covering the whole fenced compound. The grass
   * carpet stops at the fence line (GrassSystem blocked-rect), so the
   * inside reads as lived-in village ground instead of patchy lawn.
   * Flat MaterialFactory color — no texture, nothing extra to destroy.
   */
  private buildFloor(
    parent: pc.Entity, materials: MaterialFactory, layout: VillageLayoutResult,
  ): void {
    const bounds = layout.fenceBounds
    const margin = 1.2
    const w = bounds.maxX - bounds.minX + margin * 2
    const d = bounds.maxZ - bounds.minZ + margin * 2

    const floor = new pc.Entity('VillageFloor')
    floor.addComponent('render', { type: 'plane' })
    floor.setLocalScale(w, 1, d)
    floor.setLocalPosition(
      (bounds.minX + bounds.maxX) / 2,
      0.012,  // above grass (0), below roads/driveways and zone overlays
      (bounds.minZ + bounds.maxZ) / 2,
    )
    floor.render!.meshInstances[0].material = materials.getColor(
      'village_floor', ...Theme.VILLAGE.floor, { gloss: 0.06 },
    )
    floor.render!.castShadows = false
    parent.addChild(floor)
  }

  /** Campfire circle in the gap between the fence and the first street. */
  private async buildCampfire(
    parent: pc.Entity, loader: AssetLoader, layout: VillageLayoutResult,
  ): Promise<void> {
    const bounds = layout.fenceBounds
    // Open pocket: east edge between the fence and the street ends.
    const cx = bounds.maxX - 2.6
    const cz = (bounds.minZ + bounds.maxZ) / 2

    const [stones, logs] = await Promise.all([
      loader.load(GARDEN_PROPS.campfireStones),
      loader.load(GARDEN_PROPS.campfireLogs),
    ])
    const stoneRing = loader.instance(stones)
    stoneRing.setLocalPosition(cx, 0, cz)
    stoneRing.setLocalScale(1.6, 1.6, 1.6)
    parent.addChild(stoneRing)

    const fire = loader.instance(logs)
    fire.setLocalPosition(cx, 0.05, cz)
    fire.setLocalScale(1.4, 1.4, 1.4)
    parent.addChild(fire)

    const stumpAsset = await loader.load(DECOR.stumpRound)
    const seatCount = 4
    for (let i = 0; i < seatCount; i++) {
      const a = (i / seatCount) * Math.PI * 2 + 0.5
      const stump = loader.instance(stumpAsset)
      stump.setLocalPosition(cx + Math.cos(a) * 1.7, 0, cz + Math.sin(a) * 1.7)
      stump.setLocalEulerAngles(0, jitter(i, 7) * 360, 0)
      stump.setLocalScale(1.1, 0.9, 1.1)
      parent.addChild(stump)
    }
  }

  /** A bench at each street end, facing inward down the street. */
  private async buildStreetBenches(
    parent: pc.Entity, loader: AssetLoader, layout: VillageLayoutResult,
  ): Promise<void> {
    const benchAsset = await loader.load(BUILDING.bench)
    for (const street of layout.streets) {
      const bench = loader.instance(benchAsset)
      bench.setLocalPosition(street.startX - 1.2, 0, street.centerZ + 1.1)
      bench.setLocalEulerAngles(0, 90, 0)
      bench.setLocalScale(1.3, 1.3, 1.3)
      parent.addChild(bench)
    }
  }

  /**
   * Per-house yard props beside each house (away from the door side),
   * cycling log stack / potted plant / mushrooms by house index.
   */
  private async buildYards(
    parent: pc.Entity, loader: AssetLoader, layout: VillageLayoutResult,
  ): Promise<void> {
    const [logStack, potted, mushroomR, mushroomT] = await Promise.all([
      loader.load(DECOR.logStack),
      loader.load(BUILDING.pottedPlant),
      loader.load(GARDEN_PROPS.mushroomRed),
      loader.load(GARDEN_PROPS.mushroomTan),
    ])

    for (const placement of layout.placements) {
      const i = placement.layoutIndex
      // Yard spot: beside the house, offset along the street (+X), pushed
      // AWAY from the door side so props never block the driveway.
      const yardX = placement.x + 2.3 + jitter(i, 1) * 0.8
      const doorSign = placement.yawDeg === 0 ? 1 : -1
      const yardZ = placement.z - doorSign * (1.4 + jitter(i, 2) * 0.6)

      const kind = i % 3
      if (kind === 0) {
        const stack = loader.instance(logStack)
        stack.setLocalPosition(yardX, 0, yardZ)
        stack.setLocalEulerAngles(0, jitter(i, 3) * 360, 0)
        parent.addChild(stack)
      } else if (kind === 1) {
        const plant = loader.instance(potted)
        plant.setLocalPosition(yardX, 0, yardZ)
        plant.setLocalScale(1.4, 1.4, 1.4)
        parent.addChild(plant)
      } else {
        const m1 = loader.instance(jitter(i, 4) > 0.5 ? mushroomR : mushroomT)
        m1.setLocalPosition(yardX, 0, yardZ)
        m1.setLocalScale(1.6, 1.6, 1.6)
        parent.addChild(m1)
        const m2 = loader.instance(jitter(i, 5) > 0.5 ? mushroomR : mushroomT)
        m2.setLocalPosition(yardX + 0.5, 0, yardZ + 0.4)
        m2.setLocalScale(1.1, 1.1, 1.1)
        parent.addChild(m2)
      }
    }
  }

  /** Two poles + sagging line + towels behind the north house row. */
  private buildWashingLine(
    parent: pc.Entity, materials: MaterialFactory, layout: VillageLayoutResult,
  ): void {
    const bounds = layout.fenceBounds
    const lineZ = bounds.minZ + 1.1
    const x0 = bounds.minX + 3
    const x1 = x0 + 4.5
    const poleH = 1.7

    const poleMat = materials.getColor('village_pole', 0.45, 0.33, 0.22)
    const lineMat = materials.getColor('village_line', 0.92, 0.92, 0.90)

    for (const px of [x0, x1]) {
      const pole = new pc.Entity('WashPole')
      pole.addComponent('render', { type: 'cylinder' })
      pole.setLocalScale(0.08, poleH, 0.08)
      pole.setLocalPosition(px, poleH / 2, lineZ)
      pole.render!.meshInstances[0].material = poleMat
      parent.addChild(pole)
    }

    const line = new pc.Entity('WashLine')
    line.addComponent('render', { type: 'cylinder' })
    line.setLocalScale(0.025, x1 - x0, 0.025)
    line.setLocalPosition((x0 + x1) / 2, poleH - 0.12, lineZ)
    line.setLocalEulerAngles(0, 0, 90)
    line.render!.meshInstances[0].material = lineMat
    parent.addChild(line)

    for (let t = 0; t < TOWEL_COLORS.length; t++) {
      const c = TOWEL_COLORS[t]
      const towel = new pc.Entity('WashTowel')
      towel.addComponent('render', { type: 'box' })
      towel.setLocalScale(0.6, 0.55, 0.04)
      towel.setLocalPosition(x0 + 1 + t * 1.3, poleH - 0.42, lineZ)
      towel.render!.meshInstances[0].material =
        materials.getColor(`village_towel_${t}`, c[0], c[1], c[2], { gloss: 0.05 })
      parent.addChild(towel)
    }
  }
}
