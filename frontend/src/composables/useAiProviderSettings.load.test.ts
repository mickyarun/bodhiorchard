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
 * The AI settings say when the saved choice is in. Until then the panel
 * offers nothing to pick, since the saved choice would replace the pick.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn(), patch: vi.fn(), post: vi.fn() } }))

import api from '@/services/api'
import { useAiProviderSettings } from '@/composables/useAiProviderSettings'

const get = vi.mocked(api.get)

const CAPS = {
  providers: [{
    provider: 'claude',
    auth_modes: [
      { value: 'host', label: 'Host login', requires_secret: false },
      { value: 'api_key', label: 'Anthropic API key', requires_secret: true },
    ],
  }],
  deployment_mode: 'hybrid',
  current_provider: 'claude',
}
const SAVED = { provider: 'claude', auth_mode: 'api_key', has_api_key: true, base_url: null, model: null, thinking: false }

let releaseSaved: (value: unknown) => void

beforeEach(() => {
  get.mockReset()
  get.mockImplementation((url: string) => (url.endsWith('/capabilities')
    ? Promise.resolve({ data: CAPS })
    : new Promise((ok) => { releaseSaved = ok })))
})

describe('useAiProviderSettings load', () => {
  it('is not loaded until the saved choice arrives, then shows it', async () => {
    const ai = useAiProviderSettings()
    const loading = ai.load()
    await vi.waitFor(() => expect(get).toHaveBeenCalledTimes(2))
    expect(ai.loaded.value).toBe(false)

    releaseSaved({ data: SAVED })
    await loading
    expect(ai.loaded.value).toBe(true)
    expect(ai.authMode.value).toBe('api_key')
  })

  it('counts as loaded when the saved choice fails to load', async () => {
    get.mockImplementation((url: string) => (url.endsWith('/capabilities')
      ? Promise.resolve({ data: CAPS })
      : Promise.reject(new Error('Network Error'))))
    const ai = useAiProviderSettings()
    await ai.load()
    expect(ai.loaded.value).toBe(true)
  })
})
