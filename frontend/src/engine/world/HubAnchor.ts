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
  /**
   * Geometry the physics builder uses to seal the raised mound. The ring
   * collider wraps the rim at `radius`; the cap closes the top so the
   * volume is fully impassable (no jumping/clipping onto the platform).
   */
  trunkCollider: { x: number; z: number; radius: number; topY: number }
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
      // Collider wraps the whole raised mound — player can't step onto
      // the platform. Geometry is tied to the visual mound constants so
      // visual and collision stay in lockstep (0.05 is the plaza-to-
      // mound clearance applied in createMound; see there for details).
      trunkCollider: {
        x,
        z,
        radius: MOUND_RADIUS,
        topY: 0.05 + MOUND_HEIGHT,
      },
    }
  }

  /**
   * Flat cobble disc just above ground level. Uses the same pattern as
   * StandupPavilion.createStonePatch — cylinder primitive scaled very thin.
   *
   * The plaza is lifted so its bottom face sits at y=0.02 rather than
   * coplanar with the ground. A PlayCanvas cylinder primitive defaults to
   * unit height centered at origin, so after scaling height by 0.02 the
   * bottom face is at (localY - 0.01). Using localY=0.03 puts the bottom
   * at y=0.02 (clear of the ground) and top at y=0.04. This clearance
   * also keeps it above path decals (wear y=0.008, strip y=0.015, zone
   * overlay y=0.02) in case a future layout tweak overlaps their XZ.
   */
  private createPlaza(parent: pc.Entity): void {
    const plaza = new pc.Entity('HubPlaza')
    plaza.addComponent('render', { type: 'cylinder' })
    plaza.setLocalScale(PLAZA_RADIUS * 2, 0.02, PLAZA_RADIUS * 2)
    plaza.setLocalPosition(0, 0.03, 0)

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
    // Cylinder primitive is unit-height centered at origin, so after
    // scaling by MOUND_HEIGHT its bottom face sits at (localY - MH/2).
    // Plaza top is now at y=0.04 — seat the mound with 0.01 clearance
    // above it (bottom at y=0.05) so they aren't coplanar either.
    mound.setLocalPosition(0, 0.05 + MOUND_HEIGHT / 2, 0)

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
    // Mound top is at y = 0.05 + MOUND_HEIGHT (see createMound). Plant the
    // tree trunk at that exact y so its base sits on the mound surface.
    const tree = await this.factory.placeFurnitureCentered(
      parent, DECOR.hubTree, 0, 0.05 + MOUND_HEIGHT, 0,
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
      // Plaza top is at y=0.04 (see createPlaza); seat bushes/flowers there.
      const entity = await this.factory.placeFurniture(parent, path, fx, 0.04, fz, yaw)
      // Scale flower accents up — their default size is invisible at the
      // zoom-out camera that dominates the garden view.
      if (path === DECOR.flowerRedA || path === DECOR.flowerPurpleA) {
        entity.setLocalScale(2.2, 2.2, 2.2)
      }
    }
  }
}
