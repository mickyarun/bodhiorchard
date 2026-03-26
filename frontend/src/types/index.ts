export type { SetupState, StepDefinition } from './setup'

export type UserRoleName =
  | 'org_owner'
  | 'admin'
  | 'pm'
  | 'tech_lead'
  | 'manager'
  | 'developer'
  | 'designer'
  | 'qa'
  | 'support'
  | 'viewer'

export interface User {
  id: string
  email: string
  name: string
  role: UserRoleName
  permissions: string[]
  organizationId: string
}

export interface Organization {
  id: string
  name: string
  slug: string
}

export interface ApiError {
  message: string
  code: string
  details?: Record<string, string[]>
}

export type BUDStatus = 'bud' | 'design' | 'tech_arch' | 'development' | 'code_review' | 'testing' | 'uat' | 'prod' | 'closed' | 'discarded'

// Canonical BUD section config: DB field → { tab slug, label, exportable }
// Backend has a mirror in backend/app/schemas/bud.py → BUD_SECTIONS.
export const BUD_SECTIONS = {
  requirements_md: { tab: 'requirements', label: 'Requirements', exportable: true },
  tech_spec_md: { tab: 'tech-spec', label: 'Tech Spec', exportable: true },
  development: { tab: 'development', label: 'Development', exportable: false },
  test_plan_md: { tab: 'test-plan', label: 'Test Plan', exportable: true },
  design: { tab: 'design', label: 'Design', exportable: false },
} as const

export type BUDSectionKey = keyof typeof BUD_SECTIONS
export type BUDTabValue = (typeof BUD_SECTIONS)[BUDSectionKey]['tab']

// Derived helpers
export const VALID_BUD_TABS = new Set(
  Object.values(BUD_SECTIONS).map(s => s.tab),
) as ReadonlySet<string>

export const TAB_TO_SECTION: Record<string, BUDSectionKey> = Object.fromEntries(
  Object.entries(BUD_SECTIONS).map(([k, v]) => [v.tab, k]),
) as Record<string, BUDSectionKey>

export interface BUDListItem {
  id: string
  bud_number: number
  title: string
  status: BUDStatus
  assignee_id: string | null
  assignee_name: string | null
  created_at: string
  updated_at: string
}

