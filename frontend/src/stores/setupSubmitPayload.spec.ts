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
 * What the setup wizard sends: only the secret the chosen sign-in mode
 * uses, the repository list in the shape the backend expects, and the
 * error shown when a step fails. ``.spec.ts`` for jsdom's localStorage.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ resetSetupCache: vi.fn(), fetchUser: vi.fn() }))
vi.mock('@/services/api', () => ({ default: { post: vi.fn() } }))
vi.mock('@/router', () => ({ resetSetupCache: h.resetSetupCache }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ fetchUser: h.fetchUser }) }))

import api from '@/services/api'
import { useSetupStore } from '@/stores/setup'
import type { SetupState } from '@/types/setup'

type Repo = SetupState['sourceCode']['repos'][number]
const post = vi.mocked(api.post)

function httpError(status: number, data: Record<string, unknown> = {}): Error {
  return Object.assign(new Error(String(status)), { response: { status, data } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  localStorage.clear()
  post.mockResolvedValue({ data: { org_slug: 'acme', org_id: 'o1', access_token: 'jwt' } })
})

describe('submitOrgInit', () => {
  it('sends the API key only in API-key mode', async () => {
    const store = useSetupStore()
    Object.assign(store.state.claude, { authMode: 'api_key', apiKey: 'sk-test', oauthToken: 'oat-test' })
    await store.submitOrgInit()
    expect(post.mock.calls[0][1]).toMatchObject({ claude: { apiKey: 'sk-test', oauthToken: null } })
  })

  it('sends the subscription token only in subscription mode', async () => {
    const store = useSetupStore()
    Object.assign(store.state.claude, { authMode: 'subscription', apiKey: 'sk-test', oauthToken: 'oat-test' })
    await store.submitOrgInit()
    expect(post.mock.calls[0][1]).toMatchObject({ claude: { apiKey: null, oauthToken: 'oat-test' } })
  })

  it('sends no secret on the host sign-in, and empty options as none', async () => {
    const store = useSetupStore()
    Object.assign(store.state.claude, { authMode: 'host', apiKey: 'sk-test', baseUrl: '', model: '' })
    await store.submitOrgInit()
    expect(post.mock.calls[0][1]).toMatchObject({
      claude: { apiKey: null, oauthToken: null, baseUrl: null, model: null },
    })
  })

  it('reads the snake_case reply, keeps the token and loads the user', async () => {
    const result = await useSetupStore().submitOrgInit()
    expect(result).toEqual({ orgSlug: 'acme', orgId: 'o1', accessToken: 'jwt' })
    expect(localStorage.getItem('bodhiorchard_token')).toBe('jwt')
    expect(h.fetchUser).toHaveBeenCalledOnce()
  })

  it('still succeeds when loading the user fails', async () => {
    h.fetchUser.mockRejectedValueOnce(new Error('500'))
    const store = useSetupStore()
    expect(await store.submitOrgInit()).not.toBeNull()
    expect(store.orgInitDone).toBe(true)
  })

  it.each([
    [httpError(400, { detail: 'Slug already taken' }), 'Slug already taken'],
    [httpError(400, { message: 'Bad request body' }), 'Bad request body'],
    [httpError(500), 'Org init failed. Please try again.'],
    [new Error('Network Error'), 'Network error. Please check your connection.'],
  ])('shows the reason a failed init gives', async (err, message) => {
    post.mockRejectedValueOnce(err)
    const store = useSetupStore()
    expect(await store.submitOrgInit()).toBeNull()
    expect(store.submitError).toBe(message)
  })
})

describe('submitFinalize', () => {
  it('sends GitHub repositories as installable items', async () => {
    post.mockResolvedValueOnce({ data: { jobId: 'job-1', scanId: 'scan-1' } })
    const store = useSetupStore()
    store.state.sourceCode.repos = [
      { gitHubFullName: 'acme/api', mainBranch: 'main', developBranch: 'develop' },
      { gitHubFullName: 'acme/web', mainBranch: 'trunk', developBranch: '' },
    ] as Repo[]
    expect(await store.submitFinalize()).toEqual({ jobId: 'job-1', scanId: 'scan-1', isSetupComplete: true })
    expect(post).toHaveBeenCalledWith('/setup/finalize-with-repos', {
      installableItems: [
        { fullName: 'acme/api', mainBranch: 'main', developBranch: 'develop' },
        { fullName: 'acme/web', mainBranch: 'trunk', developBranch: undefined },
      ],
    })
    expect(store.jobId).toBe('job-1')
    expect(store.scanId).toBe('scan-1')
    expect(localStorage.getItem('bodhiorchard_setup_complete')).toBe('true')
    expect(h.resetSetupCache).toHaveBeenCalled()
  })

  it('sends the whole list when any repository is a local folder', async () => {
    post.mockResolvedValueOnce({ data: {} })
    const store = useSetupStore()
    const repos = [
      { gitHubFullName: 'acme/api', mainBranch: 'main' },
      { source: 'local-path', path: '/src/web', mainBranch: 'main', developBranch: 'dev' },
    ] as Repo[]
    store.state.sourceCode.repos = repos
    await store.submitFinalize()
    expect(post).toHaveBeenCalledWith('/setup/finalize-with-repos', { sourceCode: { repos } })
  })

  it('treats an install that is already finished as done', async () => {
    post.mockRejectedValueOnce(httpError(409, { detail: 'Setup already complete' }))
    const store = useSetupStore()
    expect(await store.submitFinalize()).toEqual({ isSetupComplete: true })
    expect(store.submitError).toBeNull()
    expect(localStorage.getItem('bodhiorchard_setup_complete')).toBe('true')
  })

  it('shows the reason and lets the user retry after a failure', async () => {
    post.mockRejectedValueOnce(httpError(422, { detail: 'No repositories selected' }))
    const store = useSetupStore()
    expect(await store.submitFinalize()).toBeNull()
    expect(store.submitError).toBe('No repositories selected')
    expect(store.finalizeDone).toBe(false)
    expect(localStorage.getItem('bodhiorchard_setup_complete')).toBeNull()
  })

  it('does not post twice once finalized', async () => {
    post.mockResolvedValueOnce({ data: { jobId: 'job-1' } })
    const store = useSetupStore()
    await store.submitFinalize()
    expect(await store.submitFinalize()).toEqual({ jobId: 'job-1', scanId: undefined, isSetupComplete: true })
    expect(post).toHaveBeenCalledOnce()
  })
})

describe('submitSetup', () => {
  it('stops when the org could not be created', async () => {
    post.mockRejectedValueOnce(httpError(500))
    const store = useSetupStore()
    expect(await store.submitSetup()).toBe(false)
    expect(post).toHaveBeenCalledOnce()
    expect(store.isSubmitting).toBe(false)
  })
})
