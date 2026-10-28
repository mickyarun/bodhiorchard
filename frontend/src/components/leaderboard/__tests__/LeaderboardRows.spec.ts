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

/** The ranked list and the top three show each person's photo when they have one. */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createVuetify } from 'vuetify'
import type { RankedEntry } from '@/utils/leaderboard'
import LeaderboardPodium from '../LeaderboardPodium.vue'
import LeaderboardRows from '../LeaderboardRows.vue'

const PHOTO = '/api/v1/employees/avatars/0123456789abcdef0123456789abcdef'

function entry(rank: number, avatarUrl: string | null): RankedEntry {
  return { key: `u${rank}`, name: `Person ${rank}`, figure: '1', rank, avatarUrl }
}

describe('leaderboard photos', () => {
  it('shows a photo on list rows that have one and initials on the rest', () => {
    const wrapper = mount(LeaderboardRows, {
      props: { label: 'Everyone else', entries: [entry(4, PHOTO), entry(5, null)] },
    })
    const rows = wrapper.findAll('li')
    expect(rows[0].find('img').attributes('src')).toBe(PHOTO)
    expect(rows[1].find('img').exists()).toBe(false)
  })

  it('shows photos on the top three', () => {
    const wrapper = mount(LeaderboardPodium, {
      props: { entries: [entry(1, PHOTO), entry(2, null), entry(3, PHOTO)] },
      global: { plugins: [createVuetify()] },
    })
    expect(wrapper.findAll('img').map(i => i.attributes('src'))).toEqual([PHOTO, PHOTO])
  })
})
