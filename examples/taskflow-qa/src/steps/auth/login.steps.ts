import { Given, When, Then } from '@cucumber/cucumber'

Given('the TaskFlow application is running', async function () {
  // Health check - application should be reachable
  const resp = await fetch(process.env.BASE_URL || 'http://localhost:9002')
  if (!resp.ok) throw new Error('Application not running')
})

Given('I am on the login page', async function () {
  await this.page.goto('/login')
})

When('I enter email {string}', async function (email: string) {
  await this.page.getByLabel('Email').fill(email)
})

When('I enter password {string}', async function (password: string) {
  await this.page.getByLabel('Password').fill(password)
})

When('I click the login button', async function () {
  await this.page.getByRole('button', { name: /log ?in/i }).click()
})

Then('I should be redirected to the task board', async function () {
  await this.page.waitForURL(/\/tasks/)
})

Then('I should see my username in the header', async function () {
  await this.page.getByTestId('user-menu').waitFor({ state: 'visible' })
})

Then('I should see an error message {string}', async function (message: string) {
  const alert = this.page.getByRole('alert')
  await alert.waitFor({ state: 'visible' })
  const text = await alert.textContent()
  if (!text?.includes(message)) {
    throw new Error(`Expected error "${message}" but got "${text}"`)
  }
})

Then('I should remain on the login page', async function () {
  const url = this.page.url()
  if (!url.includes('/login')) {
    throw new Error(`Expected to be on login page but was at ${url}`)
  }
})

Then('I should see validation errors', async function () {
  // Check that form validation messages are shown
  const errorMessages = this.page.locator('.v-messages__message')
  const count = await errorMessages.count()
  if (count === 0) throw new Error('No validation errors shown')
})
