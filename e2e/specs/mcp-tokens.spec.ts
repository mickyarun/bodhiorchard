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

/** Personal MCP tokens: made in the browser, used by a local AI client, revoked. */
import { request } from '@playwright/test'
import { BACKEND_URL } from '../stack/config.ts'
import { seedOrg } from '../fixtures/stack.ts'
import { expect, test } from '../fixtures/test.ts'

/** What a local AI client does with the token: call one read-only tool. */
async function callTool(token: string): Promise<number> {
  const client = await request.newContext({ baseURL: BACKEND_URL })
  try {
    const response = await client.post('/mcp/tools/list_design_systems', {
      data: { params: {} },
      headers: { Authorization: `Bearer ${token}` },
    })
    return response.status()
  } finally {
    await client.dispose()
  }
}

test('a developer creates an MCP token, a client uses it, and revoking locks it out', async ({ signedIn }) => {
  const org = await seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  await page.goto('/settings/mcp-connect')
  await expect(page.getByRole('heading', { name: 'Connect your local AI', level: 1 })).toBeVisible()
  await expect(page.getByText('No tokens yet')).toBeVisible()

  await page.getByRole('button', { name: 'New token' }).click()
  const create = page.getByRole('dialog').filter({ hasText: 'New MCP token' })
  await create.getByLabel('Token name').fill('Work laptop')
  await create.getByRole('button', { name: 'Create' }).click()

  const created = page.getByRole('dialog').filter({ hasText: 'Token created' })
  const token = await created.getByRole('textbox').inputValue()
  expect(token.length).toBeGreaterThan(20)
  await created.getByRole('button', { name: 'I have copied it' }).click()
  await expect(created).toBeHidden()
  await expect(page.getByText('Work laptop')).toBeVisible()
  expect(await callTool(token)).toBe(200)

  // Revoking asks the browser to confirm first.
  page.once('dialog', (confirm) => void confirm.accept())
  await page.getByRole('button', { name: 'Revoke Work laptop' }).click()
  await expect(page.getByText('No tokens yet')).toBeVisible()
  expect(await callTool(token)).toBe(401)
})
