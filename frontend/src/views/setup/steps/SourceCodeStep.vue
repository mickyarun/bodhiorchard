<template>
  <div class="d-flex flex-column align-center">
    <v-icon icon="mdi-source-repository" size="48" color="primary" class="mb-4" />
    <h2 class="text-h5 font-weight-bold mb-2">Repositories</h2>
    <p class="text-body-2 text-medium-emphasis mb-6 text-center" style="max-width: 560px;">
      Point to the repos you want to work with. Bodhiorchard uses Claude Code to
      auto-detect developer skills, extract existing features, and build full
      context so AI agents can help manage your workflow.
    </p>

    <v-card class="pa-5 card-border-dark w-100" color="surface" style="max-width: 640px;">
      <!-- Step 1: Source picker (tabs) -->
      <div class="d-flex align-center ga-2 mb-3">
        <v-avatar size="24" color="primary" class="text-caption font-weight-bold">1</v-avatar>
        <span class="text-body-2 font-weight-medium">Add repositories</span>
        <v-spacer />
        <v-chip
          v-if="deploymentMode"
          :color="deploymentMode === 'docker' ? 'info' : 'success'"
          variant="tonal"
          size="x-small"
          :prepend-icon="deploymentMode === 'docker' ? 'mdi-docker' : 'mdi-laptop'"
        >
          {{ deploymentMode === 'docker' ? 'Full Docker' : 'Hybrid' }}
        </v-chip>
      </div>

      <v-tabs
        v-model="activeTab"
        density="compact"
        color="primary"
        class="mb-3"
      >
        <v-tab value="github" prepend-icon="mdi-github">GitHub clone</v-tab>
        <v-tab
          v-if="deploymentMode !== 'docker'"
          value="local"
          prepend-icon="mdi-folder-outline"
        >
          Local path
        </v-tab>
      </v-tabs>

      <!-- GitHub clone tab -->
      <div v-if="activeTab === 'github'">
        <div v-if="cloneQueue.length" class="mb-3">
          <v-chip
            v-for="(q, idx) in cloneQueue"
            :key="q.url"
            closable
            variant="tonal"
            size="small"
            class="ma-1"
            :color="cloneChipColor(q.status)"
            :disabled="q.status === 'cloning'"
            :prepend-icon="cloneChipIcon(q.status)"
            @click:close="removeCloneQueueItem(idx)"
          >
            {{ cloneRepoLabel(q.url) }}
            <v-tooltip activator="parent" location="top">
              <div>{{ q.url }}</div>
              <div v-if="q.error" class="text-caption text-error">{{ q.error }}</div>
            </v-tooltip>
          </v-chip>
        </div>

        <div class="d-flex align-start ga-2 mb-1">
          <v-text-field
            v-model="cloneUrl"
            label="GitHub URL"
            placeholder="https://github.com/owner/repo"
            variant="outlined"
            density="comfortable"
            hide-details
            prepend-inner-icon="mdi-link-variant"
            class="flex-grow-1"
            @keyup.enter="addUrlToQueue"
          />
          <v-btn
            color="primary"
            variant="tonal"
            prepend-icon="mdi-plus"
            :disabled="!cloneUrl.trim() || cloning"
            style="min-height: 48px;"
            @click="addUrlToQueue"
          >
            Add
          </v-btn>
        </div>
        <div class="text-caption text-medium-emphasis mb-3 ml-1">
          {{ cloneUrlHint }}
          <span v-if="cloneQueue.length === 0" class="text-primary">
            Add as many as you want, then Clone.
          </span>
        </div>

        <v-switch
          v-model="isPrivate"
          label="Private repository"
          color="primary"
          density="compact"
          hide-details
          class="mb-2"
        />

        <v-expand-transition>
          <div v-if="isPrivate">
            <v-alert
              v-if="urlIsSsh"
              type="success"
              variant="tonal"
              density="compact"
              icon="mdi-lock-check-outline"
              class="mb-3"
            >
              <div class="text-body-2">
                SSH URL detected — we'll authenticate with the deploy key below.
                No token needed.
              </div>
            </v-alert>
            <v-alert
              v-else-if="urlIsHttps"
              type="info"
              variant="tonal"
              density="compact"
              icon="mdi-key-variant"
              class="mb-3"
            >
              <div class="text-body-2">
                HTTPS URL — paste a fine-grained personal-access token.
                Prefer SSH? Use the <code>git@github.com:&lt;owner&gt;/&lt;repo&gt;.git</code>
                URL instead and we'll switch to the deploy-key flow.
              </div>
            </v-alert>

            <v-expand-transition>
              <div v-if="privateAuthMode === 'pat'">
                <v-alert
                  type="info"
                  variant="tonal"
                  density="compact"
                  icon="mdi-shield-key-outline"
                  class="mb-3"
                >
                  <div class="text-body-2 font-weight-medium mb-1">
                    Generate a fine-grained token (read-only)
                  </div>
                  <ol class="text-caption mb-2 pl-4">
                    <li>
                      Open
                      <a
                        href="https://github.com/settings/personal-access-tokens/new"
                        target="_blank"
                        rel="noopener"
                        class="text-primary"
                      >github.com/settings/personal-access-tokens/new</a>.
                    </li>
                    <li>
                      <strong>Repository access</strong> → <em>Only select repositories</em>
                      → pick the repo you're cloning.
                    </li>
                    <li>
                      <strong>Repository permissions</strong> → click
                      <em>Add permissions</em> → search for <strong>Contents</strong>
                      → set to <strong>Read-only</strong>.
                      <br>
                      <span class="text-medium-emphasis">
                        (<em>Metadata: Read-only</em> is auto-added — leave it alone.
                        Nothing else is needed.)
                      </span>
                    </li>
                    <li>Click <strong>Generate token</strong> and paste it below.</li>
                  </ol>
                  <div class="text-caption text-medium-emphasis">
                    Classic tokens also work — use the <code>repo</code> scope
                    (broader access than needed, but functional).
                  </div>
                </v-alert>

                <v-text-field
                  v-model="pat"
                  label="GitHub personal-access token"
                  placeholder="github_pat_… (fine-grained) or ghp_… (classic)"
                  type="password"
                  variant="outlined"
                  density="compact"
                  autocomplete="off"
                  hide-details
                  prepend-inner-icon="mdi-key-variant"
                  class="mb-2"
                />
                <div class="text-caption text-medium-emphasis mb-3 ml-1">
                  The token is used once to clone and never stored.
                </div>
              </div>
            </v-expand-transition>

            <v-expand-transition>
              <div v-if="privateAuthMode === 'ssh'">
                <v-alert
                  type="info"
                  variant="tonal"
                  density="compact"
                  icon="mdi-key-chain"
                  class="mb-3"
                >
                  <div class="text-body-2 font-weight-medium mb-1">
                    Add this deploy key to GitHub
                  </div>
                  <ol class="text-caption mb-2 pl-4">
                    <li>Copy the key below.</li>
                    <li>
                      Open <strong>your repo → Settings → Deploy keys → Add deploy key</strong>.
                    </li>
                    <li>Title: <code>bodhiorchard</code>. Paste the key. Leave <em>Allow write</em> off. Click <strong>Add key</strong>.</li>
                    <li>Come back here and clone the SSH URL (<code>git@github.com:owner/repo.git</code>).</li>
                  </ol>
                </v-alert>

                <v-textarea
                  :model-value="deployKey"
                  label="Public deploy key"
                  rows="2"
                  variant="outlined"
                  density="compact"
                  hide-details
                  readonly
                  auto-grow
                  class="mb-2 font-monospace"
                  style="font-size: 11px;"
                />
                <div class="d-flex ga-2 mb-3">
                  <v-btn
                    size="small"
                    variant="tonal"
                    prepend-icon="mdi-content-copy"
                    :disabled="!deployKey"
                    @click="copyDeployKey"
                  >
                    {{ copied ? 'Copied' : 'Copy key' }}
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="text"
                    href="https://github.com/settings/keys"
                    target="_blank"
                    rel="noopener"
                    append-icon="mdi-open-in-new"
                  >
                    GitHub deploy keys help
                  </v-btn>
                </div>
              </div>
            </v-expand-transition>
          </div>
        </v-expand-transition>

        <v-btn
          color="primary"
          variant="flat"
          block
          size="large"
          :loading="cloning"
          :disabled="!canClone"
          prepend-icon="mdi-download"
          @click="handleClone"
        >
          {{ cloneButtonLabel }}
        </v-btn>

        <v-expand-transition>
          <v-alert
            v-if="cloneError"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-3"
            icon="mdi-alert-circle-outline"
          >
            {{ cloneError }}
          </v-alert>
        </v-expand-transition>
      </div>

      <!-- Local path tab (Hybrid only) -->
      <div v-if="activeTab === 'local'">
        <v-text-field
          v-model="inputPath"
          label="Absolute path to git repository"
          placeholder="/Users/me/code/my-repo"
          variant="outlined"
          density="comfortable"
          hide-details="auto"
          hint="Type a path and press Enter, or browse to select"
          persistent-hint
          prepend-inner-icon="mdi-folder-outline"
          class="mb-3"
          @keyup.enter="addPathToList"
        >
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
      </div>

      <!-- Selected repos -->
      <div v-if="repos.length" class="mt-3">
        <v-divider class="mb-3" />
        <div class="text-caption text-medium-emphasis mb-2">
          {{ repos.length }} repo{{ repos.length > 1 ? 's' : '' }} added
        </div>
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
          {{ repoLabel(r.path) }}
          <v-tooltip activator="parent" location="top" :text="r.path" />
        </v-chip>
      </div>

      <v-alert
        v-if="repos.length > 0 && deploymentMode !== 'docker'"
        type="warning"
        variant="tonal"
        density="compact"
        icon="mdi-source-branch-sync"
        class="mt-3"
      >
        Scanning will temporarily stash uncommitted changes and checkout the main branch.
        <strong>Commit or back up your work</strong> in all repos before proceeding.
      </v-alert>

      <v-divider class="my-4" />

      <!-- Step 2: Branch mapping -->
      <div class="d-flex align-center ga-2 mb-3">
        <v-avatar size="24" color="primary" class="text-caption font-weight-bold">2</v-avatar>
        <span class="text-body-2 font-weight-medium">Map branches</span>
      </div>

      <div v-if="!repos.length" class="text-caption text-medium-emphasis mb-3 ml-8">
        Add at least one repository above to configure branches.
      </div>

      <div v-for="(repo, idx) in repos" :key="repo.path" class="mb-4">
        <div class="text-body-2 font-weight-medium mb-2 d-flex align-center ga-2">
          <v-icon icon="mdi-source-repository" size="16" />
          {{ repoLabel(repo.path) }}
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
        (0 = unlimited).
      </div>
    </v-card>

    <!-- Directory picker dialog (host mode only) -->
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
              <v-list-item-title>
                {{ entry.name }}
                <span
                  v-if="entry.is_git_repo && entry.has_sub_repos"
                  class="text-caption text-medium-emphasis ml-1"
                >
                  (contains repos)
                </span>
              </v-list-item-title>
              <v-list-item-subtitle v-if="entry.is_git_repo">
                Git repository
              </v-list-item-subtitle>
              <template #append>
                <v-chip
                  v-if="entry.has_sub_repos"
                  size="x-small"
                  variant="tonal"
                  color="warning"
                  class="mr-2"
                >
                  monorepo
                </v-chip>
                <v-btn
                  v-if="entry.is_git_repo"
                  icon="mdi-chevron-right"
                  size="small"
                  variant="text"
                  density="compact"
                  title="Browse inside"
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
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useSetupStore } from '@/stores/setup'
import type { SetupRepoConfig } from '@/types/setup'
import api from '@/services/api'

