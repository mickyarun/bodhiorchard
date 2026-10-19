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

/**
 * Two forms edit one policy: "Edit details" and Rules. Saving one must
 * neither send the other's unsaved edits nor throw them away.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick } from 'vue'

import type { PolicyRead, PolicyWrite } from '@/types/leavePolicy'

const apiPut = vi.fn()
vi.mock('@/services/api', () => ({ default: { put: apiPut } }))

const { usePolicyDraft } = await import('./usePolicyDraft')
const { useLeavePoliciesStore } = await import('@/stores/leavePolicies')
const { DETAIL_FIELDS, newPolicy, RULE_FIELDS } = await import('@/utils/leavePolicy')

function seed(): PolicyRead {
  return {
    ...newPolicy(),
    name: 'India',
    timezone: 'Asia/Kolkata',
    id: 'p1',
    is_default: true,
    employee_count: 4,
    has_requests: false,
  }
}

function setup() {
  const store = useLeavePoliciesStore()
  store.policies = [seed()]
  const policy = computed(() => store.policies[0])
  return {
    details: usePolicyDraft(policy, DETAIL_FIELDS),
    rules: usePolicyDraft(policy, RULE_FIELDS),
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  apiPut.mockReset()
  apiPut.mockImplementation(async (_url: string, body: PolicyWrite) => ({
    data: { ...seed(), ...body },
  }))
})

describe('usePolicyDraft', () => {
  it('saving details keeps unsaved rule edits, and does not send them', async () => {
    const { details, rules } = setup()
    rules.draft.value.backdate_limit_days = 30
    details.draft.value.name = 'India HQ'

    expect(await details.save()).toBe(true)
    await nextTick()

    expect(apiPut.mock.calls[0][1]).toMatchObject({ name: 'India HQ', backdate_limit_days: 7 })
    expect(rules.draft.value.backdate_limit_days).toBe(30)
    expect(rules.dirty.value).toBe(true)
    expect(details.dirty.value).toBe(false)
  })

  it('saving rules sends the latest name, not a stale copy', async () => {
    const { details, rules } = setup()
    rules.draft.value.backdate_limit_days = 30
    details.draft.value.name = 'India HQ'
    await details.save()
    await nextTick()

    await rules.save()
    expect(apiPut.mock.calls[1][1]).toMatchObject({ name: 'India HQ', backdate_limit_days: 30 })
    expect(rules.dirty.value).toBe(false)
  })

  it('discard puts the saved values back', () => {
    const { rules } = setup()
    rules.draft.value.working_days = [0, 1, 2]
    expect(rules.dirty.value).toBe(true)
    rules.discard()
    expect(rules.draft.value.working_days).toEqual([0, 1, 2, 3, 4])
    expect(rules.dirty.value).toBe(false)
  })

  it('keeps what was typed while a save was in flight', async () => {
    const { rules } = setup()
    rules.draft.value.backdate_limit_days = 30
    const saving = rules.save()
    rules.draft.value.optional_holiday_quota = 3
    await saving
    await nextTick()
    expect(rules.draft.value.optional_holiday_quota).toBe(3)
    expect(rules.dirty.value).toBe(true)
  })

  it('keeps the draft when a save fails', async () => {
    apiPut.mockRejectedValueOnce(new Error('nope'))
    const { rules } = setup()
    rules.draft.value.optional_holiday_quota = 2
    expect(await rules.save()).toBe(false)
    expect(rules.error.value).not.toBe('')
    expect(rules.draft.value.optional_holiday_quota).toBe(2)
  })
})
