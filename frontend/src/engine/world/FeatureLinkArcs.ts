// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * FeatureLinkArcs — golden Bezier arcs between trees sharing cross-repo features.
 *
 * When a feature's linked_repos has 2+ entries, a golden arc connects the trees.
 * Labels at arc midpoints (billboard via LabelRenderer) shown on hover.
 *
 * Pattern sources:
 *   - ArcBuilder from engine/graph/ArcBuilder.ts (Bezier math)
 *   - GraphCrossRepoSystem (detection + arc construction)
 *   - LabelRenderer (billboard labels via Application.registerBillboard)
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { EngineFeature } from '../types'
import { ArcBuilder } from '../graph/ArcBuilder'
import { LabelRenderer } from '../rendering/LabelRenderer'

// ─── Constants ───────────────────────────────────

const GOLDEN_COLOR: [number, number, number] = [0.95, 0.75, 0.15]
const ARC_HEIGHT = 4
const ARC_SEGMENTS = 10
const SEGMENT_THICKNESS = 0.04
const ARC_OPACITY = 0.7

// ─── System ──────────────────────────────────────

export class FeatureLinkArcs {
  private app: Application | null = null
  private root: pc.Entity | null = null
  private matKeysUsed: string[] = []
  private arc = new ArcBuilder(ARC_SEGMENTS)
  private labels: pc.Entity[] = []
  private titleToLabelIdx = new Map<string, number>()
  private highlightedTitle: string | null = null
  private repoCountMap = new Map<string, number>()
  private visible = true

  /**
   * Build golden arcs for cross-repo features.
   * Returns the root entity to be added to the scene.
   */
  build(
    app: Application,
    materials: MaterialFactory,
    features: EngineFeature[],
    treePositions: Map<string, pc.Vec3>,
  ): pc.Entity {
    this.app = app
    this.root = new pc.Entity('FeatureLinkArcs')

    // Deduplicate features by title — collect unique cross-repo features
    const crossRepoFeatures = new Map<string, string[]>()
    for (const f of features) {
      if (f.linked_repos.length < 2) continue
      if (!crossRepoFeatures.has(f.title)) {
        crossRepoFeatures.set(f.title, f.linked_repos)
      }
    }

    if (crossRepoFeatures.size === 0) return this.root

    // Create shared golden material
    const matKey = 'golden_thread'
    this.matKeysUsed.push(matKey)
    const mat = materials.getColor(matKey, GOLDEN_COLOR[0], GOLDEN_COLOR[1], GOLDEN_COLOR[2], {
      metalness: 0,
      gloss: 0.5,
      opacity: ARC_OPACITY,
      emissive: [0.5, 0.4, 0.08],
    })

    // Build arcs for each cross-repo feature
    for (const [title, repos] of crossRepoFeatures) {
      this.repoCountMap.set(title, repos.length)

      // Connect all pairs of repos
      for (let i = 0; i < repos.length; i++) {
        for (let j = i + 1; j < repos.length; j++) {
          const posA = treePositions.get(repos[i])
          const posB = treePositions.get(repos[j])
          if (!posA || !posB) continue

          const arcParent = new pc.Entity(`GoldenArc_${title.slice(0, 15)}_${repos[i]}_${repos[j]}`)
          this.arc.buildSegments(posA, posB, ARC_HEIGHT, SEGMENT_THICKNESS, mat, arcParent, 'GA')
          this.root.addChild(arcParent)
        }
      }

      // Create label at midpoint of first pair
      if (repos.length >= 2) {
        const posA = treePositions.get(repos[0])
        const posB = treePositions.get(repos[1])
        if (posA && posB) {
          const label = LabelRenderer.create(app, title, {
            bgColor: 'rgba(120, 90, 10, 0.85)',
            textColor: '#FFF8E1',
          })
          label.setLocalPosition(
            (posA.x + posB.x) / 2,
            (posA.y + posB.y) / 2 + ARC_HEIGHT * 0.8,
            (posA.z + posB.z) / 2,
          )
          label.enabled = false
          app.registerBillboard(label)
          this.root.addChild(label)
          this.titleToLabelIdx.set(title, this.labels.length)
          this.labels.push(label)
        }
      }
    }

    return this.root
  }

  /** Toggle visibility of all golden arcs. */
  setVisible(visible: boolean): void {
    this.visible = visible
    if (this.root) this.root.enabled = visible
    if (!visible) {
      for (const label of this.labels) label.enabled = false
      this.highlightedTitle = null
    }
  }

  /** Toggle visibility. Returns new visible state. */
  toggle(): boolean {
    this.setVisible(!this.visible)
    return this.visible
  }

  /** Show label for a specific feature title (on hover). null hides all. */
  showLabelForTitle(title: string | null): void {
    // Hide previous
    if (this.highlightedTitle) {
      const prevIdx = this.titleToLabelIdx.get(this.highlightedTitle)
      if (prevIdx !== undefined) this.labels[prevIdx].enabled = false
    }
    this.highlightedTitle = title
    // Show new
    if (title && this.visible) {
      const idx = this.titleToLabelIdx.get(title)
      if (idx !== undefined) this.labels[idx].enabled = true
    }
  }

  /** Get the number of repos a feature spans (1 = single-repo). */
  getRepoCount(title: string): number {
    return this.repoCountMap.get(title) ?? 1
  }

  /** Release materials, unregister billboards, destroy entities. */
  destroy(materials: MaterialFactory): void {
    // Unregister billboard labels BEFORE entity destruction
    if (this.app) {
      for (const label of this.labels) {
        this.app.unregisterBillboard(label)
        LabelRenderer.cleanup(this.app, label)
      }
    }
    this.labels = []
    this.titleToLabelIdx.clear()
    this.highlightedTitle = null
    this.repoCountMap.clear()

    for (const key of this.matKeysUsed) {
      materials.release(key)
    }
    this.matKeysUsed = []

    if (this.root) {
      this.root.destroy()
      this.root = null
    }
    this.app = null
  }
}
