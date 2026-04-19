// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Engine-specific types — self-contained data contract.
 * No imports from @/stores, @/types, @/views, etc.
 * The Vue layer adapts app types to these before calling setData().
 */

// ─── Shared Unions ──────────────────────────────────

export type RepoHealth = 'thriving' | 'healthy' | 'dormant' | 'wilted'
export type ThreatSeverity = 'low' | 'medium' | 'high' | 'critical'
export type BUDStatus = 'bud' | 'design' | 'development' | 'testing' | 'uat' | 'prod' | 'closed' | 'discarded'
export type RelType = 'CALLS' | 'IMPORTS' | 'EXTENDS' | 'IMPLEMENTS'

// ─── Repo / Tree Data ───────────────────────────────

export interface EngineLeafData {
  path: string
  age_days: number
  color: string
  branch_name: string
  has_bug: boolean
}

export interface EngineBranchData {
  name: string
  file_count: number
  commit_count: number
  health: RepoHealth
  bug_count: number
  leaves: EngineLeafData[]
}

export interface EngineRepoData {
  repo_name: string
  repo_path: string
  branches: EngineBranchData[]
  total_files: number
  total_commits: number
  health: RepoHealth
  growth_stage: 'sprout' | 'sapling' | 'medium' | 'mature'
}

// ─── Features / BUDs / Threats ──────────────────────

export interface EngineFeature {
  title: string
  status: string
  source_ref: string | null
  branch_name: string | null
  repo_name: string | null
  from_bud: number | null
  linked_repos: string[]
  code_locations: Record<string, string[]> | null
}

export interface EngineBUD {
  bud_number: number
  title: string
  status: BUDStatus
  branch_name: string | null
  repo_name: string | null
}

export interface EngineThreat {
  id: string
  title: string
  severity: ThreatSeverity
  module: string | null
  branch_name: string | null
}

// ─── Members / Agents ───────────────────────────────

export type PresenceState = 'active' | 'on_break' | 'at_home'

export interface EngineMember {
  user_id: string
  name: string
  email: string
  avatar_url: string | null
  care_pct: number
  top_modules: string[]
  character_model: string | null
  presence?: PresenceState
  level?: number
  level_name?: string
  house_level?: number
}

export interface EngineAgentActivity {
  agent_name: string
  action: string
  timestamp: string
  status: string
  skill_slug: string
  repo_name: string | null
  bud_number: number | null
  session_id: string | null
  event_type: string
  task_id: string | null
  bud_title: string | null
  impacted_repo_names: string[]
}

// ─── Feature Skills (Bus Factor) ────────────────────

export interface EngineFeatureSkill {
  feature_title: string
  developer_count: number
  developers: string[]
  top_developer_name: string | null
}

// ─── Relationships ──────────────────────────────────

export interface EngineRelationship {
  source_branch: string
  target_branch: string
  source_repo: string
  target_repo: string
  rel_type: RelType
  weight: number
}

// ─── Top-level Data Contract ────────────────────────

export interface EngineData {
  repos: EngineRepoData[]
  features: EngineFeature[]
  buds: EngineBUD[]
  threats: EngineThreat[]
  members: EngineMember[]
  agent_activity: EngineAgentActivity[]
  relationships: EngineRelationship[]
  feature_skills: EngineFeatureSkill[]
}

// ─── Callback Events ────────────────────────────────

export interface EngineTreeInfo {
  repoName: string
  health: RepoHealth
  growthStage: string
  branchCount: number
  totalFiles: number
  totalCommits: number
}

export interface EngineCharacterInfo {
  name: string
  modelName: string
  isAgent: boolean
  careMode: 'water' | 'fertilizer' | null
  member: EngineMember | null
}

export interface EngineHouseInfo {
  memberId: string
  name: string
  activity: ActivityState
}

export interface EngineFeatureInfo {
  title: string
  status: string
  repoName: string | null
  linkedRepos: string[]
  codeLocations: Record<string, string[]> | null
  branchName: string | null
  fromBud: number | null
  sourceRef: string | null
}

// ─── Time / Activity ────────────────────────────────

export type ActivityState =
  | 'sleeping'
  | 'home'
  | 'coffee_bar'
  | 'cafeteria'
  | 'pool_resort'

export type DayPeriod = 'weekday' | 'weekend'

export interface EngineAgentInfo {
  agentKey: string
  skillSlug: string
  skillName: string
}

// ─── Engine Callbacks ───────────────────────────────

export interface EngineCallbacks {
  onSceneReady?: () => void
  onTreeClick?: (info: EngineTreeInfo) => void
  onDeveloperClick?: (info: EngineCharacterInfo) => void
  onHouseClick?: (info: EngineHouseInfo) => void
  onFeatureClick?: (info: EngineFeatureInfo) => void
  onAgentClick?: (info: EngineAgentInfo) => void
  onHover?: (tooltip: { text: string; screenX: number; screenY: number } | null) => void
  onZoneEnter?: (zone: string) => void
  onZoneExit?: (zone: string) => void
}

// ─── Event Bus Types ────────────────────────────────

export interface EngineEvents {
  'scene:ready': void
  'scene:resize': { width: number; height: number }
  'scene:destroy': void
  'data:set': EngineData
  'camera:mode': 'overview' | 'play'
  'camera:focus': { x: number; y: number; z: number; distance?: number }
  'pick:click': { type: string; id: string; data: Record<string, unknown> }
  'pick:hover': { text: string; screenX: number; screenY: number } | null
  'interior:enter': { memberId: string; memberName: string }
  'interior:exit': void
}
