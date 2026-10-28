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

/** A new or removed photo reaches the top bar without a reload. */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import type { User } from '@/types'
import { useAuthStore } from '@/stores/auth'

const ME: User = {
  id: 'u1',
  email: 'asha@example.com',
  name: 'Asha Rao',
  role: 'developer',
  permissions: [],
  org_id: 'o1',
  character_model: null,
  avatar_url: null,
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('setAvatarUrl', () => {
  it('replaces the signed-in user, so everything reading it updates', () => {
    const auth = useAuthStore()
    auth.user = ME
    const before = auth.user
    auth.setAvatarUrl('/api/v1/employees/avatars/abc')
    expect(auth.user?.avatar_url).toBe('/api/v1/employees/avatars/abc')
    expect(auth.user).not.toBe(before)
    auth.setAvatarUrl(null)
    expect(auth.user?.avatar_url).toBeNull()
  })

  it('does nothing when nobody is signed in', () => {
    const auth = useAuthStore()
    auth.setAvatarUrl('/api/v1/employees/avatars/abc')
    expect(auth.user).toBeNull()
  })
})