export interface BUDAgentTask {
  id: string
  task_type: string
  skill_slug: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  job_id: string | null
  attempt: number
  status_message: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface BUDDocument extends BUDListItem {
  org_id: string
  requirements_md: string | null
  tech_spec_md: string | null
  test_plan_md: string | null
  designs: BUDDesign[]
  metadata: Record<string, unknown> | null
  active_agent_task: BUDAgentTask | null
}

// ── Timeline Types ──────────────────────────────────────────
export interface TimelineEvent {
  id: string
  event_type: string
  actor_name: string | null
  detail: Record<string, unknown> | null
  created_at: string
}

// ── Dev Activity Types ───────────────────────────────────────────
export interface DevActivity {
  id: string
  status: 'in_progress' | 'completed' | 'failed' | 'blocked'
  message: string
  source: 'mcp' | 'hook' | 'agent'
  actor_name: string | null
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface DevCommit {
  commit_sha: string
  commit_message: string
  branch_name: string
  files_changed: string
  repo_path: string
  created_at: string
}

export interface DevCommitRepo {
  repo_path: string
  repo_name: string
  commit_count: number
  first_sha: string
  last_sha: string
}

export interface DevStats {
  total_commits: number
  total_files_changed: number
  repos_touched: number
  agent_runs: number
  effectiveness_score: number
  confidence: number
  completion_rate: number
  cost_per_commit: number
  total_cost_usd: number
  test_coverage: string
  risk_count: number
}

export interface DevActivityResponse {
  activities: DevActivity[]
  commits: DevCommit[]
  repos: DevCommitRepo[]
  stats: DevStats
}

// ── BUD Design Types ─────────────────────────────────────────────
export type BUDDesignStatus = 'pending' | 'generating' | 'ready' | 'failed'

export interface BUDDesign {
  id: string
  bud_id: string
  repo_id: string | null
  repo_name: string | null
  design_html: string | null
  design_path: string | null
  notes: string | null
  status: BUDDesignStatus
  job_id: string | null
  created_at: string
  updated_at: string
}

export interface DesignJobCreated {
  designId: string
  repoId: string | null
  jobId: string
}

// ── Design System Types ──────────────────────────────────────────
export interface DesignSystemRead {
  id: string
  orgId: string
  repoId: string
  repoName: string | null
  isDefault: boolean
  content: string
  sourceHash: string | null
  extractedAt: string
  createdAt: string | null
  updatedAt: string | null
}

export const BUD_STATUS_ORDER: BUDStatus[] = [
  'bud', 'design', 'tech_arch', 'development', 'code_review', 'testing', 'uat', 'prod', 'closed', 'discarded',
]

export const BUD_STATUS_LABELS: Record<BUDStatus, string> = {
  'bud': 'BUD',
  'design': 'Design',
  'tech_arch': 'Tech Architecture',
  'development': 'Development',
  'code_review': 'Code Review',
  'testing': 'Testing',
  'uat': 'UAT',
  'prod': 'Prod',
  'closed': 'Closed',
  'discarded': 'Discarded',
}

// Knowledge / Features types
export interface KnowledgeItem {
  id: string
  title: string
  content: string | null
  category: string
  tags: string[] | null
  source: string | null
  sourceRef: string | null
  featureStatus: string | null
  repoIds: string[]
}

export interface KnowledgeSearchResult extends KnowledgeItem {
  score: number
}

export const KNOWLEDGE_CATEGORIES = [
  { value: '', label: 'All' },
  { value: 'feature_registry', label: 'Features' },
  { value: 'code_doc', label: 'Code Docs' },
  { value: 'api_pattern', label: 'API Patterns' },
  { value: 'architecture', label: 'Architecture' },
  { value: 'convention', label: 'Conventions' },
] as const

export const FEATURE_STATUS_COLORS: Record<string, string> = {
  planned: 'info',
  in_progress: 'warning',
  implemented: 'success',
}

// Skill Profile types
export interface ModuleSkill {
  name: string
  score: number
  languages: string[]
  touchCount: number
}

export interface SkillProfile {
  userId: string | null
  userName: string
  email: string
  modules: ModuleSkill[]
}

// Repo types
export interface RepoInfo {
  id: string
  path: string
  name: string
  status: 'active' | 'ignored' | 'removed'
  lastScanned: string | null
  sha: string | null
  knowledgeCount: number
  featureCount: number
  mainBranch: string | null
  developBranch: string | null
  hasUncommittedChanges: boolean
  repoType: string | null
  setupStatus: 'merged' | 'not_setup'
}

export interface RepoBranchList {
  branches: string[]
  currentMain: string | null
  currentDevelop: string | null
}

export const BUD_STATUS_COLORS: Record<BUDStatus, string> = {
  'bud': 'brown',
  'design': 'teal',
  'tech_arch': 'deep-purple',
  'development': 'primary',
  'code_review': 'indigo',
  'testing': 'purple',
  'uat': 'orange',
  'prod': 'success',
  'closed': 'blue-grey',
  'discarded': 'grey',
}

// ── Job Queue Types ───────────────────────────────────────────────
export type JobState = 'queued' | 'running' | 'completed' | 'failed'

export interface JobStatusRead {
  jobId: string
  jobType: string
  state: JobState
  statusMessage: string
  progressPct: number
  result: unknown
  error: string | null
}

export interface JobCreatedResponse {
  jobId: string
}

// ── Chat Message Types ──────────────────────────────────────────
export interface ChatMessageRead {
  id: string
  role: 'user' | 'ai'
  message: string
  user_id: string | null
  session_id: string | null
  user_name: string | null
  created_at: string
}

// ── Notification Types ──────────────────────────────────────────
export type NotificationType =
  | 'job_completed'
  | 'job_failed'
  | 'approval_requested'
  | 'approval_granted'
  | 'approval_rejected'
  | 'developer_assigned'
  | 'reassignment_done'

export interface AppNotification {
  id: string
  type: NotificationType
  jobId: string | null
  jobType: string | null
  title: string
  message: string | null
  deepLink: string | null
  isRead: boolean
  isDismissed: boolean
  createdAt: string
}
