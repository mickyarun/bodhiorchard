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

/** Frontend types mirroring backend TreeData schema. */

export interface LeafData {
  path: string
  age_days: number
  color: string
  branch_name: string
  has_bug: boolean
}

export interface BranchData {
  name: string
  file_count: number
  commit_count: number
  health: string
  bug_count: number
  leaves: LeafData[]
}

export interface BUDStageCount {
  bud: number
  design: number
  development: number
  testing: number
  uat: number
  prod: number
  closed: number
  discarded: number
}

export interface MemberActivity {
  user_id: string
  name: string
  email: string
  avatar_url: string | null
  care_pct: number
  top_modules: string[]
  character_model: string | null
  presence?: 'active' | 'on_break' | 'at_home'
  level?: number
  level_name?: string
  house_level?: number
}

export interface SecurityThreat {
  id: string
  title: string
  severity: string
  module: string | null
  branch_name: string | null
}

export interface AgentActivityItem {
  agent_name: string
  action: string
  timestamp: string
  status: string
  skill_slug?: string
  repo_name?: string | null
  bud_number?: number | null
  session_id?: string | null
  event_type?: string
  task_id?: string | null
  bud_title?: string | null
  impacted_repo_names?: string[]
}

export interface FeatureItem {
  title: string
  status: string
  source_ref: string | null
  branch_name: string | null
  repo_name: string | null
  from_bud: number | null
  linked_repos: string[]
  code_locations: Record<string, string[]> | null
  repo_code_locations?: Record<string, Record<string, string[]>> | null
  // "primary" — feature lives in repo_name. "backend" — shadow row
  // placed under a repo this feature calls; consumers that key by
  // repo_name (procedural tree, detail panels) should filter these out.
  link_role?: 'primary' | 'backend'
}

export interface BUDItem {
  bud_number: number
  title: string
  status: string
  branch_name: string | null
  repo_name: string | null
}

export interface RelationshipArc {
  source_branch: string
  target_branch: string
  source_repo: string
  target_repo: string
  rel_type: string
  weight: number
  feature_title?: string | null
}

export interface RepoLimbData {
  repo_name: string
  repo_path: string
  branches: BranchData[]
  total_files: number
  total_commits: number
  health: string
  growth_stage: 'sprout' | 'sapling' | 'medium' | 'mature'
}

export interface TreeData {
  org_id?: string
  symbol_count: number
  relationship_count: number
  total_files: number
  total_lines: number
  project_age_days: number
  repos: RepoLimbData[]
  branches: BranchData[]
  bud_stages: BUDStageCount
  total_features: number
  features: FeatureItem[]
  buds: BUDItem[]
  members: MemberActivity[]
  threats: SecurityThreat[]
  agent_activity: AgentActivityItem[]
  relationships: RelationshipArc[]
  feature_skills: FeatureSkillSummary[]
  // Superset of ``members``: includes every user with a feature-mapped
  // skill profile in this org, even non-OrgToUser contributors (e.g.
  // example-workspace authors). Detail panels use this so a feature
  // with real attribution still shows the developer who wrote it.
  contributors?: MemberActivity[]
}

export interface FeatureSkillSummary {
  feature_title: string
  developer_count: number
  developers: string[]
  top_developer_name: string | null
}
