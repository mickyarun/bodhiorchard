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
 * The setup wizard's steps: what each one needs before Continue moves on,
 * the slug made from the organization name, and the step bounds.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/router', () => ({ resetSetupCache: vi.fn() }))

import { useSetupStore } from '@/stores/setup'
import type { SetupState } from '@/types/setup'

type Repo = SetupState['sourceCode']['repos'][number]

const ORG = 1
const ADMIN = 2
const SOURCE = 4

function storeAt(step: number) {
  const store = useSetupStore()
  store.goToStep(step)
  return store
}

beforeEach(() => setActivePinia(createPinia()))

describe('generateSlug', () => {
  it.each([
    ['Acme Inc', 'acme-inc'],
    ['Acme   Corp  Ltd', 'acme-corp-ltd'],
    ['R&D Labs (UK)', 'rd-labs-uk'],
    ['Café 42', 'caf-42'],
    ['already-a-slug', 'already-a-slug'],
    ['Two -- dashes', 'two-dashes'],
  ])('turns %j into %j', (name, slug) => {
    expect(useSetupStore().generateSlug(name)).toBe(slug)
  })
})

describe('organization step', () => {
  it.each([
    ['Acme', 'acme', true],
    ['Acme', 'a', true],
    ['Acme', 'acme-inc-2', true],
    ['', 'acme', false],
    ['   ', 'acme', false],
    ['Acme', '', false],
    ['Acme', 'Acme', false],
    ['Acme', '-acme', false],
    ['Acme', 'acme-', false],
    ['Acme', 'acme inc', false],
  ])('name %j with slug %j is valid: %s', (name, slug, valid) => {
    const store = storeAt(ORG)
    store.state.organization = { name, slug }
    expect(store.validateCurrentStep()).toBe(valid)
  })

  it('does not move on while invalid', () => {
    const store = storeAt(ORG)
    expect(store.nextStep()).toBe(false)
    expect(store.currentStep).toBe(ORG)
    store.state.organization = { name: 'Acme', slug: 'acme' }
    expect(store.nextStep()).toBe(true)
    expect(store.currentStep).toBe(ADMIN)
    expect(store.state.currentStep).toBe(ADMIN)
  })
})

describe('admin step', () => {
  it.each([
    [{ name: 'Ana', email: 'ana@example.com', password: '12345678' }, true],
    [{ name: 'Ana', email: 'ana@example.com', password: '1234567' }, false],
    [{ name: '  ', email: 'ana@example.com', password: '12345678' }, false],
    [{ name: 'Ana', email: 'ana@example', password: '12345678' }, false],
    [{ name: 'Ana', email: 'ana @example.com', password: '12345678' }, false],
    [{ name: 'Ana', email: '', password: '12345678' }, false],
  ])('%j is valid: %s', (admin, valid) => {
    const store = storeAt(ADMIN)
    store.state.admin = admin
    expect(store.validateCurrentStep()).toBe(valid)
  })
})

describe('source code step', () => {
  function withRepos(repos: Partial<Repo>[]) {
    const store = storeAt(SOURCE)
    store.state.sourceCode.repos = repos as Repo[]
    return store
  }

  it('needs at least one repository', () => {
    expect(withRepos([]).validateCurrentStep()).toBe(false)
  })

  it('needs a main branch on every repository', () => {
    expect(withRepos([{ gitHubFullName: 'acme/api', mainBranch: 'main' }, { gitHubFullName: 'acme/web' }])
      .validateCurrentStep()).toBe(false)
  })

  it('needs a develop branch only for a local folder', () => {
    expect(withRepos([{ source: 'local-path', mainBranch: 'main' }]).validateCurrentStep()).toBe(false)
    expect(withRepos([{ source: 'local-path', mainBranch: 'main', developBranch: 'develop' }])
      .validateCurrentStep()).toBe(true)
    expect(withRepos([{ gitHubFullName: 'acme/api', mainBranch: 'main' }]).validateCurrentStep()).toBe(true)
  })
})

describe('step navigation', () => {
  it('lets the welcome, AI and review steps through without input', () => {
    for (const step of [0, 3, 5]) expect(storeAt(step).validateCurrentStep()).toBe(true)
  })

  it('stays inside the six steps', () => {
    const store = useSetupStore()
    store.prevStep()
    expect(store.currentStep).toBe(0)
    expect(store.isFirstStep).toBe(true)
    store.goToStep(6)
    store.goToStep(-1)
    expect(store.currentStep).toBe(0)
    store.goToStep(5)
    expect(store.isLastStep).toBe(true)
    expect(store.progress).toBe(100)
    expect(store.nextStep()).toBe(true)
    expect(store.currentStep).toBe(5)
  })
})
