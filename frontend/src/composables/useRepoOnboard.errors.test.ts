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
 * Bulk import's failure paths and limits: a failed list, branch or submit
 * call shows the store's reason; nothing is sent without a main branch on
 * every pick or past the repository cap; branch picks the user made are
 * not overwritten.
 */
import { describe, expect, it, vi } from 'vitest'
import { useRepoOnboard } from './useRepoOnboard'
import { APP_INSTALL_STATE, BULK_IMPORT_MAX_REPOS, type InstallableRepo } from '@/types/repoOnboard'

function repo(fullName: string, defaultBranch = 'main'): InstallableRepo {
  return {
    fullName,
    ownerLogin: fullName.split('/')[0],
    ownerAvatarUrl: '',
    defaultBranch,
    private: false,
    ghRepoId: 1,
    alreadyTracked: false,
    pushedAt: null,
  }
}

function makeStore(repos: InstallableRepo[], branches: Record<string, string[] | null> = {}) {
  return {
    lastError: null as string | null,
    loadInstallableRepos: vi.fn(async () => ({
      appInstallState: APP_INSTALL_STATE.READY, installUrl: null, repos,
    })),
    loadInstallableBranches: vi.fn(async (name: string) => branches[name] ?? null),
    submitBulkOnboard: vi.fn(async () => ({ jobId: 'job-1' })),
  }
}

async function onboardWith(store: ReturnType<typeof makeStore>) {
  const onboard = useRepoOnboard({ store: store as never })
  await onboard.loadInstallable()
  return onboard
}

describe('useRepoOnboard failures', () => {
  it('shows why the repository list did not load', async () => {
    const store = makeStore([])
    store.loadInstallableRepos.mockResolvedValueOnce(null as never)
    store.lastError = 'GitHub App not installed'
    const onboard = await onboardWith(store)
    expect(onboard.errorMessage.value).toBe('GitHub App not installed')
    expect(onboard.installable.value).toEqual([])
    expect(onboard.loadingInstallable.value).toBe(false)
  })

  it('shows why branches did not load, and caches nothing', async () => {
    const store = makeStore([repo('acme/api')])
    store.lastError = 'Repository not found'
    const onboard = await onboardWith(store)
    await onboard.toggleSelection('acme/api')
    expect(onboard.errorMessage.value).toBe('Repository not found')
    expect(onboard.branchOptions.has('acme/api')).toBe(false)
    expect(onboard.canSubmit.value).toBe(false)
    expect(onboard.loadingBranchesFor.has('acme/api')).toBe(false)
  })

  it('leaves the main branch for the user when the default is missing', async () => {
    const onboard = await onboardWith(makeStore([repo('acme/api', 'main')], { 'acme/api': ['trunk'] }))
    await onboard.toggleSelection('acme/api')
    expect(onboard.branchesByRepo.get('acme/api')).toBeUndefined()
    expect(onboard.canSubmit.value).toBe(false)
    onboard.setBranchPick('acme/api', 'main', 'trunk')
    expect(onboard.canSubmit.value).toBe(true)
  })

  it('keeps a branch the user picked when branches are refreshed', async () => {
    const onboard = await onboardWith(makeStore([repo('acme/api')], { 'acme/api': ['main', 'release'] }))
    await onboard.toggleSelection('acme/api')
    onboard.setBranchPick('acme/api', 'main', 'release')
    await onboard.refreshBranchesFor('acme/api')
    expect(onboard.branchesByRepo.get('acme/api')?.main).toBe('release')
  })

  it('does not pick develop as both main and develop', async () => {
    const onboard = await onboardWith(makeStore([repo('acme/api', 'develop')], { 'acme/api': ['develop', 'main'] }))
    await onboard.toggleSelection('acme/api')
    expect(onboard.branchesByRepo.get('acme/api')).toEqual({ main: 'develop', develop: undefined })
  })

  it('sends nothing until it can submit', async () => {
    const store = makeStore([repo('acme/api')])
    const onboard = await onboardWith(store)
    expect(await onboard.submitBulkOnboard()).toBeNull()
    expect(store.submitBulkOnboard).not.toHaveBeenCalled()
  })

  it('refuses more repositories than one import takes', async () => {
    const repos = Array.from({ length: BULK_IMPORT_MAX_REPOS + 1 }, (_, i) => repo(`acme/r${i}`))
    const branches = Object.fromEntries(repos.map(r => [r.fullName, ['main']]))
    const onboard = await onboardWith(makeStore(repos, branches))
    await onboard.selectAllForOwner('acme', true)
    expect(onboard.selectionCount.value).toBe(BULK_IMPORT_MAX_REPOS + 1)
    expect(onboard.canSubmit.value).toBe(false)
  })

  it('shows why the import was refused and keeps the selection', async () => {
    const store = makeStore([repo('acme/api')], { 'acme/api': ['main'] })
    store.submitBulkOnboard.mockResolvedValueOnce(null as never)
    store.lastError = 'Import already running'
    const onboard = await onboardWith(store)
    await onboard.toggleSelection('acme/api')
    expect(await onboard.submitBulkOnboard()).toBeNull()
    expect(onboard.errorMessage.value).toBe('Import already running')
    expect(onboard.selectionCount.value).toBe(1)
    expect(onboard.submitting.value).toBe(false)
  })

  it('clears the selection, picks and error on reset', async () => {
    const store = makeStore([repo('acme/api')], { 'acme/api': ['main'] })
    const onboard = await onboardWith(store)
    await onboard.toggleSelection('acme/api')
    onboard.errorMessage.value = 'old'
    onboard.reset()
    expect(onboard.selectionCount.value).toBe(0)
    expect(onboard.branchesByRepo.size).toBe(0)
    expect(onboard.errorMessage.value).toBeNull()
  })

  it('deselects a whole owner, dropping their picks', async () => {
    const onboard = await onboardWith(makeStore([repo('acme/api'), repo('acme/web')], {
      'acme/api': ['main'], 'acme/web': ['main'],
    }))
    await onboard.selectAllForOwner('acme', true)
    await onboard.selectAllForOwner('acme', false)
    expect(onboard.selectionCount.value).toBe(0)
    expect(onboard.branchesByRepo.size).toBe(0)
  })
})
