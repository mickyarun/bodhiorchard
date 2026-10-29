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

/**
 * Screens that change shape on a phone (the `mobile` project runs these on a
 * Pixel 7 profile): the approval opens inline in the queue, and the team
 * calendar is an agenda instead of a month grid.
 */
import { approveLeave, requestLeave } from '../fixtures/api.ts'
import type { StackClient } from '../fixtures/client.ts'
import { upcomingWeekdays } from '../fixtures/dates.ts'
import { expect, test } from '../fixtures/test.ts'
import { allCaughtUp, openApproval, showCalendarMonth } from '../screens/leave.ts'
import { signInWithPassword } from '../screens/login.ts'

function team(stack: StackClient) {
  return stack.seedOrg({
    members: [
      { key: 'mgr', role: 'manager', name: 'Maya Manager' },
      { key: 'emp', role: 'developer', name: 'Eli Employee', manager: 'mgr' },
    ],
  })
}

test.describe('on a phone', { tag: '@mobile' }, () => {
  test('a manager approves a request inline in the queue', async ({ signedIn, stack }) => {
    const org = await team(stack)
    await requestLeave(await stack.api(org.members.emp), org.leaveTypes.CL, upcomingWeekdays(), 'Family visit')

    const manager = await signedIn(org.members.mgr)
    await openApproval(manager, 'Eli Employee')
    const card = manager.getByRole('region', { name: 'Requests' }).getByRole('region', { name: 'Eli Employee' })
    await expect(card.getByText('“Family visit”')).toBeVisible()
    await card.getByRole('button', { name: 'Approve' }).click()
    await expect(allCaughtUp(manager)).toBeVisible()
  })

  test('the team calendar lists who is out as an agenda', async ({ signedIn, stack }) => {
    const org = await team(stack)
    const days = upcomingWeekdays()
    const request = await requestLeave(await stack.api(org.members.emp), org.leaveTypes.CL, days, 'Conference')
    await approveLeave(await stack.api(org.members.mgr), request.id)

    const manager = await signedIn(org.members.mgr)
    await manager.goto('/leave/team')
    const month = await showCalendarMonth(manager, days.start)
    await expect(month.getByRole('grid')).toHaveCount(0)
    await expect(month.getByText('Eli Employee').first()).toBeVisible()
  })

  test('signing in reaches the dashboard', async ({ page, stack }) => {
    const org = await stack.seedOrg({ primary: true, members: [{ key: 'dev', role: 'developer', name: 'Pia Phone' }] })
    await page.goto('/login')
    await signInWithPassword(page, org.members.dev.email, org.members.dev.password)
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(/, Pia$/)
  })
})
