import { test, expect } from '@playwright/test'
import { LoginPage } from '../../src/pages/LoginPage'
import { TEST_USER } from '../../src/helpers/test-data'

test.describe('Login Flow', () => {
  test('successful login redirects to tasks', async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login(TEST_USER.email, TEST_USER.password)

    await expect(page).toHaveURL(/\/tasks/)
  })

  test('invalid credentials shows error', async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login(TEST_USER.email, 'wrong-password')

    await expect(loginPage.errorMessage).toBeVisible()
  })

  test('empty form shows validation', async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.loginButton.click()

    // Should stay on login page
    await expect(page).toHaveURL(/\/login/)
  })
})
