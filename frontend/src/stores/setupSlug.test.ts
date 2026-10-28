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
 * The slug the wizard makes from the organization name passes the
 * wizard's own check, even when the name starts or ends with a space or a
 * symbol (a pasted "Acme Inc ", say).
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/router', () => ({ resetSetupCache: vi.fn() }))

import { useSetupStore } from '@/stores/setup'

beforeEach(() => setActivePinia(createPinia()))

describe('generateSlug at the edges of the name', () => {
  it.each([
    ['Acme Inc ', 'acme-inc'],
    ['  Acme Inc', 'acme-inc'],
    ['Acme - ', 'acme'],
    ['& Acme &', 'acme'],
  ])('turns %j into %j', (name, slug) => {
    expect(useSetupStore().generateSlug(name)).toBe(slug)
  })

  it('makes a slug the organization step accepts', () => {
    const store = useSetupStore()
    store.goToStep(1)
    const name = 'Acme Inc '
    store.state.organization = { name, slug: store.generateSlug(name) }
    expect(store.validateCurrentStep()).toBe(true)
  })
})
