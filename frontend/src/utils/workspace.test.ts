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
import { canOpenWorkspace, homeRouteFor, WORKSPACE_ENGINEERING } from './workspace'

describe('homeRouteFor', () => {
  it('sends engineers to the dashboard', () => {
    expect(homeRouteFor([WORKSPACE_ENGINEERING, 'buds:view'])).toEqual({ name: 'dashboard' })
  })

  it('sends people-only roles to leave', () => {
    expect(homeRouteFor([])).toEqual({ name: 'leave' })
    expect(homeRouteFor(['leave:approve', 'employees:view'])).toEqual({ name: 'leave' })
  })

  it('treats a missing permission list as people-only', () => {
    expect(homeRouteFor(undefined)).toEqual({ name: 'leave' })
    expect(homeRouteFor(null)).toEqual({ name: 'leave' })
  })
})

describe('canOpenWorkspace', () => {
  it('requires the workspace permission itself, not any engineering permission', () => {
    expect(canOpenWorkspace(['buds:view'], 'engineering')).toBe(false)
    expect(canOpenWorkspace([WORKSPACE_ENGINEERING], 'engineering')).toBe(true)
  })
})
