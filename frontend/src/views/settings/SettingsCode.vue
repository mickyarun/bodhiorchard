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
  <div class="settings-page">
    <div class="settings-header pa-6 pb-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h5 font-weight-bold">Code</div>
          <div class="text-body-2 text-medium-emphasis">
            Connect repositories so Bodhiorchard can scan, embed, and synthesize
            features across them.
          </div>
        </div>
      </div>

      <v-alert
        v-if="settingsStore.error"
        type="error"
        variant="tonal"
        class="mt-4"
        closable
        @click:close="settingsStore.error = null"
      >
        {{ settingsStore.error }}
      </v-alert>
    </div>

    <div class="settings-content px-6 pb-6">
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useReposcanV2ScansStore } from '@/stores/reposcanv2Scans'
import { useDeploymentMode } from '@/composables/useDeploymentMode'
import { useRepoBranches } from '@/composables/useRepoBranches'
import RepoList from '@/components/settings/code/RepoList.vue'
import RepoBranchMappingDialog from '@/components/settings/code/RepoBranchMappingDialog.vue'
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

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.settings-header {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.settings-content {
  overflow-y: auto;
  flex-grow: 1;
}
</style>
