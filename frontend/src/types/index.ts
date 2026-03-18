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

export type PRDStatus = 'draft' | 'design' | 'tech-spec' | 'in-dev' | 'in-qa' | 'in-uat' | 'deployed'

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
  'draft', 'design', 'tech-spec', 'in-dev', 'in-qa', 'in-uat', 'deployed',
]

export const PRD_STATUS_LABELS: Record<PRDStatus, string> = {
  'draft': 'Draft',
  'design': 'Design',
  'tech-spec': 'Tech Spec',
  'in-dev': 'In Dev',
  'in-qa': 'In QA',
  'in-uat': 'In UAT',
  'deployed': 'Deployed',
}

export const PRD_STATUS_COLORS: Record<PRDStatus, string> = {
  'draft': 'grey',
  'design': 'purple',
  'tech-spec': 'info',
  'in-dev': 'primary',
  'in-qa': 'warning',
  'in-uat': 'orange',
  'deployed': 'success',
}
