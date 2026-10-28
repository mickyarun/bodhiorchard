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
  coerceEffort,
  coerceModel,
  defaultSkillCaps,
  effortOptions,
  iterationModelOptions,
  modelOptions,
  skillCapsFromPayload,
  supportsModelChoice,
  type SkillCaps,
} from './skillCapabilities.util'

const caps: SkillCaps = {
  models: [{ id: '', label: 'Default' }, { id: 'sonnet', label: 'Sonnet' }],
  defaultModel: '',
  effortValues: ['low', 'high'],
  supportsEffort: true,
  supportsIterationModel: true,
}

describe('skillCapsFromPayload', () => {
  it('picks the current provider and keeps effort only when supported', () => {
    const parsed = skillCapsFromPayload({
      current_provider: 'codex',
      providers: [
        { provider: 'claude', models: [{ id: 'x', label: 'X' }] },
        { provider: 'codex', models: [], default_model: 'gpt', supports_effort: false, effort_values: ['low'] },
      ],
    })
    expect(parsed).toEqual({
      models: [{ id: '', label: 'Default' }],
      defaultModel: 'gpt',
      effortValues: [],
      supportsEffort: false,
      supportsIterationModel: false,
    })
  })

  it('defaults to claude and returns null when the provider is missing', () => {
    expect(skillCapsFromPayload({ providers: [{ provider: 'claude' }] })?.defaultModel).toBe('')
    expect(skillCapsFromPayload({ current_provider: 'ollama', providers: [] })).toBeNull()
  })
})

describe('coercion', () => {
  it('keeps a listed model and falls back to the provider default otherwise', () => {
    expect(coerceModel(caps, 'sonnet')).toBe('sonnet')
    expect(coerceModel({ ...caps, defaultModel: 'auto' }, 'opus')).toBe('auto')
    expect(coerceModel(caps, null)).toBe('')
  })

  it('drops effort the provider cannot honour', () => {
    expect(coerceEffort(caps, 'high')).toBe('high')
    expect(coerceEffort(caps, 'max')).toBe('')
    expect(coerceEffort({ ...caps, supportsEffort: false }, 'high')).toBe('')
  })
})

describe('options', () => {
  it('needs more than one model to offer a choice', () => {
    expect(supportsModelChoice(caps)).toBe(true)
    expect(supportsModelChoice(defaultSkillCaps())).toBe(false)
  })

  it('adds an unlisted saved model as a labelled fallback', () => {
    expect(modelOptions(caps, 'opus').at(-1)).toEqual({ title: 'opus (falls back to default)', value: 'opus' })
    expect(modelOptions(caps, 'sonnet')).toHaveLength(2)
  })

  it('names the empty iteration model "Same as model"', () => {
    expect(iterationModelOptions(caps, '')[0]).toEqual({ title: 'Same as model', value: '' })
  })

  it('title-cases effort values after Default', () => {
    expect(effortOptions(caps)).toEqual([
      { title: 'Default', value: '' },
      { title: 'Low', value: 'low' },
      { title: 'High', value: 'high' },
    ])
  })
})
