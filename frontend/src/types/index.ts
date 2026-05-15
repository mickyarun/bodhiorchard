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
  // Wire field is snake_case (UserRead.org_id in backend/app/schemas/user.py)
  // and there's no axios snake→camel transformer, so this MUST stay
  // ``org_id`` to be readable at runtime.
  org_id: string
  character_model: string | null
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
  code_review: { tab: 'code-review', label: 'Code Review', exportable: false },
  testing: { tab: 'testing', label: 'Testing', exportable: false },
  design: { tab: 'design', label: 'Design', exportable: false },
} as const

export type BUDSectionKey = keyof typeof BUD_SECTIONS
export type BUDTabValue = (typeof BUD_SECTIONS)[BUDSectionKey]['tab']

// Tabs that don't correspond to a BUD_SECTIONS entry but are still
// valid for ?tab= deep-linking. Release-stage tabs (uat, prod) are
// observational \u2014 they have no markdown content, no exportable section,
// and no editor \u2014 so they don't fit the BUD_SECTIONS shape, but the
// router still needs to accept them as valid tab params.
const NON_SECTION_BUD_TABS = ['uat', 'prod', 'closed'] as const

// Derived helpers
export const VALID_BUD_TABS = new Set([
  ...Object.values(BUD_SECTIONS).map(s => s.tab),
  ...NON_SECTION_BUD_TABS,
]) as ReadonlySet<string>

export const TAB_TO_SECTION: Record<string, BUDSectionKey> = Object.fromEntries(
  Object.entries(BUD_SECTIONS).map(([k, v]) => [v.tab, k]),
) as Record<string, BUDSectionKey>

// Phase that owns each section — only when bud.status equals this value
// is the section editable. Sections without an entry (development) have
// no markdown editor at all. Backend mirror lives in
// backend/app/services/bud_edit_policy.py and the two MUST stay in sync.
export const SECTION_EDIT_STATUS: Partial<Record<BUDSectionKey, BUDStatus>> = {
  requirements_md: 'bud',
  design: 'design',
  tech_spec_md: 'tech_arch',
  code_review: 'code_review',
  testing: 'testing',
}

export function isSectionEditable(
  section: BUDSectionKey,
  status: BUDStatus | undefined | null,
): boolean {
  const required = SECTION_EDIT_STATUS[section]
  if (!required) return false
  return status === required
}

// Phase that owns each section for chat. Mirrors backend
// SECTION_REQUIRED_STAGES in app/schemas/bud_constants.py. Sections
// absent from this map are not chattable at any stage (code_review,
// test_plan_md). Slightly tighter than SECTION_EDIT_STATUS because
// code_review is read-only by design.
export const SECTION_CHAT_STAGES: Partial<Record<BUDSectionKey, BUDStatus>> = {
  requirements_md: 'bud',
  tech_spec_md: 'tech_arch',
  design: 'design',
  testing: 'testing',
}

export function isSectionChatable(
  section: BUDSectionKey,
  status: BUDStatus | undefined | null,
): boolean {
  const required = SECTION_CHAT_STAGES[section]
  if (!required) return false
  return status === required
}

// Human-readable labels for UserRoleName — single source of truth so
// banners, member dropdowns, and invite views all render the same
// string. Keep keys in sync with UserRoleName above.
export const ROLE_LABELS: Record<UserRoleName, string> = {
  org_owner: 'Org Owner',
  admin: 'Admin',
  pm: 'Product Manager',
  tech_lead: 'Tech Lead',
  manager: 'Manager',
  developer: 'Developer',
  designer: 'Designer',
  qa: 'QA',
  support: 'Support',
  viewer: 'Viewer',
}

export interface BUDListItem {
  id: string
  bud_number: number
  title: string
  status: BUDStatus
  complexity: number | null
  prod_p70_date: string | null
  current_phase_deadline: string | null
  assignee_id: string | null
  assignee_name: string | null
  open_bug_count: number
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
  qa_automation_cases: AutomationTestCase[] | null
  qa_manual_cases: ManualTestCase[] | null
  qa_execution_plan_md: string | null
  designs: BUDDesign[]
  metadata: Record<string, unknown> | null
  impacted_repos: { repo_id: string; repo_name: string }[] | null
  estimated_dates: Record<string, PhaseEstimateData> | null
  code_review_comments: CodeReviewComment[] | null
  active_agent_task: BUDAgentTask | null
  // Mid-flight phase worker (assignment / todo-gen / estimation). Returned
  // by GET /buds/{id} so the progress banner re-attaches after a route
  // change — synthetic skills don't have BUDAgentTask rows, so this is
  // the only signal the banner has for phase chains on remount.
  active_phase_worker: { skill_slug: string; message: string } | null
  // Sticky last-failed-phase banner. Most recent unresolved skill_failed
  // event for this BUD (later skill_completed for same slug clears it),
  // newer than the user's last dismissal. Cleared by POSTing to
  // /buds/{id}/phase-failure/dismiss.
  last_phase_failure: {
    skill_slug: string
    message: string
    failed_at: string | null
    metadata: Record<string, unknown>
  } | null
}

