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
 * Phase J — idempotency contract for ``submitOrgInit``.
 *
 * The wizard fires ``submitOrgInit`` on the AI Engine → Connect GitHub
 * transition. If the user navigates Back and then Continue again, the
 * org already exists in the backend; calling ``POST /setup/init-org`` a
 * second time would either 409 or duplicate-create. The store guards
 * against this by short-circuiting once ``orgInitDone`` is true.
 *
 * We mock the api service entirely — neither axios nor a real HTTP
 * roundtrip is needed for this contract.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Vitest hoists vi.mock above imports — the factory runs before the
// store under test imports the api module.
vi.mock('@/services/api', () => {
  const post = vi.fn()
  return {
    default: { post },
  }
})

vi.mock('@/router', () => ({
  resetSetupCache: vi.fn(),
}))

// vitest is configured to run in the Node env (vitest.config.ts), which
// has no global ``localStorage``. submitOrgInit / submitFinalize both
// persist tokens via ``localStorage.setItem`` — install a tiny in-memory
// shim so they don't throw and bail back through the error path.
class MemoryStorage {
  private data = new Map<string, string>()
  getItem(key: string): string | null {
    return this.data.get(key) ?? null
  }
  setItem(key: string, value: string): void {
    this.data.set(key, value)
  }
  removeItem(key: string): void {
    this.data.delete(key)
  }
  clear(): void {
    this.data.clear()
  }
  key(_index: number): string | null {
    return null
  }
  get length(): number {
    return this.data.size
  }
}

if (typeof globalThis.localStorage === 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(globalThis as any).localStorage = new MemoryStorage()
}

import api from '@/services/api'
import { useSetupStore } from './setup'

const mockedPost = api.post as unknown as ReturnType<typeof vi.fn>

beforeEach(() => {
  setActivePinia(createPinia())
  mockedPost.mockReset()
  // Default: succeed with a JWT-bearing payload.
  mockedPost.mockResolvedValue({
    data: {
      orgSlug: 'acme',
      orgId: 'org-uuid',
      accessToken: 'jwt.token.here',
    },
  })
  globalThis.localStorage?.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('submitOrgInit', () => {
  it('hits POST /setup/init-org once on first call and flips orgInitDone', async () => {
    const store = useSetupStore()
    const result = await store.submitOrgInit()

    expect(result).not.toBeNull()
    expect(result?.accessToken).toBe('jwt.token.here')
    expect(store.orgInitDone).toBe(true)
    expect(mockedPost).toHaveBeenCalledTimes(1)
    expect(mockedPost).toHaveBeenCalledWith(
      '/setup/init-org',
      expect.objectContaining({ organization: expect.anything() }),
    )
  })

  it('is idempotent on Back/Forward navigation — second call no-ops', async () => {
    const store = useSetupStore()
    await store.submitOrgInit()
    expect(store.orgInitDone).toBe(true)

    // Simulate the wizard re-entering the trigger after Back→Continue.
    const second = await store.submitOrgInit()

    expect(second).toBeNull()
    // The api was not called a second time — the store skipped the
    // network round-trip entirely.
    expect(mockedPost).toHaveBeenCalledTimes(1)
    expect(store.orgInitDone).toBe(true)
  })

  it('leaves orgInitDone false if init-org fails', async () => {
    mockedPost.mockRejectedValueOnce({
      response: { status: 500, data: { detail: 'boom' } },
    })

    const store = useSetupStore()
    const result = await store.submitOrgInit()

    expect(result).toBeNull()
    expect(store.orgInitDone).toBe(false)
    expect(store.submitError).toBe('boom')
    // A subsequent retry must actually re-call the endpoint.
    mockedPost.mockResolvedValueOnce({
      data: { orgSlug: 'acme', orgId: 'org-uuid', accessToken: 'tok' },
    })
    const retry = await store.submitOrgInit()
    expect(retry).not.toBeNull()
    expect(store.orgInitDone).toBe(true)
    expect(mockedPost).toHaveBeenCalledTimes(2)
  })
})

describe('submitSetup back-compat shim', () => {
  it('chains init-org and finalize when neither has run yet', async () => {
    mockedPost
      .mockResolvedValueOnce({
        data: {
          orgSlug: 'acme',
          orgId: 'org-uuid',
          accessToken: 'jwt.token.here',
        },
      })
      .mockResolvedValueOnce({
        data: { jobId: 'job-1', scanId: 'scan-1' },
      })

    const store = useSetupStore()
    // Add at least one repo so finalize has something to send.
    store.state.sourceCode.repos.push({
      path: '/tmp/repo',
      mainBranch: 'main',
      developBranch: 'develop',
    })
    const ok = await store.submitSetup()

    expect(ok).toBe(true)
    expect(mockedPost).toHaveBeenNthCalledWith(
      1,
      '/setup/init-org',
      expect.anything(),
    )
    expect(mockedPost).toHaveBeenNthCalledWith(
      2,
      '/setup/finalize-with-repos',
      expect.anything(),
    )
  })

  it('skips init-org when orgInitDone — only fires finalize', async () => {
    mockedPost.mockResolvedValueOnce({
      data: { jobId: 'job-1', scanId: 'scan-1' },
    })

    const store = useSetupStore()
    store.orgInitDone = true
    store.state.sourceCode.repos.push({
      path: '/tmp/repo',
      mainBranch: 'main',
      developBranch: 'develop',
    })

    const ok = await store.submitSetup()

    expect(ok).toBe(true)
    expect(mockedPost).toHaveBeenCalledTimes(1)
    expect(mockedPost).toHaveBeenCalledWith(
      '/setup/finalize-with-repos',
      expect.anything(),
    )
  })
})
