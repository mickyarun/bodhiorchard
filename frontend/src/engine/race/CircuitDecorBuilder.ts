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
 * CircuitDecorBuilder — trackside village + cheering spectators for the
 * circuit loop. The straight track keeps its own DecorBuilder; this one
 * places everything through loopPose so the props hug the organic shape.
 *
 * Placement is fully deterministic: fixed fractional arcs, fixed asset
 * rotation, and a tiny seeded LCG for clearance jitter — identical layout
 * on every mount, never Math.random.
 *
 * Ownership (mirrors RacerAvatar's teardown):
 *   - Owns one root entity parenting every prop (destroy() cascades).
 *   - Spectators carry cloned tint materials (KayKitCharacterFactory) —
 *     destroyed per spectator via getClonedMaterials + safeDestroyMaterial.
 *   - Building GLBs are borrowed from the shared AssetLoader — never
 *     destroyed here. The private character factory's container caches
 *     are reference-dropped via clear(); the assets stay loader-owned.
 */
import * as pc from 'playcanvas'
import { loopPose } from '@shared/race/LoopPath'
import type { AssetLoader } from '../assets/AssetLoader'
import { KayKitCharacterFactory, getClonedMaterials } from '../characters/KayKitCharacterFactory'
import type { CharacterConfig } from '../characters/CharacterConfig'
import { entityYawDeg } from './TrackProjection'
import { disposeEntity, safeDestroyMaterial } from './dispose'

/**
 * Village sites: KayKit building GLBs (same pack the garden's houses
 * use) at fixed fractions of the lap, leaving the start/finish straight
 * (fractions near 0/1) clear for the arch and checker band. Scales match
 * the garden's exterior treatment (~2x) so a house reads ~4-6 m wide
 * beside the 0.9 m racers.
 */
const BUILDING_SITES: ReadonlyArray<{ glb: string; arcFraction: number; scale: number }> = [
  { glb: 'assets/buildings/kaykit/home_small.glb', arcFraction: 0.08, scale: 2.0 },
  { glb: 'assets/buildings/kaykit/home_medium.glb', arcFraction: 0.2, scale: 2.0 },
  { glb: 'assets/buildings/kaykit/well.glb', arcFraction: 0.32, scale: 1.6 },
  { glb: 'assets/buildings/kaykit/home_blacksmith.glb', arcFraction: 0.45, scale: 1.9 },
  { glb: 'assets/buildings/kaykit/home_large.glb', arcFraction: 0.58, scale: 2.0 },
  { glb: 'assets/buildings/kaykit/home_church.glb', arcFraction: 0.72, scale: 1.8 },
  { glb: 'assets/buildings/kaykit/home_barracks.glb', arcFraction: 0.86, scale: 1.9 },
]

/**
 * Buildings sit OUTSIDE the loop: lateral offsets are negative (positive
 * lateral points inward, per loopPose), beyond the road edge by this
 * clearance plus a per-site jitter so the village doesn't read as a
 * picket fence at constant distance.
 */
const BUILDING_CLEARANCE_M = 4
const BUILDING_CLEARANCE_JITTER_M = 3

/**
 * Spectator posts interleave the building fractions so fans stand in the
 * gaps between houses, closer to the road than the village line.
 */
const SPECTATOR_ARC_FRACTIONS: readonly number[] = [
  0.05, 0.14, 0.26, 0.385, 0.51, 0.65, 0.79, 0.9, 0.965,
]
const SPECTATOR_CLEARANCE_M = 1.6
const SPECTATOR_CLEARANCE_JITTER_M = 0.8

/** Matches RACE_AVATAR_SCALE so spectators and racers share proportions. */
const SPECTATOR_SCALE = 1.3

/**
 * Cheer loops while emote stays 2 (Idle → Cheer in LOCOMOTION_STATE_GRAPH)
 * — set once after creation, never cleared: spectators cheer all race.
 */
const CHEER_EMOTE = 2

/** Fixed spectator wardrobe, cycled by index — varied but deterministic. */
const SPECTATOR_CONFIGS: readonly CharacterConfig[] = [
  { characterId: 'barbarian', shirtColor: 'E63946', pantsColor: '1D3557', skinColor: 'F4C28F', rightHand: '', leftHand: '' },
  { characterId: 'mage', shirtColor: '457B9D', pantsColor: '2B2D42', skinColor: 'C68642', rightHand: '', leftHand: '' },
  { characterId: 'knight', shirtColor: 'F4A261', pantsColor: '264653', skinColor: 'F4C28F', rightHand: '', leftHand: '' },
  { characterId: 'ranger', shirtColor: '2A9D8F', pantsColor: '3A2E2A', skinColor: '8D5524', rightHand: '', leftHand: '' },
  { characterId: 'rogue', shirtColor: '9B5DE5', pantsColor: '22223B', skinColor: 'F4C28F', rightHand: '', leftHand: '' },
  { characterId: 'rogue_hooded', shirtColor: 'FFD75E', pantsColor: '283618', skinColor: 'C68642', rightHand: '', leftHand: '' },
]

/**
 * Seed for the clearance-jitter LCG. Any fixed value works — it only has
 * to be constant so every mount reproduces the exact same layout.
 */
const DECOR_LCG_SEED = 0x5eed1

/** Degrees per radian — loopPose speaks radians, PlayCanvas degrees. */
const DEG_PER_RAD = 180 / Math.PI

export interface CircuitDecorBuildOptions {
  /** Lap length — selects the LoopPath table everything is placed on. */
  circumferenceM: number
  /** Full road width — props clear the road edge, not the centreline. */
  trackWidthM: number
}

export class CircuitDecorBuilder {
  private loader: AssetLoader
  private characters: KayKitCharacterFactory
  private root: pc.Entity | null = null
  private spectators: pc.Entity[] = []

  constructor(loader: AssetLoader) {
    this.loader = loader
    this.characters = new KayKitCharacterFactory(loader)
  }

  async build(parent: pc.Entity, opts: CircuitDecorBuildOptions): Promise<void> {
    this.root = new pc.Entity('CircuitDecor')
    parent.addChild(this.root)
    try {
      await this.buildVillage(opts)
      await this.buildSpectators(opts)
    } catch (err) {
      // Same convention as RaceScene's avatar loop: a mid-build failure
      // cleans up everything already placed before rethrowing, so the
      // caller never holds half-built props it has no handle to.
      this.destroy()
      throw err
    }
  }

  destroy(): void {
    // Reverse build order: spectators (cloned tint materials first, as
    // RacerAvatar.destroy does), then the root cascade drops buildings.
    for (const wrapper of this.spectators) {
      const mats = getClonedMaterials(wrapper)
      if (mats) for (const mat of mats) safeDestroyMaterial(mat)
      disposeEntity(wrapper)
    }
    this.spectators = []
    disposeEntity(this.root)
    this.root = null
    // Drop container-cache references; the GLB assets stay loader-owned.
    this.characters.clear()
  }

  private async buildVillage(opts: CircuitDecorBuildOptions): Promise<void> {
    const assets = await this.loader.loadBatch(BUILDING_SITES.map((s) => s.glb))
    const rand = makeLcg(DECOR_LCG_SEED)
    for (let i = 0; i < BUILDING_SITES.length; i++) {
      const site = BUILDING_SITES[i]
      const clearanceM = BUILDING_CLEARANCE_M + rand() * BUILDING_CLEARANCE_JITTER_M
      const lateralM = -(opts.trackWidthM / 2 + clearanceM)
      const pose = loopPose(site.arcFraction * opts.circumferenceM, opts.circumferenceM, lateralM)

      const entity = this.loader.instance(assets[i])
      entity.setLocalPosition(pose.x, 0, pose.z)
      entity.setLocalEulerAngles(0, inwardFacingYawDeg(pose.headingRad * DEG_PER_RAD), 0)
      entity.setLocalScale(site.scale, site.scale, site.scale)
      this.root!.addChild(entity)
    }
  }

  private async buildSpectators(opts: CircuitDecorBuildOptions): Promise<void> {
    const rand = makeLcg(DECOR_LCG_SEED + 1)
    for (let i = 0; i < SPECTATOR_ARC_FRACTIONS.length; i++) {
      const clearanceM = SPECTATOR_CLEARANCE_M + rand() * SPECTATOR_CLEARANCE_JITTER_M
      const lateralM = -(opts.trackWidthM / 2 + clearanceM)
      const arcM = SPECTATOR_ARC_FRACTIONS[i] * opts.circumferenceM
      const pose = loopPose(arcM, opts.circumferenceM, lateralM)
      const config = SPECTATOR_CONFIGS[i % SPECTATOR_CONFIGS.length]

      const wrapper = await this.characters.create(
        `spectator-${i}`,
        'Spectator',
        config,
        pose.x, 0, pose.z,
        inwardFacingYawDeg(pose.headingRad * DEG_PER_RAD),
        false,
        true, // skipLabel — fans don't need name billboards
      )
      this.root!.addChild(wrapper.entity)
      wrapper.entity.setLocalScale(SPECTATOR_SCALE, SPECTATOR_SCALE, SPECTATOR_SCALE)
      wrapper.entity.anim?.setInteger('emote', CHEER_EMOTE)
      this.spectators.push(wrapper.entity)
    }
  }
}

/**
 * Yaw that turns a +Z-fronted KayKit model (buildings and characters
 * alike) toward the track from the outside. Facing direction is the
 * inward normal — travel heading rotated +90° toward +Z — and composing
 * with the +Z-front correction (+90, see RacerAvatar's AVATAR_YAW_DEG)
 * collapses to 90 + entityYawDeg(heading + 90) = −heading.
 */
function inwardFacingYawDeg(headingDeg: number): number {
  return entityYawDeg(headingDeg)
}

/**
 * Minimal linear congruential generator (Numerical Recipes constants) —
 * deterministic [0, 1) stream for placement jitter. Math.random is
 * banned here: layouts must be identical across mounts and clients.
 */
function makeLcg(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0
    return state / 0x100000000
  }
}