// ── BUD TODO Types ────────────────────────────────────────

export type BUDTodoStatus = 'pending' | 'in_progress' | 'completed' | 'blocked'

export interface BUDTodo {
  id: string
  budId: string
  sequence: number
  title: string
  description: string | null
  phase: string
  status: BUDTodoStatus
  isCheckpoint: boolean
  repoName: string | null
  codeLocations: string[]
  assigneeId: string | null
  assigneeName: string | null
  contextMd: string | null
  summary: string | null
  takenAt: string | null
  detail: Record<string, unknown> | null
  createdAt: string
  updatedAt: string
}

export interface CodeReviewComment {
  github_comment_id?: number
  review_id?: number
  repo: string
  file: string
  line: number
  body: string
  author: string
  html_url?: string
  created_at?: string
  is_summary?: boolean
  source?: string
}

// ── Estimation Types ──────────────────────────────────────

export interface PhaseEstimateData {
  estimated_completion: string
  p50_date: string | null
  p70_date: string | null
  p85_date: string | null
  expected_days: number | null
  std_dev_days: number | null
  source: 'ai_pert' | 'override'
  confidence: number
  override_reason: string | null
}

export interface BUDEstimates {
  bud_id: string
  complexity: number | null
  phases: PhaseEstimate[]
  prod_p50: string | null
  prod_p70: string | null
  prod_p85: string | null
  // Critical Chain Method fields. ``project_buffer_days`` aggregates
  // per-phase variance via Goldratt's √Σ formula; ``commit_date`` is
  // the date stakeholders should commit to (prod-P50 + buffer).
  // Both nullable for backward compat with snapshots persisted before
  // Phase D landed — render falls back to "no buffer" gracefully.
  project_buffer_days: number | null
  commit_date: string | null
  generated_at: string | null
  trigger: string | null
}

export interface PhaseEstimate {
  phase: string
  estimated_completion: string
  p50_date: string | null
  p70_date: string | null
  p85_date: string | null
  expected_days: number | null
  std_dev_days: number | null
  source: string
  confidence: number
  override_reason: string | null
}

// ── QA Test Case Types ─────────────────────────────────────

export interface AutomationTestCase {
  id: string
  title: string
  type: 'e2e' | 'integration' | 'unit' | 'api'
  gherkin: string
  input: string
  expected_output: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  tags: string[]
}

export interface ManualTestCase {
  id: string
  title: string
  description: string
  preconditions: string
  steps: string[]
  expected_result: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  category: 'functional' | 'usability' | 'accessibility' | 'security'
  result: 'pending' | 'pass' | 'fail' | 'blocked' | 'skipped'
  evidence: TestEvidence[]
  tester_name: string | null
  tested_at: string | null
  notes?: string
}

