// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { describe, expect, it } from 'vitest'
import { isInviteUnexpired } from './inviteExpiry'

describe('isInviteUnexpired', () => {
  const now = Date.parse('2026-07-21T10:00:00Z')

  it('keeps legacy invitations that have no expiry', () => {
    expect(isInviteUnexpired(undefined, now)).toBe(true)
  })

  it('accepts a future expiry and rejects elapsed or malformed values', () => {
    expect(isInviteUnexpired('2026-07-21T10:00:01Z', now)).toBe(true)
    expect(isInviteUnexpired('2026-07-21T10:00:00Z', now)).toBe(false)
    expect(isInviteUnexpired('not-a-date', now)).toBe(false)
  })
})
