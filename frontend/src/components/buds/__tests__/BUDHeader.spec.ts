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

/** The header shows the assignee's photo, initials without one, and an empty ring when unassigned. */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createVuetify } from 'vuetify'
import type { BUDDocument } from '@/types'
import BUDHeader from '../BUDHeader.vue'

const PHOTO = '/api/v1/employees/avatars/0123456789abcdef0123456789abcdef'

function mountHeader(assignee: { name: string | null; photo: string | null }) {
  const bud = {
    id: 'b1',
    bud_number: 7,
    title: 'Checkout retries',
    status: 'development',
    priority: 'P2',
    assignee_id: assignee.name ? 'u1' : null,
    assignee_name: assignee.name,
    assignee_avatar_url: assignee.photo,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-02T00:00:00Z',
    prod_p70_date: null,
  } as unknown as BUDDocument
  return mount(BUDHeader, {
    props: {
      bud,
      statusItems: [],
      nextStatus: null,
      canMoveTo: () => false,
      changingStatus: false,
      canDelete: false,
      isClosed: false,
      agentLocked: false,
      chatOpen: false,
      chatable: false,
      canEditPriority: false,
      canEditBuds: false,
    },
    global: {
      plugins: [createVuetify()],
      stubs: {
        RouterLink: true,
        BUDPriorityMenu: true,
        BUDMoreMenu: true,
        BUDAssigneeMenu: { template: '<div><slot name="activator" :props="{}" /></div>' },
      },
    },
  })
}

describe('BUDHeader assignee', () => {
  it('shows the assignee photo', () => {
    const button = mountHeader({ name: 'Asha Rao', photo: PHOTO }).find('.bud-header__assignee')
    expect(button.find('img').attributes('src')).toBe(PHOTO)
  })

  it('shows initials when the assignee has no photo', () => {
    const button = mountHeader({ name: 'Asha Rao', photo: null }).find('.bud-header__assignee')
    expect(button.find('img').exists()).toBe(false)
    expect(button.text()).toContain('AR')
  })

  it('shows an empty ring when nobody is assigned', () => {
    const button = mountHeader({ name: null, photo: null }).find('.bud-header__assignee')
    expect(button.find('.bud-header__avatar-empty').exists()).toBe(true)
    expect(button.text()).toBe('Unassigned')
  })
})
