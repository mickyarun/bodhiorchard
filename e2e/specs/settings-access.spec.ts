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
 * Which settings screens each built-in role can open. Allowed screens show
 * their heading; the rest send the person to their home screen.
 */
import type { SystemRole } from '../fixtures/types.ts'
import { expect, test } from '../fixtures/test.ts'

interface Screen {
  path: string
  heading: string
}

const SCREENS: Record<string, Screen> = {
  integrations: { path: '/settings', heading: 'Settings' },
  code: { path: '/settings/code', heading: 'Code' },
  members: { path: '/members', heading: 'Members' },
  leave: { path: '/settings/leave', heading: 'Leave' },
  offices: { path: '/settings/offices', heading: 'Offices' },
  celebrations: { path: '/settings/celebrations', heading: 'Celebrations' },
  quizGame: { path: '/settings/quiz-game', heading: 'Quiz Game' },
  agentPrompts: { path: '/settings/agent-prompts', heading: 'Agent Prompts' },
}

interface Case {
  role: SystemRole
  home: RegExp
  opens: (keyof typeof SCREENS)[]
  bounces: (keyof typeof SCREENS)[]
}

const CASES: Case[] = [
  { role: 'admin', home: /\/dashboard$/, opens: ['integrations', 'code', 'members', 'leave', 'celebrations', 'agentPrompts'], bounces: ['offices', 'quizGame'] },
  { role: 'manager', home: /\/dashboard$/, opens: ['members'], bounces: ['integrations', 'code', 'leave', 'offices', 'quizGame'] },
  { role: 'hr', home: /\/leave$/, opens: ['leave', 'offices', 'celebrations'], bounces: ['integrations', 'code', 'members', 'agentPrompts'] },
  { role: 'tech_lead', home: /\/dashboard$/, opens: ['agentPrompts'], bounces: ['integrations', 'code', 'offices'] },
  { role: 'quiz_master', home: /\/dashboard$/, opens: ['quizGame'], bounces: ['integrations', 'members', 'leave'] },
]

for (const { role, home, opens, bounces } of CASES) {
  test(`${role}: the settings screens it may open, and the ones it may not`, async ({ signedIn, stack }) => {
    const org = await stack.seedOrg({ members: [{ key: 'member', role }] })
    const page = await signedIn(org.members.member)
    for (const key of opens) {
      const screen = SCREENS[key]
      await page.goto(screen.path)
      await expect(page.getByRole('heading', { name: screen.heading, level: 1 }), `${role} opens ${screen.path}`).toBeVisible()
    }
    for (const key of bounces) {
      await page.goto(SCREENS[key].path)
      await expect(page, `${role} is sent home from ${SCREENS[key].path}`).toHaveURL(home)
    }
  })
}
