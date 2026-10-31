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
 * The rest of leave: work from home, half days, who sees the leave type on
 * the team calendar, HR adjusting a balance, and the approver's bell.
 */
import { approveLeave, requestLeave, requestWfh } from '../fixtures/api.ts'
import type { StackClient } from '../fixtures/client.ts'
import { upcomingWeekdays } from '../fixtures/dates.ts'
import { expect, test } from '../fixtures/test.ts'
import { pickOption } from '../screens/forms.ts'
import { allCaughtUp, dayLabel, myRequests, openApproval, showCalendarMonth } from '../screens/leave.ts'

function team(stack: StackClient) {
  return stack.seedOrg({
    members: [
      { key: 'hr', role: 'hr', name: 'Hana People' },
      { key: 'mgr', role: 'manager', name: 'Maya Manager' },
      { key: 'emp', role: 'developer', name: 'Eli Employee', manager: 'mgr' },
      { key: 'peer', role: 'developer', name: 'Pia Peer', manager: 'mgr' },
    ],
  })
}

test('a work-from-home day is asked for, approved and marked on the calendar', async ({ signedIn, stack }) => {
  const org = await team(stack)
  const days = upcomingWeekdays()
  const employee = await signedIn(org.members.emp)
  await employee.goto('/leave')
  await employee.getByRole('button', { name: 'Work from home' }).click()
  await expect(employee.getByRole('heading', { name: 'Work from home', level: 2 })).toBeVisible()
  await employee.getByLabel('From', { exact: true }).fill(days.from)
  await employee.getByLabel('To', { exact: true }).fill(days.from)
  await employee.getByRole('button', { name: 'Send request' }).click()
  await expect(employee.getByText('Request sent')).toBeVisible()

  const manager = await signedIn(org.members.mgr)
  await openApproval(manager, 'Eli Employee')
  await manager.getByRole('button', { name: 'Approve' }).click()
  await expect(allCaughtUp(manager)).toBeVisible()
  await manager.goto('/leave/team')
  const month = await showCalendarMonth(manager, days.start)
  await expect(month.getByTitle(/^Eli Employee\b.*Work from home/).first()).toBeVisible()
})

test('a morning off is a half day, shown as one', async ({ signedIn, stack }) => {
  const org = await team(stack)
  const days = upcomingWeekdays()
  const employee = await signedIn(org.members.emp)
  await employee.goto('/leave')
  await employee.getByRole('button', { name: 'Request leave' }).click()
  await employee.getByRole('radio', { name: /Casual leave/ }).check()
  await employee.getByLabel('From', { exact: true }).fill(days.from)
  await employee.getByLabel('To', { exact: true }).fill(days.from)
  await employee.getByRole('radiogroup', { name: 'Part of the day' }).getByRole('radio', { name: 'Morning' }).click()
  await employee.getByRole('button', { name: 'Send request' }).click()
  await expect(employee.getByText('Request sent')).toBeVisible()
  await expect(myRequests(employee).getByText(/Half day, morning/).first()).toBeVisible()
  await expect(employee.getByText('0 used · 0.5 pending · of 10').first()).toBeVisible()
})

test('the leave type shows to the manager but not to a teammate', async ({ signedIn, stack }) => {
  const org = await team(stack)
  const days = upcomingWeekdays()
  const request = await requestLeave(await stack.api(org.members.emp), org.leaveTypes.CL, days, 'Private')
  await approveLeave(await stack.api(org.members.mgr), request.id)
  await requestWfh(await stack.api(org.members.peer), upcomingWeekdays(5), 'Unrelated')

  for (const [who, title] of [['mgr', 'Eli Employee · Casual leave'], ['peer', 'Eli Employee · Leave']] as const) {
    const page = await signedIn(org.members[who])
    await page.goto('/leave/team')
    const month = await showCalendarMonth(page, days.start)
    const day = month.getByRole('button', { name: new RegExp(`^${dayLabel(days.start)},`) })
    await expect(day.getByTitle(title, { exact: true }), `${who} sees "${title}"`).toBeVisible()
  }
})

test('HR adjusts a leave balance, and the ledger shows why', async ({ signedIn, stack }) => {
  const org = await team(stack)
  const hr = await signedIn(org.members.hr)
  await hr.goto(`/people/${org.members.emp.id}`)
  await hr.getByRole('tab', { name: 'Leave' }).click()
  await hr.getByRole('button', { name: 'Adjust balance' }).click()
  const dialog = hr.getByRole('dialog').filter({ hasText: 'Adjust balance' })
  await pickOption(dialog, 'Leave type', /Casual leave/)
  await dialog.getByRole('spinbutton', { name: 'Days (negative removes)' }).fill('2')
  await dialog.getByLabel('Note').fill('Carried over from last year')
  await dialog.getByRole('button', { name: 'Save adjustment' }).click()
  await expect(dialog).toBeHidden()
  await expect(hr.getByText('Carried over from last year')).toBeVisible()
})

test('the approver is told about a new request, and can clear it', async ({ signedIn, stack }) => {
  const org = await team(stack)
  await requestLeave(await stack.api(org.members.emp), org.leaveTypes.CL, upcomingWeekdays(), 'School play')
  const manager = await signedIn(org.members.mgr)
  await manager.goto('/leave')
  await manager.getByRole('button', { name: /^Notifications, 1 unread/ }).click()
  await expect(manager.getByText('Request to review').first()).toBeVisible()
  await manager.getByRole('button', { name: 'Mark all read' }).click()
  await manager.keyboard.press('Escape')
  await expect(manager.getByRole('button', { name: 'Notifications', exact: true })).toBeVisible()
})
