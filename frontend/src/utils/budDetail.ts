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

// Pure helpers behind the BUD detail page: the tab list, which tab each
// status opens on, and the stage stepper.

import { BUD_STATUS_LABELS, BUD_STATUS_ORDER, type BUDStatus } from '@/types'

/** The tab a BUD opens on for each status; also followed on every status change. */
export const STATUS_TAB_MAP: Record<BUDStatus, string> = {
  bud: 'requirements',
  design: 'design',
  tech_arch: 'tech-spec',
  development: 'development',
  code_review: 'code-review',
  testing: 'testing',
  uat: 'uat',
  prod: 'prod',
  closed: 'closed',
  discarded: 'closed',
}

/** Tabs without an editable markdown section; the section toolbar hides on them. */
export const READ_ONLY_TABS: ReadonlySet<string> = new Set([
  'development', 'code-review', 'testing', 'uat', 'prod', 'closed',
])

export interface DetailTab {
  value: string
  label: string
}

export interface DetailTabOptions {
  uatEnabled: boolean
  status: BUDStatus
  hasLearning: boolean
}

/**
 * The detail page's tabs in lifecycle order. UAT follows the org setting,
 * the Closed tab (labelled Discarded for discarded BUDs) appears once the
 * BUD has ended, and Learnings once it has any. The values are the ones
 * the tab panels and ``?tab=`` deep links use.
 */
export function detailTabs({ uatEnabled, status, hasLearning }: DetailTabOptions): DetailTab[] {
  const tabs: DetailTab[] = [
    { value: 'requirements', label: 'Requirements' },
    { value: 'design', label: 'Design' },
    { value: 'tech-spec', label: 'Tech spec' },
    { value: 'development', label: 'Development' },
    { value: 'code-review', label: 'Code review' },
    { value: 'testing', label: 'Testing' },
  ]
  if (uatEnabled) tabs.push({ value: 'uat', label: 'UAT' })
  tabs.push({ value: 'prod', label: 'Prod' })
  if (status === 'closed' || status === 'discarded') {
    tabs.push({ value: 'closed', label: status === 'discarded' ? 'Discarded' : 'Closed' })
  }
  if (hasLearning) tabs.push({ value: 'learnings', label: 'Learnings' })
  return tabs
}

export type StepState = 'done' | 'current' | 'todo'

export interface StageStep {
  status: BUDStatus
  label: string
  state: StepState
}

const ENDED: ReadonlySet<BUDStatus> = new Set(['closed', 'discarded'])

/**
 * The live stages for a BUD: the org's phase order up to prod, plus the
 * BUD's own stage if the org has since switched it off (a BUD can sit in
 * UAT after UAT is turned off), in canonical lifecycle order.
 */
function liveStages(phaseOrder: readonly BUDStatus[], status: BUDStatus): BUDStatus[] {
  return BUD_STATUS_ORDER.filter(s => !ENDED.has(s) && (phaseOrder.includes(s) || s === status))
}

/**
 * The stepper's stages and where the BUD sits on them. A closed BUD has
 * finished every stage; a discarded one has no position.
 */
export function stageSteps(phaseOrder: readonly BUDStatus[], status: BUDStatus): StageStep[] {
  const stages = liveStages(phaseOrder, status)
  const at = status === 'closed' ? stages.length : stages.indexOf(status)
  return stages.map((s, i) => ({
    status: s,
    label: BUD_STATUS_LABELS[s],
    state: at < 0 ? 'todo' : i < at ? 'done' : i === at ? 'current' : 'todo',
  }))
}

/**
 * The live stage after ``status``, for the one-click "Move to" action.
 * Null at prod: closing can't be undone, so it is only offered from the
 * stage menu, behind a confirmation. Null once ended too.
 */
export function nextStage(phaseOrder: readonly BUDStatus[], status: BUDStatus): BUDStatus | null {
  if (ENDED.has(status)) return null
  const stages = liveStages(phaseOrder, status)
  const i = stages.indexOf(status)
  return i >= 0 && i < stages.length - 1 ? stages[i + 1] : null
}

/** The branch prefix commits for a BUD go on, e.g. 8 → "bud-008/". Git hooks match on it. */
export function branchPrefix(budNumber: number | undefined): string {
  return `bud-${String(budNumber || 0).padStart(3, '0')}/`
}

/**
 * Stage moves a buds:test holder (QA) may make without buds:edit. Mirrors
 * _QA_OWNED_TRANSITIONS in backend/app/api/v1/bud.py: QA is the gate out
 * of testing, to UAT, or to prod when the org has UAT off.
 */
const QA_OWNED_TRANSITIONS: ReadonlySet<string> = new Set(['testing>uat', 'testing>prod'])

/** Whether someone with these permissions may move a BUD from one stage to another. */
export function canMoveBud(hasPermission: (p: string) => boolean, from: BUDStatus, to: BUDStatus): boolean {
  if (hasPermission('buds:edit')) return true
  return hasPermission('buds:test') && QA_OWNED_TRANSITIONS.has(`${from}>${to}`)
}
