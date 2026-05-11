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
 * Pure helpers + types for ``useRepoOnboard``.
 *
 * Kept separate to keep the composable file under the project's
 * 200-line cap. No Vue reactivity primitives are imported here — every
 * function is referentially transparent and easy to unit-test in
 * isolation.
 */

import {
  BULK_IMPORT_MAX_REPOS,
  type BranchPick,
  type BulkOnboardItemRequest,
} from '@/types/repoOnboard'

export type BranchKind = 'main' | 'develop' | 'uat'

export function isReadyToSubmit(
  selection: Set<string>,
  branchesByRepo: Map<string, BranchPick>,
): boolean {
  if (selection.size === 0 || selection.size > BULK_IMPORT_MAX_REPOS) {
    return false
  }
  for (const fullName of selection) {
    const pick = branchesByRepo.get(fullName)
    if (!pick || !pick.main) {
      return false
    }
  }
  return true
}

export function buildSubmitItems(
  selection: Set<string>,
  branchesByRepo: Map<string, BranchPick>,
): BulkOnboardItemRequest[] {
  const items: BulkOnboardItemRequest[] = []
  for (const fullName of selection) {
    const pick = branchesByRepo.get(fullName)
    if (!pick || !pick.main) {
      continue
    }
    items.push({
      fullName,
      mainBranch: pick.main,
      developBranch: pick.develop || undefined,
      uatBranch: pick.uat || undefined,
    })
  }
  return items
}

// Auto-select the develop branch only when a branch literally named
// "develop" exists in the repo. Conservative on purpose — develop is an
// optional field and we shouldn't guess at variant names like "dev" or
// "development". If a user has a different convention they pick it
// manually.
const DEVELOP_BRANCH_NAME = 'develop'

export function detectDevelopBranch(
  branches: readonly string[],
  mainBranch: string,
): string | undefined {
  if (mainBranch === DEVELOP_BRANCH_NAME) return undefined
  return branches.includes(DEVELOP_BRANCH_NAME) ? DEVELOP_BRANCH_NAME : undefined
}

export function applyBranchPick(
  existing: BranchPick | undefined,
  kind: BranchKind,
  branch: string | null,
): BranchPick {
  const next: BranchPick = { ...(existing ?? { main: '' }) }
  if (kind === 'main') {
    next.main = branch ?? ''
  } else if (kind === 'develop') {
    next.develop = branch ?? undefined
  } else {
    next.uat = branch ?? undefined
  }
  return next
}
