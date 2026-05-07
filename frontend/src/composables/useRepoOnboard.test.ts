// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Unit tests for ``useRepoOnboard``. Branches the composable's
 * branching logic — selection toggles, branch caching idempotency,
 * canSubmit gating, and submit payload shape.
 *
 * The composable internally calls ``useRepoOnboardStore()`` (Pinia) by
 * default; tests inject a hand-rolled stub via the ``store`` option so
 * we never need a Pinia container or a real axios client.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { useRepoOnboard } from './useRepoOnboard'
import type {
  BulkOnboardJobCreated,
  BulkOnboardRequestBody,
  InstallableListResponse,
  InstallableRepo,
} from '@/types/repoOnboard'
import { APP_INSTALL_STATE } from '@/types/repoOnboard'

type AnyMock = ReturnType<typeof vi.fn>

interface StoreStub {
  lastError: string | null
  loadInstallableRepos: AnyMock
  loadInstallableBranches: AnyMock
  submitBulkOnboard: AnyMock
}

function makeRepo(fullName: string, owner: string, def = 'main'): InstallableRepo {
  return {
    fullName,
    ownerLogin: owner,
    ownerAvatarUrl: '',
    defaultBranch: def,
    private: false,
    ghRepoId: Math.floor(Math.random() * 1_000_000),
    alreadyTracked: false,
    pushedAt: null,
  }
}

function makeStoreStub(opts: {
  installable: InstallableRepo[]
  branchesByRepo?: Record<string, string[]>
  job?: BulkOnboardJobCreated
}): StoreStub {
  const listResponse: InstallableListResponse = {
    appInstallState: APP_INSTALL_STATE.READY,
    installUrl: null,
    repos: opts.installable,
  }
  const branchesByRepo = opts.branchesByRepo ?? {}
  return {
    lastError: null,
    loadInstallableRepos: vi.fn().mockResolvedValue(listResponse),
    loadInstallableBranches: vi.fn(
      async (fullName: string) => branchesByRepo[fullName] ?? null,
    ) as AnyMock,
    submitBulkOnboard: vi.fn().mockResolvedValue(opts.job ?? { jobId: 'job-1' }),
  }
}

describe('useRepoOnboard', () => {
  let scope: ReturnType<typeof effectScope>

  beforeEach(() => {
    scope = effectScope()
  })

  afterEach(() => {
    scope.stop()
  })

  it('toggles a repo into and out of the selection set', async () => {
    const repo = makeRepo('acme/api', 'acme')
    const store = makeStoreStub({ installable: [repo], branchesByRepo: { 'acme/api': ['main'] } })
    const onboard = scope.run(() => useRepoOnboard({ store: store as never }))!
    await onboard.loadInstallable()
    onboard.toggleSelection('acme/api')
    expect(onboard.selection.value.has('acme/api')).toBe(true)
    expect(onboard.selectionCount.value).toBe(1)
    onboard.toggleSelection('acme/api')
    expect(onboard.selection.value.has('acme/api')).toBe(false)
  })

  it('caches branches per repo and skips redundant fetches', async () => {
    const repo = makeRepo('acme/api', 'acme')
    const store = makeStoreStub({ installable: [repo], branchesByRepo: { 'acme/api': ['main'] } })
    const onboard = scope.run(() => useRepoOnboard({ store: store as never }))!
    await onboard.loadInstallable()
    await onboard.loadBranchesFor('acme/api')
    await onboard.loadBranchesFor('acme/api')
    expect(store.loadInstallableBranches).toHaveBeenCalledTimes(1)
    await onboard.refreshBranchesFor('acme/api')
    expect(store.loadInstallableBranches).toHaveBeenCalledTimes(2)
  })

  it('flips canSubmit only when every selected repo has a main branch', async () => {
    const a = makeRepo('acme/api', 'acme', 'main')
    const b = makeRepo('acme/web', 'acme', 'master')
    const store = makeStoreStub({
      installable: [a, b],
      branchesByRepo: { 'acme/api': ['main'], 'acme/web': ['master', 'develop'] },
    })
    const onboard = scope.run(() => useRepoOnboard({ store: store as never }))!
    await onboard.loadInstallable()
    expect(onboard.canSubmit.value).toBe(false)
    await onboard.toggleSelection('acme/api')
    expect(onboard.canSubmit.value).toBe(true)
    await onboard.toggleSelection('acme/web')
    expect(onboard.canSubmit.value).toBe(true)
  })

  it('submits the correct payload shape', async () => {
    const repo = makeRepo('acme/api', 'acme', 'main')
    const store = makeStoreStub({
      installable: [repo],
      branchesByRepo: { 'acme/api': ['main', 'develop'] },
      job: { jobId: 'job-42' },
    })
    const onboard = scope.run(() => useRepoOnboard({ store: store as never }))!
    await onboard.loadInstallable()
    await onboard.toggleSelection('acme/api')
    onboard.setBranchPick('acme/api', 'develop', 'develop')
    const created = await onboard.submitBulkOnboard()
    expect(created).toEqual({ jobId: 'job-42' })
    const body = store.submitBulkOnboard.mock.calls[0][0] as BulkOnboardRequestBody
    expect(body.items).toEqual([
      { fullName: 'acme/api', mainBranch: 'main', developBranch: 'develop', uatBranch: undefined },
    ])
  })

  it('selectAllForOwner skips already-tracked repos', async () => {
    const a = makeRepo('acme/api', 'acme')
    const b = makeRepo('acme/web', 'acme')
    b.alreadyTracked = true
    const store = makeStoreStub({
      installable: [a, b],
      branchesByRepo: { 'acme/api': ['main'] },
    })
    const onboard = scope.run(() => useRepoOnboard({ store: store as never }))!
    await onboard.loadInstallable()
    onboard.selectAllForOwner('acme', true)
    expect(onboard.selection.value.has('acme/api')).toBe(true)
    expect(onboard.selection.value.has('acme/web')).toBe(false)
  })
})
