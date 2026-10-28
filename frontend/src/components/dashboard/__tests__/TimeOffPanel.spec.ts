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

/** The dashboard's time-off list shows each person's photo when they have one. */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createVuetify } from 'vuetify'
import type { CalendarEntry } from '@/types/leave'
import TimeOffPanel from '../TimeOffPanel.vue'

const PHOTO = '/api/v1/employees/avatars/0123456789abcdef0123456789abcdef'

function entry(request_id: string, avatar_url: string | null): CalendarEntry {
  return {
    request_id,
    user: { user_id: request_id, name: 'Neha Sharma', avatar_url },
    kind: 'leave',
    start_date: '2026-11-02',
    end_date: '2026-11-03',
    half_day: 'none',
    status: 'approved',
    is_own: false,
    leave_type: null,
    reason: null,
    working_days: [0, 1, 2, 3, 4],
  }
}

describe('TimeOffPanel', () => {
  it('shows a photo for people who have one and initials for the rest', () => {
    const wrapper = mount(TimeOffPanel, {
      props: { entries: [entry('a', PHOTO), entry('b', null)], error: '' },
      global: { plugins: [createVuetify()], stubs: { RouterLink: true } },
    })
    const rows = wrapper.findAll('li')
    expect(rows[0].find('img').attributes('src')).toBe(PHOTO)
    expect(rows[1].find('img').exists()).toBe(false)
    expect(rows[1].text()).toContain('NS')
  })
})
