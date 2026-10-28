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

import { initialsOf, resolveAvatarUrl } from './avatar'

describe('resolveAvatarUrl', () => {
  const hosted = '/api/v1/employees/avatars/abc'

  it('returns null for no photo', () => {
    expect(resolveAvatarUrl(null, '')).toBeNull()
  })

  it('passes Slack CDN URLs through', () => {
    const slack = 'https://avatars.slack-edge.com/x.png'
    expect(resolveAvatarUrl(slack, 'https://api.example.com/api')).toBe(slack)
  })

  it('keeps hosted paths relative on a same-origin deployment', () => {
    expect(resolveAvatarUrl(hosted, '')).toBe(hosted)
    expect(resolveAvatarUrl(hosted, '/api')).toBe(hosted)
  })

  it('rebases hosted paths onto a split-host API', () => {
    expect(resolveAvatarUrl(hosted, 'https://api.example.com/api')).toBe(
      'https://api.example.com/api/v1/employees/avatars/abc',
    )
  })
})

describe('initialsOf', () => {
  it('takes the first two initials', () => {
    expect(initialsOf('Ada Byron Lovelace')).toBe('AB')
  })

  it('tolerates extra spaces and empty names', () => {
    expect(initialsOf('  sid  ')).toBe('S')
    expect(initialsOf('')).toBe('?')
  })

  it('ignores a trailing ellipsis and any whitespace', () => {
    expect(initialsOf('38ca3fde…')).toBe('3')
    expect(initialsOf('…')).toBe('?')
    expect(initialsOf('Alice\tKim')).toBe('AK')
  })
})
