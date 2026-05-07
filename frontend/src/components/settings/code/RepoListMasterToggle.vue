<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Master select-all row sitting beneath RepoListHeader. Owns the
  tristate logic so the header above stays focused on add/scan
  controls.

  Tristate behaviour: a click on an indeterminate state promotes to
  "all selected" (matching the existing pattern from the legacy
  settings page) rather than clearing — so a partial selection from a
  prior scan never silently disappears.
-->
<template>
  <div class="d-flex align-center ga-2 px-5 py-2 select-row">
    <v-checkbox-btn
      :model-value="masterChecked"
      :indeterminate="masterIndeterminate"
      color="primary"
      density="compact"
      hide-details
      class="select-checkbox flex-grow-0"
      :disabled="disabled || activeRepos.length === 0"
      @update:model-value="onToggle"
    />
    <div class="text-caption text-medium-emphasis select-label">
      {{ label }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useReposcanV2ScansStore } from '@/stores/reposcanv2Scans'
import type { RepoInfo } from '@/types'

const props = defineProps<{
  repos: RepoInfo[]
  disabled: boolean
}>()

const scanStore = useReposcanV2ScansStore()

const activeRepos = computed(() => props.repos.filter(r => r.status === 'active'))
const selectedActiveCount = computed(
  () => activeRepos.value.filter(r => scanStore.selectedRepoIds.has(r.id)).length,
)
const masterChecked = computed(
  () => activeRepos.value.length > 0 && selectedActiveCount.value === activeRepos.value.length,
)
const masterIndeterminate = computed(
  () => selectedActiveCount.value > 0 && !masterChecked.value,
)

const label = computed(() => {
  if (props.disabled) return 'Selection locked while scanning.'
  if (activeRepos.value.length === 0) return 'No active repositories to scan'
  if (selectedActiveCount.value === 0) return `Select all (${activeRepos.value.length})`
  if (masterChecked.value) return `All ${activeRepos.value.length} selected — click to clear`
  return `${selectedActiveCount.value} of ${activeRepos.value.length} selected`
})

function onToggle(checked: boolean | null): void {
  if (props.disabled) return
  if (checked || masterIndeterminate.value) {
    scanStore.selectedRepoIds = new Set(activeRepos.value.map(r => r.id))
  } else {
    scanStore.selectedRepoIds = new Set()
  }
}
</script>

<style scoped>
.select-row {
  background: rgba(var(--v-theme-on-surface), 0.02);
}

/* v-checkbox-btn defaults to flex: 1 1 auto, which pushes the label to
   the far right of the row. Constrain it so the checkbox + label cluster
   sits flush on the left. */
.select-checkbox {
  flex: 0 0 auto;
  width: auto;
}

.select-checkbox :deep(.v-selection-control) {
  flex: 0 0 auto;
}

.select-label {
  flex: 0 1 auto;
}
</style>
