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

import { accessLine, formatBytes, maskLabel } from '@/utils/employeeRecords'

const person = { user_id: 'u1', name: 'Priya' }

describe('maskLabel', () => {
  it('never shows more than the last four', () => {
    expect(maskLabel({ is_set: true, last4: '7890' })).toBe('•••• 7890')
    expect(maskLabel({ is_set: true, last4: null })).toBe('Saved')
    expect(maskLabel({ is_set: false, last4: null })).toBe('—')
  })
})

describe('accessLine', () => {
  it('names the fields, never values', () => {
    const at = '2026-10-19T09:00:00Z'
    expect(accessLine({ action: 'field_revealed', actor: person, target: 'bank_account_number', at })).toBe(
      'Priya viewed Account number',
    )
    expect(accessLine({ action: 'details_updated', actor: person, target: 'aadhaar,pan', at })).toBe(
      'Priya changed Aadhaar and PAN',
    )
    expect(accessLine({ action: 'document_viewed', actor: person, target: 'd1', at })).toBe(
      'Priya opened a document',
    )
  })
})

describe('formatBytes', () => {
  it('rounds to KB or MB', () => {
    expect(formatBytes(1_258_291)).toBe('1.2 MB')
    expect(formatBytes(348_160)).toBe('340 KB')
    expect(formatBytes(10)).toBe('1 KB')
    expect(formatBytes(10 * 1024 * 1024)).toBe('10 MB')
  })
})
