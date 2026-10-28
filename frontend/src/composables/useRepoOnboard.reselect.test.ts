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
 * Picking a repository again (after unticking it, or after "Onboard
 * more") gets the same default branch picks as the first time, even
 * though its branch list is already cached.
 */
import { describe, expect, it, vi } from 'vitest'
import { useRepoOnboard } from './useRepoOnboard'
import { APP_INSTALL_STATE, type InstallableRepo } from '@/types/repoOnboard'

const API: InstallableRepo = {
  fullName: 'acme/api',
  ownerLogin: 'acme',
  ownerAvatarUrl: '',
  defaultBranch: 'main',
  private: false,
  ghRepoId: 1,
  alreadyTracked: false,
  pushedAt: null,
}

async function onboard() {
  const store = {
    lastError: null,
    loadInstallableRepos: vi.fn(async () => ({
      appInstallState: APP_INSTALL_STATE.READY, installUrl: null, repos: [API],
    })),
    loadInstallableBranches: vi.fn(async () => ['main', 'develop']),
    submitBulkOnboard: vi.fn(async () => ({ jobId: 'job-1' })),
  }
  const o = useRepoOnboard({ store: store as never })
  await o.loadInstallable()
  return { o, store }
}

describe('picking a repository again', () => {
  it('restores the default picks after unticking and ticking it', async () => {
    const { o, store } = await onboard()
    await o.toggleSelection('acme/api')
    await o.toggleSelection('acme/api')
    await o.toggleSelection('acme/api')
    expect(store.loadInstallableBranches).toHaveBeenCalledOnce()
    expect(o.branchesByRepo.get('acme/api')).toEqual({ main: 'main', develop: 'develop' })
    expect(o.canSubmit.value).toBe(true)
  })

  it('restores the default picks after a reset', async () => {
    const { o } = await onboard()
    await o.selectAllForOwner('acme', true)
    o.reset()
    await o.selectAllForOwner('acme', true)
    expect(o.branchesByRepo.get('acme/api')?.main).toBe('main')
    expect(o.canSubmit.value).toBe(true)
  })
})
