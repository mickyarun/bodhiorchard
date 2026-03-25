<template>
  <v-card
    v-if="!dismissed && checklist"
    class="setup-checklist"
    color="surface"
    elevation="8"
    rounded="lg"
    width="340"
  >
    <v-card-title class="d-flex align-center ga-2 py-3 px-4">
      <v-icon icon="mdi-clipboard-check-outline" size="20" color="primary" />
      <span class="text-body-1 font-weight-medium">Getting Started</span>
      <v-spacer />
      <v-btn
        icon="mdi-close"
        variant="text"
        size="x-small"
        @click="dismiss"
      />
    </v-card-title>

    <v-divider />

    <v-list density="compact" class="py-1">
      <v-list-item
        v-for="item in items"
        :key="item.key"
        :class="{ 'text-medium-emphasis': item.done }"
        @click="item.route && !item.done ? $router.push(item.route) : undefined"
      >
        <template #prepend>
          <v-icon
            v-if="item.inProgress"
            icon="mdi-loading"
            class="mdi-spin"
            size="20"
            color="primary"
          />
          <v-icon
            v-else
            :icon="item.done ? 'mdi-check-circle' : 'mdi-circle-outline'"
            :color="item.done ? 'success' : 'grey'"
            size="20"
          />
        </template>

        <v-list-item-title class="text-body-2">
          {{ item.label }}
          <span v-if="item.inProgress" class="text-caption text-primary ml-1">
            {{ item.progressText }}
          </span>
        </v-list-item-title>

        <v-list-item-subtitle v-if="item.optional" class="text-caption">
          Optional
        </v-list-item-subtitle>
      </v-list-item>
    </v-list>

    <!-- Scan progress bar -->
    <div v-if="checklist.scanInProgress || wsScanActive" class="px-4 pb-3">
      <v-progress-linear
        :model-value="displayProgress"
        color="primary"
        rounded
        height="6"
      />
      <div class="text-caption text-medium-emphasis mt-1">
        {{ displayStatusLabel }}
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import api from '@/services/api'
import { useScanSocket } from '@/composables/useScanSocket'
import type { ScanStatusData } from '@/composables/useScanSocket'
import type { SetupChecklistStatus } from '@/types/setup'

const checklist = ref<SetupChecklistStatus | null>(null)
const dismissed = ref(localStorage.getItem('flowdev_checklist_dismissed') === 'true')
let pollInterval: ReturnType<typeof setInterval> | null = null

// WS-driven progress (real-time, replaces stale poll data)
const { startTracking, stopTracking } = useScanSocket()
const wsScanActive = ref(false)
const wsProgress = ref(0)
const wsStatusLabel = ref('')
let currentWsScanId: string | null = null

// Use WS progress when available, fall back to poll data
const displayProgress = computed(() =>
  wsScanActive.value ? wsProgress.value : (checklist.value?.scanProgress ?? 0),
)
const displayStatusLabel = computed(() =>
  wsScanActive.value && wsStatusLabel.value
    ? wsStatusLabel.value
    : 'Scanning repository...',
)

interface ChecklistItem {
  key: string
  label: string
  done: boolean
  inProgress?: boolean
  progressText?: string
  route?: string
  optional?: boolean
}

const items = computed<ChecklistItem[]>(() => {
  if (!checklist.value) return []
  const c = checklist.value
  const scanInProgress = c.scanInProgress || wsScanActive.value
  const progress = displayProgress.value
  return [
    { key: 'org', label: 'Create organization', done: c.orgCreated },
    { key: 'claude', label: 'Connect Claude Code', done: c.claudeCodeTested },
    { key: 'repo', label: 'Add repository', done: c.repoAdded, route: '/settings' },
    {
      key: 'scan',
      label: 'Scan repository',
      done: c.scanComplete,
      inProgress: scanInProgress,
      progressText: scanInProgress ? `${progress}%` : undefined,
    },
    { key: 'branches', label: 'Map branch strategy', done: c.branchesMapped, route: '/settings' },
    { key: 'github', label: 'Connect GitHub', done: c.githubConnected, route: '/settings', optional: true },
    { key: 'slack', label: 'Connect Slack', done: c.slackConnected, route: '/settings', optional: true },
    { key: 'members', label: 'Import team members', done: c.membersImported, route: '/members', optional: true },
  ]
})

const allRequiredDone = computed(() => {
  if (!checklist.value) return false
  return checklist.value.orgCreated
    && checklist.value.repoAdded
    && checklist.value.scanComplete
    && checklist.value.branchesMapped
})

// Start WS tracking when poll detects an active scan
function maybeStartWsTracking(scanId: string): void {
  if (currentWsScanId === scanId) return // already tracking
  if (currentWsScanId) stopTracking()

  currentWsScanId = scanId
  wsScanActive.value = true

  startTracking(scanId, {
    onProgress: (data: ScanStatusData) => {
      wsProgress.value = data.progressPct || 0
      wsStatusLabel.value = data.statusLabel || ''
    },
    onComplete: () => {
      wsScanActive.value = false
      currentWsScanId = null
      // Refresh checklist state to mark scan as complete
      fetchStatus()
    },
    onError: () => {
      wsScanActive.value = false
      currentWsScanId = null
      fetchStatus()
    },
  })
}

async function fetchStatus(): Promise<void> {
  try {
    const { data } = await api.get('/setup/checklist-status')
    checklist.value = data

    // If org was re-created (reset_db), clear the dismiss flag so
    // the checklist reappears for the new setup.
    if (!data.orgCreated || !data.scanComplete) {
      if (dismissed.value) {
        dismissed.value = false
        localStorage.removeItem('flowdev_checklist_dismissed')
        // Start polling now that we're un-dismissed
        if (!pollInterval) {
          pollInterval = setInterval(fetchStatus, 10_000)
        }
      }
    }

    // Start WS tracking if a scan is running
    if (data.scanInProgress && data.scanId) {
      maybeStartWsTracking(data.scanId)
    }

    if (allRequiredDone.value && !data.scanInProgress) {
      stopPolling()
    }
  } catch {
    // Silently fail — widget is non-critical
  }
}

function dismiss(): void {
  dismissed.value = true
  localStorage.setItem('flowdev_checklist_dismissed', 'true')
  stopPolling()
  stopTracking()
  wsScanActive.value = false
  currentWsScanId = null
}

function stopPolling(): void {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

onMounted(() => {
  // Always fetch once — even if dismissed — so we can detect a DB reset
  // and re-show the checklist.
  fetchStatus()
  if (!dismissed.value) {
    pollInterval = setInterval(fetchStatus, 10_000)
  }
})

onUnmounted(() => {
  stopPolling()
  stopTracking()
})
</script>

<style scoped>
.setup-checklist {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 100;
}

.mdi-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
