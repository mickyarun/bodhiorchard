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

import { connectOutcome } from '@/composables/useSlackStatus'

describe('connectOutcome', () => {
  it('explains what happened when Slack sends the member back', () => {
    expect(connectOutcome(null)).toBeNull()
    expect(connectOutcome('connected')?.ok).toBe(true)
    expect(connectOutcome('moved')?.text).toContain('instead of your other team')
    expect(connectOutcome('wrong_account')?.text).toContain('your own Slack account')
    expect(connectOutcome('not_yours')?.text).toContain('started by someone else')
    expect(connectOutcome('unlinkable')?.text).toContain('Ask HR to link it')
    expect(connectOutcome('something_new')).toEqual(connectOutcome('failed'))
  })
})
