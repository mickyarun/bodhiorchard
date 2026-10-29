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
import type { Page } from '@playwright/test'
import { approveLeave, requestLeave, upcomingWeekdays } from '../fixtures/leave.ts'
import { seedOrg } from '../fixtures/stack.ts'
import { expect, test } from '../fixtures/test.ts'

function team() {
  return seedOrg({
    members: [
      { key: 'mgr', role: 'manager', name: 'Maya Manager' },
      { key: 'emp', role: 'developer', name: 'Eli Employee', manager: 'mgr' },
      { key: 'hr', role: 'hr', name: 'Hana People' },
    ],
  })
}

const myRequests = (page: Page) => page.getByRole('region', { name: 'My requests' })

/** Decided and cancelled requests leave the default "Upcoming" view. */
async function showAllRequests(page: Page): Promise<void> {
  await myRequests(page).getByRole('radio', { name: 'All' }).click()
}

const monthTitle = (day: Date): string => day.toLocaleString('en-GB', { month: 'long', year: 'numeric' })

async function openRequest(page: Page, employee: string): Promise<void> {
  await page.goto('/leave/approvals')
  await expect(page.getByRole('heading', { name: 'Approvals', level: 1 })).toBeVisible()
  await page.getByRole('button', { name: new RegExp(employee) }).click()
}

test('an employee asks for leave and their manager approves it', async ({ signedIn }) => {
  const org = await team()
  const days = upcomingWeekdays()
  const employee = await signedIn(org.members.emp)
  await employee.goto('/leave')
  await expect(employee.getByRole('heading', { name: 'My leave', level: 1 })).toBeVisible()
  await employee.getByRole('button', { name: 'Request leave' }).click()
  await expect(employee.getByRole('heading', { name: 'Request leave', level: 2 })).toBeVisible()
  await employee.getByRole('radio', { name: /Casual leave/ }).check()
  await employee.getByLabel('From', { exact: true }).fill(days.from)
  await employee.getByLabel('To', { exact: true }).fill(days.to)
  await employee.getByLabel('Reason (optional)').fill('Moving house')
  await employee.getByRole('button', { name: 'Send request' }).click()
  await expect(employee.getByText('Request sent')).toBeVisible()
  await expect(myRequests(employee).getByText('Pending', { exact: true })).toBeVisible()

  const manager = await signedIn(org.members.mgr)
  await openRequest(manager, 'Eli Employee')
  await expect(manager.getByText('Moving house')).toBeVisible()
  await manager.getByRole('button', { name: 'Approve' }).click()
  await expect(manager.getByText("You're all caught up")).toBeVisible()

  await employee.reload()
  await showAllRequests(employee)
  await expect(myRequests(employee).getByText('Approved', { exact: true })).toBeVisible()
  await expect(myRequests(employee).getByText('Approved by Maya Manager')).toBeVisible()
})

test('HR rejects a request, and has to say why', async ({ signedIn }) => {
  const org = await team()
  await requestLeave(org.members.emp, org.leaveTypes.CL, upcomingWeekdays(), 'Long weekend')

  const hr = await signedIn(org.members.hr)
  await openRequest(hr, 'Eli Employee')
  await hr.getByRole('button', { name: 'Reject' }).click()
  await expect(hr.getByText(/Add a note so Eli.* knows why\./)).toBeVisible()
  await hr.getByLabel('Reason for rejecting').fill('Release week, please pick another date')
  await hr.getByRole('button', { name: 'Reject' }).click()
  await expect(hr.getByText("You're all caught up")).toBeVisible()

  const employee = await signedIn(org.members.emp)
  await employee.goto('/leave')
  await showAllRequests(employee)
  await expect(myRequests(employee).getByText('Rejected', { exact: true })).toBeVisible()
  await expect(myRequests(employee).getByText(/Rejected by Hana People/)).toBeVisible()
})

test('an employee cancels a request that is still pending', async ({ signedIn }) => {
  const org = await team()
  await requestLeave(org.members.emp, org.leaveTypes.CL, upcomingWeekdays(), 'Dentist')

  const employee = await signedIn(org.members.emp)
  await employee.goto('/leave')
  await myRequests(employee).getByRole('button', { name: /^Options for / }).click()
  await employee.getByRole('menuitem', { name: 'Cancel request' }).or(
    employee.getByRole('listitem').filter({ hasText: 'Cancel request' }),
  ).first().click()
  const confirm = employee.getByRole('dialog').filter({ hasText: 'Cancel this request?' })
  await confirm.getByRole('button', { name: 'Cancel request' }).click()
  await expect(employee.getByText('Request cancelled')).toBeVisible()
  await showAllRequests(employee)
  await expect(myRequests(employee).getByText('Cancelled', { exact: true })).toBeVisible()

  const manager = await signedIn(org.members.mgr)
  await manager.goto('/leave/approvals')
  await expect(manager.getByText("You're all caught up")).toBeVisible()
})

test('approved leave shows on the team calendar', async ({ signedIn }) => {
  const org = await team()
  const days = upcomingWeekdays()
  const request = await requestLeave(org.members.emp, org.leaveTypes.CL, days, 'Conference')
  await approveLeave(org.members.mgr, request.id)

  const manager = await signedIn(org.members.mgr)
  await manager.goto('/leave/team')
  await expect(manager.getByRole('heading', { name: 'Team calendar', level: 1 })).toBeVisible()
  const today = new Date()
  const monthsAhead = (days.start.getFullYear() - today.getFullYear()) * 12 + days.start.getMonth() - today.getMonth()
  for (let step = 1; step <= monthsAhead; step += 1) {
    const shown = new Date(today.getFullYear(), today.getMonth() + step, 1)
    await manager.getByRole('button', { name: 'Next month' }).click()
    await expect(manager.getByRole('region', { name: monthTitle(shown) })).toBeVisible()
  }
  const calendar = manager.getByRole('region', { name: monthTitle(days.start) })
  const day = days.start.toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  await expect(calendar.getByRole('button', { name: `${day}, 1 out` })).toContainText('Eli Employee')
})
