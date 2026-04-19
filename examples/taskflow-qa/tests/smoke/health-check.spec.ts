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
