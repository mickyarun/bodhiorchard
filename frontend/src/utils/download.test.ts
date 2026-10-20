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

import { filenameFrom } from '@/utils/download'

describe('filenameFrom', () => {
  it('reads plain and encoded names', () => {
    expect(filenameFrom('attachment; filename="leave-summary-2026-06.csv"', 'x.csv')).toBe(
      'leave-summary-2026-06.csv',
    )
    expect(filenameFrom("attachment; filename*=UTF-8''a%20b.csv", 'x.csv')).toBe('a b.csv')
  })

  it('prefers the encoded name when both are sent', () => {
    const header = `attachment; filename="plain.csv"; filename*=UTF-8''r%C3%A9sum%C3%A9.csv`
    expect(filenameFrom(header, 'x.csv')).toBe('résumé.csv')
  })

  it('leaves a percent sign in a plain name alone', () => {
    expect(filenameFrom('attachment; filename="100%.csv"', 'x.csv')).toBe('100%.csv')
  })

  it('falls back to the plain name when the encoding is malformed', () => {
    const header = `attachment; filename="plain.csv"; filename*=UTF-8''bad%E0.csv`
    expect(filenameFrom(header, 'x.csv')).toBe('plain.csv')
  })

  it('falls back when the header is missing', () => {
    expect(filenameFrom(undefined, 'leave-history.csv')).toBe('leave-history.csv')
  })
})
