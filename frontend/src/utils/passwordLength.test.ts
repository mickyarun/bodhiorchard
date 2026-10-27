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
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, passwordLengthRule } from './passwordLength'

describe('passwordLengthRule', () => {
  it('refuses a password shorter than the minimum', () => {
    expect(passwordLengthRule('x'.repeat(PASSWORD_MIN_LENGTH - 1))).toBe('At least 8 characters')
  })

  it('accepts both ends of the allowed range', () => {
    expect(passwordLengthRule('x'.repeat(PASSWORD_MIN_LENGTH))).toBe(true)
    expect(passwordLengthRule('x'.repeat(PASSWORD_MAX_LENGTH))).toBe(true)
  })

  it('refuses a password longer than the backend allows', () => {
    expect(passwordLengthRule('x'.repeat(PASSWORD_MAX_LENGTH + 1))).toBe('At most 128 characters')
  })
})
