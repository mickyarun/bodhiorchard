<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Modal hosting both add-repo flows.

  Layout:
    [ header: title + deployment chip + close ]
    [ tab strip (Local / Clone) ]
    [ scrollable body — RepoLocalPickForm | RepoCloneForm ]
    [ footer: Scan-after-add toggle | Cancel | primary submit ]

  Submit + cancel live in the dialog footer (single source of truth).
  The active tab form exposes `canSubmit` and `submitLabel` via the
  shared useRepoImport composable so the footer button stays
  context-aware without prop drilling.

  Post-add follow-up (branch walkthrough for unmapped clones,
  optional scan kick-off) is delegated to useAddRepoSubmit so this
  component stays a presentation layer. The page passes its
  useRepoBranches instance in via the `branches` prop so the
  walkthrough drives the same dialog state the page already has
  mounted — no second BranchMappingDialog instance needed.
-->
<template>
  <v-dialog
    :model-value="modelValue"
    :max-width="560"
    :scrim="true"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card color="surface" class="add-card">
      <header class="add-head px-4 py-3">
        <v-icon icon="mdi-source-repository-multiple" size="18" class="text-medium-emphasis" />
        <span class="text-body-1 font-weight-medium ml-2">Add repositories</span>
        <v-chip
          v-if="deploymentMode"
          :color="deploymentMode === 'docker' ? 'info' : 'success'"
          variant="tonal"
          size="x-small"
          class="ml-2"
          :prepend-icon="deploymentMode === 'docker' ? 'mdi-docker' : 'mdi-laptop'"
        >
          {{ deploymentMode === 'docker' ? 'Full Docker' : 'Hybrid' }}
        </v-chip>
        <v-spacer />
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          density="compact"
          @click="close"
        />
      </header>

      <template v-if="modeReady">
        <div class="add-tabs px-2">
          <button
            v-if="canPickLocal"
            type="button"
            class="add-tab"
            :class="{ 'is-active': tab === TAB_LOCAL }"
            @click="tab = TAB_LOCAL"
          >
            <v-icon icon="mdi-folder-open-outline" size="16" />
            <span>Local folder</span>
          </button>
          <button
            type="button"
            class="add-tab"
            :class="{ 'is-active': tab === TAB_CLONE }"
            @click="tab = TAB_CLONE"
          >
            <v-icon icon="mdi-github" size="16" />
            <span>GitHub clone</span>
          </button>
          <button
            v-if="mode !== 'setup'"
            type="button"
            class="add-tab"
            :class="{ 'is-active': tab === TAB_BULK }"
            @click="tab = TAB_BULK"
          >
            <v-icon icon="mdi-source-repository-multiple" size="16" />
            <span>Bulk import</span>
          </button>
        </div>

        <div class="add-body px-4 py-4">
          <RepoOnboardBulkTab
            v-if="tab === TAB_BULK"
            @onboarded="onBulkOnboarded"
          />
          <RepoLocalPickForm
            v-else-if="canPickLocal && tab === TAB_LOCAL"
            :imp="imp"
          />
          <RepoCloneForm v-else ref="cloneFormRef" :imp="imp" />
        </div>

        <footer v-if="tab !== TAB_BULK" class="add-foot px-4 py-3">
          <v-checkbox
            v-model="submitter.scanAfterAdd.value"
            label="Scan after adding"
            density="compact"
            hide-details
            class="add-scan-toggle"
            color="primary"
          />
          <v-spacer />
          <span class="text-caption text-medium-emphasis">{{ footHint }}</span>
          <v-btn
            variant="text"
            class="text-none"
            :disabled="imp.running.value"
            @click="close"
          >
            Cancel
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            class="text-none"
            :disabled="!canSubmit"
            :loading="imp.running.value"
            @click="onSubmit"
          >
            {{ submitLabel }}
          </v-btn>
        </footer>
      </template>

      <div v-else class="pa-4">
        <v-skeleton-loader type="list-item-three-line" />
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import RepoLocalPickForm from './RepoLocalPickForm.vue'
import RepoCloneForm from './RepoCloneForm.vue'
import RepoOnboardBulkTab from './onboard/RepoOnboardBulkTab.vue'
import { useAddRepoSubmit } from '@/composables/useAddRepoSubmit'
import { useDeploymentMode } from '@/composables/useDeploymentMode'
import { useRepoImport } from '@/composables/useRepoImport'
import { useSettingsStore } from '@/stores/settings'
import type { useRepoBranches } from '@/composables/useRepoBranches'
import type { BulkOnboardJobTerminalResult } from '@/types/repoOnboard'

const TAB_LOCAL = 'local'
const TAB_CLONE = 'clone'
const TAB_BULK = 'bulk'
type AddTab = typeof TAB_LOCAL | typeof TAB_CLONE | typeof TAB_BULK

