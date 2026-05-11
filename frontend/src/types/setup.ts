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
 * Origin of a wizard repo entry. Drives section-2 ("Map branches") visibility:
 * only ``local-path`` entries need manual branch mapping — the other two flows
 * auto-detect branches at add-time. Absence is treated as ``github-clone`` for
 * back-compat with legacy paste-URL fixtures.
 */
export type SetupRepoSource = 'github-clone' | 'local-path' | 'bulk'

export interface SetupRepoConfig {
  path: string
  mainBranch: string | null
  developBranch: string | null
  /**
   * Set when the repo entry came from the bulk-import (GitHub App) flow.
   * Triggers the ``installableItems`` payload shape on finalize instead of
   * the legacy ``sourceCode`` shape.
   */
  gitHubFullName?: string
  /** See ``SetupRepoSource``. Optional for back-compat; defaults to ``github-clone``. */
  source?: SetupRepoSource
}

export type ClaudeAuthMode = 'host' | 'api_key'

export interface SetupClaudeConfig {
  authMode: ClaudeAuthMode
  apiKey: string
  // True once detectDeployment has applied the backend's recommended default.
  // Guards against later remounts clobbering the user's explicit choice.
  initialized: boolean
  // Last connection-test outcome for the current (authMode, apiKey) pair.
  // Lets the AI Engine step restore the green "Connected" state on revisit.
  testPassed: boolean
  testedVersion: string
}

export interface SetupState {
  currentStep: number
  organization: {
    name: string
    slug: string
  }
  admin: {
    email: string
    name: string
    password: string
  }
  sourceCode: {
    repos: SetupRepoConfig[]
  }
  scan: {
    timeoutSeconds: number
    maxTurns: number
  }
  claude: SetupClaudeConfig
}

export interface StepDefinition {
  title: string
  icon: string
  key: string
}

export interface SetupChecklistStatus {
  orgCreated: boolean
  claudeCodeTested: boolean
  repoAdded: boolean
  scanComplete: boolean
  scanInProgress: boolean
  scanId: string | null
  scanProgress: number
  githubConnected: boolean
  slackConnected: boolean
  branchesMapped: boolean
  membersImported: boolean
  // True once the org has visited the QA automation settings page and
  // saved any value (even defaults). See backend/app/api/v1/setup.py.
  qaConfigured: boolean
}
