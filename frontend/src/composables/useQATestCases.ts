import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { AutomationTestCase, ManualTestCase, TestEvidence } from '@/types'

interface QATestCasesResponse {
  automation_test_cases: AutomationTestCase[]
  manual_test_cases: ManualTestCase[]
  execution_plan_md: string
  evidence: TestEvidence[]
}

export function useQATestCases(budId: string) {
  const authStore = useAuthStore()
  const automationCases = ref<AutomationTestCase[]>([])
  const manualCases = ref<ManualTestCase[]>([])
  const executionPlan = ref('')
  const evidence = ref<TestEvidence[]>([])
  const loading = ref(false)

  async function load(): Promise<void> {
    loading.value = true
    try {
      const resp = await fetch(`/api/v1/buds/${budId}/qa/test-cases`, {
        headers: { Authorization: `Bearer ${authStore.token}` },
      })
      if (resp.ok) {
        const data: QATestCasesResponse = await resp.json()
        automationCases.value = data.automation_test_cases
        manualCases.value = data.manual_test_cases
        executionPlan.value = data.execution_plan_md
        evidence.value = data.evidence
      }
    } finally {
      loading.value = false
    }
  }

  const error = ref<string | null>(null)

  async function updateManualResult(
    testCaseId: string,
    result: 'pass' | 'fail' | 'blocked' | 'skipped',
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
    // collapsed card header reflects "Tested by X · just now" immediately.
    // The backend will stamp the same fields from the authenticated user
    // on the PATCH, so on success these values converge.
    if (tc) {
      tc.result = result
      tc.tester_name = authStore.user?.name ?? 'You'
      tc.tested_at = new Date().toISOString()
      if (notes !== undefined) tc.notes = notes
    }

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
    } else {
      // Revert every field we optimistically touched
      if (tc) {
        tc.result = previousResult ?? 'pending'
        tc.tester_name = previousTester
        tc.tested_at = previousTestedAt
        tc.notes = previousNotes
      }
      error.value = `Failed to update test result (${resp.status})`
    }
  }

  async function uploadEvidence(testCaseId: string, file: File): Promise<TestEvidence | null> {
    const formData = new FormData()
    formData.append('file', file)

    const resp = await fetch(`/api/v1/buds/${budId}/qa/evidence/${testCaseId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${authStore.token}` },
      body: formData,
    })
    if (resp.ok) {
      const ev: TestEvidence = await resp.json()
      evidence.value.push(ev)
      return ev
    }
    return null
  }

  async function deleteEvidence(evidenceId: string): Promise<void> {
    const resp = await fetch(`/api/v1/buds/${budId}/qa/evidence/${evidenceId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    if (resp.ok) {
      evidence.value = evidence.value.filter(e => e.id !== evidenceId)
    }
  }

  return {
    automationCases,
    manualCases,
    executionPlan,
    evidence,
    loading,
    error,
    load,
    updateManualResult,
    uploadEvidence,
    deleteEvidence,
  }
}
