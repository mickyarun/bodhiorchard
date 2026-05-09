// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { describe, expect, it } from 'vitest'
import {
  AGENT_ERROR_CODES,
  friendlyAgentError,
  isAgentErrorCode,
} from './agentErrors'

describe('isAgentErrorCode', () => {
  it.each(Object.values(AGENT_ERROR_CODES))('accepts known code %s', (code) => {
    expect(isAgentErrorCode(code)).toBe(true)
  })

  it.each([null, undefined, '', 'random_code', 42, {}])(
    'rejects unknown value %p',
    (value) => {
      expect(isAgentErrorCode(value)).toBe(false)
    },
  )
})

describe('friendlyAgentError', () => {
  it('returns the max-turns CTA package for max_turns', () => {
    const result = friendlyAgentError(AGENT_ERROR_CODES.MAX_TURNS, null)
    expect(result.headline).toContain('maximum turns limit')
    expect(result.suggestSettings).toBe(true)
    expect(result.settingsRoute).toBe('/settings/agent-prompts')
    expect(result.suggestContactAdmin).toBe(true)
  })

  it('hides settings deep-link for non-max-turns categories', () => {
    for (const code of [
      AGENT_ERROR_CODES.TIMEOUT,
      AGENT_ERROR_CODES.BINARY_MISSING,
      AGENT_ERROR_CODES.UNKNOWN,
    ]) {
      const result = friendlyAgentError(code, null)
      expect(result.suggestSettings).toBe(false)
      expect(result.settingsRoute).toBeNull()
      expect(result.suggestContactAdmin).toBe(true)
    }
  })

  it('renders specific headlines per code', () => {
    expect(friendlyAgentError(AGENT_ERROR_CODES.TIMEOUT, null).headline)
      .toContain('timed out')
    expect(friendlyAgentError(AGENT_ERROR_CODES.BINARY_MISSING, null).headline)
      .toContain('Claude CLI is not installed')
    expect(friendlyAgentError(AGENT_ERROR_CODES.UNKNOWN, null).headline)
      .toContain('failed unexpectedly')
  })

  it('falls back to backend message when code is unknown or missing', () => {
    expect(friendlyAgentError(null, 'Something exploded').headline)
      .toBe('Something exploded')
    expect(friendlyAgentError(undefined, 'Something exploded').headline)
      .toBe('Something exploded')
    expect(friendlyAgentError('mystery_code', 'Backend detail').headline)
      .toBe('Backend detail')
  })

  it('falls back to a generic headline when neither code nor message is given', () => {
    const result = friendlyAgentError(null, null)
    expect(result.headline).toContain('AI agent failed')
    expect(result.suggestContactAdmin).toBe(true)
  })

  it('always invites the user to contact their admin on failure', () => {
    const cases = [
      friendlyAgentError(AGENT_ERROR_CODES.MAX_TURNS, null),
      friendlyAgentError(AGENT_ERROR_CODES.TIMEOUT, null),
      friendlyAgentError(AGENT_ERROR_CODES.UNKNOWN, null),
      friendlyAgentError(null, 'raw text'),
    ]
    for (const c of cases) {
      expect(c.suggestContactAdmin).toBe(true)
    }
  })
})
