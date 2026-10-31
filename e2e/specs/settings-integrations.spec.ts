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
 * Settings → Integrations: the AI provider and the workspace MCP token.
 * GitHub and Slack are left alone: saving their credentials makes the
 * backend call those services, which the stack refuses.
 */
import type { Locator, Page } from '@playwright/test'
import { expect, test } from '../fixtures/test.ts'

async function openCard(page: Page, title: string): Promise<Locator> {
  // Each card is a region named by its heading.
  const section = page.getByRole('region', { name: title, exact: true })
  await section.getByRole('button', { name: /^(Manage|Set up|Connect)/ }).click()
  await expect(section.getByRole('button', { name: 'Hide' })).toBeVisible()
  return section
}

test('an owner switches the AI sign-in to an API key, and it is kept', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'owner', role: 'org_owner' }] })
  const page = await signedIn(org.members.owner)
  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Integrations', level: 2 })).toBeVisible()

  let ai = await openCard(page, 'AI provider')
  await expect(ai.getByRole('radiogroup', { name: 'AI provider' }).getByRole('radio', { name: /^Claude/ })).toBeChecked()
  await ai.getByRole('radiogroup', { name: 'Sign-in' }).getByRole('radio', { name: /^Anthropic API key/ }).click()
  await ai.getByLabel('Anthropic API key', { exact: true }).fill('sk-ant-e2e-not-a-real-key')
  // Saving runs a connection test, which the stack's fake CLI answers.
  const tested = page.waitForResponse((r) => r.url().endsWith('/api/v1/settings/claude/test'))
  await ai.getByRole('button', { name: 'Save' }).click()
  expect((await tested).ok()).toBe(true)

  await page.reload()
  ai = await openCard(page, 'AI provider')
  await expect(ai.getByRole('radiogroup', { name: 'Sign-in' }).getByRole('radio', { name: /^Anthropic API key/ })).toBeChecked()
  await expect(ai.getByLabel('Anthropic API key', { exact: true })).toHaveAttribute('placeholder', 'Saved. Leave blank to keep it.')
  await expect(ai.getByLabel('Anthropic API key', { exact: true })).toHaveValue('')
})

test('an owner generates the workspace MCP token once, then can only replace it', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'owner', role: 'org_owner' }] })
  const page = await signedIn(org.members.owner)
  await page.goto('/settings')
  let mcp = await openCard(page, 'MCP for Claude Code')
  await expect(mcp.getByText('No workspace token yet.')).toBeVisible()
  await mcp.getByRole('button', { name: 'Generate token' }).click()
  await expect(mcp.getByText('Copy the token now. It is not shown again.')).toBeVisible()
  expect((await mcp.getByLabel('Workspace MCP token').inputValue()).length).toBeGreaterThan(20)

  await page.reload()
  mcp = await openCard(page, 'MCP for Claude Code')
  await expect(mcp.getByLabel('Workspace MCP token')).toHaveCount(0)
  await mcp.getByRole('button', { name: 'Replace token' }).click()
  await expect(page.getByRole('dialog').filter({ hasText: 'Replace the workspace token?' })).toBeVisible()
})
