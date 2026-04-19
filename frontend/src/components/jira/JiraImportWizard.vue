<template>
  <v-card class="pa-5 settings-card" color="surface">
    <!-- Stepper Header -->
    <div class="d-flex align-center ga-2 mb-5">
      <template v-for="(s, i) in steps" :key="s.key">
        <v-chip
          :color="i <= currentStep ? 'primary' : 'grey'"
          :variant="i === currentStep ? 'flat' : 'tonal'"
          size="small"
        >
          {{ i + 1 }}. {{ s.label }}
        </v-chip>
        <v-icon v-if="i < steps.length - 1" icon="mdi-chevron-right" size="16" class="text-medium-emphasis" />
      </template>
      <v-spacer />
      <v-btn icon="mdi-close" size="small" variant="text" @click="$emit('close')" />
    </div>

    <!-- Step 1: Select Project -->
    <template v-if="currentStep === 0">
      <div class="text-body-1 font-weight-medium mb-3">Select a Jira Project</div>

      <div v-if="store.loading" class="d-flex justify-center py-6">
        <v-progress-circular indeterminate size="24" />
      </div>

      <template v-else>
        <v-text-field
          v-model="projectSearch"
          placeholder="Search projects..."
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
        />
        <div class="d-flex flex-column ga-2" style="max-height: 300px; overflow-y: auto">
          <div
            v-for="p in filteredProjects"
            :key="p.key"
            class="pa-3 cursor-pointer project-item d-flex align-center ga-3"
            :class="{ 'project-item--selected': selectedProject?.key === p.key }"
            @click="selectedProject = p"
          >
            <v-chip size="x-small" variant="flat" color="primary" label>
              {{ p.key }}
            </v-chip>
            <span class="text-body-2">{{ p.name }}</span>
            <v-spacer />
            <span v-if="p.lead" class="text-caption text-medium-emphasis">{{ p.lead }}</span>
          </div>
        </div>
      </template>

      <div class="d-flex justify-end mt-4">
        <v-btn
          color="primary"
          variant="flat"
          :disabled="!selectedProject"
          @click="runDiscovery"
        >
          Next: Discover
        </v-btn>
      </div>
    </template>

    <!-- Step 2: Discovery Results -->
    <template v-if="currentStep === 1">
      <template v-if="discovering">
        <div class="text-center py-8">
          <v-progress-circular indeterminate size="40" color="primary" class="mb-4" />
          <div class="text-body-2">{{ discoveryStatus || 'Scanning Jira project...' }}</div>
          <div v-if="discoveryPct > 0" class="mt-2">
            <v-progress-linear :model-value="discoveryPct" color="primary" rounded height="6" />
          </div>
        </div>
      </template>

      <template v-else-if="store.discoveryResult">
        <div class="text-body-1 font-weight-medium mb-3">Discovery Results</div>
        <div class="d-flex flex-wrap ga-4 mb-4">
          <div class="text-center">
            <div class="text-h5 font-weight-bold text-primary">
              {{ store.discoveryResult.totalIssues }}
            </div>
            <div class="text-caption text-medium-emphasis">Backlog Issues</div>
          </div>
          <div v-if="store.discoveryResult.alreadyImportedCount" class="text-center">
            <div class="text-h5 font-weight-bold text-warning">
              {{ store.discoveryResult.alreadyImportedCount }}
            </div>
            <div class="text-caption text-medium-emphasis">Already Imported</div>
          </div>
          <div class="text-center">
            <div class="text-h5 font-weight-bold" :class="newToImport > 0 ? 'text-success' : 'text-error'">
              {{ newToImport }}
            </div>
            <div class="text-caption text-medium-emphasis">New to Import</div>
          </div>
          <div v-if="newToImport > 0" class="text-center">
            <div class="text-h5 font-weight-bold text-medium-emphasis">
              ~{{ Math.ceil(store.discoveryResult.estimatedTimeSeconds / 60) }} min
            </div>
            <div class="text-caption text-medium-emphasis">Est. Time</div>
          </div>
        </div>

        <!-- Nothing to import warning -->
        <v-alert v-if="newToImport === 0" type="warning" variant="tonal" density="compact" class="mb-4">
          All backlog issues from this project have already been imported.
          There is nothing new to import.
        </v-alert>

        <!-- Issue type breakdown -->
        <div class="mb-4">
          <div class="text-body-2 font-weight-medium mb-2">By Issue Type</div>
          <div class="d-flex flex-wrap ga-2">
            <v-chip
              v-for="t in store.discoveryResult.byType"
              :key="t.issueType"
              size="small"
              variant="tonal"
            >
              {{ t.issueType }}: {{ t.count }}
            </v-chip>
          </div>
        </div>

        <!-- Sample issues -->
        <div v-if="store.discoveryResult.sampleIssues.length" class="mb-4">
          <div class="text-body-2 font-weight-medium mb-2">Sample Issues</div>
          <v-table density="compact">
            <thead>
              <tr>
                <th>Key</th>
                <th>Type</th>
                <th>Summary</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in store.discoveryResult.sampleIssues" :key="s.key">
                <td class="text-caption font-weight-medium">{{ s.key }}</td>
                <td class="text-caption">{{ s.type }}</td>
                <td class="text-caption">{{ s.summary }}</td>
                <td class="text-caption">{{ s.status }}</td>
              </tr>
            </tbody>
          </v-table>
        </div>

        <div class="d-flex ga-3 justify-end">
          <v-btn variant="text" @click="currentStep = 0">Back</v-btn>
          <v-btn color="primary" variant="flat" :disabled="newToImport === 0" @click="currentStep = 2">
            Configure Import
          </v-btn>
        </div>
      </template>
    </template>

    <!-- Step 3: Configure -->
    <template v-if="currentStep === 2">
      <div class="text-body-1 font-weight-medium mb-3">Import Configuration</div>

      <!-- Scope explanation -->
      <v-alert type="info" variant="tonal" density="compact" class="mb-4">
        <div class="text-body-2 font-weight-medium mb-1">Importing backlog only</div>
        <div class="text-caption">
          Only <strong>backlog items</strong> (To Do, Open, Backlog) will be imported.
          Closed/resolved issues are already done. In-progress and testing items
          are actively being worked on. All imported issues start as BUD status.
        </div>
      </v-alert>

      <!-- Consolidation mode -->
      <div class="mb-4">
        <div class="text-body-2 font-weight-medium mb-2">Consolidation Mode</div>
        <v-radio-group v-model="consolidationMode" inline hide-details>
          <v-radio value="epic" label="Epic (group children under parent Epic)" />
          <v-radio value="flat" label="Flat (each issue becomes a separate BUD)" />
        </v-radio-group>
      </div>

      <div class="d-flex ga-3 justify-end">
        <v-btn variant="text" @click="currentStep = 1">Back</v-btn>
        <v-btn color="primary" variant="flat" @click="runImport">Start Import</v-btn>
      </div>
    </template>

    <!-- Step 4: Import Progress -->
    <template v-if="currentStep === 3">
      <div class="text-center py-8">
        <!-- Processing / Review header — hidden after decisions applied -->
        <template v-if="!decisionsApplied">
          <v-progress-circular
            v-if="!importDone"
            indeterminate
            size="48"
            color="primary"
            class="mb-4"
          />
          <v-icon
            v-else
            :icon="importFailed ? 'mdi-alert-circle' : (importResult?.reviewNeeded.length ? 'mdi-clipboard-check-outline' : 'mdi-check-circle')"
            :color="importFailed ? 'error' : (importResult?.reviewNeeded.length ? 'primary' : 'success')"
            size="48"
            class="mb-4"
          />
          <div class="text-body-1 font-weight-medium mb-2">
            {{ importDone
              ? (importFailed ? 'Import Failed' : (importResult?.reviewNeeded.length ? 'Review & Import' : 'Import Complete'))
              : 'Processing...'
            }}
          </div>
          <div class="text-body-2 text-medium-emphasis mb-3">
            {{ importDone && !importFailed && importResult?.reviewNeeded.length
              ? 'Select which items to create as BUDs'
              : importStatusMessage
            }}
          </div>
        </template>
        <v-progress-linear
          v-if="!importDone"
          :model-value="importPct"
          color="primary"
          rounded
          height="8"
          class="mx-auto"
          style="max-width: 400px"
        />

        <!-- Decisions applied — show summary -->
        <div v-if="decisionsApplied" class="mt-6 text-center">
          <v-icon icon="mdi-check-circle" color="success" size="48" class="mb-3" />
          <div class="text-body-1 font-weight-medium mb-2">{{ importStatusMessage }}</div>
          <v-btn color="primary" variant="flat" class="mt-3" @click="$emit('complete')">Done</v-btn>
        </div>

        <!-- Review items — user decides per item -->
        <div v-if="importResult && importResult.reviewNeeded.length && !decisionsApplied" class="mt-6 text-left">
          <div class="text-body-1 font-weight-medium mb-1">
            {{ importResult.reviewNeeded.length }} items ready for import
          </div>
          <div class="text-caption text-medium-emphasis mb-3">
            Choose which items to import as BUDs. Similar existing BUDs shown for reference.
          </div>

          <div class="d-flex flex-column ga-2 mb-4">
            <div
              v-for="r in importResult.reviewNeeded"
              :key="r.jiraKey"
              class="pa-3 d-flex align-center ga-3 project-item"
              :class="{
                'project-item--selected': reviewDecisions[r.jiraKey] === 'import',
                'opacity-50': reviewDecisions[r.jiraKey] === 'skip',
              }"
            >
              <div class="flex-grow-1">
                <div class="d-flex align-center ga-2">
                  <span class="text-body-2 font-weight-medium">{{ r.jiraKey }}</span>
                  <v-chip v-if="r.issueType" size="x-small" variant="tonal" label>
                    {{ r.issueType }}
                  </v-chip>
                </div>
                <div v-if="r.summary" class="text-body-2">{{ r.summary }}</div>
                <div v-if="r.descriptionPreview" class="text-caption text-medium-emphasis" style="max-width: 600px">
                  {{ r.descriptionPreview }}
                </div>
                <div v-if="r.similarToBud" class="text-caption text-warning mt-1">
                  Similar to BUD-{{ r.similarToBud }} ({{ r.distance.toFixed(2) }})
                </div>
              </div>
              <div class="d-flex ga-2">
                <v-btn
                  size="small"
                  variant="flat"
                  :color="reviewDecisions[r.jiraKey] === 'import' ? 'success' : 'surface-variant'"
                  @click="reviewDecisions[r.jiraKey] = 'import'"
                >
                  Import
                </v-btn>
                <v-btn
                  size="small"
                  variant="flat"
                  :color="reviewDecisions[r.jiraKey] === 'skip' ? 'grey' : 'surface-variant'"
                  @click="reviewDecisions[r.jiraKey] = 'skip'"
                >
                  Skip
                </v-btn>
                <v-btn
                  v-if="r.similarToBud"
                  size="small"
                  variant="flat"
                  :color="reviewDecisions[r.jiraKey] === 'merge' ? 'warning' : 'surface-variant'"
                  @click="reviewDecisions[r.jiraKey] = 'merge'"
                >
                  Merge
                </v-btn>
              </div>
            </div>
          </div>

          <!-- Quick actions -->
          <div class="d-flex ga-2 mb-4">
            <v-btn size="small" variant="tonal" @click="selectAll('import')">Import All</v-btn>
            <v-btn size="small" variant="tonal" @click="selectAll('skip')">Skip All</v-btn>
          </div>

          <!-- Failed items -->
          <div v-if="importResult.failed.length" class="mb-4">
            <div class="text-body-2 font-weight-medium mb-2 text-error">
              {{ importResult.failed.length }} items failed during processing
            </div>
            <div v-for="f in importResult.failed" :key="f.jiraKey" class="text-caption mb-1">
              <span class="font-weight-medium">{{ f.jiraKey }}:</span> {{ f.error }}
            </div>
          </div>
        </div>

        <div v-if="importDone && !importFailed && !decisionsApplied" class="d-flex justify-center ga-3 mt-4">
          <v-btn
            color="primary"
            variant="flat"
            :loading="applyingDecisions"
            :disabled="!hasAnyDecision"
            @click="applyDecisions"
          >
            Apply Decisions ({{ importCount }} to import)
          </v-btn>
          <v-btn variant="text" @click="$emit('complete')">Close</v-btn>
        </div>
        <div v-if="importDone && importFailed" class="d-flex justify-center mt-4">
          <v-btn color="primary" variant="flat" @click="$emit('complete')">Close</v-btn>
        </div>
      </div>
    </template>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useJiraImportStore } from '@/stores/jiraImport'
