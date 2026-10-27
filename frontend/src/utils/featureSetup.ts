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

/** The three steps the empty Features page walks through, from the org's repositories. */
import type { RepoInfo } from '@/types'

export type SetupStepState = 'done' | 'next' | 'then'

export interface FeatureSetupStep {
  key: 'connect' | 'scan' | 'browse'
  title: string
  body: string
  state: SetupStepState
}

export const SETUP_STATE_LABEL: Record<SetupStepState, string> = { done: 'Done', next: 'Next', then: 'Then' }

type RepoSummary = Pick<RepoInfo, 'status' | 'lastScanned'>

/** Steps already taken are done, the first open one is next, the rest follow. */
export function featureSetupSteps(repos: RepoSummary[]): FeatureSetupStep[] {
  const connected = repos.filter(r => r.status !== 'removed')
  const reached = [connected.length > 0, connected.some(r => r.lastScanned !== null), false]
  const firstOpen = reached.indexOf(false)
  const state = (i: number): SetupStepState => (reached[i] ? 'done' : i === firstOpen ? 'next' : 'then')
  return [
    { key: 'connect', title: 'Connect a repository', body: 'GitHub or a local path. Read access is enough.', state: state(0) },
    { key: 'scan', title: 'Scan the code', body: 'Takes a few minutes, and updates when a PR merges to the main branch.', state: state(1) },
    {
      key: 'browse',
      title: 'Browse the feature map',
      body: 'Each feature shows where it lives in the code and the PR or BUD that last changed it.',
      state: state(2),
    },
  ]
}
