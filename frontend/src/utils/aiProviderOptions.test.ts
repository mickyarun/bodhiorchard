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
import type { ProviderCaps } from '@/constants/aiProviders'
import {
  authTiles,
  canSaveProvider,
  credentialPlaceholder,
  modeDescription,
  providerSummary,
  providerTiles,
  recommendedMode,
  testOutcome,
  visibleModes,
  withArticle,
} from './aiProviderOptions'

function caps(provider: string, cli: string | null, modes: [string, boolean][]): ProviderCaps {
  return {
    provider,
    cli,
    models: [],
    default_model: '',
    supports_effort: false,
    effort_values: [],
    supports_iteration_model: false,
    auth_modes: modes.map(([value, requires_secret]) => ({ value, label: value === 'api_key' ? 'API key' : value, requires_secret })),
    install_hint: '',
    docs_url: '',
    supports_thinking: false,
    supports_mcp: true,
    supports_files: true,
    dynamic_models: false,
    requires_base_url: false,
    default_base_url: null,
  }
}

const claude = caps('claude', 'claude', [['host', false], ['api_key', true], ['subscription', true]])
const ollama = caps('ollama', null, [['host', false], ['api_key', true]])

describe('modes per deployment', () => {
  it('hides the host login in Docker for CLI providers only', () => {
    expect(visibleModes(claude, 'docker').map(m => m.value)).toEqual(['api_key', 'subscription'])
    expect(visibleModes(ollama, 'docker').map(m => m.value)).toEqual(['host', 'api_key'])
    expect(visibleModes(claude, 'hybrid')).toHaveLength(3)
  })
  it('recommends a credential in Docker and the host login elsewhere', () => {
    expect(recommendedMode(claude, 'docker')).toBe('api_key')
    expect(recommendedMode(claude, 'hybrid')).toBe('host')
    expect(recommendedMode(ollama, 'docker')).toBe('host')
  })
  it('badges the recommended tile', () => {
    expect(authTiles(claude, 'hybrid').find(t => t.badge)?.value).toBe('host')
    expect(authTiles(undefined, 'hybrid')).toEqual([])
  })
})

describe('descriptions', () => {
  it('tells a host login from no credential', () => {
    expect(modeDescription(claude.auth_modes[0], claude)).toContain('login already on the host')
    expect(modeDescription(ollama.auth_modes[0], ollama)).toContain('Sends no credential')
    expect(modeDescription(claude.auth_modes[2], claude)).toContain('claude setup-token command')
    expect(modeDescription(claude.auth_modes[1], claude)).toContain('Paste an API key.')
  })
  it('names the CLI or the local server', () => {
    const [c, o] = providerTiles([claude, ollama])
    expect(c.description).toBe('Runs through the claude CLI.')
    expect(o.description).toContain('No CLI needed')
  })
})

describe('credentialPlaceholder', () => {
  it('matches the provider token shape', () => {
    expect(credentialPlaceholder('copilot', 'api_key')).toBe('ghp_…')
    expect(credentialPlaceholder('claude', 'subscription')).toBe('sk-ant-oat…')
  })
})

describe('canSaveProvider', () => {
  it('needs a typed secret unless the stored one still applies', () => {
    expect(canSaveProvider({ requiresSecret: false, hasStored: false, providerChanged: false, typed: '' })).toBe(true)
    expect(canSaveProvider({ requiresSecret: true, hasStored: true, providerChanged: false, typed: '' })).toBe(true)
    expect(canSaveProvider({ requiresSecret: true, hasStored: true, providerChanged: true, typed: '' })).toBe(false)
    expect(canSaveProvider({ requiresSecret: true, hasStored: false, providerChanged: false, typed: ' k ' })).toBe(true)
  })
})

describe('providerSummary', () => {
  it('says which provider and how it signs in', () => {
    expect(providerSummary(claude, claude.auth_modes[0])).toBe('Agents run through Claude, using the host login.')
    expect(providerSummary(claude, claude.auth_modes[1])).toBe('Agents run through Claude, using a stored API key.')
    expect(providerSummary(ollama, ollama.auth_modes[0])).toBe('Agents run through Ollama, with no credential.')
    expect(providerSummary(undefined, undefined)).toContain('Choose which agent')
  })
})

describe('withArticle', () => {
  it('picks a or an', () => {
    expect(withArticle('Anthropic API key')).toBe('an Anthropic API key')
    expect(withArticle('GitHub token')).toBe('a GitHub token')
  })
})

describe('testOutcome', () => {
  it('reads a missing CLI, a pass and a failure', () => {
    expect(testOutcome({ cli_available: false })).toMatchObject({ passed: false, showInstallHint: true })
    expect(testOutcome({ cli_available: true, test_passed: true, cli_version: '2.1' })).toEqual({ passed: true, message: '2.1', showInstallHint: false })
    expect(testOutcome({ cli_available: true, test_passed: false, error: 'nope' }).message).toBe('nope')
  })
})
