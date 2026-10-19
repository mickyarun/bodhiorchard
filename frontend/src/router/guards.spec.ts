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
 * Workspace routing: people-only roles land on their own home and never
 * bounce through the engineering dashboard; engineers are unaffected.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { WORKSPACE_ENGINEERING } from '@/utils/workspace'
import { installGuards, resetSetupCache } from './guards'

vi.mock('@/services/api', () => ({
  default: { get: vi.fn(async () => ({ data: { is_setup_complete: true } })) },
}))

const Stub = { template: '<div />' }

function makeRouter(): Router {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: Stub },
      { path: '/dashboard', name: 'dashboard', component: Stub, meta: { workspace: 'engineering' } },
      {
        path: '/triage',
        name: 'triage',
        component: Stub,
        meta: { workspace: 'engineering', permission: 'backlog:approve' },
      },
      { path: '/leave', name: 'leave', component: Stub },
    ],
  })
  installGuards(router)
  return router
}

function signInWith(permissions: string[]): void {
  localStorage.setItem('bodhiorchard_token', 'token')
  const auth = useAuthStore()
  auth.user = { permissions } as unknown as typeof auth.user
}

describe('workspace guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    resetSetupCache()
  })

  it('sends a people-only member from the dashboard to leave', async () => {
    signInWith([])
    const router = makeRouter()
    await router.push('/dashboard')
    expect(router.currentRoute.value.name).toBe('leave')
  })

  it('keeps an engineer on the dashboard', async () => {
    signInWith([WORKSPACE_ENGINEERING])
    const router = makeRouter()
    await router.push('/dashboard')
    expect(router.currentRoute.value.name).toBe('dashboard')
  })

  it('sends an engineer without a route permission to their home', async () => {
    signInWith([WORKSPACE_ENGINEERING])
    const router = makeRouter()
    await router.push('/triage')
    expect(router.currentRoute.value.name).toBe('dashboard')
  })

  it('sends a signed-in member away from login to their home', async () => {
    signInWith([])
    const router = makeRouter()
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('leave')
  })

  it('does not guess a workspace when the profile fails to load', async () => {
    localStorage.setItem('bodhiorchard_token', 'token')
    const auth = useAuthStore()
    auth.fetchUser = vi.fn(async () => {
      throw new Error('network')
    })
    const router = makeRouter()
    await router.push('/dashboard')
    expect(router.currentRoute.value.name).toBe('dashboard')
  })
})
