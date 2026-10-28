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
 * The AI provider connection test (POST /v1/settings/claude/test) and the
 * result it shows: passed with a version, or failed with a reason and an
 * optional install hint. ``body`` builds the request for the choice on
 * screen; null tests the saved provider.
 */
import { ref } from 'vue'
import api from '@/services/api'
import { testOutcome, type ProviderTestResult } from '@/utils/aiProviderOptions'
import type { ProviderTest } from '@/utils/integrations'

const TEST_TIMEOUT_MS = 120_000

export function useAiProviderTest(body: () => Record<string, unknown> | null) {
  const test = ref<ProviderTest>('idle')
  const testError = ref('')
  const testVersion = ref('')
  const showInstallHint = ref(false)

  /** Drop a finished result so the tag always describes what is on screen. */
  function clearOutcome(): void {
    if (test.value === 'passed' || test.value === 'failed') {
      test.value = 'idle'
      testError.value = ''
      testVersion.value = ''
    }
  }

  function applyTest(data: ProviderTestResult): void {
    const outcome = testOutcome(data)
    test.value = outcome.passed ? 'passed' : 'failed'
    testVersion.value = outcome.passed ? outcome.message : ''
    testError.value = outcome.passed ? '' : outcome.message
    showInstallHint.value = outcome.showInstallHint
  }

  async function runTest(): Promise<void> {
    test.value = 'checking'
    testError.value = ''
    testVersion.value = ''
    showInstallHint.value = false
    try {
      const { data } = await api.post<ProviderTestResult>('/v1/settings/claude/test', body(), { timeout: TEST_TIMEOUT_MS })
      applyTest(data)
    } catch (err) {
      test.value = 'failed'
      testError.value = 'Could not reach the server to test the provider.'
      console.warn('[ai settings] test failed', err)
    }
  }

  return { test, testError, testVersion, showInstallHint, clearOutcome, runTest }
}
