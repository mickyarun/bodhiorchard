<template>
  <!-- Multi-design sub-tabs when designs exist -->
  <div v-if="designs.length > 0" class="design-multi-panel">
    <div class="design-sub-tabs-row">
      <v-tabs v-model="activeDesignTab" density="compact" color="teal" class="design-sub-tabs">
        <v-tab v-for="d in designs" :key="d.id" :value="d.id">
          {{ d.repo_name || 'Default' }}
          <v-icon
            v-if="d.status === 'generating'"
            icon="mdi-loading"
            size="14"
            class="ml-1 mdi-spin"
          />
          <v-icon
            v-else-if="d.status === 'failed'"
            icon="mdi-alert-circle-outline"
            size="14"
            class="ml-1"
            color="error"
          />
        </v-tab>
      </v-tabs>
      <div class="d-flex align-center ga-1">
        <v-btn
          v-if="activeDesignObj?.status === 'ready'"
          variant="text"
          size="small"
          title="Open in new tab"
          @click="openDesignInTab(activeDesignTab)"
        >
          <v-icon size="15">mdi-open-in-new</v-icon>
        </v-btn>
        <v-btn
          v-if="activeDesignObj?.status === 'ready'"
          variant="text"
          size="small"
          title="Refresh preview"
          @click="refreshDesignPreview()"
        >
          <v-icon size="15">mdi-refresh</v-icon>
        </v-btn>
        <v-btn
          variant="text"
          size="small"
          @click="triggerDesignGeneration"
        >
          <v-icon size="15" class="mr-1">mdi-plus</v-icon>
          Add
        </v-btn>
      </div>
    </div>

    <v-tabs-window v-model="activeDesignTab">
      <v-tabs-window-item v-for="d in designs" :key="d.id" :value="d.id">
        <!-- Generating -->
        <div v-if="d.status === 'generating'" class="section-empty">
          <v-progress-circular indeterminate color="secondary" size="40" class="mb-3" />
          <div>{{ designJobProgress.get(d.id) || 'Generating wireframe...' }}</div>
          <div class="text-caption text-medium-emphasis mt-1">
            Using {{ d.repo_name || 'default' }} design system
          </div>
        </div>
        <!-- Failed -->
        <div v-else-if="d.status === 'failed'" class="section-empty">
          <v-icon icon="mdi-alert-circle-outline" size="40" class="mb-3" color="error" />
          <div>Design generation failed</div>
          <v-btn variant="tonal" size="small" class="mt-3" @click="handleRegenerate(d.id)">
            <v-icon start size="15">mdi-refresh</v-icon>
            Retry
          </v-btn>
        </div>
        <!-- Edit mode -->
        <template v-else-if="editingDesignId === d.id">
          <textarea
            v-model="editDesign"
            class="section-editor"
            placeholder="HTML wireframe content..."
            @blur="saveDesignById(d.id)"
          />
        </template>
        <!-- Ready with HTML — use blob URL for full interactivity -->
        <template v-else-if="d.design_html">
          <iframe
            :key="d.id + '-' + designPreviewKey"
            :src="designPreviewUrl(d.id)"
            class="design-iframe"
          />
          <!-- Notes / Figma links -->
          <div class="design-notes-row">
            <v-text-field
              :model-value="d.notes || ''"
              variant="outlined"
              density="compact"
              placeholder="Add notes, Figma link, or design references..."
              hide-details
              prepend-inner-icon="mdi-link-variant"
              class="design-notes-input"
              @update:model-value="(v: string) => debouncedSaveNotes(d.id, v)"
            />
          </div>
        </template>
        <!-- Pending (no HTML yet) -->
        <div v-else class="section-empty">
          <v-icon icon="mdi-palette-outline" size="40" class="mb-3" />
          <div>Waiting for generation...</div>
        </div>
      </v-tabs-window-item>
    </v-tabs-window>
  </div>

  <!-- Empty state: generate or extracting -->
  <div v-else class="section-empty">
    <!-- Extraction in progress -->
    <v-alert
      v-if="extractingRepos.length > 0"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-4"
      style="max-width: 440px;"
    >
      <div class="d-flex align-center ga-2">
        <v-progress-circular indeterminate size="16" width="2" />
        <span>
          Design system extraction in progress for
          {{ extractingRepos.map(r => r.name).join(', ') }}...
        </span>
      </div>
      <div class="text-caption text-medium-emphasis mt-1">
        Wireframe generation will be available once extraction completes.
      </div>
    </v-alert>

    <v-icon icon="mdi-palette-outline" size="40" class="mb-3" />
    <div>No design yet</div>
    <div class="text-caption text-medium-emphasis mt-1 mb-3">
      Generate wireframes using your repos' design systems
    </div>
    <v-btn
      variant="tonal"
      size="small"
      :disabled="extractingRepos.length > 0 && designSystemStore.items.length === 0"
      @click="triggerDesignGeneration"
    >
      <v-icon start size="15">mdi-creation-outline</v-icon>
      Generate Wireframes
    </v-btn>
  </div>

  <!-- Repo selection dialog for design generation -->
  <v-dialog v-model="showRepoDialog" max-width="480">
    <v-card color="surface" class="pa-6">
      <div class="text-h6 mb-1">Select Repository</div>
      <div class="text-body-2 text-medium-emphasis mb-4">
        Select which repository to generate a design wireframe for.
      </div>
      <div v-if="availableReposLoading" class="d-flex justify-center py-4">
        <v-progress-circular indeterminate size="24" />
      </div>
      <div v-else-if="availableRepos.length > 0" style="max-height: 300px; overflow-y: auto;" class="mx-n2 px-2">
        <v-checkbox
          v-for="repo in availableRepos"
          :key="repo.id"
          v-model="selectedRepoIds"
          :value="repo.id"
          density="compact"
          hide-details
          class="mb-2"
        >
          <template #label>
            <div>
              <div class="text-body-2 font-weight-medium">{{ repo.name }}</div>
              <div class="text-caption text-medium-emphasis" style="word-break: break-all;">{{ repo.path }}</div>
            </div>
          </template>
        </v-checkbox>
      </div>
      <div v-else class="text-body-2 text-medium-emphasis py-2">
        No tracked repositories found. Add repositories in Settings.
      </div>
      <v-card-actions class="pa-0 mt-4">
        <v-spacer />
        <v-btn variant="text" @click="showRepoDialog = false">Cancel</v-btn>
        <v-btn color="primary" variant="flat" @click="confirmDesignGeneration">
          Generate
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { useSettingsStore } from '@/stores/settings'
import { useDesignSystemStore } from '@/stores/designSystem'
import { useJobSocket } from '@/composables/useJobSocket'
import type { BUDDesign, RepoInfo } from '@/types'

