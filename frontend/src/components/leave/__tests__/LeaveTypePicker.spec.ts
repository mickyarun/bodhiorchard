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

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LeaveTypePicker from '../LeaveTypePicker.vue'
import type { Balance, LeavePreview } from '@/types/leave'

function balance(id: string, name: string, available: string | null): Balance {
  return {
    leave_type: { id, name, code: id.toUpperCase(), color_key: 'swatch-1' },
    is_paid: true,
    accrual: 'upfront',
    allocated: available === null ? null : '12',
    earned: available === null ? null : '12',
    adjustments: '0',
    added: '0',
    used: '0',
    pending: '0',
    available,
  }
}

const BALANCES = [balance('cl', 'Casual leave', '1'), balance('sl', 'Sick leave', null)]

// A parent's v-model: each update is written back into the prop.
function mountPicker(modelValue: string | null) {
  const wrapper = mount(LeaveTypePicker, {
    props: {
      balances: BALANCES,
      modelValue,
      'onUpdate:modelValue': (value: string | null) => wrapper.setProps({ modelValue: value }),
    },
  })
  return wrapper
}

describe('LeaveTypePicker', () => {
  it('lists each type with what is left, under a visible legend', () => {
    const wrapper = mountPicker(null)
    expect(wrapper.find('legend').text()).toBe('Leave type')
    const labels = wrapper.findAll('label').map(l => l.text())
    expect(labels).toEqual(['Casual leave1 day left', 'Sick leaveNo limit'])
  })

  it('reflects v-model and updates it when a type is picked', async () => {
    const wrapper = mountPicker('cl')
    const radios = wrapper.findAll<HTMLInputElement>('input[type="radio"]')
    expect(radios[0].element.checked).toBe(true)

    await radios[1].setValue(true)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['sl'])
    expect(wrapper.props('modelValue')).toBe('sl')
    expect(wrapper.findAll('label')[1].classes()).toContain('types__option--on')
  })

  it('shows what is left on the start date once the preview has priced the dates', () => {
    const preview = { balances_on_start: { cl: '4' } } as unknown as LeavePreview
    const wrapper = mount(LeaveTypePicker, { props: { balances: BALANCES, modelValue: null, preview } })
    const labels = wrapper.findAll('label').map(l => l.text())
    expect(labels).toEqual(['Casual leave4 days left', 'Sick leaveNo limit'])
  })
})
