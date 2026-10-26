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

import { beforeEach, describe, expect, it } from 'vitest'
import { afterSignIn } from '@/utils/afterSignIn'
import { forgetReturnTo, rememberReturnTo, takeReturnTo } from '@/utils/returnTo'
import { WORKSPACE_ENGINEERING } from '@/utils/workspace'

const engineer = { permissions: [WORKSPACE_ENGINEERING], character_model: 'barbarian' }
const peopleOnly = { permissions: [], character_model: null }

describe('afterSignIn', () => {
  beforeEach(() => {
    forgetReturnTo()
    sessionStorage.clear()
  })

  it('goes back to the page they were going to', () => {
    rememberReturnTo('/leave#slackCode=c&slackState=s')
    expect(afterSignIn(peopleOnly)).toBe('/leave#slackCode=c&slackState=s')
    expect(takeReturnTo()).toBeNull()
  })

  it('lands on their home otherwise', () => {
    expect(afterSignIn(engineer)).toEqual({ name: 'dashboard' })
    expect(afterSignIn(peopleOnly)).toEqual({ name: 'leave' })
  })

  it('sends an engineer without an avatar to pick one, keeping the page for after', () => {
    rememberReturnTo('/leave')
    expect(afterSignIn({ ...engineer, character_model: null })).toEqual({ name: 'character-select' })
    expect(takeReturnTo()).toBe('/leave')
  })

  it('never sends someone outside engineering to the avatar picker', () => {
    // e.g. after changing a temporary password
    rememberReturnTo('/people/1')
    expect(afterSignIn(peopleOnly)).toBe('/people/1')
  })

  it('lets the router guard sort out a profile that did not load', () => {
    expect(afterSignIn(null)).toBe('/')
  })
})