const setupStore = useSetupStore()
const repos = computed(() => setupStore.state.sourceCode.repos)

// Deployment detection — drives which tab is visible/default.
const deploymentMode = ref<'docker' | 'host' | null>(null)
const activeTab = ref<'github' | 'local'>('github')

// GitHub clone form state — queued list lets the user batch multiple
// repos in one setup step with shared PAT/deploy-key auth.
type CloneQueueStatus = 'pending' | 'cloning' | 'done' | 'error'
interface CloneQueueItem {
  url: string
  status: CloneQueueStatus
  error?: string
}

const cloneUrl = ref('')
const cloneQueue = ref<CloneQueueItem[]>([])
const isPrivate = ref(false)
const privateAuthMode = ref<'pat' | 'ssh'>('pat')
const pat = ref('')
const deployKey = ref('')
const cloning = ref(false)
const cloneError = ref('')
const copied = ref(false)

// Local path form state (host mode)
const inputPath = ref('')
const showPicker = ref(false)
const currentDir = ref('')
const parentDir = ref<string | null>(null)
const directories = ref<Array<{
  name: string
  path: string
  is_git_repo: boolean
  has_sub_repos: boolean
}>>([])
const browseLoading = ref(false)

// Branch options per repo index
const branchOptions = reactive<Record<number, string[]>>({})
const branchLoading = reactive<Record<number, boolean>>({})

