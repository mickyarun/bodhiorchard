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

/** Garden games and the leaderboard: games have their own boards and never pay XP. */
import { expect, test } from '../fixtures/test.ts'
import { openGames, playFirefly, watchFlashes } from '../screens/games.ts'

interface Xp {
  total_xp: number
}

interface GameBoard {
  entries: { user_name: string; best_score: number }[]
}

test('a Firefly Follow game lands on its board and pays no XP', async ({ signedIn, stack }) => {
  test.slow() // Real rounds against the multiplayer server, with playback delays.
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer', name: 'Fern Player' }] })
  const api = await stack.api(org.members.dev)
  const before = await api.get<Xp>('xp/me')

  const page = await signedIn(org.members.dev)
  const hub = await openGames(page)
  await watchFlashes(page)
  await hub.getByRole('button', { name: /Firefly Follow/ }).click()
  await playFirefly(page, 2)
  await expect(page.getByText(/New personal best — 2!/)).toBeVisible()
  // The game server records the score with the backend after the round ends.
  await expect.poll(async () => (await api.get<GameBoard>('minigames/leaderboard?game=firefly')).entries)
    .toEqual([expect.objectContaining({ user_name: 'Fern Player', best_score: 2 })])

  await page.goto('/leaderboard')
  await expect(page.getByText('XP comes only from real dev work. Games have their own boards and never award XP.')).toBeVisible()
  await page.getByRole('tablist', { name: 'Boards' }).getByRole('tab', { name: 'Firefly Follow' }).click()
  // One player gets a ranked row; the podium needs three.
  const row = page.getByRole('region', { name: 'Firefly Follow scores' }).getByRole('listitem')
  await expect(row).toContainText('Fern Player (you)')
  await expect(row).toHaveText(/^1.*2$/)

  expect((await api.get<Xp>('xp/me')).total_xp).toBe(before.total_xp)
  await page.getByRole('tablist', { name: 'Boards' }).getByRole('tab', { name: 'XP' }).click()
  const me = page.getByRole('region', { name: 'Everyone by XP' }).getByRole('listitem').filter({ hasText: 'Fern Player (you)' })
  await expect(me.getByText(/^0\s?XP$/)).toBeVisible()
})

test('a game nobody has played says so', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'dev', role: 'developer' }] })
  const page = await signedIn(org.members.dev)
  await page.goto('/leaderboard')
  await page.getByRole('tablist', { name: 'Boards' }).getByRole('tab', { name: 'Pollen Pop' }).click()
  await expect(page.getByText(/No scores yet for Pollen Pop/)).toBeVisible()
})
