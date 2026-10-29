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

/** Today's company quiz, played from the dashboard. */
import type { Page } from '@playwright/test'
import { expect, test } from '../fixtures/test.ts'

const QUIZ = {
  prompt: 'Which BUD stage comes right after Design?',
  choices: ['Tech Architecture', 'Testing', 'Prod'],
  correctIndex: 0,
  explanation: 'Design hands over to the tech plan.',
}

async function openQuiz(page: Page) {
  await page.goto('/dashboard')
  await page.getByRole('button', { name: /Today's quiz/ }).click()
  const hub = page.getByRole('dialog').filter({ hasText: 'Company Quiz' })
  await expect(hub).toBeVisible()
  return hub
}

test('a player locks in an answer and nothing gives the result away before the reveal', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ quiz: true, members: [{ key: 'dev', role: 'developer' }] })
  await stack.openQuiz(org, QUIZ)
  const page = await signedIn(org.members.dev)
  const hub = await openQuiz(page)
  await expect(hub.getByText(QUIZ.prompt)).toBeVisible()

  const lockIn = hub.getByRole('button', { name: 'Lock in answer' })
  await expect(lockIn).toBeDisabled()
  const testing = hub.getByRole('button', { name: /Testing$/ })
  await testing.click()
  await expect(testing).toHaveAttribute('aria-pressed', 'true')
  await expect(hub.getByRole('button', { name: /Tech Architecture$/ })).toHaveAttribute('aria-pressed', 'false')
  await lockIn.click()

  await expect(hub.getByText('Answer locked in')).toBeVisible()
  await expect(hub.getByText(/Reveal in/)).toBeVisible()
  await expect(hub.getByText(QUIZ.explanation)).toHaveCount(0)
  await expect(hub.getByText(/\b(correct|wrong|incorrect)\b/i)).toHaveCount(0)

  // Answering again is not offered, after a reload too.
  await page.reload()
  const again = await openQuiz(page)
  await expect(again.getByText('Answer locked in')).toBeVisible()
  await expect(again.getByRole('button', { name: 'Lock in answer' })).toHaveCount(0)
})

test('with no quiz open the hub says so', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ quiz: true, members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  const hub = await openQuiz(page)
  await expect(hub.getByText('No quiz open right now')).toBeVisible()
})
