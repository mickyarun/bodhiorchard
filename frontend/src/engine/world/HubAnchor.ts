// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * HubAnchor — orchard-center landmark: hero Bodhi tree on a raised mound,
 * ringed by flowers, footed on a cobble plaza. Sits at world origin (0,0)
 * and gives the zoom-out view a focal point so spokes + activity zones
 * read as arranged around something rather than radiating from nothing.
 * Downstream systems treat its exclusion zone like any other zone.
 *
 * All layout geometry (radii, ring count, tree scale, exclusion margin)
 * is sourced from `HubGeometry` in `shared/world/layoutScale.ts`. The
 * only numeric literals here are visual style — material colours, gloss,
 * plaza-elevation epsilons that prevent z-fighting with path decals.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { DECOR } from '../assets/AssetManifest'
import type { ExclusionZone } from '../utils/MathUtils'
import type { HubGeometry } from '@shared/world/layoutScale'

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

export class HubAnchor {
  private factory: BuildingFactory
  private geometry: HubGeometry
  private materials: pc.StandardMaterial[] = []

  constructor(factory: BuildingFactory, geometry: HubGeometry) {
    this.factory = factory
    this.geometry = geometry
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

    const { plazaRadius, plazaExclusionMargin, moundRadius, moundHeight } = this.geometry
    return {
      entity: root,
      // Slightly larger than plaza so paths stop at the plaza rim with a
      // tiny breathing margin (prevents stepping stones landing on cobble).
      exclusionZone: { x, z, radius: plazaRadius + plazaExclusionMargin },
      // Collider wraps the whole raised mound — player can't step onto
      // the platform. Geometry is tied to the visual mound constants so
      // visual and collision stay in lockstep (0.05 is the plaza-to-
      // mound clearance applied in createMound; see there for details).
      trunkCollider: {
        x,
        z,
        radius: moundRadius,
        topY: 0.05 + moundHeight,
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
    const { plazaRadius } = this.geometry
    const plaza = new pc.Entity('HubPlaza')
    plaza.addComponent('render', { type: 'cylinder' })
    plaza.setLocalScale(plazaRadius * 2, 0.02, plazaRadius * 2)
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
    const { moundRadius, moundHeight } = this.geometry
    const mound = new pc.Entity('HubMound')
    mound.addComponent('render', { type: 'cylinder' })
    mound.setLocalScale(moundRadius * 2, moundHeight, moundRadius * 2)
    // Cylinder primitive is unit-height centered at origin, so after
    // scaling by moundHeight its bottom face sits at (localY - MH/2).
    // Plaza top is now at y=0.04 — seat the mound with 0.01 clearance
    // above it (bottom at y=0.05) so they aren't coplanar either.
    mound.setLocalPosition(0, 0.05 + moundHeight / 2, 0)

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

  /** Hero Bodhi tree on the mound top, center-aligned via AABB-correcting
   *  placeFurnitureCentered. Scale is applied after placement so it grows
   *  upward from the trunk base rather than drifting off-center. */
  private async placeHubTree(parent: pc.Entity): Promise<void> {
    const { moundHeight, treeScale } = this.geometry
    const tree = await this.factory.placeFurnitureCentered(
      parent, DECOR.hubTree, 0, 0.05 + moundHeight, 0,
    )
    tree.setLocalScale(treeScale, treeScale, treeScale)
  }

  /**
   * Ring of bushes + a few accent flowers around the mound perimeter.
   * Bushes read from the overhead camera (~0.8u tall) where raw flowers
   * disappear at this zoom. Flowers are interleaved as colored accents —
   * the eye catches them but the silhouette is carried by the bushes.
   */
  private async placeBushRing(parent: pc.Entity): Promise<void> {
    const { ringRadius, ringCount } = this.geometry
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
    for (let i = 0; i < ringCount; i++) {
      const theta = (i / ringCount) * Math.PI * 2
      const fx = Math.cos(theta) * ringRadius
      const fz = Math.sin(theta) * ringRadius
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
