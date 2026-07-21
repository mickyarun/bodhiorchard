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
import { BACKLASH_ENCOURAGEMENTS } from '@shared/minigames/backlashSocial'
import BacklashCrowdPanel from './BacklashCrowdPanel.vue'

describe('BacklashCrowdPanel', () => {
  it('renders and emits every shared encouragement', async () => {
    const wrapper = mount(BacklashCrowdPanel, {
      props: {
        viewer: true,
        viewerCount: 0,
        viewers: [],
        disabled: false,
      },
      global: {
        stubs: {
          VIcon: true,
        },
      },
    })

    const buttons = wrapper.findAll('.crowd-panel__actions button')
    expect(buttons).toHaveLength(BACKLASH_ENCOURAGEMENTS.length)
    expect(buttons.map((button) => button.text())).toEqual([...BACKLASH_ENCOURAGEMENTS])

    await wrapper.get('[aria-label="Send 😭 encouragement"]').trigger('click')

    expect(wrapper.emitted('encourage')).toEqual([['😭']])
  })
})
