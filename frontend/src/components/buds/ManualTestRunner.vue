<template>
  <div>
    <div v-if="cases.length === 0" class="text-center text-medium-emphasis py-6">
      No manual test cases generated yet.
    </div>

    <template v-if="cases.length > 0">
      <!-- Progress bar -->
      <div class="d-flex align-center ga-3 mb-4">
        <v-progress-linear
          :model-value="(completedCount / cases.length) * 100"
          :color="progressColor"
          height="8"
          rounded
        />
        <span class="text-caption text-medium-emphasis" style="white-space: nowrap">
          {{ completedCount }}/{{ cases.length }} completed
        </span>
      </div>

      <!-- Test case list -->
      <v-expansion-panels variant="accordion">
        <v-expansion-panel v-for="tc in cases" :key="tc.id">
          <v-expansion-panel-title>
            <div class="d-flex align-center ga-2 flex-grow-1">
              <v-chip
                size="x-small"
                :color="resultColor[tc.result] || 'grey'"
                variant="tonal"
              >
                {{ tc.result }}
              </v-chip>
              <v-chip
                size="x-small"
                :color="priorityColor[tc.priority] || 'grey'"
                variant="outlined"
              >
                {{ tc.priority }}
              </v-chip>
              <span class="text-body-2">{{ tc.id }}: {{ tc.title }}</span>
              <v-spacer />
              <v-chip size="x-small" variant="outlined">{{ tc.category }}</v-chip>
            </div>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <!-- Description -->
            <div v-if="tc.description" class="text-body-2 mb-3">{{ tc.description }}</div>

            <!-- Preconditions -->
            <div v-if="tc.preconditions" class="mb-3">
              <div class="text-caption text-medium-emphasis mb-1">Preconditions</div>
              <div class="text-body-2 bg-amber-lighten-5 pa-2 rounded">{{ tc.preconditions }}</div>
            </div>

            <!-- Steps -->
            <div class="mb-3">
              <div class="text-caption text-medium-emphasis mb-1">Steps</div>
              <ol class="text-body-2 pl-4">
                <li v-for="(step, i) in tc.steps" :key="i" class="mb-1">{{ step }}</li>
              </ol>
            </div>

            <!-- Expected Result -->
            <div class="mb-3">
              <div class="text-caption text-medium-emphasis mb-1">Expected Result</div>
              <div class="text-body-2 bg-green-lighten-5 pa-2 rounded">{{ tc.expected_result }}</div>
            </div>

            <!-- Result selector -->
            <div class="mb-3">
              <div class="text-caption text-medium-emphasis mb-1">Test Result</div>
              <v-btn-toggle
                :model-value="tc.result"
                mandatory
                density="compact"
                color="primary"
                @update:model-value="(val: string) => emit('update-result', tc.id, val as ManualTestCase['result'])"
              >
                <v-btn value="pass" size="small" color="success">
                  <v-icon start size="16">mdi-check-circle</v-icon>
                  Pass
                </v-btn>
                <v-btn value="fail" size="small" color="error">
                  <v-icon start size="16">mdi-close-circle</v-icon>
                  Fail
                </v-btn>
                <v-btn value="blocked" size="small" color="warning">
                  <v-icon start size="16">mdi-block-helper</v-icon>
                  Blocked
                </v-btn>
                <v-btn value="skipped" size="small" color="grey">
                  <v-icon start size="16">mdi-skip-next</v-icon>
                  Skip
                </v-btn>
              </v-btn-toggle>
            </div>

            <!-- Tester info -->
            <div v-if="tc.tester_name" class="text-caption text-medium-emphasis mb-3">
              Tested by {{ tc.tester_name }}
              <span v-if="tc.tested_at">at {{ new Date(tc.tested_at).toLocaleString() }}</span>
            </div>

            <!-- Evidence -->
            <div class="mb-2">
              <div class="text-caption text-medium-emphasis mb-1">Evidence</div>
              <div class="d-flex flex-wrap ga-2 mb-2">
                <v-chip
                  v-for="ev in getEvidenceForCase(tc.id)"
                  :key="ev.id"
                  size="small"
                  variant="outlined"
                  closable
                  @click:close="emit('delete-evidence', ev.id)"
                >
                  <v-icon start size="14">
                    {{ ev.mime_type.startsWith('image/') ? 'mdi-image' : 'mdi-file' }}
                  </v-icon>
                  {{ ev.filename }}
                </v-chip>
                <span v-if="getEvidenceForCase(tc.id).length === 0" class="text-caption text-medium-emphasis">
                  No evidence attached
                </span>
              </div>
              <v-btn
                size="x-small"
                variant="tonal"
                @click="triggerUpload(tc.id)"
              >
                <v-icon start size="14">mdi-upload</v-icon>
                Upload Evidence
              </v-btn>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <!-- Hidden file input -->
      <input
        ref="fileInputRef"
        type="file"
        style="display: none"
        accept="image/*,.pdf,.txt"
        @change="handleFileSelected"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ManualTestCase, TestEvidence } from '@/types'

const props = defineProps<{
  cases: ManualTestCase[]
  evidence: TestEvidence[]
}>()

const emit = defineEmits<{
  (e: 'update-result', testCaseId: string, result: ManualTestCase['result']): void
  (e: 'upload-evidence', testCaseId: string, file: File): void
  (e: 'delete-evidence', evidenceId: string): void
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadTargetCaseId = ref('')

const resultColor: Record<string, string> = {
  pass: 'success',
  fail: 'error',
  blocked: 'warning',
  skipped: 'grey',
  pending: 'blue-grey',
}

const priorityColor: Record<string, string> = {
  critical: 'error',
  high: 'warning',
  medium: 'info',
  low: 'grey',
}

const completedCount = computed(() =>
  props.cases.filter(c => c.result !== 'pending').length,
)

const progressColor = computed(() => {
  const pct = props.cases.length ? (completedCount.value / props.cases.length) * 100 : 0
  if (pct === 100) return 'success'
  if (pct > 50) return 'primary'
  return 'warning'
})

function getEvidenceForCase(testCaseId: string): TestEvidence[] {
  return props.evidence.filter(e => e.test_case_id === testCaseId)
}

function triggerUpload(testCaseId: string): void {
  uploadTargetCaseId.value = testCaseId
  fileInputRef.value?.click()
}

function handleFileSelected(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file && uploadTargetCaseId.value) {
    emit('upload-evidence', uploadTargetCaseId.value, file)
  }
  input.value = ''
}
</script>