const allMapped = computed(() =>
  repos.value.length > 0 && repos.value.every(r => r.mainBranch && r.developBranch),
)

const cloneUrlHint = computed<string>(() => {
  const v = cloneUrl.value.trim()
  if (!v) return 'Paste a GitHub URL — HTTPS or SSH. Private repos need auth below.'
  if (v.startsWith('git@') || v.startsWith('ssh://')) {
    return 'SSH URL — will use the deploy key below.'
  }
  return 'HTTPS URL — public repos clone anonymously.'
})

function isSshUrl(url: string): boolean {
  const v = url.trim()
  return v.startsWith('git@') || v.startsWith('ssh://')
}
function isHttpsUrl(url: string): boolean {
  return url.trim().startsWith('https://')
}

const urlIsSsh = computed<boolean>(() => isSshUrl(cloneUrl.value))
const urlIsHttps = computed<boolean>(() => isHttpsUrl(cloneUrl.value))

// Hidden auth mode tracks the current URL's shape so the right sub-panel
// (deploy key vs PAT) is visible.
watch([urlIsSsh, urlIsHttps], ([ssh]) => {
  privateAuthMode.value = ssh ? 'ssh' : 'pat'
})

const pendingCount = computed<number>(
  () => cloneQueue.value.filter((q) => q.status === 'pending' || q.status === 'error').length
    + (cloneUrl.value.trim() ? 1 : 0),
)

