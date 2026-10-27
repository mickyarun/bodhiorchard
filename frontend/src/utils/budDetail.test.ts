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

import { describe, expect, it } from 'vitest'
import { BUD_STATUS_ORDER, VALID_BUD_TABS } from '@/types'
import { STATUS_TAB_MAP, branchPrefix, detailTabs, nextStage, stageSteps } from './budDetail'

const NO_UAT = BUD_STATUS_ORDER.filter(s => s !== 'uat')

describe('detailTabs', () => {
  it('lists the lifecycle tabs, with UAT only when enabled', () => {
    const on = detailTabs({ uatEnabled: true, status: 'development', hasLearning: false }).map(t => t.value)
    expect(on).toEqual(['requirements', 'design', 'tech-spec', 'development', 'code-review', 'testing', 'uat', 'prod'])
    const off = detailTabs({ uatEnabled: false, status: 'development', hasLearning: false }).map(t => t.value)
    expect(off).not.toContain('uat')
  })
  it('adds the ended tab, labelled by how the BUD ended, and Learnings', () => {
    const closed = detailTabs({ uatEnabled: true, status: 'closed', hasLearning: true })
    expect(closed.slice(-2)).toEqual([{ value: 'closed', label: 'Closed' }, { value: 'learnings', label: 'Learnings' }])
    const gone = detailTabs({ uatEnabled: true, status: 'discarded', hasLearning: false })
    expect(gone.at(-1)).toEqual({ value: 'closed', label: 'Discarded' })
  })
  it('only uses tab values that deep links accept, apart from Learnings', () => {
    const all = detailTabs({ uatEnabled: true, status: 'closed', hasLearning: false })
    for (const tab of all) expect(VALID_BUD_TABS.has(tab.value)).toBe(true)
    for (const tab of Object.values(STATUS_TAB_MAP)) expect(VALID_BUD_TABS.has(tab)).toBe(true)
  })
})

describe('stageSteps', () => {
  it('marks earlier stages done and the current one current', () => {
    const steps = stageSteps(BUD_STATUS_ORDER, 'development')
    expect(steps.map(s => s.status)).toEqual(
      ['bud', 'design', 'tech_arch', 'development', 'code_review', 'testing', 'uat', 'prod'])
    expect(steps.map(s => s.state)).toEqual(['done', 'done', 'done', 'current', 'todo', 'todo', 'todo', 'todo'])
  })
  it('follows the org phase order', () => {
    expect(stageSteps(NO_UAT, 'prod').map(s => s.status)).not.toContain('uat')
  })
  it('shows a closed BUD as finished and a discarded one with no position', () => {
    expect(stageSteps(BUD_STATUS_ORDER, 'closed').every(s => s.state === 'done')).toBe(true)
    expect(stageSteps(BUD_STATUS_ORDER, 'discarded').every(s => s.state === 'todo')).toBe(true)
  })
})

describe('nextStage', () => {
  it('steps through the org phase order', () => {
    expect(nextStage(BUD_STATUS_ORDER, 'development')).toBe('code_review')
    expect(nextStage(BUD_STATUS_ORDER, 'testing')).toBe('uat')
    expect(nextStage(NO_UAT, 'testing')).toBe('prod')
  })
  it('moves prod to closed and stops once ended', () => {
    expect(nextStage(BUD_STATUS_ORDER, 'prod')).toBe('closed')
    expect(nextStage(BUD_STATUS_ORDER, 'closed')).toBeNull()
    expect(nextStage(BUD_STATUS_ORDER, 'discarded')).toBeNull()
  })
})

describe('branchPrefix', () => {
  it('pads the BUD number to three digits', () => {
    expect(branchPrefix(8)).toBe('bud-008/')
    expect(branchPrefix(1234)).toBe('bud-1234/')
  })
})
