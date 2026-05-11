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
  Top-level orchestrator for the new "Bulk import" tab.

  Internal state machine:
    idle    → GitHubAppConnectionCard rendered until @ready fires
    picking → installable-repo picker + branch picker + Continue button
    running → progress drawer bound to the in-flight jobId
    done    → terminal summary + "Onboard more" / "View scan" CTAs

  Phase H will mount this component into ``SourceCodeStep.vue`` and
  ``RepoAddDialog.vue`` — those wrappers are NOT touched here.
-->
<template>
  <div class="d-flex flex-column ga-4">
    <GitHubAppConnectionCard
      v-if="phase === 'idle'"
      standalone
      @ready="onAppReady"
      @status-change="onStatusChange"
    />

    <template v-if="phase === 'picking'">
      <v-alert v-if="onboard.errorMessage.value" type="error" variant="tonal" density="compact">
        {{ onboard.errorMessage.value }}
      </v-alert>
      <v-progress-linear v-if="onboard.loadingInstallable.value" indeterminate />
      <RepoOnboardPickerList
        v-else
        :repos="onboard.installable.value"
        :selection="onboard.selection.value"
        @toggle:repo="onboard.toggleSelection"
        @toggle:owner="onboard.selectAllForOwner"
      />
      <RepoOnboardBranchPicker
        :selected-repos="onboard.selectedRepos.value"
        :branches-by-repo="onboard.branchesByRepo"
        :branch-options="onboard.branchOptions"
        :loading-branches-for="onboard.loadingBranchesFor"
        @change:branch="onboard.setBranchPick"
        @request:branches="onboard.loadBranchesFor"
      />
      <div v-if="props.mode === MODE_SETTINGS" class="d-flex justify-end">
        <v-btn
          color="primary"
          size="large"
          :disabled="!onboard.canSubmit.value || onboard.submitting.value"
          :loading="onboard.submitting.value"
          @click="onSubmit"
        >
          {{ submitButtonLabel }}
        </v-btn>
      </div>
    </template>

    <RepoOnboardProgressDrawer
      v-if="phase === 'running' && jobId"
      :job-id="jobId"
      @complete="onJobComplete"
      @cancel="resetToPicking"
    />

    <v-card v-if="phase === 'done' && terminalResult" variant="outlined" class="pa-4">
      <div class="text-h6 mb-2">{{ DONE_TITLE }}</div>
      <div class="text-body-2 mb-3">
        {{ terminalResult.succeeded.length }} {{ SUCCEEDED_SUFFIX }} ·
        {{ terminalResult.failed.length }} {{ FAILED_SUFFIX }}
      </div>
      <div class="d-flex ga-2">
        <v-btn variant="text" @click="resetToPicking">{{ ONBOARD_MORE_LABEL }}</v-btn>
        <v-btn
          v-if="terminalResult.scan_id"
          color="primary"
          variant="flat"
          :to="scanLinkFor(terminalResult.scan_id)"
        >
          {{ VIEW_SCAN_LABEL }}
        </v-btn>
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import GitHubAppConnectionCard from '@/components/settings/connections/GitHubAppConnectionCard.vue'
import { GITHUB_APP_STATUS, type GitHubAppStatus } from '@/types/connections'
import { useSettingsStore } from '@/stores/settings'
import { useRepoOnboard } from '@/composables/useRepoOnboard'
import { useBulkTabSetupSync } from '@/composables/useBulkTabSetupSync'
import type { BulkOnboardJobTerminalResult } from '@/types/repoOnboard'
import RepoOnboardPickerList from './RepoOnboardPickerList.vue'
import RepoOnboardBranchPicker from './RepoOnboardBranchPicker.vue'
import RepoOnboardProgressDrawer from './RepoOnboardProgressDrawer.vue'

const MODE_SETUP = 'setup' as const
const MODE_SETTINGS = 'settings' as const
type BulkTabMode = typeof MODE_SETUP | typeof MODE_SETTINGS

const DONE_TITLE = 'Bulk onboarding complete'
const SUCCEEDED_SUFFIX = 'succeeded'
const FAILED_SUFFIX = 'failed'
const ONBOARD_MORE_LABEL = 'Onboard more'
const VIEW_SCAN_LABEL = 'View scan'
const SUBMIT_BUTTON_PREFIX = 'Clone'
const SUBMIT_BUTTON_SUFFIX = 'repositories'
// TODO(phase-H): replace with a typed router-link target once the
// scan-detail route exists. Today there is no /scans/:id route — we
// surface the scanId in copy + link to settings as a stop-gap.
const SCAN_LINK_FALLBACK = '/settings'

type Phase = 'idle' | 'picking' | 'running' | 'done'

const emit = defineEmits<{
  onboarded: [BulkOnboardJobTerminalResult]
}>()

const props = withDefaults(
  defineProps<{
    /**
     * Surface mode. ``setup`` (wizard) hides the inline submit button and
     * continuously syncs picker state into ``setupStore.state.sourceCode.repos``
     * so the wizard's Continue button drives finalize. ``settings`` (default)
     * keeps the legacy self-driven flow inside ``RepoAddDialog``.
     */
    mode?: BulkTabMode
  }>(),
  { mode: MODE_SETTINGS },
)

const phase = ref<Phase>('idle')
const jobId = ref<string | null>(null)
const terminalResult = ref<BulkOnboardJobTerminalResult | null>(null)
const onboard = useRepoOnboard()
const settingsStore = useSettingsStore()

const submitButtonLabel = computed(
  () => `${SUBMIT_BUTTON_PREFIX} ${onboard.selectionCount.value} ${SUBMIT_BUTTON_SUFFIX}`,
)

function scanLinkFor(_scanId: string): string {
  return SCAN_LINK_FALLBACK
}

async function enterPicking(): Promise<void> {
  phase.value = 'picking'
  if (onboard.installable.value.length === 0) {
    await onboard.loadInstallable()
  }
}

function onStatusChange(next: GitHubAppStatus): void {
  if (next === GITHUB_APP_STATUS.READY && phase.value === 'idle') {
    void enterPicking()
  }
}

function onAppReady(): void {
  void enterPicking()
}

async function onSubmit(): Promise<void> {
  const created = await onboard.submitBulkOnboard()
  if (!created) return
  jobId.value = created.jobId
  phase.value = 'running'
}

function onJobComplete(result: BulkOnboardJobTerminalResult): void {
  terminalResult.value = result
  phase.value = 'done'
  emit('onboarded', result)
}

function resetToPicking(): void {
  jobId.value = null
  terminalResult.value = null
  onboard.reset()
  void enterPicking()
}

useBulkTabSetupSync(onboard, () => props.mode === MODE_SETUP)

onMounted(async () => {
  // The card's @ready event fires on a status TRANSITION only — if
  // the org is already connected on mount we need to peek at the
  // settings store ourselves and skip straight to picking.
  if (!settingsStore.connections.github.status) {
    await settingsStore.fetchConnections()
  }
  if (settingsStore.connections.github.status === GITHUB_APP_STATUS.READY) {
    void enterPicking()
  }
})
</script>