import type { DiscoveryResult, JiraProject, ReconciliationReport } from '@/stores/jiraImport'
import { useJobSocket } from '@/composables/useJobSocket'
import type { JobStatusRead } from '@/types'
import api from '@/services/api'

defineEmits<{
  close: []
  complete: []
}>()

const store = useJiraImportStore()
const { startTracking, stopTracking } = useJobSocket()
const SAFETY_TIMEOUT_MS = 660_000
let safetyTimer: ReturnType<typeof setTimeout> | null = null

onBeforeUnmount(() => {
  stopTracking()
  if (safetyTimer) clearTimeout(safetyTimer)
})

// Steps
const steps = [
  { key: 'select', label: 'Select' },
  { key: 'discover', label: 'Discover' },
  { key: 'configure', label: 'Configure' },
  { key: 'import', label: 'Import' },
]
const currentStep = ref(0)

// Derived: how many new issues will be imported
const newToImport = computed(() => {
  const dr = store.discoveryResult
  if (!dr) return 0
  return Math.max(0, dr.totalIssues - dr.alreadyImportedCount)
})

// Step 1: Project selection
const projectSearch = ref('')
const selectedProject = ref<JiraProject | null>(null)

const filteredProjects = computed(() => {
  const q = projectSearch.value.toLowerCase()
  if (!q) return store.projects
  return store.projects.filter(
    (p) => p.key.toLowerCase().includes(q) || p.name.toLowerCase().includes(q),
  )
})

