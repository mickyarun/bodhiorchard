<template>
  <div class="qa-panel pa-4">
    <!-- Loading -->
    <div v-if="loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate size="24" width="2" />
    </div>

    <!-- Agent failed -->
    <div v-else-if="props.activeAgentTask?.task_type === 'testing' && props.activeAgentTask?.status === 'failed' && !hasTestCases" class="empty-state">
      <v-icon icon="mdi-alert-circle" size="48" color="error" class="mb-3 opacity-60" />
      <div class="text-h6 font-weight-medium mb-2">Test case generation failed</div>
      <div class="text-body-2 text-medium-emphasis mb-2" style="max-width: 440px;">
        {{ props.activeAgentTask.error_message || 'The QA agent encountered an error.' }}
      </div>
      <div class="text-caption text-medium-emphasis mb-4">Attempt {{ props.activeAgentTask.attempt }}</div>
    </div>

    <!-- Agent running -->
    <div v-else-if="props.activeAgentTask?.task_type === 'testing' && (props.activeAgentTask?.status === 'running' || props.activeAgentTask?.status === 'pending')" class="empty-state">
      <v-progress-circular indeterminate size="32" width="3" color="purple" class="mb-3" />
      <div class="text-h6 font-weight-medium mb-2">Generating test cases...</div>
      <div class="text-body-2 text-medium-emphasis">
        {{ props.activeAgentTask.status_message || 'The QA agent is analyzing code changes and generating test cases.' }}
      </div>
    </div>

    <!-- Empty state: no test cases yet -->
    <div v-else-if="!hasTestCases" class="empty-state">
      <v-icon icon="mdi-test-tube" size="48" color="purple" class="mb-3 opacity-40" />
      <div class="text-h6 font-weight-medium mb-2">Ready for QA</div>
      <div class="text-body-2 text-medium-emphasis mb-4" style="max-width: 440px;">
        Test cases are being generated. Once ready, configure MCP and start testing on a
        <code>bud-{{ budNumber }}/</code> branch.
      </div>

      <!-- MCP setup guide -->
      <v-card variant="outlined" class="mb-4 pa-3 text-left" style="max-width: 440px;">
        <div class="d-flex align-center ga-2 mb-2">
          <v-icon icon="mdi-wrench" size="16" color="purple" />
          <span class="text-body-2 font-weight-medium">Setup MCP Token</span>
        </div>
        <ol class="text-caption text-medium-emphasis pl-4" style="margin: 0;">
          <li>Go to <strong>Settings → Integrations → MCP Token</strong></li>
          <li>Generate and copy your token</li>
          <li>Run: <code>export BODHIGROVE_MCP_TOKEN="your-token"</code></li>
          <li>Restart Claude Code in the repo</li>
        </ol>
      </v-card>

      <!-- Impacted repos hint -->
      <div v-if="impactedRepos && impactedRepos.length" class="mb-4">
        <div class="text-caption text-medium-emphasis mb-1">Impacted repositories</div>
        <div class="d-flex ga-2 flex-wrap justify-center">
          <v-chip
            v-for="r in impactedRepos"
            :key="r.repo_id || r.repo_name"
            size="small"
            variant="tonal"
            prepend-icon="mdi-source-repository"
          >
            {{ r.repo_name }}
          </v-chip>
        </div>
      </div>

      <div class="d-flex ga-2 justify-center">
        <v-btn
          variant="outlined"
          size="small"
          prepend-icon="mdi-content-copy"
          @click="copyBranchName"
        >
          Copy Branch Name
        </v-btn>
      </div>
      <div v-if="branchCopied" class="text-caption text-success mt-2">Copied!</div>
    </div>

    <!-- Has test cases -->
    <template v-else>
      <!-- Stats row -->
      <v-row dense class="mb-4">
        <v-col cols="3">
          <v-card variant="tonal" class="pa-3 text-center">
            <div class="text-h5 font-weight-bold">{{ totalCases }}</div>
            <div class="text-caption text-medium-emphasis">Total Cases</div>
          </v-card>
        </v-col>
        <v-col cols="3">
          <v-card variant="tonal" color="blue" class="pa-3 text-center">
            <div class="text-h5 font-weight-bold">{{ automationCases.length }}</div>
            <div class="text-caption">Automation</div>
          </v-card>
        </v-col>
        <v-col cols="3">
          <v-card variant="tonal" color="purple" class="pa-3 text-center">
            <div class="text-h5 font-weight-bold">{{ manualCases.length }}</div>
            <div class="text-caption">Manual</div>
          </v-card>
        </v-col>
        <v-col cols="3">
          <v-card variant="tonal" :color="passRate === 100 ? 'success' : 'warning'" class="pa-3 text-center">
            <div class="text-h5 font-weight-bold">{{ passRate }}%</div>
            <div class="text-caption">Pass Rate</div>
          </v-card>
        </v-col>
      </v-row>

      <!-- Actions -->
      <div class="d-flex ga-2 mb-4">
        <v-btn
          v-if="props.testPlanMd"
          variant="tonal"
          size="small"
          prepend-icon="mdi-download"
          @click="downloadTestPlan"
        >
          Download Test Plan
        </v-btn>
        <v-btn
          variant="outlined"
          size="small"
          prepend-icon="mdi-content-copy"
          @click="copyBranchName"
        >
          Copy Branch Name
        </v-btn>
      </div>

      <!-- Test Plan Summary (generated from agent) -->
      <v-card v-if="props.testPlanMd" variant="tonal" class="mb-4 pa-3">
        <div class="markdown-body" v-html="renderMarkdown(props.testPlanMd)" />
      </v-card>

      <!-- Sections -->
      <v-expansion-panels variant="accordion">
        <!-- Test Execution Plan -->
        <v-expansion-panel v-if="executionPlan">
          <v-expansion-panel-title>
            <v-icon start size="18">mdi-clipboard-list-outline</v-icon>
            Test Execution Plan
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="markdown-body" v-html="renderMarkdown(executionPlan)" />
          </v-expansion-panel-text>
        </v-expansion-panel>

        <!-- Automation Test Cases -->
        <v-expansion-panel v-if="automationCases.length > 0">
          <v-expansion-panel-title>
            <v-icon start size="18">mdi-test-tube</v-icon>
            Automation Test Cases ({{ automationCases.length }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <AutomationTestCases :cases="automationCases" />
          </v-expansion-panel-text>
        </v-expansion-panel>

        <!-- Manual Test Cases -->
        <v-expansion-panel v-if="manualCases.length > 0">
          <v-expansion-panel-title>
            <v-icon start size="18">mdi-clipboard-check-outline</v-icon>
            Manual Test Cases ({{ manualCases.length }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <ManualTestRunner
              :cases="manualCases"
              :evidence="evidence"
              @update-result="handleUpdateResult"
              @upload-evidence="handleUploadEvidence"
              @delete-evidence="handleDeleteEvidence"
            />
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { useQATestCases } from '@/composables/useQATestCases'
import AutomationTestCases from './AutomationTestCases.vue'
import ManualTestRunner from './ManualTestRunner.vue'
import type { ManualTestCase } from '@/types'

import type { BUDAgentTask } from '@/types'

const props = defineProps<{
  budId: string
  budNumber?: number
  testPlanMd?: string | null
  impactedRepos?: { repo_id: string; repo_name: string }[] | null
  activeAgentTask?: BUDAgentTask | null
}>()

const {
  automationCases,
  manualCases,
  executionPlan,
  evidence,
  loading,
  load,
  updateManualResult,
  uploadEvidence,
  deleteEvidence,
} = useQATestCases(props.budId)

const branchCopied = ref(false)

const hasTestCases = computed(() =>
  automationCases.value.length > 0 || manualCases.value.length > 0,
)

const totalCases = computed(() =>
  automationCases.value.length + manualCases.value.length,
)

const passRate = computed(() => {
  const manual = manualCases.value
  if (manual.length === 0) return 0
  const completed = manual.filter(c => c.result !== 'pending')
  if (completed.length === 0) return 0
  const passed = completed.filter(c => c.result === 'pass').length
  return Math.round((passed / completed.length) * 100)
})

function renderMarkdown(md: string | null): string {
  if (!md) return ''
  const raw = marked.parse(md, { async: false }) as string
  return DOMPurify.sanitize(raw)
}

function downloadTestPlan(): void {
  if (!props.testPlanMd) return
  const budRef = `BUD-${String(props.budNumber ?? 0).padStart(3, '0')}`
  const blob = new Blob([props.testPlanMd], { type: 'text/markdown' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${budRef}-test-plan.md`
  a.click()
  URL.revokeObjectURL(a.href)
}

function copyBranchName(): void {
  const name = `bud-${String(props.budNumber ?? 0).padStart(3, '0')}/`
  navigator.clipboard.writeText(name)
  branchCopied.value = true
  setTimeout(() => { branchCopied.value = false }, 2000)
}

async function handleUpdateResult(testCaseId: string, result: ManualTestCase['result']): Promise<void> {
  await updateManualResult(testCaseId, result)
}

async function handleUploadEvidence(testCaseId: string, file: File): Promise<void> {
  await uploadEvidence(testCaseId, file)
}

async function handleDeleteEvidence(evidenceId: string): Promise<void> {
  await deleteEvidence(evidenceId)
}

onMounted(load)
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 16px;
  text-align: center;
}
</style>
