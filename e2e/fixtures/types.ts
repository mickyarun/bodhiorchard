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

/** What the `/__e2e` routes take and return (backend/tests/e2e_stack/specs.py). */

export type SystemRole =
  | 'org_owner' | 'admin' | 'hr' | 'manager' | 'pm' | 'tech_lead' | 'developer'
  | 'designer' | 'qa' | 'support' | 'viewer' | 'quiz_master' | 'sales'

export interface MemberSpec<K extends string = string> {
  key: K
  role?: SystemRole | null
  name?: string
  /** Key of another member who is this member's primary manager. */
  manager?: K
  mustChangePassword?: boolean
  characterModel?: string | null
}

export interface OrgSpec<K extends string = string> {
  members: MemberSpec<K>[]
  /** Seed into the org the login page signs in to, instead of a new one. */
  primary?: boolean
  /** Leave the company quiz switched on (it is off for seeded orgs). */
  quiz?: boolean
  leaveTypes?: { name: string, code: string, quotaDays?: number }[]
}

export interface FeatureSpec {
  title: string
  description: string
  tags?: string[]
}

export interface QuizSpec {
  prompt: string
  choices: string[]
  correctIndex: number
  explanation?: string
}

export interface Member {
  id: string
  email: string
  name: string
  password: string
  orgSlug: string
  /** Minted by the seed route the way the login API would, so tests skip it. */
  accessToken: string
  refreshToken: string
}

export interface SeededOrg<K extends string = string> {
  id: string
  slug: string
  name: string
  members: Record<K, Member>
  leaveTypes: Record<string, string>
}

export interface GuardReport {
  /** External calls the backend refused. */
  violations: string[]
  /** Agent runs the real CLI would have rejected, or that had no script. */
  agentProblems: string[]
}
