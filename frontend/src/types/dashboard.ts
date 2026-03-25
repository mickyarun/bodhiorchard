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
}

export interface FeatureSkillSummary {
  feature_title: string
  developer_count: number
  developers: string[]
  top_developer_name: string | null
}
