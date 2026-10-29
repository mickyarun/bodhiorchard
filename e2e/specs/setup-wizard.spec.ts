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
 * A fresh install: the wizard shows on an empty database and creates the
 * first org. The `setup-wizard` project runs this against a backend and
 * database of its own, emptied before each test.
 */
import type { Page } from '@playwright/test'
import { makeGitRepo } from '../fixtures/git.ts'
import { expect, test } from '../fixtures/test.ts'

test.describe.configure({ mode: 'serial' })

test.beforeEach(async ({ stack }) => {
  await stack.reset()
})

const next = (page: Page) => page.getByRole('button', { name: 'Continue' })

test('the wizard holds each step until it is filled in', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/setup/)
  await page.getByRole('button', { name: 'Get started' }).click()

  await expect(page.getByRole('heading', { name: 'Name your workspace' })).toBeVisible()
  await next(page).click()
  await expect(page.getByText('Please fill in the organization name and slug.')).toBeVisible()

  await page.getByLabel('Organization name').fill('Orchard Works')
  await expect(page.getByLabel('URL slug')).toHaveValue('orchard-works')
  await next(page).click()

  await expect(page.getByRole('heading', { name: 'Create the admin account' })).toBeVisible()
  await page.getByLabel('Password', { exact: true }).fill('short')
  await next(page).click()
  await expect(page.getByText('Please complete all admin account fields with valid values.')).toBeVisible()
})

test('a fresh install walks through the wizard to the dashboard', async ({ page }) => {
  const repo = makeGitRepo('orchard-api')
  const password = 'Wizard-pass-2026'

  await page.goto('/login')
  await expect(page).toHaveURL(/\/setup/)
  await page.getByRole('button', { name: 'Get started' }).click()

  await page.getByLabel('Organization name').fill('Orchard Works')
  await next(page).click()

  await page.getByLabel('Full name').fill('Ada Admin')
  await page.getByLabel('Work email').fill('ada@orchard.example.com')
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel('Confirm password').fill(password)
  await next(page).click()

  // Continuing past the AI step creates the org.
  await expect(page.getByRole('heading', { name: 'Connect the AI engine' })).toBeVisible()
  const created = page.waitForResponse((r) => r.url().endsWith('/api/setup/init-org'))
  await next(page).click()
  expect((await created).status()).toBe(201)

  await expect(page.getByRole('heading', { name: 'Add your repositories' })).toBeVisible()
  await page.getByRole('tab', { name: 'Local path' }).click()
  const pathField = page.getByLabel('Absolute path to git repository')
  await pathField.fill(repo)
  await pathField.press('Enter')
  await expect(page.getByText('Mapped', { exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Main branch' })).toHaveValue('main')
  await expect(page.getByRole('combobox', { name: 'Develop branch' })).toHaveValue('develop')
  await next(page).click()

  await expect(page.getByRole('heading', { name: 'Ready to launch' })).toBeVisible()
  await page.getByRole('button', { name: 'Launch Glideship' }).click()
  // A new engineer picks an avatar first, then reaches the dashboard.
  await expect(page).toHaveURL(/\/(dashboard|character-select)/)

  // The install is set up now: the wizard is gone and the admin can sign in.
  await page.goto('/setup')
  await expect(page).not.toHaveURL(/\/setup/)
})
