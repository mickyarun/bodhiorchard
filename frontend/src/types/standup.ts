/** TypeScript interfaces for the Standup API. */

export interface BUDTransition {
  bud_number: number
  title: string
  from_stage: string
  to_stage: string
}

export interface StandupFlag {
  type: 'no_activity' | 'bud_lagging' | 'critical_bugs' | 'bus_factor'
  severity: 'info' | 'warning' | 'critical'
  description: string
  bud_number?: number | null
  user_id?: string | null
  user_name?: string | null
}

export interface MemberStandupItem {
  user_id: string
  name: string
  avatar_url: string | null
  level: number
  level_name: string

  commits_count: number
  files_changed: number
  prs_opened: number
  prs_merged: number
  buds_transitioned: BUDTransition[]
  bugs_filed: number
  bugs_resolved: number
  xp_earned: number
  agent_tasks_completed: number

  flags: StandupFlag[]
}

export interface StandupReport {
  id: string
  date: string
  members: MemberStandupItem[]
  flags: StandupFlag[]
  summary: string | null
  since_timestamp: string | null
  created_at: string
}

export interface StandupReportListItem {
  id: string
  date: string
  member_count: number
  flag_count: number
  created_at: string
}