export interface TestEvidence {
  id: string
  test_case_id: string
  filename: string
  mime_type: string
  uploaded_by: string | null
  created_at: string
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
  event_type: string
  status: string
  message: string | null
  source: string
  actor_name: string | null
  session_id: string | null
  branch: string | null
  commit_sha: string | null
  file_path: string | null
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface DevCommit {
  commit_sha: string
  commit_message: string
  branch_name: string
  files_changed: string
  repo_path: string
  author_name: string | null
  author_email: string | null
  user_id: string | null
  user_name: string | null
  created_at: string
}

export interface DevContributor {
  user_id: string | null
  user_name: string | null
  author_name: string | null
  author_email: string | null
  commit_count: number
  files_changed: number
  commits: DevCommit[]
}

export interface DevCommitRepo {
  repo_path: string
  repo_name: string
  commit_count: number
  first_sha: string
  last_sha: string
}

/**
 * A repo that has commits for a BUD but is NOT in tracked_repositories.
 *
 * Surfaced separately from DevCommitRepo so the BUD detail testing tab
 * can render an "Add as tracked" CTA. The QA tester ran Claude Code in
 * a path the org hasn't added yet — the row exists in dev_activity_logs
 * but couldn't resolve to a tracked_repositories.id.
 */
export interface UntrackedRepo {
  repo_path: string
  name: string
  commit_count: number
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
  contributors: DevContributor[]
  repos: DevCommitRepo[]
  untracked_repos: UntrackedRepo[]
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

// Feature types — match backend app/schemas/feature.py response shape.
export interface PrimaryLink {
  repoId: string
  repoName: string
  codeLocations: Record<string, string[]> | null
}

export interface BackendLink {
  repoId: string
  repoName: string
  apiPaths: string[]
  codeLocations: Record<string, string[]> | null
}

export interface Feature {
  id: string
  featureTitle: string
  description: string
  capabilities: Record<string, unknown>
  clusterNames: string[]
  tags: string[]
  featureStatus: string | null
  source: string | null
  sourceRef: string | null
  synthesizedAt: string
  primary: PrimaryLink
  backendLinks: BackendLink[]
}

export interface FeaturePage {
  items: Feature[]
  total: number
}

export interface LinkedFeature {
  id: string
  title: string
  linkType: 'touches' | 'depends_on'
  source: 'pm_agent' | 'manual' | 'tech_arch'
  repoId: string | null
  repoName: string | null
  codeLocations: Record<string, string[]> | null
}

export interface LinkFeaturesResponse {
  insertedCount: number
  insertedFeatureIds: string[]
}

export interface FeaturesByRepo {
  repoId: string
  repoName: string
  featureCount: number
  features: Feature[]
}

export interface RepoContributor {
  userId: string | null
  actorName: string
  commitCount: number
  filesChanged: number
}

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
export type LastScanStatus
  = | 'queued' | 'running' | 'done' | 'failed' | 'skipped_unchanged' | 'cancelled'

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
  uatBranch: string | null
  hasUncommittedChanges: boolean
  setupStatus: 'merged' | 'not_setup'
  /** MCP setup-PR tracking. `setupBranchPushedAt` is the only signal
   *  that distinguishes "first scan never ran" from "branch on origin
   *  but no PR" (GitHub App not configured). `setupCompareUrl` is
   *  derived server-side, so the row chip just needs an anchor href. */
  setupBranchPushedAt?: string | null
  setupPrUrl?: string | null
  setupPrNumber?: number | null
  setupPrState?: 'open' | 'merged' | 'closed' | null
  setupCompareUrl?: string | null
  designSystemStatus: 'none' | 'extracting' | 'ready'
  /** Status of the most recent ScanRepoRun for this repo across all
   *  scans. `null` when never scanned. Drives the recency pill on the
   *  Settings → Code list when the row isn't part of the live scan. */
  lastScanStatus?: LastScanStatus | null
  lastScanFinishedAt?: string | null
  lastScanStartedAt?: string | null
  lastScanFeatureCount?: number | null
  lastScanId?: string | null
  /** Architectural classification produced by the ``classify_repo``
   *  scan stage. ``null`` until the first scan touches the repo (or
   *  the user hits the manual classify endpoint). */
  repoLayer?: RepoLayer | null
  techStack?: string | null
  dbFlavor?: string | null
}

/** Mirrors `app.models.repo_layer.RepoLayer`. */
export type RepoLayer
  = | 'frontend' | 'backend' | 'processor' | 'batch' | 'db' | 'shared'

export interface RepoBranchList {
  branches: string[]
  currentMain: string | null
  currentDevelop: string | null
  currentUat: string | null
}

// ── BUD Release Stage Types ────────────────────────────────────────
export type ReleaseStage = 'uat' | 'prod'
export type ReleaseStageStatus = 'not_reached' | 'in_stage' | 'passed'

export interface ReleasePR {
  prNumber: number
  repoName: string
  htmlUrl: string
  title: string | null
  authorLogin: string | null
  mergedAt: string | null
}

export interface ReleaseCommit {
  sha: string
  shortSha: string
  message: string | null
  repoName: string
}

export interface ReleaseTimelineEvent {
  occurredAt: string
  prNumber: number
  repoName: string
  htmlUrl: string
}

export interface BUDReleaseStage {
  budId: string
  stage: ReleaseStage
  status: ReleaseStageStatus
  firstReachedAt: string | null
  releasePRs: ReleasePR[]
  openPRs: ReleasePR[]
  commits: ReleaseCommit[]
  events: ReleaseTimelineEvent[]
}

// ── Bug Types ────────────────────────────────────────────────────
export type BugSeverity = 'low' | 'medium' | 'high' | 'critical'
export type BugStatusValue = 'open' | 'in-progress' | 'resolved' | 'closed' | 'blocked'
export type BugType = 'testing' | 'production'

export interface BugListItem {
  id: string
  title: string
  severity: BugSeverity
  status: BugStatusValue
  bugType: BugType
  module: string | null
  budId: string | null
  budNumber: number | null
  reporterName: string | null
  assigneeName: string | null
  createdAt: string
}

export interface BugRead {
  id: string
  title: string
  description: string | null
  severity: BugSeverity
  status: BugStatusValue
  bugType: BugType
  module: string | null
  linkedPr: string | null
  budId: string | null
  budNumber: number | null
  budTitle: string | null
  reporterId: string
  reporterName: string | null
  assigneeId: string | null
  assigneeName: string | null
  resolvedAt: string | null
  createdAt: string
  updatedAt: string
}

export interface BugListResponse {
  items: BugListItem[]
  total: number
  page: number
  pageSize: number
}

export const BUG_SEVERITY_COLORS: Record<BugSeverity, string> = {
  low: 'grey',
  medium: 'warning',
  high: 'orange',
  critical: 'error',
}

export const BUG_STATUS_COLORS: Record<BugStatusValue, string> = {
  open: 'error',
  'in-progress': 'warning',
  resolved: 'success',
  closed: 'grey',
  blocked: 'purple',
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
export type JobState = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface JobStatusRead {
  jobId: string
  jobType: string
  state: JobState
  statusMessage: string
  progressPct: number
  result: unknown
  error: string | null
  /** Stable category code for failures; see types/agentErrors.ts. */
  errorCode?: string | null
}

export interface JobCreatedResponse {
  jobId: string
}

export interface ChatJobCreatedResponse extends JobCreatedResponse {
  // Server-generated session_id for the chat thread. Echoed back to the
  // backend on subsequent messages so the worker can pass --resume <id>
  // and the Anthropic prompt cache stays warm for back-to-back edits.
  sessionId: string
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
  | 'race_invite'

/**
 * Structured payload attached to a race-invite notification.
 *
 * Lives on `AppNotification.meta`. Populated by the backend's
 * `POST /internal/colyseus/race-invite` endpoint and mirrored onto the
 * WS push so `<RaceInviteToast>` can render the button without parsing
 * the message string. Fields are optional so future notification types
 * can reuse `meta` without carrying race fields they don't need.
 */
export interface RaceInviteMeta {
  roomId?: string
  hostUserId?: string
  hostName?: string
  distanceM?: number
}

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
  /** Generic JSON payload — see `RaceInviteMeta` for race-invite shape. */
  meta?: Record<string, unknown> | null
}

// ── Pull Request Types ──────────────────────────────────────────
export interface PullRequest {
  id: string
  bud_id: string | null
  repo_id: string | null
  github_pr_number: number
  github_repo_full_name: string
  title: string
  html_url: string
  head_branch: string
  base_branch: string
  state: 'open' | 'closed' | 'merged'
  review_status: 'pending' | 'approved' | 'changes_requested'
  author_github_login: string
  merged_at: string | null
  created_at: string
  updated_at: string
}

export interface PRChecklistItem {
  repo_id: string
  repo_name: string
  pr: PullRequest | null
  status: 'no_pr' | 'open' | 'merged'
}

// ─── Code Review tab ───────────────────────────

export type CodeReviewPRState = 'not_raised' | 'open' | 'merged' | 'closed'

export interface CodeReviewRepoStatus {
  repo_id: string
  repo_name: string
  pr_number: number | null
  pr_state: CodeReviewPRState
  pr_url: string | null
  comment_count: number
}

export interface CodeReviewStatusResponse {
  repos: CodeReviewRepoStatus[]
}

// Mirror of backend `CodeReviewOverrideRequest` Pydantic constraints in
// backend/app/schemas/bud.py. Keep in sync manually if the backend limits
// change — a drift here silently turns into 422s with generic messages.
export const CODE_REVIEW_OVERRIDE_REASON_MIN = 10
export const CODE_REVIEW_OVERRIDE_REASON_MAX = 2000

// ─── XP / Gamification ─────────────────────────

export interface XPProfile {
  total_xp: number
  level: number
  level_name: string
  xp_to_next_level: number
  next_level_threshold: number
  streak_count: number
  streak_best: number
  unlocked_characters: string[]
  unlocked_accessories: string[]
  skill_points: number
  house_level: number
  vehicle_unlocks: string[]
}

export interface LeaderboardEntry {
  user_id: string
  name: string
  avatar_url: string | null
  total_xp: number
  level: number
  level_name: string
  streak_count: number
}

export interface RewardEvent {
  id: string
  type: 'xp' | 'sp'
  amount: number
  source: string
  source_ref: string | null
  multiplier: number
  created_at: string
}
