import { test as base } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'
import { TEST_USER } from '../helpers/test-data'

type AuthFixtures = {
  authenticatedPage: ReturnType<typeof base['page']> extends Promise<infer T> ? T : never
}

export const test = base.extend<AuthFixtures>({
  authenticatedPage: async ({ page }, use) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login(TEST_USER.email, TEST_USER.password)
    await page.waitForURL(/\/tasks/)
    await use(page)
  },
})

export { expect } from '@playwright/test'