// Step 2: Discovery
const discovering = ref(false)
const discoveryStatus = ref('')
const discoveryPct = ref(0)

// Step 3: Configuration
const consolidationMode = ref<'epic' | 'flat'>('epic')

// Step 4: Import progress + review decisions
const importDone = ref(false)
const importFailed = ref(false)
const reviewDecisions = ref<Record<string, 'import' | 'skip' | 'merge'>>({})
const applyingDecisions = ref(false)
const decisionsApplied = ref(false)

const hasAnyDecision = computed(() =>
  Object.values(reviewDecisions.value).some((d) => d === 'import' || d === 'merge'),
)
const importCount = computed(() =>
  Object.values(reviewDecisions.value).filter((d) => d === 'import').length,
)
const importStatusMessage = ref('')
const importPct = ref(0)
const importResult = ref<ReconciliationReport | null>(null)

onMounted(async () => {
  if (store.isConnected) await store.fetchProjects()
})

async function runDiscovery(): Promise<void> {
  if (!selectedProject.value) return
  discovering.value = true
  discoveryStatus.value = 'Starting discovery...'
  discoveryPct.value = 0
  currentStep.value = 1

  const jobId = await store.discoverProject(selectedProject.value.key)
  if (!jobId) {
    discovering.value = false
    return
  }

  safetyTimer = setTimeout(() => {
    stopTracking()
    discovering.value = false
    store.error = 'Discovery timed out. Please try again.'
  }, SAFETY_TIMEOUT_MS)

  startTracking(jobId, {
    onProgress(data: JobStatusRead) {
      discoveryStatus.value = data.statusMessage || 'Scanning...'
      discoveryPct.value = data.progressPct
    },
    onComplete(data: JobStatusRead) {
      if (safetyTimer) clearTimeout(safetyTimer)
      discovering.value = false
      if (data.result) {
        store.setDiscoveryResult(data.result as DiscoveryResult)
      }
    },
    onError(err: string) {
      if (safetyTimer) clearTimeout(safetyTimer)
      discovering.value = false
      store.error = err
    },
  })
}

