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
        <v-tab
          :value="TAB_GITHUB"
          prepend-icon="mdi-github"
          text="GitHub clone"
        />
        <v-tab
          v-if="deploymentMode !== 'docker'"
          :value="TAB_LOCAL"
          prepend-icon="mdi-folder-outline"
          text="Local path"
        />
        <v-tab
          :value="TAB_BULK"
          prepend-icon="mdi-source-repository-multiple"
          text="Bulk import"
        />
      </v-tabs>

      <!--
        Bulk Import is shown in both setup and settings mode (Phase J
        restored). The wizard pre-creates the org after the AI Engine
        step so the picker has a backend to talk to.
      -->
      <div v-if="activeTab === TAB_BULK">
        <RepoOnboardBulkTab :mode="props.mode" @onboarded="onBulkOnboarded" />
      </div>

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
                    Generate a fine-grained token
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
                      → set to <strong>Read and Write</strong>.
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
          :key="r.gitHubFullName || r.path || idx"
          closable
          variant="tonal"
          size="small"
          class="ma-1"
          @click:close="removeRepo(idx)"
        >
          <v-icon icon="mdi-source-repository" size="14" start />
          {{ repoChipLabel(r) }}
          <v-tooltip activator="parent" location="top" :text="r.gitHubFullName || r.path" />
        </v-chip>
      </div>

      <template v-if="hasReposConfigured">
        <!-- Step 2: Branch mapping — local-path entries only. Bulk + GitHub
             clone flows auto-detect branches at add-time, so re-rendering
             the picker here would just duplicate UI the user already saw. -->
        <template v-if="localPathRepos.length > 0">
        <v-divider class="my-4" />

        <div class="d-flex align-center ga-2 mb-3">
          <v-avatar size="24" color="primary" class="text-caption font-weight-bold">2</v-avatar>
          <span class="text-body-2 font-weight-medium">Map branches</span>
        </div>

        <div v-for="repo in localPathRepos" :key="repo.path" class="mb-4">
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
            v-if="branchLoading[repoIndex(repo)]"
            indeterminate
            size="14"
            width="2"
          />
        </div>

        <div class="d-flex ga-3">
          <v-combobox
            v-model="repo.mainBranch"
            :items="branchOptions[repoIndex(repo)] || []"
            label="Main branch"
            density="compact"
            variant="outlined"
            hide-details
            placeholder="e.g. main"
            class="flex-grow-1"
          />
          <v-combobox
            v-model="repo.developBranch"
            :items="branchOptions[repoIndex(repo)] || []"
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
        v-if="!allMapped"
        type="warning"
        variant="tonal"
        density="compact"
        icon="mdi-source-branch"
        class="text-body-2 mt-2"
      >
        Local repos need both <strong>main</strong> and <strong>develop</strong>
        branches mapped before we can scan.
      </v-alert>
        </template>

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
          :max="3600"
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
      </template>
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
// TODO(post-bulk-import): split this 800+ line file into per-tab subcomponents.
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useSetupStore } from '@/stores/setup'
import type { SetupRepoConfig } from '@/types/setup'
import type { BulkOnboardJobTerminalResult } from '@/types/repoOnboard'
import api from '@/services/api'
import RepoOnboardBulkTab from '@/components/settings/code/onboard/RepoOnboardBulkTab.vue'

const TAB_GITHUB = 'github'
const TAB_LOCAL = 'local'
const TAB_BULK = 'bulk'
type SourceTab = typeof TAB_GITHUB | typeof TAB_LOCAL | typeof TAB_BULK

// Phase J: Bulk Import is now visible in both modes — the wizard
// pre-creates the org after the AI Engine step so a live JWT exists by
// the time the user reaches Source Code. The ``mode`` prop stays so
// callers can opt into per-surface tweaks in the future without another
// breaking signature change.
const props = withDefaults(defineProps<{
  /** Surface mode — propagated into the bulk tab so the wizard's
   *  Continue button drives finalize in setup mode. */
  mode?: 'setup' | 'settings'
}>(), { mode: 'settings' })

