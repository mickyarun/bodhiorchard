<template>
  <div class="qa-panel pa-4">
    <!-- Initial fetch of QA test cases. Agent running/failed state is
         handled by the unified top banner in BUDDetail.vue, matching the
         pattern other tabs follow — no per-tab duplication. -->
    <div v-if="loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate size="24" width="2" />
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
  const budRef = `BUD-${String(props.budNumber ?? 0).padStart(3, '0')}`
  const autoCount = automationCases.value.length
  const manualCount = manualCases.value.length

  let md = `# Test Plan: ${budRef}\n\n`
  md += `- **${autoCount}** automation test cases\n`
  md += `- **${manualCount}** manual test cases\n\n`

  if (executionPlan.value) {
    md += `## Execution Plan\n\n${executionPlan.value}\n\n`
  }

  if (autoCount > 0) {
    md += `## Automation Test Cases (${autoCount})\n\n`
    for (const tc of automationCases.value) {
      md += `### ${tc.id}: ${tc.title}\n\n`
      md += `- **Type:** ${tc.type}\n`
      md += `- **Priority:** ${tc.priority}\n`
      if (tc.gherkin) md += `- **Test Scenario:**\n\`\`\`\n${tc.gherkin}\n\`\`\`\n`
      if (tc.input) md += `- **Input:** ${tc.input}\n`
      if (tc.expected_output) md += `- **Expected:** ${tc.expected_output}\n`
      if (tc.tags?.length) md += `- **Tags:** ${tc.tags.join(', ')}\n`
      md += '\n'
    }
  }

  if (manualCount > 0) {
    md += `## Manual Test Cases (${manualCount})\n\n`
    for (const tc of manualCases.value) {
      md += `### ${tc.id}: ${tc.title}\n\n`
      md += `- **Category:** ${tc.category}\n`
      md += `- **Priority:** ${tc.priority}\n`
      md += `- **Status:** ${tc.result || 'pending'}\n`
      if (tc.description) md += `- **Description:** ${tc.description}\n`
      if (tc.preconditions) md += `- **Preconditions:** ${tc.preconditions}\n`
      if (tc.steps?.length) {
        md += `- **Steps:**\n`
        for (const step of tc.steps) md += `  1. ${step}\n`
      }
      if (tc.expected_result) md += `- **Expected:** ${tc.expected_result}\n`
      md += '\n'
    }
  }

  const blob = new Blob([md], { type: 'text/markdown' })
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
  if (result === 'pending') return
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

/* Markdown rendering for test plan + execution plan */
.markdown-body :deep(h1) { font-size: 1.4em; font-weight: 700; margin: 0 0 12px; }
.markdown-body :deep(h2) { font-size: 1.15em; font-weight: 600; margin: 20px 0 8px; }
.markdown-body :deep(h3) { font-size: 1em; font-weight: 600; margin: 16px 0 6px; }
.markdown-body :deep(p) { margin: 0 0 10px; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 0 0 10px; padding-left: 24px; }
.markdown-body :deep(ol) { list-style-type: decimal; }
.markdown-body :deep(li) { margin-bottom: 6px; }
.markdown-body :deep(li p) { margin: 0; }
.markdown-body :deep(strong) { font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.95); }
.markdown-body :deep(code) {
  background: rgba(var(--v-theme-on-surface), 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.87em;
}
.markdown-body :deep(pre) {
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 6px;
  padding: 12px 16px;
  margin: 0 0 10px;
  overflow-x: auto;
}
.markdown-body :deep(pre code) { background: none; padding: 0; }
</style>
