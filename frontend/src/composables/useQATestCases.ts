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

import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { AutomationTestCase, ManualTestCase, TestEvidence } from '@/types'

interface QATestCasesResponse {
  automation_test_cases: AutomationTestCase[]
  manual_test_cases: ManualTestCase[]
  execution_plan_md: string
  evidence: TestEvidence[]
}

// Backend's 10 MB cap on evidence size (see ``MAX_FILE_SIZE`` in
// ``backend/app/services/file_storage.py``). Mirrored on the frontend
// so the 413 fallback message can compute the limit without an extra
// API round-trip, AND so the upload UI can render a "Max 10 MB" hint
// next to the picker without hardcoding the number per-component.
// Exported because ManualTestRunner displays it alongside the upload
// affordance — keep the source of truth here.
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
export const MAX_UPLOAD_MB = MAX_UPLOAD_BYTES / (1024 * 1024)

// Error responses reach this composable via three shapes:
//   1. Backend ``HTTPException`` → JSON ``{"detail": "..."}``.
//   2. nginx 413 above ``client_max_body_size`` → HTML page.
//   3. Network failure (offline, DNS, CORS pre-flight) → ``fetch``
//      throws ``TypeError`` before any ``Response`` exists.
// Every QA endpoint funnels its non-ok / thrown branch through
// ``readResponseError`` (or its upload-aware sibling) so the UI never
// has to render a bare HTTP status code or, worse, fail silently.
async function readResponseError(resp: Response, fallback: string): Promise<string> {
  try {
    const body = await resp.clone().json()
    if (body?.detail) return String(body.detail)
  }
  catch {
    // Non-JSON body (nginx HTML page, empty 504 from a gateway, etc.)
    // — fall through to the generic message.
  }
  const reason = resp.statusText ? ` ${resp.statusText}` : ''
  return `${fallback} (${resp.status}${reason}).`
}

async function readUploadError(resp: Response, file: File): Promise<string> {
  if (resp.status === 413) {
    const sizeMb = (file.size / (1024 * 1024)).toFixed(1)
    try {
      const body = await resp.clone().json()
      if (body?.detail) return String(body.detail)
    }
    catch {
      // nginx returns HTML for its own 413; fall through to a sentence
      // that still tells the user the actual size + the limit.
    }
    return `File too large (${sizeMb} MB). Evidence must be ${MAX_UPLOAD_MB} MB or smaller.`
  }
  return readResponseError(resp, 'Upload failed')
}

function networkErrorMessage(action: string, err: unknown): string {
  const detail = err instanceof Error ? err.message : 'unknown error'
  return `${action} could not reach the server (${detail}). Check your connection and retry.`
}

