/**
 * GraphTypes — shared callback types for the graph module.
 *
 * Extracted to avoid circular imports between GraphEngine and GraphPickingSystem.
 */

export interface GraphRepoInfo {
  repoName: string
  health: string
  growthStage: string
  totalFiles: number
  totalCommits: number
}

export interface GraphFeatureInfo {
  title: string
  status: string
  repoName: string | null
  sourceRef: string | null
  fromBud: number | null
  branchName: string | null
}

export interface GraphCallbacks {
  onRepoClick?: (info: GraphRepoInfo) => void
  onFeatureClick?: (info: GraphFeatureInfo) => void
  onHover?: (
    tooltip: { text: string; screenX: number; screenY: number } | null,
  ) => void
  onReady?: () => void
}
