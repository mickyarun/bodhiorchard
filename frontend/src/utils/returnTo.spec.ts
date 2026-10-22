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

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isSafeReturnPath, rememberReturnTo, takeReturnTo } from '@/utils/returnTo'

describe('isSafeReturnPath', () => {
  it.each(['/leave', '/leave#slackCode=c&slackState=s', '/people/123?tab=leave', '/'])(
    'accepts the in-app path %s',
    path => expect(isSafeReturnPath(path)).toBe(true),
  )

  it.each([
    'https://evil.example/leave',
    '//evil.example/leave',
    '/\\evil.example',
    'javascript:alert(1)',
    'leave',
    '',
    '/le\nave',
    '/login',
    '/login?next=/leave',
    '/setup',
    '/change-password',
  ])('refuses %s', path => expect(isSafeReturnPath(path)).toBe(false))

  it('only refuses login itself, not pages that start with the same letters', () => {
    expect(isSafeReturnPath('/login-help')).toBe(true)
  })
})

describe('return-to', () => {
  beforeEach(() => sessionStorage.clear())
  afterEach(() => vi.useRealTimers())

  it('gives the remembered page back once, fragment included', () => {
    rememberReturnTo('/leave#slackCode=c&slackState=s')
    expect(takeReturnTo()).toBe('/leave#slackCode=c&slackState=s')
    expect(takeReturnTo()).toBeNull()
  })

  it('never remembers somewhere unsafe', () => {
    rememberReturnTo('//evil.example')
    expect(takeReturnTo()).toBeNull()
  })

  it('ignores an unsafe value someone put in storage', () => {
    const at = Date.now()
    sessionStorage.setItem('bodhiorchard_return_to', JSON.stringify({ path: '//evil.example', at }))
    expect(takeReturnTo()).toBeNull()
    sessionStorage.setItem('bodhiorchard_return_to', 'https://evil.example')
    expect(takeReturnTo()).toBeNull()
  })

  it('forgets an abandoned sign-in after a while', () => {
    vi.useFakeTimers()
    rememberReturnTo('/leave')
    vi.advanceTimersByTime(16 * 60 * 1000)
    expect(takeReturnTo()).toBeNull()
  })
})
