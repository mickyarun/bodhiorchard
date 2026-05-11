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
 * Bulk repo-onboard shared types.
 *
 * Mirrors the camelCase aliases emitted by the Phase B/C backend
 * schemas in ``backend/app/schemas/repo_install.py`` and
 * ``backend/app/schemas/jobs.py`` (``BulkOnboardItemProgress`` /
 * ``BulkOnboardJobPayload``).
 */

export const APP_INSTALL_STATE = {
  READY: 'ready',
  NO_CREDENTIALS: 'no_credentials',
  NO_INSTALL: 'no_install',
} as const

export type AppInstallState = (typeof APP_INSTALL_STATE)[keyof typeof APP_INSTALL_STATE]

export const BULK_ONBOARD_ITEM_STATE = {
  PENDING: 'pending',
  CLONING: 'cloning',
  DONE: 'done',
  ERROR: 'error',
} as const

export type BulkOnboardItemState =
  (typeof BULK_ONBOARD_ITEM_STATE)[keyof typeof BULK_ONBOARD_ITEM_STATE]

export interface InstallableRepo {
  fullName: string
  ownerLogin: string
  ownerAvatarUrl: string
  defaultBranch: string
  private: boolean
  ghRepoId: number
  alreadyTracked: boolean
  pushedAt: string | null
}

export interface InstallableListResponse {
  appInstallState: AppInstallState
  installUrl: string | null
  repos: InstallableRepo[]
}

export interface RepoBranchListResponse {
  branches: string[]
}

/** Local-only structure carrying the user's main/develop picks per repo. */
export interface BranchPick {
  main: string
  develop?: string
  uat?: string
}

/** Wire shape consumed by ``POST /v1/settings/repos/bulk-onboard``. */
export interface BulkOnboardItemRequest {
  fullName: string
  mainBranch: string
  developBranch?: string
  uatBranch?: string
}

export interface BulkOnboardRequestBody {
  items: BulkOnboardItemRequest[]
}

export interface BulkOnboardJobCreated {
  jobId: string
}

/** Per-item progress row reported through the running job's ``result``. */
export interface BulkOnboardItemProgress {
  fullName: string
  mainBranch: string
  developBranch?: string | null
  uatBranch?: string | null
  status: BulkOnboardItemState
  repoId?: string | null
  error?: string | null
}

/** Mid-flight job result shape (``BulkOnboardJobPayload`` serialised). */
export interface BulkOnboardJobProgressResult {
  orgId: string
  items: BulkOnboardItemProgress[]
}

/** Terminal job result built by ``summarise()`` server-side. */
export interface BulkOnboardJobTerminalResult {
  items: BulkOnboardItemProgress[]
  scan_id: string | null
  succeeded: string[]
  failed: { full_name: string; error: string }[]
}

export const BULK_IMPORT_MAX_REPOS = 200
