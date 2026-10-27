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

/** What a triage request card shows, from the API's triage session. */
import type { TriageSession } from '@/stores/triage'

/** Label and theme colour for each status a request moves through. */
export const TRIAGE_STATUS: Record<string, { label: string; color: string }> = {
  interviewing: { label: 'Being scoped', color: 'info' },
  checking: { label: 'Being checked', color: 'info' },
  awaiting_pm: { label: 'Waiting', color: 'warning' },
  approved: { label: 'Approved', color: 'success' },
  bud_created: { label: 'BUD created', color: 'success' },
  rejected: { label: 'Rejected', color: 'error' },
}

export function triageStatus(status: string): { label: string; color: string } {
  return TRIAGE_STATUS[status] ?? { label: status, color: 'muted' }
}

/** The requester's name from the users table, else the Slack name, else the Slack ID. */
export function requesterName(s: Pick<TriageSession, 'requester_display_name' | 'requester_name' | 'requester_slack_id'>): string {
  if (s.requester_display_name) return s.requester_display_name
  if (s.requester_name && s.requester_name !== s.requester_slack_id) return s.requester_name
  return s.requester_slack_id
}

export interface TriageFact {
  label: string
  value: string
}

const CONTEXT_FACTS: Array<[key: string, label: string]> = [
  ['business_justification', 'Why'],
  ['user_impact', 'Who it affects'],
  ['urgency', 'Urgency'],
  ['merchant_name', 'Customer'],
]

/** The scoped context the Triage agent gathered, as labelled text. */
export function contextFacts(context: Record<string, unknown> | null): TriageFact[] {
  const facts: TriageFact[] = []
  for (const [key, label] of CONTEXT_FACTS) {
    const value = context?.[key]
    if (typeof value === 'string' && value.trim()) facts.push({ label, value: value.trim() })
  }
  return facts
}

/** Whether the request has regulatory or legal drivers. */
export function isCompliance(context: Record<string, unknown> | null): boolean {
  return !!context?.compliance
}
