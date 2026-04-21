// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * HubAnchor — The orchard-center landmark.
 *
 * A single hero "Bodhi tree" sitting on a raised earth mound, ringed by
 * flowers, and footed on a cobble plaza. Purpose: give the zoom-out view a
 * strong focal point so the spoke-wheel of paths + surrounding activity
 * zones read as "arranged around something" rather than "radiating out of
 * nothing." See plan file image-41-garden-... for composition rationale.
 *
 * Layout (top-down, concentric rings):
 *
 *                   flower    flower
 *                      ·        ·
 *              flower  ┌──────┐  flower
 *                      │ 🌳   │
 *                      │ tree │          <- scaled 2.5× on mound
 *                      │ mound│
 *              flower  └──────┘  flower
 *                      ·        ·
 *                   flower    flower
 *                ─────────────────────   <- cobble plaza
 *
 * The entire anchor sits at the world origin (0,0). Downstream systems
 * (PathSystem, PineTreeSystem) treat its exclusion zone like any other
 * zone so paths terminate at the plaza edge rather than crossing it.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { DECOR } from '../assets/AssetManifest'
import type { ExclusionZone } from '../utils/MathUtils'

export interface HubAnchorResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
}

// ─── Layout tuning (local units, centered on anchor origin) ───────────────
/**
 * Hub scale matters — at the original (6.5, 2.5× tree) the Bodhi was just
 * visually "competing" with surrounding activity zones (r=8), not dominating.
 * Widened to ~28% larger radius and ~28% larger tree so the hub clearly
 * reads as primary focal point from both zoom-out and walk-up views.
 */
const PLAZA_RADIUS = 8.5        // outer cobble disc — hero-scale to hold canopy shadow
const MOUND_RADIUS = 4.0        // raised earth pad under tree
const MOUND_HEIGHT = 0.7        // visible elevation of the mound
const RING_RADIUS = 5.8         // bush/flower ring, sits between mound and plaza edge
const RING_COUNT = 12           // more bushes for larger circumference
const HUB_TREE_SCALE = 3.2      // hero tree — clearly largest silhouette in scene

export class HubAnchor {
  private factory: BuildingFactory
  private materials: pc.StandardMaterial[] = []

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  /** Destroy all GPU materials this builder allocated. */
  destroy(): void {
    for (const mat of this.materials) mat.destroy()
    this.materials = []
  }

  async build(app: Application, x: number, z: number): Promise<HubAnchorResult> {
    const root = new pc.Entity('HubAnchor')
    root.setPosition(x, 0, z)

    this.createPlaza(root)
    this.createMound(root)
    await this.placeHubTree(root)
    await this.placeBushRing(root)

    app.root.addChild(root)

    return {
      entity: root,
      // Slightly larger than plaza so paths stop at the plaza rim with a
      // tiny breathing margin (prevents stepping stones landing on cobble).
      exclusionZone: { x, z, radius: PLAZA_RADIUS + 0.5 },
    }
  }

  /**
   * Flat cobble disc at ground level. Uses the same pattern as
   * StandupPavilion.createStonePatch — cylinder primitive scaled very thin.
   */
  private createPlaza(parent: pc.Entity): void {
    const plaza = new pc.Entity('HubPlaza')
    plaza.addComponent('render', { type: 'cylinder' })
    plaza.setLocalScale(PLAZA_RADIUS * 2, 0.02, PLAZA_RADIUS * 2)
    plaza.setLocalPosition(0, 0.01, 0)

    const mat = new pc.StandardMaterial()
    this.materials.push(mat)
    mat.diffuse = new pc.Color(0.55, 0.53, 0.50)  // weathered cobble grey
    mat.metalness = 0
    mat.gloss = 0.2
    mat.update()
    plaza.render!.meshInstances[0].material = mat
    plaza.render!.castShadows = false

    parent.addChild(plaza)
  }

  /**
   * Raised earth mound on top of the plaza — visually elevates the tree
   * and separates it from the flat cobble surface. Shadow-casting so the
   * mound's silhouette contributes to the scene read.
   */
  private createMound(parent: pc.Entity): void {
    const mound = new pc.Entity('HubMound')
    mound.addComponent('render', { type: 'cylinder' })
    mound.setLocalScale(MOUND_RADIUS * 2, MOUND_HEIGHT, MOUND_RADIUS * 2)
    // Cylinder primitive is centered at origin and unit height, so after
    // scaling by MOUND_HEIGHT we sit its base at y=0.02 (just above the
    // plaza) by translating up half the scaled height.
    mound.setLocalPosition(0, 0.02 + MOUND_HEIGHT / 2, 0)

    const mat = new pc.StandardMaterial()
    this.materials.push(mat)
    mat.diffuse = new pc.Color(0.35, 0.28, 0.18)  // damp earth brown
    mat.metalness = 0
    mat.gloss = 0.1
    mat.update()
    mound.render!.meshInstances[0].material = mat
    mound.render!.castShadows = true

    parent.addChild(mound)
  }

  /**
   * Place the hero Bodhi tree GLB on the mound top, center-aligned via
   * placeFurnitureCentered (which measures AABB so the trunk base sits at
   * y=MOUND_HEIGHT regardless of the source model's pivot offset).
   */
  private async placeHubTree(parent: pc.Entity): Promise<void> {
    const tree = await this.factory.placeFurnitureCentered(
      parent, DECOR.hubTree, 0, MOUND_HEIGHT, 0,
    )
    // Uniform scale-up for hero treatment. placeFurnitureCentered stashes
    // the AABB-corrected local position; multiplying scale after placement
    // scales about the entity origin, which sits at the trunk base — so
    // the tree grows upward from the mound rather than drifting off-center.
    tree.setLocalScale(HUB_TREE_SCALE, HUB_TREE_SCALE, HUB_TREE_SCALE)
  }

  /**
   * Ring of bushes + a few accent flowers around the mound perimeter.
   * Bushes read from the overhead camera (~0.8u tall) where raw flowers
   * disappear at this zoom. Flowers are interleaved as colored accents —
   * the eye catches them but the silhouette is carried by the bushes.
   */
  private async placeBushRing(parent: pc.Entity): Promise<void> {
    const paths = [
      DECOR.bushRound,
      DECOR.bushGreen,
      DECOR.bushRound,
      DECOR.flowerRedA,   // accent — scaled up below
      DECOR.bushCluster,
      DECOR.bushGreen,
      DECOR.bushRound,
      DECOR.flowerPurpleA, // accent
      DECOR.bushCluster,
      DECOR.bushGreen,
    ]
    for (let i = 0; i < RING_COUNT; i++) {
      const theta = (i / RING_COUNT) * Math.PI * 2
      const fx = Math.cos(theta) * RING_RADIUS
      const fz = Math.sin(theta) * RING_RADIUS
      const path = paths[i % paths.length]
      // Random yaw breaks the perfect radial symmetry — ring reads as
      // "planted" rather than "procedurally generated asterisk."
      const yaw = (i * 47) % 360
      const entity = await this.factory.placeFurniture(parent, path, fx, 0.02, fz, yaw)
      // Scale flower accents up — their default size is invisible at the
      // zoom-out camera that dominates the garden view.
      if (path === DECOR.flowerRedA || path === DECOR.flowerPurpleA) {
        entity.setLocalScale(2.2, 2.2, 2.2)
      }
    }
  }
}
