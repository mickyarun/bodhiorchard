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
 * Leave from both sides: an employee asks, their manager or HR decides, and
 * the answer reaches the employee's list and the team calendar.
 */
import { approveLeave, requestLeave } from '../fixtures/api.ts'
import type { StackClient } from '../fixtures/client.ts'
import { upcomingWeekdays } from '../fixtures/dates.ts'
import { expect, test } from '../fixtures/test.ts'
import {
  allCaughtUp, dayLabel, myRequests, openApproval, sendLeaveRequest, showAllRequests, showCalendarMonth,
} from '../screens/leave.ts'

function team(stack: StackClient) {
  return stack.seedOrg({
    members: [
      { key: 'mgr', role: 'manager', name: 'Maya Manager' },
      { key: 'emp', role: 'developer', name: 'Eli Employee', manager: 'mgr' },
      { key: 'hr', role: 'hr', name: 'Hana People' },
    ],
  })
}

test('an employee asks for leave and their manager approves it', async ({ signedIn, stack }) => {
  const org = await team(stack)
  const employee = await signedIn(org.members.emp)
  await employee.goto('/leave')
  await expect(employee.getByRole('heading', { name: 'My leave', level: 1 })).toBeVisible()
  await sendLeaveRequest(employee, 'Casual leave', upcomingWeekdays(), 'Moving house')
  await expect(myRequests(employee).getByText('Pending', { exact: true })).toBeVisible()

  const manager = await signedIn(org.members.mgr)
  await openApproval(manager, 'Eli Employee')
  await expect(manager.getByText('Moving house')).toBeVisible()
  await manager.getByRole('button', { name: 'Approve' }).click()
  await expect(allCaughtUp(manager)).toBeVisible()

  await employee.reload()
  await showAllRequests(employee)
  await expect(myRequests(employee).getByText('Approved', { exact: true })).toBeVisible()
  await expect(myRequests(employee).getByText('Approved by Maya Manager')).toBeVisible()
})

test('HR rejects a request, and has to say why', async ({ signedIn, stack }) => {
  const org = await team(stack)
  await requestLeave(await stack.api(org.members.emp), org.leaveTypes.CL, upcomingWeekdays(), 'Long weekend')

  const hr = await signedIn(org.members.hr)
  await openApproval(hr, 'Eli Employee')
  await hr.getByRole('button', { name: 'Reject' }).click()
  await expect(hr.getByText(/Add a note so Eli.* knows why\./)).toBeVisible()
  await hr.getByLabel('Reason for rejecting').fill('Release week, please pick another date')
  await hr.getByRole('button', { name: 'Reject' }).click()
  await expect(allCaughtUp(hr)).toBeVisible()

  const employee = await signedIn(org.members.emp)
  await employee.goto('/leave')
  await showAllRequests(employee)
  await expect(myRequests(employee).getByText('Rejected', { exact: true })).toBeVisible()
  await expect(myRequests(employee).getByText(/Rejected by Hana People/)).toBeVisible()
})

test('an employee cancels a request that is still pending', async ({ signedIn, stack }) => {
  const org = await team(stack)
  await requestLeave(await stack.api(org.members.emp), org.leaveTypes.CL, upcomingWeekdays(), 'Dentist')

  const employee = await signedIn(org.members.emp)
  await employee.goto('/leave')
  await myRequests(employee).getByRole('button', { name: /^Options for / }).click()
  await employee.getByRole('menuitem', { name: 'Cancel request' })
    .or(employee.getByRole('listitem').filter({ hasText: 'Cancel request' }))
    .first()
    .click()
  const confirm = employee.getByRole('dialog').filter({ hasText: 'Cancel this request?' })
  await confirm.getByRole('button', { name: 'Cancel request' }).click()
  await expect(employee.getByText('Request cancelled')).toBeVisible()
  await showAllRequests(employee)
  await expect(myRequests(employee).getByText('Cancelled', { exact: true })).toBeVisible()

  const manager = await signedIn(org.members.mgr)
  await manager.goto('/leave/approvals')
  await expect(allCaughtUp(manager)).toBeVisible()
})

test('approved leave shows on the team calendar', async ({ signedIn, stack }) => {
  const org = await team(stack)
  const days = upcomingWeekdays()
  const request = await requestLeave(await stack.api(org.members.emp), org.leaveTypes.CL, days, 'Conference')
  await approveLeave(await stack.api(org.members.mgr), request.id)

  const manager = await signedIn(org.members.mgr)
  await manager.goto('/leave/team')
  await expect(manager.getByRole('heading', { name: 'Team calendar', level: 1 })).toBeVisible()
  const calendar = await showCalendarMonth(manager, days.start)
  await expect(calendar.getByRole('button', { name: `${dayLabel(days.start)}, 1 out` })).toContainText('Eli Employee')
})