// Bulk import requires a live org+JWT (Settings → Code path). Hidden during first-time setup.
const props = withDefaults(defineProps<{
  modelValue: boolean
  /** Page-level branch composable, forwarded so the post-clone
   *  walkthrough drives the same dialog instance the page already
   *  hosts — avoids a second RepoBranchMappingDialog under this dialog. */
  branches: ReturnType<typeof useRepoBranches>
  /** Surface mode — "setup" hides the Bulk Import tab (no live org yet). */
  mode?: 'setup' | 'settings'
}>(), { mode: 'settings' })

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const imp = useRepoImport()
const submitter = useAddRepoSubmit()
const { mode: deploymentMode } = useDeploymentMode()
const settingsStore = useSettingsStore()
const cloneFormRef = ref<InstanceType<typeof RepoCloneForm> | null>(null)

const modeReady = computed(() => deploymentMode.value !== null)
const canPickLocal = computed(() => deploymentMode.value === 'host')
const tab = ref<AddTab>(TAB_CLONE)

watch(modeReady, (ready) => {
  if (!ready) return
  tab.value = canPickLocal.value ? TAB_LOCAL : TAB_CLONE
}, { immediate: true })

async function onBulkOnboarded(_result: BulkOnboardJobTerminalResult): Promise<void> {
  // Bulk onboard runs the full clone+scan path server-side. Once it
  // terminates we close the dialog and refresh the repo list to surface
  // the newly tracked repos.
  emit('update:modelValue', false)
  await settingsStore.fetchConnections()
}

// Pending counts feed both the footer hint + the submit label so we
// don't recompute the same logic in two places.
const pendingLocal = computed(() =>
  imp.localPaths.value.filter(i => i.status === 'pending' || i.status === 'error').length,
)
const pendingClone = computed(() =>
  imp.cloneItems.value.filter(i => i.status === 'pending' || i.status === 'error').length,
)

const httpsCloneNeedsPat = computed(() => {
  if (!imp.usePrivateAuth.value) return false
  const hasHttps = imp.cloneItems.value.some(
    i => (i.status === 'pending' || i.status === 'error') && !imp.isSshUrl(i.source),
  )
  return hasHttps && !imp.sharedPat.value.trim()
})

const canSubmit = computed(() => {
  if (imp.running.value) return false
  if (tab.value === TAB_LOCAL) return pendingLocal.value > 0
  if (tab.value === TAB_CLONE) return pendingClone.value > 0 && !httpsCloneNeedsPat.value
  return false
})

const submitLabel = computed(() => {
  if (imp.running.value) return tab.value === TAB_LOCAL ? 'Adding…' : 'Cloning…'
  const n = tab.value === TAB_LOCAL ? pendingLocal.value : pendingClone.value
  const verb = tab.value === TAB_LOCAL ? 'Add' : 'Clone'
  if (n === 0) return `${verb} repositories`
  return n === 1 ? `${verb} 1 repository` : `${verb} ${n} repositories`
})

const footHint = computed(() => {
  if (tab.value === TAB_LOCAL) {
    if (pendingLocal.value === 0) return 'Pick folders to stage them.'
    return `${pendingLocal.value} ready to add`
  }
  if (httpsCloneNeedsPat.value) return 'Private repos need a token.'
  if (pendingClone.value === 0) return 'Paste a URL to queue it.'
  return `${pendingClone.value} ready to clone`
})

function close(): void {
  if (imp.running.value) return
  emit('update:modelValue', false)
}

async function onSubmit(): Promise<void> {
  if (tab.value !== TAB_LOCAL && tab.value !== TAB_CLONE) return
  if (tab.value === TAB_CLONE) {
    cloneFormRef.value?.flushPendingInput()
  }
  const { allDone, newlyAdded } = await submitter.submit(tab.value, imp)
  if (!allDone) {
    // Partial failure — keep the dialog open so the user can retry just
    // the errored rows. The walkthrough/scan only fires on a clean run.
    return
  }
  emit('update:modelValue', false)
  if (newlyAdded.length > 0) {
    await submitter.afterDialogClose(newlyAdded, props.branches)
  }
}
</script>

<style scoped>
.add-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.add-head {
  display: flex;
  align-items: center;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.add-tabs {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.add-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 0;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  opacity: 0.7;
  font-size: 13px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: opacity 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}

.add-tab:hover {
  opacity: 1;
}

.add-tab.is-active {
  opacity: 1;
  color: rgb(var(--v-theme-primary));
  border-bottom-color: rgb(var(--v-theme-primary));
}

.add-body {
  max-height: min(60vh, 480px);
  overflow-y: auto;
}

.add-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.add-scan-toggle {
  /* v-checkbox claims full width by default; keep it just wide enough
     for "Scan after adding" so the cancel/submit buttons stay right-
     aligned in the footer. */
  flex: 0 0 auto;
  margin-top: 0;
}

.add-scan-toggle :deep(.v-selection-control) {
  min-height: 28px;
}
</style>
