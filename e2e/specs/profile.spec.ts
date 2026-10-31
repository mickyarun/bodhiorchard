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

/** Your own details, Slack notification choices, and changing your password. */
import { expect, test } from '../fixtures/test.ts'

test('an employee adds their phone number, and it is kept', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'emp', role: 'developer', name: 'Eli Employee' }] })
  const page = await signedIn(org.members.emp)
  await page.goto('/me/profile')
  await page.getByRole('button', { name: 'Edit Contact' }).click()
  await expect(page.getByRole('heading', { name: 'Edit my details' })).toBeVisible()
  await page.getByRole('textbox', { name: 'Phone', exact: true }).fill('+44 20 7946 0123')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('+44 20 7946 0123')).toBeVisible()
  await page.reload()
  await expect(page.getByText('+44 20 7946 0123')).toBeVisible()
})

test('a Slack notification switched off stays off', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'mgr', role: 'manager' }] })
  const page = await signedIn(org.members.mgr)
  await page.goto('/profile/notifications')
  // Found by name: the switches had no label of their own.
  const approvals = page.getByRole('checkbox', { name: 'Requests to approve' })
  await expect(approvals).toBeChecked()
  const saved = page.waitForResponse((r) => r.url().endsWith('/api/v1/me/notification-preferences') && r.request().method() === 'PATCH')
  await approvals.uncheck()
  expect((await saved).ok()).toBe(true)
  await page.reload()
  await expect(approvals).not.toBeChecked()
})

test('a password changed from the profile replaces the old one', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const dev = org.members.dev
  const page = await signedIn(dev)
  await page.goto('/profile')
  await page.getByRole('link', { name: 'Change Password' }).click()
  await expect(page.getByRole('heading', { name: 'Change your password' })).toBeVisible()
  const fresh = `${dev.password}-2`
  await page.getByLabel('New password', { exact: true }).fill(fresh)
  await page.getByLabel('Confirm password', { exact: true }).fill(fresh)
  await page.getByRole('button', { name: 'Set new password' }).click()
  await expect(page).not.toHaveURL(/change-password/)

  await expect(stack.login(dev.email, fresh, dev.orgSlug)).resolves.toHaveProperty('access')
  await expect(stack.login(dev.email, dev.password, dev.orgSlug)).rejects.toThrow(/401/)
})
