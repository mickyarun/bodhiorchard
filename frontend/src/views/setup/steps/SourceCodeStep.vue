<template>
  <div class="d-flex flex-column align-center">
    <v-icon icon="mdi-source-repository" size="48" color="primary" class="mb-4" />
    <h2 class="text-h5 font-weight-bold mb-2">Repositories</h2>
    <p class="text-body-2 text-medium-emphasis mb-6" style="max-width: 560px; text-align: center;">
      Point to the repos you want to work with. Bodhigrove uses Claude Code to
      auto-detect developer skills, extract existing features, and build full
      context so AI agents can help manage your workflow.
    </p>

    <v-card class="pa-5 card-border-dark w-100" color="surface" style="max-width: 620px;">
      <!-- Step 1: Select repos -->
      <div class="d-flex align-center ga-2 mb-3">
        <v-avatar size="24" color="primary" class="text-caption font-weight-bold">1</v-avatar>
        <span class="text-body-2 font-weight-medium">Select repositories</span>
      </div>

      <!-- Selected repos as chips -->
      <div v-if="repos.length" class="mb-3">
        <v-chip
          v-for="(r, idx) in repos"
          :key="r.path"
          closable
          variant="tonal"
          size="small"
          class="ma-1"
          @click:close="removeRepo(idx)"
        >
          <v-icon icon="mdi-source-repository" size="14" start />
          {{ r.path.split('/').pop() }}
          <v-tooltip activator="parent" location="top" :text="r.path" />
        </v-chip>
      </div>

      <!-- Stash warning -->
      <v-alert
        v-if="repos.length > 0"
        type="warning"
        variant="tonal"
        density="compact"
        icon="mdi-source-branch-sync"
        class="mb-3"
      >
        Scanning will temporarily stash uncommitted changes and checkout the main branch.
        <strong>Commit or back up your work</strong> in all repos before proceeding.
      </v-alert>

      <!-- Path input -->
      <v-text-field
        v-model="inputPath"
        label="Absolute path to git repository"
        placeholder="/path/to/repo"
        variant="outlined"
        density="compact"
        hint="Type a path and press Enter, or browse to select"
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
            :disabled="!inputPath.trim()"
            @click="addPathToList"
          />
          <v-btn
            icon="mdi-folder-search-outline"
            size="small"
            variant="text"
            density="compact"
            @click="showPicker = true"
          />
        </template>
      </v-text-field>

      <div class="text-caption text-medium-emphasis mt-2 mb-4">
        Make sure each repo is cloned locally. Share the absolute path.
      </div>

      <v-divider class="mb-4" />

      <!-- Step 2: Map branches -->
      <div class="d-flex align-center ga-2 mb-3">
        <v-avatar size="24" color="primary" class="text-caption font-weight-bold">2</v-avatar>
        <span class="text-body-2 font-weight-medium">Map branches</span>
      </div>

      <div v-if="!repos.length" class="text-caption text-medium-emphasis mb-3 ml-8">
        Add at least one repository above to configure branches.
      </div>

      <!-- Branch mapping per repo -->
      <div v-for="(repo, idx) in repos" :key="repo.path" class="mb-4">
        <div class="text-body-2 font-weight-medium mb-2 d-flex align-center ga-2">
          <v-icon icon="mdi-source-repository" size="16" />
          {{ repo.path.split('/').pop() }}
          <v-chip
            v-if="repo.mainBranch && repo.developBranch"
            size="x-small"
            color="success"
            variant="tonal"
          >
            Mapped
          </v-chip>
          <v-progress-circular
            v-if="branchLoading[idx]"
            indeterminate
            size="14"
            width="2"
          />
        </div>

        <div class="d-flex ga-3">
          <v-combobox
            v-model="repo.mainBranch"
            :items="branchOptions[idx] || []"
            label="Main branch"
            density="compact"
            variant="outlined"
            hide-details
            placeholder="e.g. main"
            class="flex-grow-1"
          />
          <v-combobox
            v-model="repo.developBranch"
            :items="branchOptions[idx] || []"
            label="Develop branch"
            density="compact"
            variant="outlined"
            hide-details
            placeholder="e.g. develop"
            class="flex-grow-1"
          />
        </div>
      </div>

      <v-alert
        v-if="repos.length && !allMapped"
        type="warning"
        variant="tonal"
        density="compact"
        icon="mdi-source-branch"
        class="text-body-2 mt-2"
      >
        All repos need both <strong>main</strong> and <strong>develop</strong>
        branches mapped before we can scan.
      </v-alert>

      <v-divider class="my-4" />

      <!-- Step 3: Scan settings -->
      <div class="d-flex align-center ga-2 mb-3">
        <v-avatar size="24" color="primary" class="text-caption font-weight-bold">3</v-avatar>
        <span class="text-body-2 font-weight-medium">Scan settings</span>
      </div>

      <div class="d-flex ga-3">
        <v-text-field
          v-model.number="setupStore.state.scan.timeoutSeconds"
          label="Timeout (seconds)"
          type="number"
          density="compact"
          variant="outlined"
          hide-details
          :min="60"
          :max="1800"
          class="flex-grow-1"
        />
        <v-text-field
          v-model.number="setupStore.state.scan.maxTurns"
          label="Max AI steps"
          type="number"
          density="compact"
          variant="outlined"
          hide-details
          :min="0"
          :max="100"
          class="flex-grow-1"
        />
      </div>
      <div class="text-caption text-medium-emphasis mt-2">
        Timeout controls how long each repo scan runs. Max AI steps limits
        how many Claude Code tool calls are made per feature synthesis
        (0 = unlimited). Defaults work well for most repos — you can
        fine-tune these later in Settings.
      </div>
    </v-card>

    <!-- Directory picker dialog -->
    <v-dialog v-model="showPicker" max-width="600" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center ga-2">
          <v-icon icon="mdi-folder-open-outline" />
          Browse Directories
        </v-card-title>

        <v-card-text>
          <div class="text-caption text-medium-emphasis mb-2">
            {{ currentDir }}
          </div>

          <v-btn
            v-if="parentDir"
            variant="text"
            size="small"
            prepend-icon="mdi-arrow-up"
            class="mb-2"
            @click="browse(parentDir!)"
          >
            Up
          </v-btn>

          <div v-if="pickerSelectedCount > 0" class="text-caption text-primary mb-2">
            {{ pickerSelectedCount }} repo{{ pickerSelectedCount > 1 ? 's' : '' }} selected
          </div>

          <v-list density="compact" select-strategy="leaf">
            <v-list-item
              v-for="entry in directories"
              :key="entry.path"
              @click="entry.is_git_repo ? toggleRepo(entry.path) : browse(entry.path)"
            >
              <template #prepend>
                <v-checkbox-btn
                  v-if="entry.is_git_repo"
                  :model-value="isRepoSelected(entry.path)"
                  color="primary"
                  density="compact"
                  hide-details
                  @click.stop="toggleRepo(entry.path)"
                />
                <v-icon v-else icon="mdi-folder-outline" size="20" class="ml-2 mr-2" />
              </template>
              <v-list-item-title>{{ entry.name }}</v-list-item-title>
              <v-list-item-subtitle v-if="entry.is_git_repo">
                Git repository
              </v-list-item-subtitle>
              <template #append>
                <v-icon
                  icon="mdi-chevron-right"
                  size="20"
                  class="text-medium-emphasis"
                  @click.stop="browse(entry.path)"
                />
              </template>
            </v-list-item>
            <v-list-item v-if="!directories.length && !browseLoading">
              <div class="text-caption text-medium-emphasis">No subdirectories</div>
            </v-list-item>
          </v-list>

          <div v-if="browseLoading" class="d-flex justify-center py-4">
            <v-progress-circular indeterminate size="24" />
          </div>
        </v-card-text>

        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showPicker = false">Done</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useSetupStore } from '@/stores/setup'
