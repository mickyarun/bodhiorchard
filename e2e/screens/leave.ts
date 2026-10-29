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

/** My leave, the request panel, approvals and the team calendar. */
import { expect, type Locator, type Page } from '@playwright/test'
import type { LeaveDays } from '../fixtures/dates.ts'

export const monthTitle = (day: Date): string => day.toLocaleString('en-GB', { month: 'long', year: 'numeric' })

export function myRequests(page: Page): Locator {
  return page.getByRole('region', { name: 'My requests' })
}

/** Decided and cancelled requests leave the default "Upcoming" view. */
export async function showAllRequests(page: Page): Promise<void> {
  await myRequests(page).getByRole('radio', { name: 'All' }).click()
}

export async function sendLeaveRequest(page: Page, leaveType: string, days: LeaveDays, reason: string): Promise<void> {
  await page.getByRole('button', { name: 'Request leave' }).click()
  await expect(page.getByRole('heading', { name: 'Request leave', level: 2 })).toBeVisible()
  await page.getByRole('radio', { name: new RegExp(leaveType) }).check()
  await page.getByLabel('From', { exact: true }).fill(days.from)
  await page.getByLabel('To', { exact: true }).fill(days.to)
  await page.getByLabel('Reason (optional)').fill(reason)
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.getByText('Request sent')).toBeVisible()
}

/** Opens the approvals queue and the first request from `employee`. */
export async function openApproval(page: Page, employee: string): Promise<void> {
  await page.goto('/leave/approvals')
  await expect(page.getByRole('heading', { name: 'Approvals', level: 1 })).toBeVisible()
  await page.getByRole('button', { name: new RegExp(employee) }).click()
}

export function allCaughtUp(page: Page): Locator {
  return page.getByText("You're all caught up")
}

/** Steps the team calendar forward to `day`'s month, checking each month on the way. */
export async function showCalendarMonth(page: Page, day: Date): Promise<Locator> {
  const today = new Date()
  const ahead = (day.getFullYear() - today.getFullYear()) * 12 + day.getMonth() - today.getMonth()
  for (let step = 1; step <= ahead; step += 1) {
    await page.getByRole('button', { name: 'Next month' }).click()
    const shown = new Date(today.getFullYear(), today.getMonth() + step, 1)
    await expect(page.getByRole('region', { name: monthTitle(shown) })).toBeVisible()
  }
  return page.getByRole('region', { name: monthTitle(day) })
}

/** A day's cell label in the month grid, e.g. "Mon 23 Nov". */
export const dayLabel = (day: Date): string =>
  day.toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
