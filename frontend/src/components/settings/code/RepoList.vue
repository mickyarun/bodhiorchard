<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<!--
  Unified Repositories card for /settings/code.

  This is the single section on the page — it owns:
    - The header (title, Add/Dismiss, Scan/Resume)
    - The master select-all toggle
    - The list of tracked repository rows (each row owns its own
      inline scan track when a scan is active)
    - The cross-repo finalization strip below the rows
    - The Add dialog and the Remove confirm dialog

  Branch-mapping editing is bubbled up to the parent so a single
  RepoBranchMappingDialog instance handles every row at page level.
-->
<template>
  <v-card class="pa-0 settings-card mb-6" color="surface" variant="flat">
    <RepoListHeader
      :repos="repos"
      :is-locked="isLocked"
      @add-repo="addOpen = true"
      @scan="onScan"
    />

    <template v-if="repos.length > 0">
      <v-divider />
      <RepoListMasterToggle :repos="repos" :disabled="isLocked" />
    </template>

    <v-divider />

    <v-empty-state
      v-if="repos.length === 0"
      icon="mdi-folder-search-outline"
      title="No repositories yet"
      text="Click 'Add repo' to import a local folder or clone from GitHub."
      class="py-10"
    />

    <div v-else class="d-flex flex-column">
      <RepoListRow
        v-for="(repo, idx) in repos"
        :key="repo.id"
        :repo="repo"
        :selectable="selectable"
        :selected="scanStore.selectedRepoIds.has(repo.id)"
        :uat-enabled="uatEnabled"
        :busy="busyId === repo.id"
        :has-divider="idx < repos.length - 1"
        :is-locked="isLocked"
        :run="runByRepo[repo.id] ?? null"
        @toggle-select="onToggleSelect"
        @edit-branches="emit('edit-branches', $event)"
        @toggle-status="onToggleStatus"
        @request-remove="onRemove"
      />
    </div>

    <ScanFinalizationRow
      v-if="scanStore.currentScan"
      :runs="scanStore.currentScan.repo_runs"
    />

    <RepoAddDialog v-model="addOpen" :branches="branches" />

    <ConfirmDialog
      v-model="confirmOpen"
      title="Remove repository?"
      :message="confirmMessage"
      confirm-label="Remove"
      tone="error"
      icon="mdi-delete-outline"
      @confirm="performRemove"
    />
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import RepoAddDialog from './RepoAddDialog.vue'
import RepoListHeader from './RepoListHeader.vue'
import RepoListMasterToggle from './RepoListMasterToggle.vue'
import RepoListRow from './RepoListRow.vue'
import ScanFinalizationRow from './ScanFinalizationRow.vue'
import type { useRepoBranches } from '@/composables/useRepoBranches'
import { useSettingsStore } from '@/stores/settings'
import { useReposcanV2ScansStore, type RepoRunRow } from '@/stores/reposcanv2Scans'
import type { RepoInfo } from '@/types'

withDefaults(defineProps<{
  repos: RepoInfo[]
  /** Page-level branch composable, forwarded into RepoAddDialog so the
   *  post-clone walkthrough drives the same RepoBranchMappingDialog
   *  instance the page already mounts. */
  branches: ReturnType<typeof useRepoBranches>
  selectable?: boolean
}>(), { selectable: true })

const emit = defineEmits<{
  'edit-branches': [repo: RepoInfo]
}>()

const settingsStore = useSettingsStore()
const scanStore = useReposcanV2ScansStore()

const busyId = ref<string | null>(null)
const confirmOpen = ref(false)
const pendingRemove = ref<RepoInfo | null>(null)
const addOpen = ref(false)

const uatEnabled = computed(
  () => settingsStore.connections.budStages?.uatEnabled ?? true,
)

// Lock every edit path while a scan is actively executing. Terminal
// states (failed / done / cancelled) release the lock so the user can
// resume, dismiss, or fix mappings before the next scan.
const isLocked = computed(() => scanStore.isCurrentScanActive)

// When a scan finishes, refresh the underlying repo list so each row's
// last-scan summary (status pill, relative time, feature count)
// reflects the run that just landed. The watcher fires only on the
// active → inactive transition so we don't spam the endpoint while a
// scan is starting up.
watch(
  () => scanStore.isCurrentScanActive,
  (active, wasActive) => {
    if (wasActive && !active) {
      void settingsStore.fetchRepos()
    }
  },
)

// Indexed for O(1) lookup per row instead of repeated linear scans.
const runByRepo = computed<Record<string, RepoRunRow>>(() => {
  const out: Record<string, RepoRunRow> = {}
  for (const run of scanStore.currentScan?.repo_runs ?? []) {
    out[run.repo_id] = run
  }
  return out
})

const confirmMessage = computed(() =>
  pendingRemove.value
    ? `Remove ${pendingRemove.value.name}? Bodhiorchard will stop scanning it; existing features stay.`
    : '',
)

function onToggleSelect(repo: RepoInfo): void {
  scanStore.toggleRepo(repo.id)
}

async function onToggleStatus(repo: RepoInfo): Promise<void> {
  busyId.value = repo.id
  try {
    await settingsStore.setRepoStatus(
      repo.id,
      repo.status === 'active' ? 'ignored' : 'active',
    )
  } finally {
    busyId.value = null
  }
}

function onRemove(repo: RepoInfo): void {
  pendingRemove.value = repo
  confirmOpen.value = true
}

async function performRemove(): Promise<void> {
  const repo = pendingRemove.value
  if (!repo) return
  busyId.value = repo.id
  try {
    await settingsStore.removeRepo(repo.path)
  } finally {
    busyId.value = null
    pendingRemove.value = null
  }
}

async function onScan(): Promise<void> {
  // Always start a fresh scan on the current selection. Resume was
  // removed in favour of having the user re-select the repos they want
  // to retry — simpler mental model than "click Resume to retry the
  // failed subset of the prior scan".
  await scanStore.startScan()
  // Nudge the page-wide BUD-stages flag so it stays current after a
  // settings change elsewhere on the page.
  if (!settingsStore.connections.budStages) {
    void settingsStore.fetchConnections()
  }
}
</script>

<style scoped>
.settings-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  /* Vuetify's ``.v-card`` clips children by default. Override so
     ``position: sticky`` on the header / finalization rows can find a
     non-clipping ancestor and stick relative to the page scroll
     instead of getting trapped inside the card. The 1px rounded border
     above is preserved by ``isolation`` — the card still draws its
     background and border, but doesn't introduce a new scroll/clip
     context. */
  overflow: visible !important;
}
</style>