import type { SetupRepoConfig } from '@/types/setup'
import api from '@/services/api'

const setupStore = useSetupStore()
const repos = computed(() => setupStore.state.sourceCode.repos)

const inputPath = ref('')
const showPicker = ref(false)
const currentDir = ref('')
const parentDir = ref<string | null>(null)
const directories = ref<Array<{ name: string; path: string; is_git_repo: boolean }>>([])
const browseLoading = ref(false)

// Branch options per repo index
const branchOptions = reactive<Record<number, string[]>>({})
const branchLoading = reactive<Record<number, boolean>>({})

const pickerSelectedCount = computed(() => repos.value.length)
const allMapped = computed(() =>
  repos.value.length > 0 && repos.value.every(r => r.mainBranch && r.developBranch),
)

function isRepoSelected(path: string): boolean {
  return repos.value.some(r => r.path === path)
}

function addRepo(path: string): void {
  if (isRepoSelected(path)) return
  const repo: SetupRepoConfig = { path, mainBranch: null, developBranch: null }
  setupStore.state.sourceCode.repos.push(repo)
  fetchBranches(setupStore.state.sourceCode.repos.length - 1, path)
}

function removeRepo(idx: number): void {
  setupStore.state.sourceCode.repos.splice(idx, 1)
  // Shift branch options
  const newOpts: Record<number, string[]> = {}
  for (const [k, v] of Object.entries(branchOptions)) {
    const ki = Number(k)
    if (ki < idx) newOpts[ki] = v
    else if (ki > idx) newOpts[ki - 1] = v
  }
  Object.keys(branchOptions).forEach(k => delete branchOptions[Number(k)])
  Object.assign(branchOptions, newOpts)
}

function addPathToList(): void {
  const p = inputPath.value.trim()
  if (p) {
    addRepo(p)
    inputPath.value = ''
  }
}

function toggleRepo(path: string): void {
  const idx = repos.value.findIndex(r => r.path === path)
  if (idx >= 0) {
    removeRepo(idx)
  } else {
    addRepo(path)
  }
}

async function fetchBranches(idx: number, path: string): Promise<void> {
  branchLoading[idx] = true
  try {
    const { data } = await api.get('/setup/repo-branches', { params: { path } })
    branchOptions[idx] = data.branches || []
    // Auto-fill detected branches
    const repo = setupStore.state.sourceCode.repos[idx]
    if (repo && data.detectedMain && !repo.mainBranch) {
      repo.mainBranch = data.detectedMain
    }
    if (repo && data.detectedDevelop && !repo.developBranch) {
      repo.developBranch = data.detectedDevelop
    }
  } catch {
    branchOptions[idx] = []
  } finally {
    branchLoading[idx] = false
  }
}

async function browse(path?: string): Promise<void> {
  browseLoading.value = true
  try {
    const { data } = await api.get('/setup/browse-directories', {
      params: { path: path || '' },
    })
    currentDir.value = data.current_path
    parentDir.value = data.parent_path
    directories.value = data.directories
  } catch {
    // ignore
  } finally {
    browseLoading.value = false
  }
}

// Browse home on first open
watch(showPicker, (open) => {
  if (open && !currentDir.value) {
    browse()
  }
})
</script>
