export type { SetupState, StepDefinition } from './setup'

export type UserRoleName =
  | 'org_owner'
  | 'admin'
  | 'pm'
  | 'tech_lead'
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

export type PRDStatus = 'draft' | 'design' | 'tech-spec' | 'in-dev' | 'in-qa' | 'in-uat' | 'deployed' | 'cancelled'

export interface PRDListItem {
  id: string
  prd_number: number
  title: string
  status: PRDStatus
  created_at: string
  updated_at: string
}

export interface PRDDocument extends PRDListItem {
  org_id: string
  content_md: string | null
  tech_spec_md: string | null
  test_plan_md: string | null
  metadata: Record<string, unknown> | null
}

export const PRD_STATUS_ORDER: PRDStatus[] = [
  'draft', 'design', 'tech-spec', 'in-dev', 'in-qa', 'in-uat', 'deployed', 'cancelled',
]

export const PRD_STATUS_LABELS: Record<PRDStatus, string> = {
  'draft': 'Draft',
  'design': 'Design',
  'tech-spec': 'Tech Spec',
  'in-dev': 'In Dev',
  'in-qa': 'In QA',
  'in-uat': 'In UAT',
  'deployed': 'Deployed',
  'cancelled': 'Cancelled',
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

// Team types
export interface Team {
  id: string
  name: string
  description: string | null
  memberCount: number
  createdAt: string
}

export interface TeamMember {
  id: string
  userId: string
  userName: string
  email: string
  role: 'lead' | 'member'
}

export interface TeamDetail extends Team {
  members: TeamMember[]
}

// Repo types
export interface RepoInfo {
  path: string
  name: string
  lastScanned: string | null
  sha: string | null
  knowledgeCount: number
  featureCount: number
}

export const PRD_STATUS_COLORS: Record<PRDStatus, string> = {
  'draft': 'grey',
  'design': 'purple',
  'tech-spec': 'info',
  'in-dev': 'primary',
  'in-qa': 'warning',
  'in-uat': 'orange',
  'deployed': 'success',
  'cancelled': 'error',
}
