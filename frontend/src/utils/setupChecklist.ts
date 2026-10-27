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

import type { SetupChecklistStatus } from '@/types/setup'

/** One row of the workspace setup checklist. */
export interface SetupStep {
  key: string
  label: string
  /** What finishing this step gives you, shown when it is next. */
  why: string
  done: boolean
  inProgress: boolean
  optional: boolean
  /** Where the step is done; absent when there is nothing to open. */
  route?: string
  /** Permission that page needs; people without it can't do the step. */
  permission?: string
}

const CONFIGURE = 'integrations:configure'

/** The setup steps in the order a new workspace should take them. */
export function setupChecklistItems(s: SetupChecklistStatus, scanning: boolean): SetupStep[] {
  const step = (
    key: string, label: string, why: string, done: boolean,
    extra: Partial<Pick<SetupStep, 'route' | 'permission' | 'optional' | 'inProgress'>> = {},
  ): SetupStep => ({ key, label, why, done, optional: false, inProgress: false, ...extra })

  return [
    step('org', 'Create organization', 'Your workspace is ready.', s.orgCreated),
    step('claude', 'Connect Claude Code', 'Agents need Claude Code to plan and review work.',
      s.claudeCodeTested, { route: '/settings', permission: CONFIGURE }),
    step('repo', 'Add repository', 'Agents read your code to plan and estimate work.',
      s.repoAdded, { route: '/settings/code', permission: CONFIGURE }),
    step('scan', 'Scan repository', 'The first scan maps features and owners in your code.',
      s.scanComplete, { inProgress: scanning }),
    step('branches', 'Map branch strategy', 'Tells Glideship which branch is each stage.',
      s.branchesMapped, { route: '/settings/code', permission: CONFIGURE }),
    step('github', 'Connect GitHub', 'Links pull requests to BUDs automatically.',
      s.githubConnected, { route: '/settings', permission: CONFIGURE, optional: true }),
    step('slack', 'Connect Slack', 'Turns Slack threads into BUDs and bugs.',
      s.slackConnected, { route: '/settings', permission: CONFIGURE, optional: true }),
    step('members', 'Import team members', 'Lets agents assign work to real people.',
      s.membersImported, { route: '/members', permission: 'team:manage', optional: true }),
    step('qa', 'Customize QA automation', 'Matches generated tests to your framework.',
      s.qaConfigured, { route: '/settings/qa-automation', permission: CONFIGURE, optional: true }),
  ]
}

/**
 * Whether the checklist can stop polling: the steps a scan depends on are
 * done and no scan is running. Optional steps and the Claude Code check
 * don't keep it polling.
 */
export function setupPollingDone(s: SetupChecklistStatus): boolean {
  return s.orgCreated && s.repoAdded && s.scanComplete && s.branchesMapped && !s.scanInProgress
}