const canClone = computed<boolean>(() => {
  if (cloning.value) return false
  if (pendingCount.value === 0) return false
  if (isPrivate.value && privateAuthMode.value === 'pat') {
    // Any pending HTTPS URL needs the shared PAT.
    const anyNeedsPat = (cloneUrl.value.trim() && isHttpsUrl(cloneUrl.value))
      || cloneQueue.value.some((q) =>
        (q.status === 'pending' || q.status === 'error') && isHttpsUrl(q.url),
      )
    if (anyNeedsPat && !pat.value.trim()) return false
  }
  return true
})

const cloneButtonLabel = computed<string>(() => {
  if (cloning.value) return 'Cloning…'
  const n = pendingCount.value
  if (n === 0) return 'Clone repository'
  return n === 1 ? 'Clone repository' : `Clone ${n} repositories`
})

function cloneRepoLabel(url: string): string {
  const cleaned = url.replace(/\.git\/?$/, '').replace(/\/$/, '')
  return cleaned.split(/[/:]/).pop() || cleaned
}
function cloneChipColor(status: CloneQueueStatus): string {
  return status === 'done'
    ? 'success'
    : status === 'error'
      ? 'error'
      : status === 'cloning'
        ? 'primary'
        : 'grey'
}
function cloneChipIcon(status: CloneQueueStatus): string {
  return status === 'done'
    ? 'mdi-check-circle-outline'
    : status === 'error'
      ? 'mdi-alert-circle-outline'
      : status === 'cloning'
        ? 'mdi-progress-download'
        : 'mdi-source-repository'
}

function addUrlToQueue(): void {
  const u = cloneUrl.value.trim()
  if (!u) return
  if (cloneQueue.value.some((q) => q.url === u)) {
    cloneUrl.value = ''
    return
  }
  cloneQueue.value.push({ url: u, status: 'pending' })
  cloneUrl.value = ''
}
function removeCloneQueueItem(idx: number): void {
  const item = cloneQueue.value[idx]
  if (item && item.status === 'cloning') return
  cloneQueue.value.splice(idx, 1)
}

