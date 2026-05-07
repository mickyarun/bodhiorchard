<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Header for the unified Repositories card. Owns:
    - Title + scan-aware summary (delegates progress wording to
      useScanProgress)
    - Add repo / Dismiss button (Dismiss replaces Add when a scan is
      terminal but not yet dismissed; Add disables during an active
      scan)
    - Primary Scan/Resume button

  The master-select-all row lives in a sibling component
  (RepoListMasterToggle) so this file stays focused on the scan
  controls.
-->
<template>
  <div class="repo-list-header d-flex align-center ga-3 px-5 pt-5 pb-3 flex-wrap">
    <v-avatar size="36" color="surface-variant" rounded="lg">
      <v-icon :icon="headerIcon" size="22" />
    </v-avatar>
    <div class="flex-grow-1 min-w-0">
      <div class="text-body-1 font-weight-medium d-flex align-center ga-2">
        {{ headerTitle }}
        <v-chip
          v-if="scanStore.currentScan"
          size="x-small"
          variant="tonal"
          :color="statusTone"
        >
          {{ statusLabel }}
        </v-chip>
      </div>
      <div class="text-caption text-medium-emphasis">{{ summary }}</div>
    </div>

    <v-tooltip
      location="top"
      :disabled="!isLocked"
      text="Locked while a scan is running."
    >
      <template #activator="{ props: tip }">
        <span v-bind="tip">
          <v-btn
            prepend-icon="mdi-plus"
            variant="tonal"
            color="primary"
            class="text-none"
            :disabled="isLocked"
            @click="emit('add-repo')"
          >
            Add repo
          </v-btn>
        </span>
      </template>
    </v-tooltip>

    <v-btn
      v-if="canCancel"
      color="error"
      variant="outlined"
      prepend-icon="mdi-stop-circle-outline"
      :loading="scanStore.cancellingScan"
      class="text-none"
      @click="cancelDialogOpen = true"
    >
      Cancel scan
    </v-btn>

    <v-btn
      color="primary"
      variant="flat"
      prepend-icon="mdi-play"
      :disabled="!canStart"
      :loading="scanStore.startingScan || (isLocked && !canCancel)"
      class="text-none"
      @click="emit('scan')"
    >
      {{ primaryLabel }}
    </v-btn>
  </div>

  <v-alert
    v-if="scanStore.error"
    type="error"
    variant="tonal"
    density="compact"
    class="mx-5 mb-3"
    closable
    @click:close="scanStore.error = null"
  >
    {{ scanStore.error }}
  </v-alert>

  <ConfirmDialog
    v-model="cancelDialogOpen"
    title="Cancel running scan?"
    message="Cancel scan and discard in-flight per-repo work? Repos that have already finished will keep their results."
    confirm-label="Cancel scan"
    cancel-label="Keep running"
    tone="error"
    icon="mdi-stop-circle-outline"
    @confirm="onCancelConfirmed"
  />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useReposcanV2ScansStore } from '@/stores/reposcanv2Scans'
import { useScanProgress } from '@/composables/useScanProgress'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import type { RepoInfo } from '@/types'

const props = defineProps<{
  repos: RepoInfo[]
  isLocked: boolean
}>()

const emit = defineEmits<{
  'add-repo': []
  'scan': []
}>()

const scanStore = useReposcanV2ScansStore()
const { statusTone, statusLabel, progressSummary } = useScanProgress()

const activeCount = computed(() => props.repos.filter(r => r.status === 'active').length)
const selectedCount = computed(() => scanStore.selectedRepoIds.size)

const canStart = computed(() => {
  if (props.isLocked || scanStore.startingScan) return false
  return selectedCount.value > 0
})

const headerIcon = computed(() => (
  props.isLocked ? 'mdi-timeline-clock-outline' : 'mdi-source-repository-multiple'
))
const headerTitle = computed(() => (props.isLocked ? 'Scan in progress' : 'Repositories'))

const summary = computed(() => {
  if (scanStore.currentScan) return progressSummary.value
  const total = props.repos.length
  if (total === 0) return 'No repositories yet — add one to get started.'
  if (selectedCount.value === 0) {
    return `${total} connected · ${activeCount.value} active — pick the ones to scan.`
  }
  return `${selectedCount.value} of ${activeCount.value} selected for scan.`
})

const primaryLabel = computed(() => {
  if (scanStore.startingScan) return 'Starting…'
  if (props.isLocked) return 'Scanning…'
  if (selectedCount.value === 0) return 'Scan'
  return selectedCount.value === 1 ? 'Scan 1 repository' : `Scan ${selectedCount.value} repositories`
})

const cancelDialogOpen = ref(false)

// Cancel is only meaningful while a scan is actually in flight. Disable
// for terminal scans so a user returning to the page after a failed run
// doesn't see a button that does nothing.
const canCancel = computed(
  () => scanStore.isCurrentScanActive && !scanStore.cancellingScan,
)

async function onCancelConfirmed(): Promise<void> {
  await scanStore.cancelActiveScan()
}
</script>

<style scoped>
/* Sticky to the top of the surrounding scroll container so the Scan /
   Cancel actions stay reachable while the user scrolls a long repo
   list. ``z-index`` keeps it above repo rows + their hover affordances;
   the surface background prevents text bleed-through during overlap. */
.repo-list-header {
  position: sticky;
  top: 0;
  z-index: 3;
  background: rgb(var(--v-theme-surface));
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}
</style>
