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
 * GraphDimSystem — manages opacity dimming for focus modes.
 *
 * When a user clicks a feature or developer, unrelated nodes dim to 30% opacity.
 * Uses 2 shared dim materials (repo and feature variants) to avoid per-entity
 * material creation. Original materials stored in a WeakMap for safe restoration.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'

const DIM_OPACITY = 0.3
const DIM_REPO_COLOR: [number, number, number] = [0.3, 0.3, 0.35]
const DIM_FEAT_COLOR: [number, number, number] = [0.25, 0.25, 0.3]

export class GraphDimSystem {
  private materials: MaterialFactory
  private dimRepMat: pc.StandardMaterial | null = null
  private dimFeatMat: pc.StandardMaterial | null = null
  private dimmedEntities = new Set<pc.Entity>()
  private originalMaterials = new WeakMap<pc.Entity, pc.Material>()
  private matKeys: string[] = []

  constructor(materials: MaterialFactory) {
    this.materials = materials
  }

  /** Initialize shared dim materials. Call after MaterialFactory is ready. */
  init(): void {
    this.dimRepMat = this.materials.getColor('gn_dim_repo', ...DIM_REPO_COLOR, {
      metalness: 0,
      gloss: 0.2,
      opacity: DIM_OPACITY,
    })
    this.matKeys.push('gn_dim_repo')

    this.dimFeatMat = this.materials.getColor('gn_dim_feat', ...DIM_FEAT_COLOR, {
      metalness: 0,
      gloss: 0.2,
      opacity: DIM_OPACITY,
    })
    this.matKeys.push('gn_dim_feat')
  }

  /**
   * Dim all nodes except those in the active set.
   * Repo-prefixed IDs use the repo dim material; others use the feature dim material.
   */
  dimExcept(
    activeEntityIds: Set<string>,
    nodeEntities: Map<string, pc.Entity>,
  ): void {
    this.restore()

    for (const [entityId, entity] of nodeEntities) {
      if (activeEntityIds.has(entityId)) continue
      if (!entity.render?.meshInstances.length) continue

      const mi = entity.render.meshInstances[0]
      const dimMat = entityId.startsWith('repo_') ? this.dimRepMat : this.dimFeatMat
      if (!dimMat) continue

      this.originalMaterials.set(entity, mi.material)
      mi.material = dimMat
      this.dimmedEntities.add(entity)
    }
  }

  /** Restore all dimmed entities to their original materials. */
  restore(): void {
    for (const entity of this.dimmedEntities) {
      if (!entity.render?.meshInstances.length) continue
      const original = this.originalMaterials.get(entity)
      if (original) {
        entity.render.meshInstances[0].material = original
      }
    }
    this.dimmedEntities.clear()
  }

  /** Check if any nodes are currently dimmed. */
  isDimmed(): boolean {
    return this.dimmedEntities.size > 0
  }

  /** Release dim materials. */
  destroy(): void {
    this.dimmedEntities.clear()
    for (const key of this.matKeys) {
      this.materials.release(key)
    }
    this.matKeys = []
    this.dimRepMat = null
    this.dimFeatMat = null
  }
}
