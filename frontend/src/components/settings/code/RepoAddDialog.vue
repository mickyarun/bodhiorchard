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
          v-if="mode"
          :color="mode === 'docker' ? 'info' : 'success'"
          variant="tonal"
          size="x-small"
          class="ml-2"
          :prepend-icon="mode === 'docker' ? 'mdi-docker' : 'mdi-laptop'"
        >
          {{ mode === 'docker' ? 'Full Docker' : 'Hybrid' }}
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
            :class="{ 'is-active': tab === 'local' }"
            @click="tab = 'local'"
          >
            <v-icon icon="mdi-folder-open-outline" size="16" />
            <span>Local folder</span>
          </button>
          <button
            type="button"
            class="add-tab"
            :class="{ 'is-active': tab === 'clone' }"
            @click="tab = 'clone'"
          >
            <v-icon icon="mdi-github" size="16" />
            <span>GitHub clone</span>
          </button>
        </div>

        <div class="add-body px-4 py-4">
          <RepoLocalPickForm
            v-if="canPickLocal && tab === 'local'"
            :imp="imp"
          />
          <RepoCloneForm v-else ref="cloneFormRef" :imp="imp" />
        </div>

        <footer class="add-foot px-4 py-3">
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
import { useAddRepoSubmit } from '@/composables/useAddRepoSubmit'
import { useDeploymentMode } from '@/composables/useDeploymentMode'
import { useRepoImport } from '@/composables/useRepoImport'
import type { useRepoBranches } from '@/composables/useRepoBranches'

const props = defineProps<{
  modelValue: boolean
  /** Page-level branch composable, forwarded so the post-clone
   *  walkthrough drives the same dialog instance the page already
   *  hosts — avoids a second RepoBranchMappingDialog under this dialog. */
  branches: ReturnType<typeof useRepoBranches>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const imp = useRepoImport()
const submitter = useAddRepoSubmit()
const { mode } = useDeploymentMode()
const cloneFormRef = ref<InstanceType<typeof RepoCloneForm> | null>(null)

const modeReady = computed(() => mode.value !== null)
const canPickLocal = computed(() => mode.value === 'host')
const tab = ref<'local' | 'clone'>('clone')

watch(modeReady, (ready) => {
  if (!ready) return
  tab.value = canPickLocal.value ? 'local' : 'clone'
}, { immediate: true })

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
  if (tab.value === 'local') return pendingLocal.value > 0
  return pendingClone.value > 0 && !httpsCloneNeedsPat.value
})

const submitLabel = computed(() => {
  if (imp.running.value) return tab.value === 'local' ? 'Adding…' : 'Cloning…'
  const n = tab.value === 'local' ? pendingLocal.value : pendingClone.value
  const verb = tab.value === 'local' ? 'Add' : 'Clone'
  if (n === 0) return `${verb} repositories`
  return n === 1 ? `${verb} 1 repository` : `${verb} ${n} repositories`
})

const footHint = computed(() => {
  if (tab.value === 'local') {
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
  if (tab.value === 'clone') {
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
