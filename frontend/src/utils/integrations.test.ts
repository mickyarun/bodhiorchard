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
  CONNECTED,
  NOT_CONNECTED,
  aiStatus,
  githubStatus,
  integrationActionLabel,
  mcpStatus,
  slackStatus,
  primaryIntegration,
  type IntegrationId,
  type IntegrationStatus,
} from './integrations'

const ORDER: IntegrationId[] = ['ai', 'github', 'slack', 'mcp']

function statuses(connected: IntegrationId[]): Record<IntegrationId, IntegrationStatus> {
  return Object.fromEntries(ORDER.map(id => [id, connected.includes(id) ? CONNECTED : NOT_CONNECTED])) as Record<
    IntegrationId,
    IntegrationStatus
  >
}

describe('primaryIntegration', () => {
  it('picks the first card that is not connected', () => {
    expect(primaryIntegration(ORDER, statuses(['ai']), null)).toBe('github')
    expect(primaryIntegration(ORDER, statuses(['ai', 'github', 'slack']), null)).toBe('mcp')
  })
  it('picks none when everything is connected or a card is open', () => {
    expect(primaryIntegration(ORDER, statuses(ORDER), null)).toBeNull()
    expect(primaryIntegration(ORDER, statuses([]), 'slack')).toBeNull()
  })
})

describe('integrationActionLabel', () => {
  it('reads as the next step', () => {
    expect(integrationActionLabel(false, false, 'Connect Slack')).toBe('Connect Slack')
    expect(integrationActionLabel(false, true, 'Connect Slack')).toBe('Manage')
    expect(integrationActionLabel(true, false, 'Connect Slack')).toBe('Hide')
  })
})

describe('status tags', () => {
  it('maps the GitHub lifecycle', () => {
    expect(githubStatus('ready')).toEqual(CONNECTED)
    expect(githubStatus('awaiting_install')).toMatchObject({ label: 'Install pending', color: 'warning', connected: false })
    expect(githubStatus('not_configured')).toEqual(NOT_CONNECTED)
  })
  it('reads Slack and the MCP token', () => {
    expect(slackStatus(true)).toEqual(CONNECTED)
    expect(mcpStatus(false)).toMatchObject({ label: 'No token', connected: false })
    expect(mcpStatus(true).color).toBe('success')
  })
  it('only tags the AI provider after a test', () => {
    expect(aiStatus('idle').label).toBe('')
    expect(aiStatus('passed')).toEqual(CONNECTED)
    expect(aiStatus('failed').color).toBe('error')
  })
})