async function runImport(): Promise<void> {
  currentStep.value = 3
  importDone.value = false
  importFailed.value = false
  importStatusMessage.value = 'Starting import...'
  importPct.value = 0

  const jobId = await store.startImport({
    consolidationMode: consolidationMode.value,
    statusMappings: [],
    typeMappings: [],
  })
  if (!jobId) {
    importDone.value = true
    importFailed.value = true
    importStatusMessage.value = store.error || 'Failed to start import.'
    return
  }

  safetyTimer = setTimeout(() => {
    stopTracking()
    importDone.value = true
    importFailed.value = true
    importStatusMessage.value = 'Import timed out. Check import history for status.'
  }, SAFETY_TIMEOUT_MS)

  startTracking(jobId, {
    onProgress(data: JobStatusRead) {
      importStatusMessage.value = data.statusMessage || 'Importing...'
      importPct.value = data.progressPct
    },
    onComplete(data: JobStatusRead) {
      if (safetyTimer) clearTimeout(safetyTimer)
      importDone.value = true
      importStatusMessage.value = 'Import complete!'
      importPct.value = 100
      if (data.result) {
        importResult.value = data.result as ReconciliationReport
      }
    },
    onError(err: string) {
      if (safetyTimer) clearTimeout(safetyTimer)
      importDone.value = true
      importFailed.value = true
      importStatusMessage.value = err
    },
  })
}