const setupStore = useSetupStore()
const repos = computed(() => setupStore.state.sourceCode.repos)
const hasReposConfigured = computed(() => setupStore.state.sourceCode.repos.length > 0)
// Phase P — section 2 ("Map branches") only renders local-path entries.
// Bulk and github-clone flows auto-detect main/develop on add, so showing
// them again duplicates UI the user already touched.
const localPathRepos = computed(() =>
  repos.value.filter((r) => (r.source ?? 'github-clone') === 'local-path'),
)

// Deployment detection — drives which tab is visible/default.
const deploymentMode = ref<'docker' | 'host' | null>(null)
const activeTab = ref<SourceTab>(TAB_GITHUB)

function onBulkOnboarded(result: BulkOnboardJobTerminalResult): void {
  // Bulk job runs full clone+scan server-side; mirror succeeded items
  // into the setup store so finalize emits the installable-items shape.
  for (const item of result.items) {
    if (item.status !== 'done') continue
    const path = `bulk:${item.fullName}`
    if (setupStore.state.sourceCode.repos.some(r => r.path === path)) continue
    setupStore.state.sourceCode.repos.push({
      path,
      mainBranch: item.mainBranch,
      developBranch: item.developBranch || null,
      gitHubFullName: item.fullName,
      source: 'bulk',
    })
  }
}

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

// Section 2 only renders local-path entries, so the unmapped-warning gate
// must scope to the same set — otherwise a bulk entry without a develop
// branch would surface a warning the user has no UI to act on.
const allMapped = computed(() =>
  localPathRepos.value.every((r) => r.mainBranch && r.developBranch),
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

  // Pre-fetch the deploy key so toggling to SSH is instant. Uses the
  // authenticated endpoint because by this step the wizard already ran
  // /setup/init-org, which mints a JWT and disables /setup/deploy-key
  // (the unauth wizard route 403s post-init).
  try {
    const { data } = await api.get('/v1/settings/repos/deploy-key')
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

// Section 2 iterates the filtered ``localPathRepos`` list, but
// ``branchOptions`` / ``branchLoading`` are keyed by the original index
// in ``setupStore.state.sourceCode.repos`` (assigned at addRepo time).
function repoIndex(repo: SetupRepoConfig): number {
  return repos.value.indexOf(repo)
}

function repoChipLabel(r: SetupRepoConfig): string {
  if (r.gitHubFullName) return r.gitHubFullName
  return repoLabel(r.path)
}

function isRepoSelected(path: string): boolean {
  return repos.value.some(r => r.path === path)
}

function addRepo(
  path: string,
  detectedMain?: string | null,
  branches?: string[],
  source: 'github-clone' | 'local-path' = 'local-path',
): void {
  if (isRepoSelected(path)) return
  const repo: SetupRepoConfig = {
    path,
    mainBranch: detectedMain || null,
    developBranch: null,
    source,
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
      // Authenticated endpoint — derives org from JWT, no orgSlug needed.
      const payload: { url: string; pat?: string | null } = { url: item.url }
      if (isPrivate.value && !useSsh && pat.value.trim()) {
        payload.pat = pat.value.trim()
      }

      try {
        // POST returns RepoInfo on success; failures surface as 4xx via the
        // catch block below. The branch list is fetched separately because
        // the auth endpoint keeps the clone response and the branch list
        // decoupled (see settings_repos.py: /repos/{id}/branches).
        const { data: repo } = await api.post('/v1/settings/repos/clone', payload, {
          timeout: 120_000,
        })
        let branches: string[] = []
        try {
          const { data: branchList } = await api.get(
            `/v1/settings/repos/${encodeURIComponent(repo.id)}/branches`,
          )
          branches = Array.isArray(branchList?.branches) ? branchList.branches : []
        } catch {
          // Branch fetch is best-effort — clone already succeeded.
        }
        item.status = 'done'
        addRepo(repo.path, repo.mainBranch || '', branches, 'github-clone')
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
