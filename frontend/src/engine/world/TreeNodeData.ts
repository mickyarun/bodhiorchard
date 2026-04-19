// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * TreeNodeData — typed discriminated union for tree-world entity metadata.
 *
 * Replaces unsafe `_userData` casts with a Symbol-keyed accessor
 * that gives compile-time safety via TypeScript narrowing.
 *
 * Pattern source: engine/graph/GraphNodeData.ts
 */
import type * as pc from 'playcanvas'

// Symbol key prevents collisions with PlayCanvas internals
const TREE_DATA = Symbol('treeData')

// ─── Discriminated Union ─────────────────────────

export interface TreeRepoNodeData {
  type: 'tree_repo'
  repoName: string
  health: string
  growthStage: string
  branchCount: number
  totalFiles: number
  totalCommits: number
}

export interface TreeFeatureNodeData {
  type: 'tree_feature'
  title: string
  status: string
  repoName: string | null
  linkedRepos: string[]
  codeLocations: Record<string, string[]> | null
  branchName: string | null
  fromBud: number | null
  sourceRef: string | null
}

export interface TreeBudNodeData {
  type: 'tree_bud'
  budNumber: number
  title: string
  status: string
  repoName: string | null
}

export interface TreeThreatNodeData {
  type: 'tree_threat'
  id: string
  title: string
  severity: string
  module: string | null
}

export interface TreeRelNodeData {
  type: 'tree_relationship'
  sourceRepo: string
  targetRepo: string
  relType: string
  weight: number
}

export interface TreeHouseNodeData {
  type: 'tree_house'
  memberId: string
  memberName: string
}

export interface TreeAgentNodeData {
  type: 'tree_agent'
  agentKey: string
  skillSlug: string
  skillName: string
}

export type TreeNodeData =
  | TreeRepoNodeData
  | TreeFeatureNodeData
  | TreeBudNodeData
  | TreeThreatNodeData
  | TreeRelNodeData
  | TreeHouseNodeData
  | TreeAgentNodeData

// ─── Accessor Functions ──────────────────────────

/** Attach typed tree data to a PlayCanvas entity. */
export function setTreeData(entity: pc.Entity, data: TreeNodeData): void {
  (entity as unknown as Record<symbol, TreeNodeData>)[TREE_DATA] = data
}

/** Read typed tree data from a PlayCanvas entity (undefined if not set). */
export function getTreeData(entity: pc.Entity): TreeNodeData | undefined {
  return (entity as unknown as Record<symbol, TreeNodeData>)[TREE_DATA]
}
