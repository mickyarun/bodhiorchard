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
 * GraphNodeData — typed discriminated union for graph node metadata.
 *
 * Replaces unsafe `_userData` casts with a Symbol-keyed accessor
 * that gives compile-time safety via TypeScript narrowing.
 */
import type * as pc from 'playcanvas'

// Symbol key prevents collisions with PlayCanvas internals
const GRAPH_DATA = Symbol('graphData')

// ─── Discriminated Union ─────────────────────────

export interface GraphRepoData {
  type: 'graph_repo'
  repoName: string
  health: string
  growthStage: string
  totalFiles: number
  totalCommits: number
}

export interface GraphFeatureData {
  type: 'graph_feature'
  title: string
  status: string
  repoName: string | null
  sourceRef: string | null
  fromBud: number | null
  branchName: string | null
  linkedRepos: string[]
  codeLocations: Record<string, string[]> | null
}

export type GraphNodeData = GraphRepoData | GraphFeatureData

// ─── Accessor Functions ──────────────────────────

/** Attach typed graph data to a PlayCanvas entity. */
export function setGraphData(entity: pc.Entity, data: GraphNodeData): void {
  (entity as unknown as Record<symbol, GraphNodeData>)[GRAPH_DATA] = data
}

/** Read typed graph data from a PlayCanvas entity (undefined if not set). */
export function getGraphData(entity: pc.Entity): GraphNodeData | undefined {
  return (entity as unknown as Record<symbol, GraphNodeData>)[GRAPH_DATA]
}
