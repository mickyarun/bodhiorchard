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

  /** Per-frame update for animated visualizations (optional). */
  update?(dt: number): void

  /** All entities tagged 'pickable' — repo containers + feature branches (optional). */
  getPickableEntities?(): pc.Entity[]

  /** Tear down all visuals and free GPU/CPU resources. */
  destroy(): void
}