function selectAll(action: 'import' | 'skip'): void {
  if (!importResult.value) return
  const decisions: Record<string, 'import' | 'skip' | 'merge'> = {}
  for (const r of importResult.value.reviewNeeded) {
    decisions[r.jiraKey] = action
  }
  reviewDecisions.value = decisions
}

async function applyDecisions(): Promise<void> {
  applyingDecisions.value = true
  importStatusMessage.value = 'Applying decisions...'

  if (!store.activeSessionId) return
  try {
    const { data: items } = await api.get(
      `/v1/jira/sessions/${store.activeSessionId}/review-items`,
    )

    let imported = 0
    let skipped = 0
    let merged = 0

    for (const item of items) {
      const decision = reviewDecisions.value[item.jiraKey]
      if (!decision) continue

      try {
        await api.post(`/v1/jira/review/${item.id}/action`, { action: decision })
        if (decision === 'import') imported++
        else if (decision === 'skip') skipped++
        else if (decision === 'merge') merged++
      } catch {
        // Individual item failure — continue with others
      }
    }

    // Update UI to show completion
    decisionsApplied.value = true
    importStatusMessage.value = `Done: ${imported} BUDs created, ${skipped} skipped, ${merged} merged`
  } catch {
    importStatusMessage.value = 'Failed to apply decisions'
  } finally {
    applyingDecisions.value = false
  }
}

</script>

<style scoped>
.project-item {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  transition: border-color 0.15s ease, background-color 0.15s ease;
  min-height: 40px;
}
.project-item:hover {
  border-color: rgba(255, 255, 255, 0.2);
  background-color: rgba(255, 255, 255, 0.03);
}
.project-item--selected {
  border-color: rgb(var(--v-theme-primary));
  background-color: rgba(var(--v-theme-primary), 0.08);
}
</style>
