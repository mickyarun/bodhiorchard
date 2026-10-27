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

import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ApprovalDecision from '../ApprovalDecision.vue'
import type { LeaveRequestRead } from '@/types/leave'

const { approve, reject } = vi.hoisted(() => ({
  approve: vi.fn(async () => null),
  reject: vi.fn(async () => null),
}))
vi.mock('@/stores/leaveApprovals', () => ({
  useLeaveApprovalsStore: () => ({ approve, reject }),
}))

const REQUEST = { id: 'req-1', user: { user_id: 'u1', name: 'Ravi Kumar' } } as LeaveRequestRead

// A textarea that keeps v-model and shows its label and error, and buttons
// that render their text: enough to drive the decision like a user.
const stubs = {
  'v-textarea': {
    props: ['modelValue', 'label', 'errorMessages'],
    emits: ['update:modelValue'],
    methods: { focus: () => undefined },
    template:
      '<label>{{ label }}<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' +
      '<span class="error">{{ errorMessages }}</span></label>',
  },
  'v-btn': { template: '<button type="button" @click="$emit(\'click\')"><slot /></button>' },
  AppCallout: { template: '<div class="callout"><slot /></div>' },
}

function mountDecision() {
  return mount(ApprovalDecision, { props: { request: REQUEST }, global: { stubs } })
}

function button(wrapper: ReturnType<typeof mountDecision>, text: string) {
  const found = wrapper.findAll('button').find(b => b.text() === text)
  if (!found) throw new Error(`No "${text}" button`)
  return found
}

describe('ApprovalDecision', () => {
  beforeEach(() => {
    approve.mockClear()
    reject.mockClear()
  })

  it('labels the note as the reason for rejecting', () => {
    expect(mountDecision().find('label').text()).toContain('Reason for rejecting')
  })

  it('approves without sending the note', async () => {
    const wrapper = mountDecision()
    await wrapper.find('textarea').setValue('Typed but not meant for approval')
    await button(wrapper, 'Approve').trigger('click')
    await flushPromises()
    expect(approve).toHaveBeenCalledWith('req-1', '')
    expect(reject).not.toHaveBeenCalled()
  })

  it('needs a note to reject, and sends it once there is one', async () => {
    const wrapper = mountDecision()
    await button(wrapper, 'Reject').trigger('click')
    await flushPromises()
    expect(reject).not.toHaveBeenCalled()
    expect(wrapper.find('.error').text()).toBe('Add a note so Ravi knows why.')

    await wrapper.find('textarea').setValue('Clashes with the release')
    expect(wrapper.find('.error').text()).toBe('')
    await button(wrapper, 'Reject').trigger('click')
    await flushPromises()
    expect(reject).toHaveBeenCalledWith('req-1', 'Clashes with the release')
  })
})
