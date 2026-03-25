<template>
  <v-card class="pa-5 settings-card mb-6" color="surface">
    <!-- Scan controls + stats header -->
    <div class="d-flex align-center justify-space-between flex-wrap ga-3 mb-4">
      <div class="d-flex align-center ga-3">
        <v-avatar size="36" color="primary" variant="tonal" rounded="lg">
          <v-icon icon="mdi-magnify-scan" size="22" />
        </v-avatar>
        <div>
          <div class="text-body-2 font-weight-medium">Code Index</div>
          <div class="text-caption text-medium-emphasis">
            Scan repositories to index features and skill profiles
          </div>
        </div>
      </div>
      <div class="d-flex align-center ga-2">
        <v-tooltip content-class="scan-tooltip" location="bottom" max-width="280">
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              color="primary"
              variant="tonal"
              prepend-icon="mdi-magnify-scan"
              :loading="scanStatus === 'running'"
              :disabled="settingsStore.repos.length === 0 || !settingsStore.allReposMapped"
              @click="confirmAndScan(false)"
            >
              Scan
            </v-btn>
          </template>
          Incremental scan — only indexes changes since the last scan. Fast and safe; existing items are kept.
        </v-tooltip>
        <v-tooltip content-class="scan-tooltip" location="bottom" max-width="280">
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              v-if="scanStatus !== 'running'"
              variant="outlined"
              size="small"
              prepend-icon="mdi-refresh"
              :disabled="settingsStore.repos.length === 0 || !settingsStore.allReposMapped"
              @click="confirmAndScan(true)"
            >
              Full Rescan
            </v-btn>
          </template>
          Rebuilds the entire index from scratch. Use when the index seems out of sync or after major refactors.
        </v-tooltip>
      </div>
    </div>

    <!-- Index stats -->
    <v-expand-transition>
      <div v-if="indexStats && indexStats.knowledgeItems.total > 0" class="mb-4">
        <div class="d-flex align-center ga-2 mb-3">
          <v-icon icon="mdi-database-check-outline" size="16" color="success" />
          <span class="text-body-2 font-weight-medium">Indexed</span>
          <v-chip v-if="indexStats.lastScan" size="x-small" variant="tonal" color="grey">
            {{ formatRelativeTime(indexStats.lastScan.completed_at) }}
          </v-chip>
        </div>
        <div class="d-flex flex-wrap ga-3">
          <div class="index-stat">
            <div class="text-h6 font-weight-bold">{{ indexStats.knowledgeItems.byCategory.feature_registry || 0 }}</div>
            <div class="text-caption text-medium-emphasis">Features</div>
          </div>
          <div class="index-stat">
            <div class="text-h6 font-weight-bold">{{ indexStats.knowledgeItems.embedded }}</div>
            <div class="text-caption text-medium-emphasis">Embedded</div>
          </div>
          <div class="index-stat">
            <div class="text-h6 font-weight-bold">{{ indexStats.skillProfiles }}</div>
            <div class="text-caption text-medium-emphasis">Profiles</div>
          </div>
          <div class="index-stat">
            <div class="text-h6 font-weight-bold">{{ settingsStore.repos.length }}</div>
            <div class="text-caption text-medium-emphasis">Repos</div>
          </div>
        </div>
      </div>
    </v-expand-transition>

    <!-- Scan progress / results -->
    <v-expand-transition>
      <div v-if="scanStatus === 'running' && scanProgress > 0" class="mb-4">
        <v-progress-linear
          :model-value="scanProgress"
          color="primary"
          class="mb-2"
          rounded
          height="6"
        />
        <div class="d-flex align-center ga-2">
          <div class="text-caption text-medium-emphasis">
            {{ scanStatusLabel }}... {{ scanProgress }}%
          </div>
          <v-btn
            variant="text"
            density="compact"
            size="x-small"
            icon="mdi-refresh"
            @click="refreshScanStatus"
          />
        </div>
      </div>
    </v-expand-transition>

    <v-expand-transition>
      <v-alert
        v-if="isLocked"
        type="info"
        variant="tonal"
        density="compact"
        icon="mdi-lock-outline"
        class="mb-4"
      >
        Repo editing is disabled while a scan is running.
      </v-alert>
    </v-expand-transition>

    <v-expand-transition>
      <v-alert
        v-if="scanStatus === 'completed'"
        type="success"
        variant="tonal"
        density="compact"
        class="mb-4"
      >
        <span class="font-weight-medium">
          {{ scanResult.scanMode === 'incremental' ? 'Incremental scan' : 'Full scan' }} complete:
        </span>
        {{ scanResult.featuresIndexed }} features indexed,
        {{ scanResult.profilesFound }} skill profiles found.
        <template v-if="scanResult.staleCleaned > 0">
          {{ scanResult.staleCleaned }} stale references cleaned.
        </template>
        <template v-if="scanResult.unmatchedAuthors.length > 0">
          <br>Unmatched git authors: {{ scanResult.unmatchedAuthors.join(', ') }}
        </template>
      </v-alert>
    </v-expand-transition>

    <v-expand-transition>
      <v-alert
        v-if="scanStatus === 'completed' && scanResult.synthesisWarning"
        type="warning"
        variant="tonal"
        density="compact"
        class="mb-4"
      >
        {{ scanResult.synthesisWarning }}
      </v-alert>
    </v-expand-transition>

    <v-expand-transition>
      <v-alert
        v-if="scanStatus === 'failed'"
        type="error"
        variant="tonal"
        density="compact"
        class="mb-4"
      >
        Scan failed: {{ scanError }}
      </v-alert>
    </v-expand-transition>

    <!-- Repository table -->
    <div class="pt-4" style="border-top: 1px solid rgba(255,255,255,0.06)">
      <div v-if="settingsStore.reposLoading" class="d-flex justify-center py-4">
        <v-progress-circular indeterminate size="24" />
      </div>

      <template v-else>
        <!-- Branch mapping warning -->
        <v-alert
          v-if="settingsStore.repos.length > 0 && !settingsStore.allReposMapped"
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          Map main and develop branches for all active repos before scanning.
        </v-alert>

        <v-table v-if="settingsStore.repos.length > 0" density="compact" class="mb-4">
          <thead>
            <tr>
              <th>Repository</th>
              <th>Path</th>
              <th class="text-center">Status</th>
              <th class="text-center">Main Branch</th>
              <th class="text-center">Dev Branch</th>
              <th class="text-center">Knowledge</th>
              <th class="text-center">Features</th>
              <th class="text-center">Last SHA</th>
              <th style="width: 100px;"></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="repo in settingsStore.repos"
              :key="repo.id"
              :class="{ 'opacity-50': repo.status === 'ignored' }"
            >
              <td class="font-weight-medium">
                {{ repo.name }}
                <v-tooltip v-if="repo.hasUncommittedChanges" text="Uncommitted changes detected" location="top">
                  <template #activator="{ props }">
                    <v-icon v-bind="props" icon="mdi-alert-circle-outline" size="14" color="warning" class="ml-1" />
                  </template>
                </v-tooltip>
              </td>
              <td class="text-caption text-medium-emphasis">{{ repo.path }}</td>
              <td class="text-center">
                <v-chip
                  :color="repo.status === 'active' ? 'success' : 'warning'"
                  size="x-small"
                  variant="tonal"
                >
                  {{ repo.status }}
                </v-chip>
              </td>
              <td class="text-center">
                <v-chip
                  v-if="repo.mainBranch"
                  size="x-small"
                  variant="tonal"
                  color="success"
                  prepend-icon="mdi-source-branch"
                  style="cursor: pointer"
                  @click="openBranchDialog(repo)"
                >
                  {{ repo.mainBranch }}
                </v-chip>
                <v-chip
                  v-else
                  size="x-small"
                  variant="tonal"
                  color="warning"
                  style="cursor: pointer"
                  @click="openBranchDialog(repo)"
                >
                  Not mapped
                </v-chip>
              </td>
              <td class="text-center">
                <v-chip
                  v-if="repo.developBranch"
                  size="x-small"
                  variant="tonal"
                  color="success"
                  prepend-icon="mdi-source-branch"
                  style="cursor: pointer"
                  @click="openBranchDialog(repo)"
                >
                  {{ repo.developBranch }}
                </v-chip>
                <v-chip
                  v-else
                  size="x-small"
                  variant="tonal"
                  color="warning"
                  style="cursor: pointer"
                  @click="openBranchDialog(repo)"
                >
                  Not mapped
                </v-chip>
              </td>
              <td class="text-center">{{ repo.knowledgeCount }}</td>
              <td class="text-center">{{ repo.featureCount }}</td>
              <td class="text-center">
                <v-chip v-if="repo.sha" size="x-small" variant="tonal">
                  {{ repo.sha?.substring(0, 7) }}
                </v-chip>
                <span v-else class="text-caption text-medium-emphasis">-</span>
              </td>
              <td class="text-right">
                <v-tooltip
                  :text="repo.status === 'active' ? 'Ignore (skip in scans)' : 'Activate'"
                  location="top"
                  content-class="text-white bg-grey-darken-3"
                >
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      :icon="repo.status === 'active' ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
                      size="x-small"
                      variant="text"
                      :color="repo.status === 'active' ? 'warning' : 'success'"
                      :disabled="isLocked"
                      @click="settingsStore.setRepoStatus(repo.id, repo.status === 'active' ? 'ignored' : 'active')"
                    />
                  </template>
                </v-tooltip>
                <v-tooltip text="Remove" location="top" content-class="text-white bg-grey-darken-3">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-close"
                      size="x-small"
                      variant="text"
                      color="error"
                      :disabled="isLocked"
                      @click="settingsStore.removeRepo(repo.path)"
                    />
                  </template>
                </v-tooltip>
              </td>
            </tr>
          </tbody>
        </v-table>

        <div
          v-else
          class="text-body-2 text-medium-emphasis text-center py-6"
        >
          <v-icon icon="mdi-source-repository" size="40" class="mb-2 d-block mx-auto" />
          No repositories added yet. Add a repository to start indexing.
        </div>

        <v-btn
          variant="tonal"
          size="small"
          prepend-icon="mdi-plus"
          :disabled="isLocked"
          @click="showAddRepoDialog = true"
        >
          Add Repository
        </v-btn>
      </template>
    </div>

    <!-- Scan Settings -->
    <div class="mt-4 pt-4" style="border-top: 1px solid rgba(255,255,255,0.06)">
      <div class="d-flex align-center ga-2 mb-3">
        <v-icon icon="mdi-tune-vertical" size="16" color="primary" />
        <span class="text-body-2 font-weight-medium">Scan Settings</span>
      </div>
      <v-row dense>
        <v-col cols="12" sm="6">
          <v-text-field
            v-model.number="settingsStore.connections.scan.timeoutSeconds"
            label="Timeout (seconds)"
            type="number"
            :min="60"
            :max="1800"
            density="compact"
            variant="outlined"
          >
            <template #append-inner>
              <v-tooltip content-class="scan-tooltip" location="top" max-width="280">
                <template #activator="{ props }">
                  <v-icon v-bind="props" icon="mdi-help-circle-outline" size="18" color="grey" />
                </template>
                How long the scan can run before it stops. Large repos with many features
                may need more time. Default: 300s (5 min). Try 600s if scans time out.
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
        <v-col cols="12" sm="6">
          <v-select
            v-model="settingsStore.connections.scan.maxTurns"
            :items="maxTurnsOptions"
            label="Max AI steps"
            density="compact"
            variant="outlined"
          >
            <template #append-inner>
              <v-tooltip content-class="scan-tooltip" location="top" max-width="280">
                <template #activator="{ props }">
                  <v-icon v-bind="props" icon="mdi-help-circle-outline" size="18" color="grey" />
                </template>
                Number of actions the AI can take per repo (read files, write feature
                descriptions, etc.). More steps = more features described but takes longer.
              </v-tooltip>
            </template>
          </v-select>
        </v-col>
      </v-row>
      <v-switch
        v-model="settingsStore.connections.scan.autoCreateMembers"
        label="Auto-create members from git authors"
        color="primary"
        density="compact"
        hide-details
        class="mt-1"
      >
        <template #append>
          <v-tooltip content-class="scan-tooltip" location="top" max-width="280">
            <template #activator="{ props }">
              <v-icon v-bind="props" icon="mdi-help-circle-outline" size="18" color="grey" />
            </template>
            When enabled, scanning a repo will automatically create org members from
            git commit authors (email + name). They get a default password and can be
            deactivated later from the Members page.
          </v-tooltip>
        </template>
      </v-switch>
    </div>
  </v-card>

  <!-- Rescan confirmation dialog -->
  <v-dialog v-model="showRescanDialog" max-width="420">
    <v-card>
      <v-card-title class="text-body-1 font-weight-bold pa-4 pb-2">
        {{ pendingFullRescan ? 'Full Rescan' : 'Re-scan Repository' }}?
      </v-card-title>
      <v-card-text class="text-body-2 pb-2">
        <template v-if="pendingFullRescan">
          This will rebuild the entire index from scratch. Existing knowledge items will be replaced.
        </template>
        <template v-else>
          This will scan for changes since the last index. Unchanged items are kept.
        </template>
        <v-alert
          type="warning"
          variant="tonal"
          density="compact"
          icon="mdi-source-branch-sync"
          class="mt-3"
        >
          Scanning will temporarily stash uncommitted changes. Commit your work first.
        </v-alert>
        <div v-if="indexStats && indexStats.knowledgeItems.total > 0" class="mt-2 text-caption text-medium-emphasis">
          Current index: {{ indexStats.knowledgeItems.total }} knowledge items,
          {{ indexStats.skillProfiles }} skill profiles.
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-2">
        <v-spacer />
        <v-btn variant="text" @click="showRescanDialog = false">Cancel</v-btn>
        <v-btn color="primary" variant="tonal" @click="proceedWithScan">
          {{ pendingFullRescan ? 'Full Rescan' : 'Scan' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Add Repo Dialog -->
  <v-dialog v-model="showAddRepoDialog" max-width="520">
    <v-card color="surface" class="pa-6">
      <div class="text-h6 font-weight-bold mb-4">Add Repositories</div>

      <!-- Selected paths list -->
      <div v-if="newRepoPaths.length" class="mb-3">
        <v-chip
          v-for="(p, idx) in newRepoPaths"
          :key="p"
          closable
          variant="tonal"
          size="small"
          class="ma-1"
          @click:close="newRepoPaths.splice(idx, 1)"
        >
          <v-icon icon="mdi-source-repository" size="14" start />
          {{ p.split('/').pop() }}
          <v-tooltip activator="parent" location="top" :text="p" />
        </v-chip>
      </div>

      <!-- Path input + browse -->
      <v-text-field
        v-model="newRepoPath"
        label="Absolute path to git repository"
        placeholder="/path/to/repo"
        variant="outlined"
        density="compact"
        hint="Add multiple repos — type or browse, then press Enter or click +"
        persistent-hint
        @keyup.enter="addPathToList"
      >
        <template #prepend-inner>
          <v-icon icon="mdi-folder-outline" size="20" class="text-medium-emphasis me-1" />
        </template>
        <template #append-inner>
          <v-btn
            icon="mdi-plus"
            size="small"
            variant="text"
            density="compact"
            :disabled="!newRepoPath.trim()"
            @click="addPathToList"
          />
          <v-btn
            icon="mdi-folder-search-outline"
            size="small"
            variant="text"
            density="compact"
            @click="directoryPicker?.open()"
          />
        </template>
      </v-text-field>
      <v-alert
        type="warning"
        variant="tonal"
        density="compact"
        icon="mdi-source-branch-sync"
        class="mt-3"
      >
        Scanning will temporarily stash uncommitted changes and checkout the main branch.
        <strong>Commit or back up your work</strong> before scanning.
      </v-alert>
      <v-checkbox
        v-model="scanAfterAdd"
        label="Scan after adding"
        density="compact"
        hide-details
        class="mt-2"
      />
      <v-card-actions class="pa-0 mt-3">
        <v-spacer />
        <v-btn variant="text" @click="showAddRepoDialog = false">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="newRepoPaths.length === 0 && !newRepoPath.trim()"
          @click="addReposAndScan"
        >
          Add {{ newRepoPaths.length > 1 ? `(${newRepoPaths.length})` : '' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Branch Mapping Dialog -->
  <v-dialog v-model="showBranchDialog" max-width="480">
    <v-card color="surface" class="pa-6">
      <div class="text-h6 font-weight-bold mb-1">Branch Mapping</div>
      <div class="text-body-2 text-medium-emphasis mb-4">
        {{ branchDialogRepo?.name }}
      </div>

      <div v-if="branchesLoading" class="d-flex justify-center py-6">
        <v-progress-circular indeterminate size="24" />
      </div>

      <template v-else>
        <v-select
          v-model="branchDialogMain"
          :items="branchDialogBranches"
          label="Main Branch *"
          variant="outlined"
          density="compact"
          prepend-inner-icon="mdi-source-branch"
          class="mb-3"
          :rules="[v => !!v || 'Required']"
        />
        <v-select
          v-model="branchDialogDev"
          :items="branchDialogBranches"
          label="Develop Branch *"
          variant="outlined"
          density="compact"
          prepend-inner-icon="mdi-source-branch"
          :rules="[v => !!v || 'Required']"
        />
      </template>

      <v-card-actions class="pa-0 mt-4">
        <v-spacer />
        <v-btn variant="text" @click="showBranchDialog = false">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="!branchDialogMain || !branchDialogDev"
          :loading="branchSaving"
          @click="saveBranchMapping"
        >
          Save
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Directory Picker (reusable component, multi-select mode) -->
  <DirectoryPicker
    ref="directoryPicker"
    :initial-path="newRepoPath || undefined"
    multi-select
    @select="onDirectorySelected"
    @select-multiple="onMultipleDirectoriesSelected"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import DirectoryPicker from '@/components/setup/DirectoryPicker.vue'
import api from '@/services/api'
import type { RepoInfo } from '@/types'

const settingsStore = useSettingsStore()

// Disable repo editing while a scan is running
const isLocked = computed(() => scanStatus.value === 'running')

// Scan state
const scanStatus = ref<'idle' | 'running' | 'completed' | 'failed'>('idle')
const scanProgress = ref(0)
const scanStatusLabel = ref('')
const scanError = ref('')
const scanResult = ref({
  scanMode: 'full',
  featuresIndexed: 0,
  featuresSkipped: 0,
  profilesFound: 0,
  staleCleaned: 0,
  unmatchedAuthors: [] as string[],
  synthesisWarning: '' as string,
})
let scanPollInterval: ReturnType<typeof setInterval> | null = null
let currentScanId = ''

// Index stats
const indexStats = ref<{
  lastScan: { completed_at: string; repos_scanned: number; features_indexed: number; profiles_found: number } | null
  knowledgeItems: { total: number; byCategory: Record<string, number>; embedded: number }
  skillProfiles: number
  reposTracked: number
} | null>(null)

// Repo management
const showAddRepoDialog = ref(false)
const newRepoPath = ref('')
const newRepoPaths = ref<string[]>([])
const scanAfterAdd = ref(true)
const directoryPicker = ref<InstanceType<typeof DirectoryPicker> | null>(null)

// Branch mapping dialog
const showBranchDialog = ref(false)
const branchDialogRepo = ref<RepoInfo | null>(null)
const branchDialogBranches = ref<string[]>([])
const branchDialogMain = ref<string | null>(null)
const branchDialogDev = ref<string | null>(null)
const branchesLoading = ref(false)
const branchSaving = ref(false)

// Rescan confirmation
const showRescanDialog = ref(false)
const pendingFullRescan = ref(false)

const maxTurnsOptions = [
  { title: '20 steps', value: 20 },
  { title: '40 steps (default)', value: 40 },
  { title: '60 steps', value: 60 },
  { title: '80 steps', value: 80 },
  { title: '100 steps', value: 100 },
  { title: 'Unlimited', value: 0 },
]

onMounted(async () => {
  fetchIndexStats()
  settingsStore.fetchRepos()

  // If a scan was auto-triggered from setup, resume polling
  const setupScanId = localStorage.getItem('flowdev_scan_id')
  if (setupScanId && scanStatus.value === 'idle') {
    currentScanId = setupScanId
    scanStatus.value = 'running'
    scanStatusLabel.value = 'Scanning'
    startPolling()
  }
})

onUnmounted(() => {
  if (scanPollInterval) {
    clearInterval(scanPollInterval)
    scanPollInterval = null
  }
})

function onDirectorySelected(path: string) {
  if (path && !newRepoPaths.value.includes(path)) {
    newRepoPaths.value.push(path)
  }
}

function onMultipleDirectoriesSelected(paths: string[]) {
  for (const p of paths) {
    if (!newRepoPaths.value.includes(p)) {
      newRepoPaths.value.push(p)
    }
  }
}

function addPathToList(): void {
  const p = newRepoPath.value.trim()
  if (p && !newRepoPaths.value.includes(p)) {
    newRepoPaths.value.push(p)
  }
  newRepoPath.value = ''
}

async function addReposAndScan(): Promise<void> {
  addPathToList()
  if (newRepoPaths.value.length === 0) return

  let anyOk = false
  for (const p of newRepoPaths.value) {
    const ok = await settingsStore.addRepo(p)
    if (ok) anyOk = true
  }
  if (anyOk) {
    showAddRepoDialog.value = false
    newRepoPaths.value = []
    newRepoPath.value = ''
    if (scanAfterAdd.value) {
      triggerScan(false)
    }
  }
}

async function openBranchDialog(repo: RepoInfo): Promise<void> {
  branchDialogRepo.value = repo
  branchDialogMain.value = repo.mainBranch
  branchDialogDev.value = repo.developBranch
  branchDialogBranches.value = []
  showBranchDialog.value = true
  branchesLoading.value = true

  const data = await settingsStore.fetchRepoBranches(repo.id)
  if (data) {
    branchDialogBranches.value = data.branches
    if (!branchDialogMain.value && data.currentMain) {
      branchDialogMain.value = data.currentMain
    }
    if (!branchDialogDev.value && data.currentDevelop) {
      branchDialogDev.value = data.currentDevelop
    }
  }
  branchesLoading.value = false
}

async function saveBranchMapping(): Promise<void> {
  if (!branchDialogRepo.value) return
  branchSaving.value = true
  await settingsStore.updateRepoBranches(
    branchDialogRepo.value.id,
    branchDialogMain.value,
    branchDialogDev.value,
  )
  branchSaving.value = false
  showBranchDialog.value = false
}

function confirmAndScan(fullRescan: boolean): void {
  if (!indexStats.value || indexStats.value.knowledgeItems.total === 0) {
    triggerScan(fullRescan)
    return
  }
  pendingFullRescan.value = fullRescan
  showRescanDialog.value = true
}

function proceedWithScan(): void {
  showRescanDialog.value = false
  triggerScan(pendingFullRescan.value)
}

function formatRelativeTime(isoDate: string): string {
  const now = Date.now()
  const then = new Date(isoDate).getTime()
  const diffMs = now - then
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  return `${diffDay}d ago`
}

async function fetchIndexStats(): Promise<void> {
  try {
    const { data } = await api.get('/v1/skills/index-stats')
    indexStats.value = data
  } catch {
    // Non-critical
  }
}

async function triggerScan(fullRescan: boolean = false): Promise<void> {
  scanStatus.value = 'running'
  scanProgress.value = 0
  scanStatusLabel.value = 'Saving path...'
  scanError.value = ''

  try {
    await api.patch('/v1/settings/connections', {
      sourceCode: {
        localPath: settingsStore.connections.sourceCode.localPath,
        type: settingsStore.connections.sourceCode.type,
      },
    })
  } catch {
    scanStatus.value = 'failed'
    scanError.value = 'Failed to save source code path. Please try saving settings first.'
    return
  }

  try {
    scanStatusLabel.value = 'Starting'
    const { data } = await api.post('/v1/skills/scan', { fullRescan: Boolean(fullRescan) })
    currentScanId = data.scanId
    startPolling()
  } catch (err: unknown) {
    scanStatus.value = 'failed'
    const axiosErr = err as { response?: { data?: { detail?: string } } }
    scanError.value = axiosErr?.response?.data?.detail || 'Failed to start scan.'
  }
}

function startPolling(): void {
  if (scanPollInterval) clearInterval(scanPollInterval)

  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }

  scanPollInterval = setInterval(async () => {
    try {
      const { data } = await api.get(`/v1/skills/scan/${currentScanId}/status`)
      scanProgress.value = data.progressPct || 0
      scanStatusLabel.value = formatStatusLabel(data.status)

      if (data.status === 'completed') {
        scanStatus.value = 'completed'
        scanResult.value = {
          scanMode: data.scanMode || 'full',
          featuresIndexed: data.featuresIndexed || 0,
          featuresSkipped: data.featuresSkipped || 0,
          profilesFound: data.profilesFound || 0,
          staleCleaned: data.staleCleaned || 0,
          unmatchedAuthors: data.unmatchedAuthors || [],
          synthesisWarning: data.synthesisWarning || '',
        }
        localStorage.removeItem('flowdev_scan_id')
        stopPolling()
        fetchIndexStats()
        notifyScanDone(true, data.featuresIndexed || 0, data.profilesFound || 0)
      } else if (data.status === 'failed') {
        scanStatus.value = 'failed'
        scanError.value = data.error || 'Scan failed.'
        localStorage.removeItem('flowdev_scan_id')
        stopPolling()
        notifyScanDone(false)
      }
    } catch {
      scanStatus.value = 'failed'
      scanError.value = 'Lost connection while polling scan status.'
      stopPolling()
    }
  }, 2000)
}

function notifyScanDone(success: boolean, features = 0, profiles = 0): void {
  if (!('Notification' in window) || Notification.permission !== 'granted') return

  const title = success ? 'Repository Scan Complete' : 'Repository Scan Failed'
  const body = success
    ? `${features} features indexed, ${profiles} skill profiles found.`
    : scanError.value || 'An error occurred during scanning.'

  new Notification(title, { body, icon: '/favicon.ico' })
}

async function refreshScanStatus(): Promise<void> {
  if (!currentScanId) return
  try {
    const { data } = await api.get(`/v1/skills/scan/${currentScanId}/status`)
    scanProgress.value = data.progressPct || 0
    scanStatusLabel.value = formatStatusLabel(data.status)

    if (data.status === 'completed') {
      scanStatus.value = 'completed'
      scanResult.value = {
        scanMode: data.scanMode || 'full',
        featuresIndexed: data.featuresIndexed || 0,
        featuresSkipped: data.featuresSkipped || 0,
        profilesFound: data.profilesFound || 0,
        staleCleaned: data.staleCleaned || 0,
        unmatchedAuthors: data.unmatchedAuthors || [],
        synthesisWarning: data.synthesisWarning || '',
      }
      stopPolling()
    } else if (data.status === 'failed') {
      scanStatus.value = 'failed'
      scanError.value = data.error || 'Scan failed.'
      stopPolling()
    }
  } catch {
    // Non-critical
  }
}

function stopPolling(): void {
  if (scanPollInterval) {
    clearInterval(scanPollInterval)
    scanPollInterval = null
  }
}

function formatStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    started: 'Starting',
    analyzing_changes: 'Analyzing changes',
    indexing: 'Indexing codebase',
    synthesizing_features: 'Synthesizing feature descriptions',
    merging_features: 'Merging cross-repo features',
    cleaning_stale: 'Cleaning stale references',
    analyzing_skills: 'Analyzing skills',
    embedding: 'Generating embeddings',
    completed: 'Complete',
    failed: 'Failed',
  }
  return labels[status] || status
}
</script>
