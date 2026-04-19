<template>
  <div>
    <div v-if="cases.length === 0" class="text-center text-medium-emphasis py-6">
      No automation test cases generated yet.
    </div>

    <template v-for="group in groupedCases" :key="group.type">
      <div class="text-subtitle-2 text-medium-emphasis mt-4 mb-2">
        {{ typeLabels[group.type] || group.type }} ({{ group.cases.length }})
      </div>

      <v-expansion-panels variant="accordion" class="mb-2">
        <v-expansion-panel v-for="tc in group.cases" :key="tc.id">
          <v-expansion-panel-title>
            <div class="d-flex align-center ga-2 flex-grow-1">
              <v-chip
                size="x-small"
                :color="priorityColor[tc.priority] || 'grey'"
                variant="tonal"
              >
                {{ tc.priority }}
              </v-chip>
              <span class="text-body-2">{{ tc.id }}: {{ tc.title }}</span>
              <v-spacer />
              <v-chip
                v-for="tag in tc.tags?.slice(0, 3)"
                :key="tag"
                size="x-small"
                variant="outlined"
                class="ml-1"
              >
                {{ tag }}
              </v-chip>
            </div>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="mb-3">
              <div class="text-caption text-medium-emphasis mb-1">Test Scenario</div>
              <pre class="bg-grey-lighten-4 pa-3 rounded text-body-2" style="white-space: pre-wrap">{{ tc.gherkin }}</pre>
              <v-btn
                size="x-small"
                variant="text"
                class="mt-1"
                @click="copyToClipboard(tc.gherkin)"
              >
                <v-icon start size="14">mdi-content-copy</v-icon>
                Copy Scenario
              </v-btn>
            </div>

            <v-row dense>
              <v-col cols="6">
                <div class="text-caption text-medium-emphasis mb-1">Input</div>
                <div class="text-body-2 bg-blue-lighten-5 pa-2 rounded">{{ tc.input }}</div>
              </v-col>
              <v-col cols="6">
                <div class="text-caption text-medium-emphasis mb-1">Expected Output</div>
                <div class="text-body-2 bg-green-lighten-5 pa-2 rounded">{{ tc.expected_output }}</div>
              </v-col>
            </v-row>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AutomationTestCase } from '@/types'

const props = defineProps<{
  cases: AutomationTestCase[]
}>()

const typeLabels: Record<string, string> = {
  e2e: 'End-to-End Tests',
  integration: 'Integration Tests',
  unit: 'Unit Tests',
  api: 'API Tests',
}

const priorityColor: Record<string, string> = {
  critical: 'error',
  high: 'warning',
  medium: 'info',
  low: 'grey',
}

const groupedCases = computed(() => {
  const groups: Record<string, AutomationTestCase[]> = {}
  for (const tc of props.cases) {
    const type = tc.type || 'other'
    if (!groups[type]) groups[type] = []
    groups[type].push(tc)
  }
  return Object.entries(groups).map(([type, cases]) => ({ type, cases }))
})

function copyToClipboard(text: string): void {
  navigator.clipboard.writeText(text)
}
</script>
