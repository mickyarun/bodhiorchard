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

import { test, expect } from '@playwright/test'

test.describe('Smoke Tests', () => {
  test('app loads and shows login page', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/TaskFlow/i)
  })

  test('login page has required fields', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByLabel('Email')).toBeVisible()
    await expect(page.getByLabel('Password')).toBeVisible()
    await expect(page.getByRole('button', { name: /log ?in/i })).toBeVisible()
  })

  test('API health endpoint responds', async ({ request }) => {
    const apiUrl = process.env.API_URL || 'http://localhost:9001'
    const response = await request.get(`${apiUrl}/health`)
    expect(response.status()).toBe(200)
  })
})
