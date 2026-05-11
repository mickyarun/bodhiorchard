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
 * RepoVisualization — Interface for how repos are rendered in 3D.
 *
 * The default implementation is TreeSystem (repos as trees).
 * Alternative implementations could render repos as crystals, planets,
 * buildings, etc. SceneManager depends on this interface, not on any
 * concrete implementation, so the visualization style is swappable.
 *
 * To create a new visualization:
 *   1. Create a class implementing RepoVisualization
 *   2. Register it via SceneManager.setRepoVisualization() or constructor config
 *   3. The class handles its own asset loading, entity creation, and cleanup
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { EngineData } from '../types'
import type { WorldLayout } from './WorldLayout'
import type { ExclusionZone } from '../utils/MathUtils'

export interface RepoVisualization {
  /** Build all repo visuals from data. Returns exclusion zones for scatter systems. */
  build(app: Application, data: EngineData, layout: WorldLayout): Promise<ExclusionZone[]>

  /** Get world-space position of a repo visual by name (for relationship arcs, camera focus). */
  getTreePosition(repoName: string): pc.Vec3 | null

  /** Get the entity for a repo visual (for picking, interaction). */
  getTreeEntity(repoName: string): pc.Entity | undefined

  /**
   * Toggle a single repo's visibility (dashboard repo-filter).
   * Implementations are responsible for hiding every entity that makes up
   * the repo's visual — typically a sibling-rooted set under app.root, not
   * a single anchor — and for ensuring distance-LOD or other update loops
   * don't re-enable hidden repos. Optional: implementations without
   * per-repo visibility just don't define this.
   */
  setRepoVisibility?(repoName: string, visible: boolean): void

  /**
   * Per-frame update for animated visualizations (optional).
   * `viewerPos`, when supplied, lets the implementation cull distant visuals
   * relative to a ground-level viewer (e.g. takeover-mode character). Pass
   * `null`/omit in modes where everything should always render.
   */
  update?(dt: number, viewerPos?: pc.Vec3 | null): void

  /** All entities tagged 'pickable' — repo containers + feature branches (optional). */
  getPickableEntities?(): pc.Entity[]

  /** Tear down all visuals and free GPU/CPU resources. */
  destroy(): void
}