onMounted(async () => {
  // Deployment mode → default tab.
  try {
    const { data } = await api.get('/setup/deployment-info')
    deploymentMode.value = data.mode === 'docker' ? 'docker' : 'host'
    // Host users who already have repos cloned locally will want the local tab
    // by default — but GitHub clone is the more general first-run experience,
    // so we start on `github` in both modes and let users switch.
    activeTab.value = 'github'
  } catch {
    deploymentMode.value = 'host'
    activeTab.value = 'github'
  }

  // Pre-fetch the deploy key so toggling to SSH is instant.
  try {
    const { data } = await api.get('/setup/deploy-key')
    deployKey.value = data.public_key || ''
  } catch {
    deployKey.value = ''
  }
})

watch([cloneUrl, isPrivate, privateAuthMode, pat], () => {
  cloneError.value = ''
})

function repoLabel(path: string): string {
  return path.split('/').filter(Boolean).pop() || path
}

function isRepoSelected(path: string): boolean {
  return repos.value.some(r => r.path === path)
}

function addRepo(path: string, detectedMain?: string | null, branches?: string[]): void {
  if (isRepoSelected(path)) return
  const repo: SetupRepoConfig = {
    path,
    mainBranch: detectedMain || null,
    developBranch: null,
  }
  setupStore.state.sourceCode.repos.push(repo)
  const idx = setupStore.state.sourceCode.repos.length - 1
  if (branches && branches.length) {
    branchOptions[idx] = branches
    if (detectedMain) repo.mainBranch = detectedMain
  }
  // Always (re)fetch branches + detect develop — the clone response only
  // gives us the GitHub default; develop must be inferred separately.
  fetchBranches(idx, path)
}

function removeRepo(idx: number): void {
  setupStore.state.sourceCode.repos.splice(idx, 1)
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
  if (idx >= 0) removeRepo(idx)
  else addRepo(path)
}

async function handleClone(): Promise<void> {
  if (!canClone.value) return
  addUrlToQueue()

  cloning.value = true
  cloneError.value = ''
  try {
    for (const item of cloneQueue.value) {
      if (item.status === 'done') continue
      item.status = 'cloning'
      item.error = undefined

      const useSsh = isSshUrl(item.url)
      const payload: {
        url: string
        orgSlug: string
        pat?: string | null
      } = {
        url: item.url,
        orgSlug: setupStore.state.organization.slug || 'default',
      }
      if (isPrivate.value && !useSsh && pat.value.trim()) {
        payload.pat = pat.value.trim()
      }

      try {
        const { data } = await api.post('/setup/clone-repo', payload, { timeout: 120_000 })
        if (!data.success) {
          item.status = 'error'
          item.error = data.error || 'Clone failed.'
          continue
        }
        item.status = 'done'
        // Append with the default branch pre-filled so branch mapping is usually just "pick develop".
        addRepo(data.path, data.default_branch, data.branches || [])
      } catch (err: unknown) {
        item.status = 'error'
        if (err && typeof err === 'object' && 'response' in err) {
          const axiosErr = err as { response?: { data?: { detail?: string } } }
          item.error = axiosErr.response?.data?.detail || 'Server unreachable.'
        } else {
          item.error = 'Server unreachable.'
        }
      }
    }
  } finally {
    cloning.value = false
  }

  // Remove completed items so the queue only holds what still needs attention
  // (successes are already reflected in the repos list below). Errored items
  // stay so the user can fix auth and retry.
  cloneQueue.value = cloneQueue.value.filter((q) => q.status !== 'done')

  // Reset auth inputs only when the batch fully succeeded.
  if (cloneQueue.value.length === 0) {
    pat.value = ''
    isPrivate.value = false
  } else if (cloneQueue.value.every((q) => q.status === 'error')) {
    // First error surfaces at the page-level alert too, for visibility.
    cloneError.value = cloneQueue.value[0]?.error || ''
  }
}

async function copyDeployKey(): Promise<void> {
  try {
    await navigator.clipboard.writeText(deployKey.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // Fall through — user can select and copy manually.
  }
}

async function fetchBranches(idx: number, path: string): Promise<void> {
  branchLoading[idx] = true
  try {
    const { data } = await api.get('/setup/repo-branches', { params: { path } })
    branchOptions[idx] = data.branches || []
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

watch(showPicker, (open) => {
  if (open && !currentDir.value) browse()
})
</script>

<style scoped>
.font-monospace {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, "Cascadia Code", monospace;
}
</style>