export function useQATestCases(budId: string) {
  const authStore = useAuthStore()
  const automationCases = ref<AutomationTestCase[]>([])
  const manualCases = ref<ManualTestCase[]>([])
  const executionPlan = ref('')
  const evidence = ref<TestEvidence[]>([])
  const loading = ref(false)
  // ``error`` holds panel-wide failures (load, update-result) that
  // aren't tied to a specific test case. ``evidenceError`` is scoped
  // to a single case so the banner can be rendered inside that
  // case's body — next to the upload affordance the user just used —
  // rather than floating above the whole test-runner where it's
  // visually disconnected from the action that triggered it.
  const error = ref<string | null>(null)
  const evidenceError = ref<{ testCaseId: string, message: string } | null>(null)

  async function load(): Promise<void> {
    loading.value = true
    try {
      const resp = await fetch(`/api/v1/buds/${budId}/qa/test-cases`, {
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      if (resp.ok) {
        error.value = null
        const data: QATestCasesResponse = await resp.json()
        automationCases.value = data.automation_test_cases
        manualCases.value = data.manual_test_cases
        executionPlan.value = data.execution_plan_md
        evidence.value = data.evidence
      }
      else {
        error.value = await readResponseError(resp, 'Failed to load QA test cases')
      }
    }
    catch (err) {
      error.value = networkErrorMessage('Loading QA test cases', err)
    }
    finally {
      loading.value = false
    }
  }

  async function updateManualResult(
    testCaseId: string,
    result: 'pass' | 'fail' | 'blocked' | 'skipped' | 'pending',
    notes?: string,
  ): Promise<void> {
    const tc = manualCases.value.find(c => c.id === testCaseId)
    // Snapshot previous state so we can revert ALL optimistic fields on
    // failure, not just result. Leaving tester_name/tested_at pinned to
    // the optimistic value after a failed PATCH would be a lie.
    const previousResult = tc?.result
    const previousTester = tc?.tester_name ?? null
    const previousTestedAt = tc?.tested_at ?? null
    const previousNotes = tc?.notes

    // Optimistic update — populate tester attribution locally so the
    // collapsed card header reflects "Tested by X · just now"
    // immediately. The backend will stamp the same fields from the
    // authenticated user on the PATCH, so on success these values
    // converge. The ``pending`` revert path is the exception: the
    // backend explicitly nulls tester / timestamp / stale notes so the
    // case looks genuinely untested again, and the optimistic UI must
    // mirror that or the row would still show the old attribution
    // until the next refresh.
    if (tc) {
      tc.result = result
      if (result === 'pending') {
        tc.tester_name = null
        tc.tested_at = null
        // ManualTestCase types ``notes`` as ``string | undefined``;
        // ``undefined`` is what we want for "no note" so the UI shows
        // an empty placeholder instead of a stale draft from the
        // previous verdict.
        tc.notes = notes ?? undefined
      }
      else {
        tc.tester_name = authStore.user?.name ?? 'You'
        tc.tested_at = new Date().toISOString()
        if (notes !== undefined) tc.notes = notes
      }
    }

    const revert = () => {
      if (tc) {
        tc.result = previousResult ?? 'pending'
        tc.tester_name = previousTester
        tc.tested_at = previousTestedAt
        tc.notes = previousNotes
      }
    }

    try {
      const resp = await fetch(`/api/v1/buds/${budId}/qa/manual-results`, {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${authStore.token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ test_case_id: testCaseId, result, notes }),
      })
      if (resp.ok) {
        error.value = null
      }
      else {
        revert()
        error.value = await readResponseError(resp, 'Failed to update test result')
      }
    }
    catch (err) {
      revert()
      error.value = networkErrorMessage('Updating the test result', err)
    }
  }

  async function uploadEvidence(testCaseId: string, file: File): Promise<TestEvidence | null> {
    const formData = new FormData()
    formData.append('file', file)

    try {
      const resp = await fetch(`/api/v1/buds/${budId}/qa/evidence/${testCaseId}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authStore.token}` },
        body: formData,
      })
      if (resp.ok) {
        evidenceError.value = null
        const ev: TestEvidence = await resp.json()
        evidence.value.push(ev)
        return ev
      }
      evidenceError.value = {
        testCaseId,
        message: await readUploadError(resp, file),
      }
      return null
    }
    catch (err) {
      evidenceError.value = {
        testCaseId,
        message: networkErrorMessage('Uploading evidence', err),
      }
      return null
    }
  }

  async function deleteEvidence(evidenceId: string): Promise<void> {
    // The deleted row's ``test_case_id`` is the scope for any error
    // banner — captured BEFORE the optimistic filter wipes it from
    // ``evidence.value`` so the message still lands on the right card
    // if the API call itself fails.
    const target = evidence.value.find(e => e.id === evidenceId)
    const testCaseId = target?.test_case_id ?? null
    try {
      const resp = await fetch(`/api/v1/buds/${budId}/qa/evidence/${evidenceId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      if (resp.ok) {
        evidenceError.value = null
        evidence.value = evidence.value.filter(e => e.id !== evidenceId)
      }
      else if (testCaseId) {
        evidenceError.value = {
          testCaseId,
          message: await readResponseError(resp, 'Failed to delete evidence'),
        }
      }
      else {
        // Couldn't find the evidence row locally (already filtered
        // out by another action). Fall back to the panel-level
        // error so the user still sees the failure.
        error.value = await readResponseError(resp, 'Failed to delete evidence')
      }
    }
    catch (err) {
      const message = networkErrorMessage('Deleting evidence', err)
      if (testCaseId) {
        evidenceError.value = { testCaseId, message }
      }
      else {
        error.value = message
      }
    }
  }

  function clearEvidenceError(testCaseId: string): void {
    // Called from the UI when the user dismisses the per-case banner
    // or interacts with that case again. Scoped clear keeps a
    // simultaneous error on another card visible.
    if (evidenceError.value?.testCaseId === testCaseId) {
      evidenceError.value = null
    }
  }

  function setEvidenceError(testCaseId: string, message: string): void {
    // Surface — from the UI layer — failures that happen BEFORE the
    // request is sent (client-side size pre-validation in
    // ManualTestRunner) or AFTER it returns (download / thumbnail
    // fetch failure in EvidenceTile).
    evidenceError.value = { testCaseId, message }
  }

  return {
    automationCases,
    manualCases,
    executionPlan,
    evidence,
    loading,
    error,
    evidenceError,
    clearEvidenceError,
    setEvidenceError,
    load,
    updateManualResult,
    uploadEvidence,
    deleteEvidence,
  }
}