const props = defineProps<{
  budId: string
}>()

const emit = defineEmits<{
  (e: 'chat-message', msg: { role: 'ai'; text: string }): void
  (e: 'switch-to-design'): void
  (e: 'design-tab-change', designId: string): void
}>()

const budStore = useBUDStore()
const settingsStore = useSettingsStore()
const designSystemStore = useDesignSystemStore()
const { startTracking } = useJobSocket()

// Repos with design system extraction in progress
const extractingRepos = computed(() =>
  settingsStore.repos.filter(r => r.designSystemStatus === 'extracting'),
)

// Multi-design state
const designs = ref<BUDDesign[]>([])
const activeDesignTab = ref<string>('')
const editingDesignId = ref<string | null>(null)
const editDesign = ref('')
const showRepoDialog = ref(false)
const availableRepos = ref<RepoInfo[]>([])
const availableReposLoading = ref(false)
const selectedRepoIds = ref<string[]>([])
const designJobProgress = reactive(new Map<string, string>())
const designPreviewKey = ref(0)
let notesSaveTimer: ReturnType<typeof setTimeout> | null = null

const activeDesignObj = computed(() =>
  designs.value.find(d => d.id === activeDesignTab.value) || null,
)

// Blob URLs for iframe rendering (no auth required)
const designBlobUrls = reactive(new Map<string, string>())

function updateBlobUrls(): void {
  for (const url of designBlobUrls.values()) {
    URL.revokeObjectURL(url)
  }
  designBlobUrls.clear()
  for (const d of designs.value) {
    if (d.design_html) {
      const blob = new Blob([d.design_html], { type: 'text/html' })
      designBlobUrls.set(d.id, URL.createObjectURL(blob))
    }
  }
}

function designPreviewUrl(designId: string): string {
  return designBlobUrls.get(designId) || ''
}

