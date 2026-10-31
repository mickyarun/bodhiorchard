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

/** Leave reports: everyone's for HR, direct reports' for a manager, none otherwise. */
import { readFileSync } from 'node:fs'
import type { Page } from '@playwright/test'
import { approveLeave, requestLeave } from '../fixtures/api.ts'
import type { StackClient } from '../fixtures/client.ts'
import { upcomingWeekdays, type LeaveDays } from '../fixtures/dates.ts'
import { expect, test } from '../fixtures/test.ts'
import { pickOption } from '../screens/forms.ts'
import { navLink } from '../screens/shell.ts'

async function teamWithLeave(stack: StackClient, days: LeaveDays) {
  const org = await stack.seedOrg({
    members: [
      { key: 'hr', role: 'hr', name: 'Hana People' },
      { key: 'mgr', role: 'manager', name: 'Maya Manager' },
      { key: 'emp', role: 'developer', name: 'Eli Employee', manager: 'mgr' },
      { key: 'peer', role: 'developer', name: 'Pia Peer' },
    ],
  })
  const request = await requestLeave(await stack.api(org.members.emp), org.leaveTypes.CL, days, 'Family wedding')
  await approveLeave(await stack.api(org.members.mgr), request.id)
  return org
}

/** Narrows the report to exactly the leave's dates, so no month boundary matters. */
async function onlyThoseDays(page: Page, days: LeaveDays): Promise<void> {
  await pickOption(page, 'Dates', /^Custom/)
  await page.getByLabel('From', { exact: true }).fill(days.from)
  await page.getByLabel('To', { exact: true }).fill(days.to)
}

test('HR sees everyone, switches reports and exports a CSV', async ({ signedIn, stack }) => {
  const days = upcomingWeekdays()
  const org = await teamWithLeave(stack, days)
  const page = await signedIn(org.members.hr)
  await page.goto('/leave/reports')
  await expect(page.getByRole('heading', { name: 'Leave reports', level: 1 })).toBeVisible()
  await expect(page.getByText('Everyone in the organisation.')).toBeVisible()
  await onlyThoseDays(page, days)

  const summary = page.getByRole('region', { name: 'Leave taken by person' })
  await expect(summary.getByText('Eli Employee')).toBeVisible()

  await page.getByRole('radiogroup', { name: 'Report' }).getByRole('radio', { name: 'Requests' }).click()
  const requests = page.getByRole('region', { name: 'Every request' })
  await expect(requests.getByRole('row').filter({ hasText: 'Eli Employee' })).toContainText('Approved')

  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export CSV' }).click()
  const file = await download
  expect(file.suggestedFilename()).toMatch(/\.csv$/)
  expect(readFileSync(await file.path(), 'utf8')).toContain('Eli Employee')
})

test('a manager sees only their direct reports', async ({ signedIn, stack }) => {
  const days = upcomingWeekdays()
  const org = await teamWithLeave(stack, days)
  const page = await signedIn(org.members.mgr)
  await page.goto('/leave')
  await navLink(page, 'Leave reports').click()
  await expect(page.getByText('Your direct reports.')).toBeVisible()
  await onlyThoseDays(page, days)
  const summary = page.getByRole('region', { name: 'Leave taken by person' })
  await expect(summary.getByText('Eli Employee')).toBeVisible()
  await expect(summary.getByText('Pia Peer')).toHaveCount(0)
})

test('someone with no reports gets no report', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  await page.goto('/leave')
  await expect(navLink(page, 'Team calendar')).toBeVisible()
  await expect(navLink(page, 'Leave reports')).toHaveCount(0)
  await page.goto('/leave/reports')
  await expect(page.getByText('No reports for you yet')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Export CSV' })).toBeDisabled()
})
