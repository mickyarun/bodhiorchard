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
  /settings/code — page shell. The unified Repositories card (RepoList)
  owns add/scan/timeline in one section: progress is rendered inline
  per row + a single cross-repo finalization strip, replacing the old
  separate ScanTimelineSection card. The page only hosts the card and
  the branch-mapping dialog.
-->
<template>
  <AppPage
    title="Code"
    subtitle="Connect repositories so Glideship can scan, embed, and synthesize features across them."
  >
    <AppCallout v-if="settingsStore.error" variant="error" class="mb-4">
      {{ settingsStore.error }}
      <template #actions>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Dismiss" @click="settingsStore.error = null" />
      </template>
    </AppCallout>
    <div>
      <div v-if="settingsStore.reposLoading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <RepoList
        v-else
        :repos="settingsStore.repos"
        :branches="branches"
        @edit-branches="onEditBranches"
      />

      <SettingsScanTuning />

      <DangerZone />
    </div>

    <RepoBranchMappingDialog
      :branches="branches"
      @close="branches.close"
      @saved="branchSavedSnackbar = true"
    />

    <v-snackbar
      v-model="branchSavedSnackbar"
      color="success"
      timeout="2500"
      location="bottom right"
    >
      Branch mapping saved.
    </v-snackbar>
  </AppPage>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import { onMounted, onUnmounted, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useReposcanV2ScansStore } from '@/stores/reposcanv2Scans'
import { useDeploymentMode } from '@/composables/useDeploymentMode'
import { useRepoBranches } from '@/composables/useRepoBranches'
import RepoList from '@/components/settings/code/RepoList.vue'
import RepoBranchMappingDialog from '@/components/settings/code/RepoBranchMappingDialog.vue'
import DangerZone from '@/components/settings/code/DangerZone.vue'
import SettingsScanTuning from './SettingsScanTuning.vue'
import type { RepoInfo } from '@/types'

const settingsStore = useSettingsStore()
const scanStore = useReposcanV2ScansStore()
const { loadMode, loadDeployKey } = useDeploymentMode()
const branches = useRepoBranches()
const branchSavedSnackbar = ref(false)

// Idempotent session-level lookups in parallel with the repo fetch.
// fetchConnections() pulls budStages.uatEnabled (rows + dialog hide UAT
// when disabled). The scan store rehydrates any in-flight scan id from
// localStorage so a refresh mid-scan lands back on the same timeline.
onMounted(() => {
  void settingsStore.fetchRepos()
  void settingsStore.fetchConnections()
  void loadMode()
  void loadDeployKey()
  void scanStore.restoreActiveScan()
})

// Pause polling — but keep state — when navigating away. The next mount
// resumes via restoreActiveScan().
onUnmounted(() => {
  scanStore.pausePolling()
})

function onEditBranches(repo: RepoInfo): void {
  void branches.open(repo)
}
</script>

