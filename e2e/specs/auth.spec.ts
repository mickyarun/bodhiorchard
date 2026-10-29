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
 * Signing in, staying signed in, and signing out. The login page signs in to
 * the install's first org, so these tests seed their people there.
 */
import type { Page } from '@playwright/test'
import { expect, test, TOKEN_KEY } from '../fixtures/test.ts'
import { apiLogin, seedOrg, type Member } from '../fixtures/stack.ts'

async function fillLogin(page: Page, email: string, password: string): Promise<void> {
  await page.getByLabel('Work email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

async function primaryMember(name: string, extra: { mustChangePassword?: boolean } = {}): Promise<Member> {
  const org = await seedOrg({ primary: true, members: [{ key: 'dev', role: 'developer', name, ...extra }] })
  return org.members.dev
}

test('signs in with email and password and lands on the dashboard', async ({ page }) => {
  const dev = await primaryMember('Dana Login')
  await page.goto('/login')
  await fillLogin(page, dev.email, dev.password)
  await expect(page).toHaveURL(/\/dashboard/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/^Good (morning|afternoon|evening), Dana/)
})

test('a wrong password shows an error and stays on the login page', async ({ page }) => {
  const dev = await primaryMember('Wes Wrong')
  await page.goto('/login')
  await fillLogin(page, dev.email, `${dev.password}-nope`)
  // Each Vuetify field also has an (empty) alert region for its own message.
  await expect(page.getByRole('alert').filter({ hasText: 'Invalid email or password.' })).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
  expect(await page.evaluate((key) => localStorage.getItem(key), TOKEN_KEY)).toBeNull()
})

test('a signed-out visit to a page goes to login, then back to that page', async ({ page }) => {
  const dev = await primaryMember('Remy Return')
  await page.goto('/bugs')
  await expect(page).toHaveURL(/\/login/)
  await fillLogin(page, dev.email, dev.password)
  await expect(page).toHaveURL(/\/bugs$/)
  await expect(page.getByRole('heading', { name: 'Bugs', level: 1 })).toBeVisible()
})

test('a reload keeps the session, and a bad access token is refreshed', async ({ signedIn }) => {
  const dev = await primaryMember('Ria Refresh')
  const page = await signedIn(dev)
  await page.goto('/buds')
  await expect(page.getByRole('heading', { name: 'Board', level: 1 })).toBeVisible()

  await page.reload()
  await expect(page.getByRole('heading', { name: 'Board', level: 1 })).toBeVisible()

  // An access token the server rejects: the app refreshes it once and carries on.
  await page.evaluate((key) => localStorage.setItem(key, 'not-a-valid-token'), TOKEN_KEY)
  const refreshed = page.waitForResponse((r) => r.url().endsWith('/api/v1/auth/refresh') && r.ok())
  await page.reload()
  await refreshed
  await expect(page.getByRole('heading', { name: 'Board', level: 1 })).toBeVisible()
  await expect(page).toHaveURL(/\/buds$/)
  expect(await page.evaluate((key) => localStorage.getItem(key), TOKEN_KEY)).not.toBe('not-a-valid-token')
})

test('signing out clears the session and protected pages bounce to login', async ({ signedIn }) => {
  const dev = await primaryMember('Sol Signout')
  const page = await signedIn(dev)
  await page.goto('/dashboard')
  await page.getByRole('button', { name: `Account menu for ${dev.name}` }).click()
  // The menu's items render as list items, not menu items.
  await page.getByRole('listitem').filter({ hasText: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()

  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login/)
  expect(await page.evaluate((key) => localStorage.getItem(key), TOKEN_KEY)).toBeNull()
})

test('a temporary password must be changed before anything else', async ({ page }) => {
  const dev = await primaryMember('Tara Temp', { mustChangePassword: true })
  await page.goto('/login')
  await fillLogin(page, dev.email, dev.password)
  await expect(page).toHaveURL(/\/change-password/)
  await expect(page.getByRole('heading', { name: 'Change your password' })).toBeVisible()

  // Other pages stay out of reach until the password is changed.
  await page.goto('/buds')
  await expect(page).toHaveURL(/\/change-password/)

  const fresh = `${dev.password}-new`
  await page.getByLabel('New password', { exact: true }).fill(fresh)
  await page.getByLabel('Confirm password', { exact: true }).fill(fresh)
  await page.getByRole('button', { name: 'Set new password' }).click()
  await expect(page).toHaveURL(/\/dashboard/)
  await expect(apiLogin({ ...dev, password: fresh })).resolves.toHaveProperty('access')
})