function openDesignInTab(designId: string): void {
  const d = designs.value.find(dd => dd.id === designId)
  if (!d?.design_html) return
  const blob = new Blob([d.design_html], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

function refreshDesignPreview(): void {
  updateBlobUrls()
  designPreviewKey.value++
}

function debouncedSaveNotes(designId: string, value: string): void {
  if (notesSaveTimer) clearTimeout(notesSaveTimer)
  notesSaveTimer = setTimeout(async () => {
    await budStore.updateDesignNotes(props.budId, designId, value)
    const idx = designs.value.findIndex(d => d.id === designId)
    if (idx !== -1) designs.value[idx] = { ...designs.value[idx], notes: value }
  }, 800)
}

onMounted(() => loadDesigns())

async function loadDesigns(): Promise<void> {
  designs.value = await budStore.fetchDesigns(props.budId)
  updateBlobUrls()
  designPreviewKey.value++
  if (designs.value.length > 0 && !activeDesignTab.value) {
    activeDesignTab.value = designs.value[0].id
  }
  for (const d of designs.value) {
    if (d.status === 'generating' && d.job_id) {
      trackDesignJob(d.id, d.job_id)
    }
  }
}

async function triggerDesignGeneration(): Promise<void> {
  availableReposLoading.value = true
  await Promise.all([settingsStore.fetchRepos(), designSystemStore.fetchAll()])

  // Only show repos that have a design system extracted
  const dsRepoIds = new Set(designSystemStore.items.map(ds => ds.repo_id))
  const frontendRepos = settingsStore.repos.filter(
    r => r.status === 'active' && dsRepoIds.has(r.id),
  )
  availableRepos.value = frontendRepos
  availableReposLoading.value = false

  if (frontendRepos.length === 0) {
    await startDesignJobs([])
  } else if (frontendRepos.length === 1) {
    await startDesignJobs([frontendRepos[0].id])
  } else {
    selectedRepoIds.value = []
    showRepoDialog.value = true
  }
}

async function confirmDesignGeneration(): Promise<void> {
  showRepoDialog.value = false
  await startDesignJobs(selectedRepoIds.value)
}

async function startDesignJobs(repoIds: string[]): Promise<void> {
  const jobs = await budStore.generateDesigns(props.budId, repoIds)
  await loadDesigns()
  await budStore.fetchBUD(props.budId)  // Trigger agent banner via active_agent_task
  emit('switch-to-design')
  for (const job of jobs) {
    trackDesignJob(job.designId, job.jobId)
  }
}

function trackDesignJob(designId: string, jobId: string): void {
  startTracking(jobId, {
    onProgress(s) {
      designJobProgress.set(designId, s.statusMessage || 'Generating wireframe...')
    },
    async onComplete(data) {
      designJobProgress.delete(designId)
      await loadDesigns()
      const result = data as { reply?: string } | null
      if (result?.reply) {
        emit('chat-message', { role: 'ai', text: result.reply })
      }
    },
    async onError(err) {
      designJobProgress.delete(designId)
      const idx = designs.value.findIndex(d => d.id === designId)
      if (idx !== -1) {
        designs.value[idx] = { ...designs.value[idx], status: 'failed' }
      }
      emit('chat-message', { role: 'ai', text: `Design generation failed: ${err}` })
      await loadDesigns()
    },
  })
}

async function handleRegenerate(designId: string): Promise<void> {
  const result = await budStore.regenerateDesign(props.budId, designId)
  if (result) {
    const idx = designs.value.findIndex(d => d.id === designId)
    if (idx !== -1) {
      designs.value[idx] = { ...designs.value[idx], status: 'generating', job_id: result.jobId }
    }
    trackDesignJob(designId, result.jobId)
  }
}

async function saveDesignById(designId: string): Promise<void> {
  const d = designs.value.find(dd => dd.id === designId)
  if (d && editDesign.value !== (d.design_html || '')) {
    await budStore.updateDesignHtml(props.budId, designId, editDesign.value)
    const idx = designs.value.findIndex(dd => dd.id === designId)
    if (idx !== -1) designs.value[idx] = { ...designs.value[idx], design_html: editDesign.value }
  }
  editingDesignId.value = null
}

function toggleDesignEdit(): void {
  if (designs.value.length > 0 && activeDesignTab.value) {
    if (editingDesignId.value === activeDesignTab.value) {
      saveDesignById(activeDesignTab.value)
    } else {
      const d = designs.value.find(dd => dd.id === activeDesignTab.value)
      editDesign.value = d?.design_html || ''
      editingDesignId.value = activeDesignTab.value
    }
  }
}

// Notify parent when design tab changes (for chat history reloading)
watch(activeDesignTab, (newVal) => {
  if (newVal) emit('design-tab-change', newVal)
})

onBeforeUnmount(() => {
  for (const url of designBlobUrls.values()) {
    URL.revokeObjectURL(url)
  }
})

defineExpose({
  designs,
  activeDesignTab,
  activeDesignObj,
  editingDesignId,
  loadDesigns,
  toggleDesignEdit,
  refreshDesignPreview,
  triggerDesignGeneration,
  updateBlobUrls,
})
</script>

<style scoped>
.design-multi-panel {
  display: flex;
  flex-direction: column;
}

.design-sub-tabs-row {
  display: flex;
  align-items: center;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding: 0 8px;
}

.design-sub-tabs {
  flex: 1;
}

.design-notes-row {
  padding: 8px 12px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  background: rgba(var(--v-theme-on-surface), 0.02);
}

.design-notes-input {
  font-size: 13px;
}

.design-iframe {
  width: 100%;
  min-height: 600px;
  border: none;
  background: #0f1117;
}

.section-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px;
  color: rgba(var(--v-theme-on-surface), 0.35);
  font-size: 14px;
}

.section-empty .v-icon {
  opacity: 0.35;
}

.section-editor {
  display: block;
  width: 100%;
  min-height: 450px;
  padding: 24px 28px;
  border: none;
  outline: none;
  resize: vertical;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.87);
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
  font-size: 13px;
  line-height: 1.75;
  box-sizing: border-box;
}
</style>
