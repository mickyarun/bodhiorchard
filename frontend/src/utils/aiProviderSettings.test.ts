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


import { describe, expect, it } from 'vitest'
import {
  buildSavePayload,
  hasUnsavedEdits,
  testRequestBody,
  type AiProviderEdits,
  type SavedSettings,
} from './aiProviderSettings'

const saved: SavedSettings = {
  provider: 'ollama', auth_mode: 'host', has_api_key: false, base_url: 'http://h:11434', model: 'qwen', thinking: true,
}
const edits: AiProviderEdits = {
  provider: 'ollama', authMode: 'host', baseUrl: ' http://h:11434 ', model: 'qwen', thinking: true, credential: '',
}

describe('hasUnsavedEdits', () => {
  it('is false before anything is saved or when nothing changed', () => {
    expect(hasUnsavedEdits(null, edits)).toBe(false)
    expect(hasUnsavedEdits(saved, edits)).toBe(false)
  })

  it('notices any changed field or a typed secret', () => {
    expect(hasUnsavedEdits(saved, { ...edits, thinking: false })).toBe(true)
    expect(hasUnsavedEdits(saved, { ...edits, model: '' })).toBe(true)
    expect(hasUnsavedEdits(saved, { ...edits, credential: ' k ' })).toBe(true)
  })
})

describe('buildSavePayload', () => {
  it('sends a typed secret as the OAuth token for subscriptions, else as the API key', () => {
    expect(buildSavePayload({ ...edits, authMode: 'subscription', credential: ' t ' }, true)).toMatchObject({ oauth_token: 't' })
    const apiKey = buildSavePayload({ ...edits, authMode: 'api_key', credential: 'k' }, true)
    expect(apiKey).toMatchObject({ api_key: 'k' })
    expect(apiKey).not.toHaveProperty('oauth_token')
  })

  it('leaves the secret out when the mode needs none or nothing was typed', () => {
    expect(buildSavePayload({ ...edits, credential: 'k' }, false)).toEqual({
      provider: 'ollama', auth_mode: 'host', base_url: 'http://h:11434', model: 'qwen', thinking: true,
    })
    expect(buildSavePayload(edits, true)).not.toHaveProperty('api_key')
  })
})

describe('testRequestBody', () => {
  it('tests the address on screen only for providers that need one', () => {
    expect(testRequestBody(true, { ...edits, model: '' })).toEqual({ base_url: 'http://h:11434', model: undefined, thinking: true })
    expect(testRequestBody(false, edits)).toBeNull()
  })
})
