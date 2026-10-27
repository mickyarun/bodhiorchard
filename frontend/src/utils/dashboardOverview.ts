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

/** Pure helpers behind the dashboard overview: key numbers, flow, attention. */
import {
  BUD_PRIORITY_WEIGHTS,
  BUD_STATUS_COLORS,
  BUD_STATUS_ORDER,
  BUD_STATUS_LABELS,
  budRef,
  type BUDListItem,
  type BUDPriority,
  type BUDStatus,
} from '@/types'

/** Stages where work is still moving: not yet live, closed or discarded. */
const DONE: ReadonlySet<BUDStatus> = new Set(['prod', 'closed', 'discarded'])

/** Short stage names for tight spaces such as the flow legend. */
export const BUD_STAGE_SHORT: Partial<Record<BUDStatus, string>> = {
  tech_arch: 'Tech arch',
  code_review: 'Review',
}

export function stageShortLabel(status: BUDStatus): string {
  return BUD_STAGE_SHORT[status] ?? BUD_STATUS_LABELS[status]
}

export function isInFlight(bud: BUDListItem): boolean {
  return !DONE.has(bud.status)
}

export interface FlowStage {
  status: BUDStatus
  label: string
  count: number
  color: string
}

/**
 * BUDs not yet closed, per stage, in lifecycle order through prod. A stage
 * the org has switched off still shows while BUDs sit in it.
 */
export function flowStages(buds: BUDListItem[], phaseOrder: BUDStatus[]): FlowStage[] {
  const counts = new Map<BUDStatus, number>()
  for (const bud of buds) counts.set(bud.status, (counts.get(bud.status) ?? 0) + 1)
  return BUD_STATUS_ORDER
    .filter(s => s !== 'closed' && s !== 'discarded')
    .filter(s => phaseOrder.includes(s) || counts.has(s))
    .map(status => ({
      status,
      label: stageShortLabel(status),
      count: counts.get(status) ?? 0,
      color: BUD_STATUS_COLORS[status],
    }))
}

export interface Kpi {
  label: string
  value: number
  sub: string
  to: string
}

function countIn(buds: BUDListItem[], statuses: BUDStatus[]): number {
  return buds.filter(b => statuses.includes(b.status)).length
}

/**
 * The four headline numbers. The last tile is the approver's leave queue
 * when there is one (``pendingLeave`` set), otherwise open bugs on work in
 * flight.
 */
export function overviewKpis(
  buds: BUDListItem[],
  pendingLeave: number | null,
  uatEnabled: boolean,
): Kpi[] {
  const inFlight = buds.filter(isInFlight)
  const last: Kpi = pendingLeave === null
    ? {
        label: 'Open bugs',
        value: inFlight.reduce((n, b) => n + b.open_bug_count, 0),
        sub: 'On BUDs in flight',
        to: '/buds',
      }
    : { label: 'Leave requests', value: pendingLeave, sub: 'Waiting for your approval', to: '/leave/approvals' }
  return [
    {
      label: 'In flight',
      value: inFlight.length,
      sub: `${countIn(buds, ['bud'])} waiting to start`,
      to: '/buds',
    },
    {
      label: 'In production',
      value: countIn(buds, ['prod']),
      sub: `${countIn(buds, ['closed'])} closed`,
      to: '/buds',
    },
    {
      label: 'Waiting on review',
      // UAT counts even when switched off, for BUDs that were already in it.
      value: countIn(buds, ['code_review', 'uat']),
      sub: uatEnabled ? 'Code review and UAT' : 'Code review',
      to: '/buds',
    },
    last,
  ]
}

export interface AttentionItem {
  key: string
  ref: string
  priority: BUDPriority
  title: string
  meta: string
  action: string
  to: string
}

const REASONS: Partial<Record<BUDStatus, { why: string; action: string }>> = {
  code_review: { why: 'waiting for review', action: 'Review' },
  uat: { why: 'needs sign-off', action: 'Sign off' },
}

export interface AttentionList {
  /** The first ``limit`` items. */
  items: AttentionItem[]
  /** How many need attention in all, shown or not. */
  total: number
}

/**
 * BUDs that need a person: anything in code review or UAT, and every P0
 * still in flight. Highest priority first, then the longest untouched.
 * People who can't pass a phase gate (``canApprove`` false) get "Open"
 * rather than "Review" or "Sign off".
 */
export function attentionItems(
  buds: BUDListItem[],
  limit: number,
  canApprove: boolean,
): AttentionList {
  const waiting = buds
    .filter(b => !!REASONS[b.status] || (b.priority === 'P0' && isInFlight(b)))
    .sort((a, b) =>
      BUD_PRIORITY_WEIGHTS[a.priority] - BUD_PRIORITY_WEIGHTS[b.priority]
      || a.updated_at.localeCompare(b.updated_at))
  const items = waiting.slice(0, limit).map(b => {
    const reason = REASONS[b.status] ?? { why: 'highest priority', action: 'Open' }
    return {
      key: b.id,
      ref: budRef(b.bud_number),
      priority: b.priority,
      title: b.title,
      meta: [BUD_STATUS_LABELS[b.status], b.assignee_name ?? 'Unassigned', reason.why].join(' · '),
      action: canApprove ? reason.action : 'Open',
      to: `/buds/${b.id}`,
    }
  })
  return { items, total: waiting.length }
}

/** "Good morning" / "Good afternoon" / "Good evening" for the hour. */
export function greetingFor(hour: number): string {
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}
