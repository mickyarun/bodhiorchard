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

<template>
  <div class="settings-page">
    <!-- Header -->
    <div class="settings-header pa-6 pb-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h5 font-weight-bold">Design Systems</div>
          <div class="text-body-2 text-medium-emphasis">
            Extract and manage design tokens from your tracked repositories
          </div>
        </div>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="extractDialog = true">
          Extract New
        </v-btn>
      </div>

      <v-alert v-if="dsStore.error" type="error" variant="tonal" class="mt-4" closable>
        {{ dsStore.error }}
      </v-alert>

      <v-alert v-if="extracting || jobActive" type="info" variant="tonal" class="mt-4">
        <div class="d-flex align-center ga-3">
          <v-progress-circular indeterminate size="18" width="2" color="info" />
          <span>{{ extractProgress || 'Extracting design system...' }}</span>
          <span
            v-if="jobStatus?.progressPct"
            class="text-caption text-medium-emphasis"
          >
            ({{ jobStatus.progressPct }}%)
          </span>
        </div>
      </v-alert>
    </div>

    <!-- Content -->
    <div class="px-6 pb-6">
      <!-- Loading -->
      <div v-if="dsStore.loading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <!-- Empty state -->
      <div v-else-if="dsStore.items.length === 0" class="text-center py-12">
        <v-icon icon="mdi-palette-outline" size="48" class="mb-4" style="opacity: 0.3" />
        <div class="text-body-1 text-medium-emphasis mb-2">
          No design systems extracted yet.
        </div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          Extract from a tracked repository to get started.
        </div>
        <v-btn variant="tonal" color="primary" @click="extractDialog = true">
          <v-icon start>mdi-plus</v-icon>
          Extract from Repository
        </v-btn>
      </div>

      <!-- Cards -->
      <div v-else class="d-flex flex-column ga-4">
        <v-card
          v-for="ds in dsStore.items"
          :key="ds.id"
          variant="outlined"
          class="ds-card"
        >
          <v-card-text>
            <div class="d-flex align-center ga-3 mb-3">
              <v-icon icon="mdi-palette-outline" size="20" color="secondary" />
              <span class="text-body-1 font-weight-medium flex-grow-1">
                {{ ds.repo_name || 'Unknown Repository' }}
              </span>
              <v-chip
                v-if="ds.is_default"
                color="primary"
                variant="tonal"
                size="x-small"
                label
              >
                DEFAULT
              </v-chip>
              <v-chip
                v-if="ds.is_customised"
                color="success"
                variant="tonal"
                size="x-small"
                label
                prepend-icon="mdi-pencil-outline"
              >
                CUSTOMISED
              </v-chip>
              <span class="text-caption text-medium-emphasis">
                Extracted {{ formatRelative(ds.extracted_at) }}
              </span>
            </div>

            <div class="text-body-2 text-medium-emphasis mb-4">
              {{ extractSummary(ds.content) }}
            </div>

            <div class="d-flex ga-2">
              <v-btn
                variant="text"
                size="small"
                @click="previewItem = ds; previewDialog = true"
              >
                <v-icon start size="15">mdi-eye-outline</v-icon>
                Preview
              </v-btn>
              <v-btn
                variant="text"
                size="small"
                @click="openCustomise(ds)"
              >
                <v-icon start size="15">mdi-pencil-outline</v-icon>
                Customise
              </v-btn>
              <v-btn
                variant="text"
                size="small"
                :loading="extractingId === ds.id"
                @click="reExtract(ds)"
              >
                <v-icon start size="15">mdi-refresh</v-icon>
                Re-extract
              </v-btn>
              <v-btn
                v-if="!ds.is_default"
                variant="text"
                size="small"
                @click="dsStore.setDefault(ds.id)"
              >
                <v-icon start size="15">mdi-star-outline</v-icon>
                Set Default
              </v-btn>
              <v-spacer />
              <v-btn
                variant="text"
                size="small"
                color="error"
                @click="deleteTarget = ds; confirmDelete = true"
              >
                <v-icon size="15">mdi-delete-outline</v-icon>
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </div>
    </div>

    <!-- Extract dialog -->
    <v-dialog v-model="extractDialog" max-width="440">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 mb-4">Extract Design System</div>

        <v-select
          v-model="selectedRepoId"
          :items="repoItems"
          label="Repository"
          item-title="text"
          item-value="value"
          variant="outlined"
          density="comfortable"
          class="mb-3"
        />

        <v-checkbox
          v-model="extractAsDefault"
          label="Set as org-wide default"
          density="compact"
          hide-details
          class="mb-4"
        />

        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="extractDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :disabled="!selectedRepoId"
            :loading="extracting"
            @click="doExtract"
          >
            Extract
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Preview dialog (merged extracted + custom) -->
    <v-dialog v-model="previewDialog" max-width="700">
      <v-card color="surface" class="pa-6">
        <div class="d-flex align-center mb-4 ga-2">
          <span class="text-h6 flex-grow-1">
            {{ previewItem?.repo_name || 'Design System' }}
          </span>
          <v-chip
            v-if="previewItem?.is_customised"
            color="success"
            variant="tonal"
            size="x-small"
            label
            prepend-icon="mdi-pencil-outline"
          >
            CUSTOMISED
          </v-chip>
          <v-btn icon="mdi-close" size="small" variant="text" @click="previewDialog = false" />
        </div>
        <div
          class="preview-content rendered-markdown"
          v-html="renderMarkdown(previewItem?.merged_content || previewItem?.content || '')"
        />
      </v-card>
    </v-dialog>

    <!-- Customise dialog — writes only custom_content; never touches the
         extracted content, so re-scans cannot clobber what you save here. -->
    <SettingsDesignSystemCustomiseDialog
      v-model="customiseDialog"
      :target="customiseTarget"
    />

    <!-- Delete confirmation -->
    <v-dialog v-model="confirmDelete" max-width="400">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 mb-2">Delete Design System?</div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          This will remove the design system for {{ deleteTarget?.repo_name || 'this repo' }}.
        </div>
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="confirmDelete = false">Cancel</v-btn>
          <v-btn color="error" variant="flat" @click="doDelete">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useDesignSystemStore, type DesignSystemItem } from '@/stores/designSystem'
import { useSettingsStore } from '@/stores/settings'
import { useJobSocket } from '@/composables/useJobSocket'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import SettingsDesignSystemCustomiseDialog from './SettingsDesignSystemCustomiseDialog.vue'

const dsStore = useDesignSystemStore()
const settingsStore = useSettingsStore()
const { status: jobStatus, isActive: jobActive, startTracking, stopTracking } = useJobSocket()

// Extract dialog
const extractDialog = ref(false)
const selectedRepoId = ref<string | null>(null)
const extractAsDefault = ref(false)
const extracting = ref(false)
const extractingId = ref<string | null>(null)
const extractProgress = ref('')

// Preview dialog
const previewDialog = ref(false)
const previewItem = ref<DesignSystemItem | null>(null)

// Customise dialog state — edits ONLY the user customisation layer; the
// extractor owns the base ``content`` field and is never reached from here.
// All draft / saving / error state lives inside the dialog component;
// we only hold open/closed and the target row at this level.
const customiseDialog = ref(false)
const customiseTarget = ref<DesignSystemItem | null>(null)

// Delete dialog
const confirmDelete = ref(false)
const deleteTarget = ref<DesignSystemItem | null>(null)

const repoItems = computed(() =>
  settingsStore.repos
    .filter(r => r.status === 'active')
    .map(r => ({ text: r.name, value: r.id })),
)

onMounted(async () => {
  await Promise.all([dsStore.fetchAll(), settingsStore.fetchRepos()])
})

const EXTRACT_TIMEOUT_MS = 660_000 // 11 min — must exceed backend's max job timeout

function trackExtraction(jobId: string, onDone: () => void): void {
  // Safety timeout — if WS and polling both fail, don't spin forever
  const safetyTimer = setTimeout(() => {
    stopTracking()
    dsStore.error = 'Extraction timed out. Check the design systems list — it may have completed.'
    dsStore.fetchAll()
    onDone()
  }, EXTRACT_TIMEOUT_MS)

  const cleanup = () => {
    clearTimeout(safetyTimer)
    onDone()
  }

  startTracking(jobId, {
    onProgress(s) {
      extractProgress.value = s.statusMessage || 'Extracting...'
    },
    async onComplete(result: unknown) {
      await dsStore.fetchAll()
      const r = result as { method?: string; error?: string } | null
      if (r?.method === 'regex_fallback' && r?.error) {
        dsStore.error = `AI extraction failed (${r.error}). Used regex fallback — results may be incomplete.`
      }
      cleanup()
    },
    onError(err) {
      dsStore.error = err
      cleanup()
    },
  })
}

async function doExtract(): Promise<void> {
  if (!selectedRepoId.value) return
  extracting.value = true
  extractProgress.value = 'Submitting...'
  const jobId = await dsStore.extract(selectedRepoId.value, extractAsDefault.value)
  if (!jobId || typeof jobId !== 'string' || jobId.length < 10) {
    extracting.value = false
    if (jobId) dsStore.error = 'Invalid job ID received from server.'
    return
  }
  extractDialog.value = false
  trackExtraction(jobId, () => {
    extracting.value = false
    extractProgress.value = ''
    selectedRepoId.value = null
    extractAsDefault.value = false
  })
}

async function reExtract(ds: DesignSystemItem): Promise<void> {
  extractingId.value = ds.id
  extractProgress.value = 'Submitting...'
  const jobId = await dsStore.extract(ds.repo_id, ds.is_default)
  if (!jobId) {
    extractingId.value = null
    return
  }
  trackExtraction(jobId, () => {
    extractingId.value = null
    extractProgress.value = ''
  })
}

async function doDelete(): Promise<void> {
  if (!deleteTarget.value) return
  await dsStore.remove(deleteTarget.value.id)
  confirmDelete.value = false
  deleteTarget.value = null
}

function openCustomise(ds: DesignSystemItem): void {
  customiseTarget.value = ds
  customiseDialog.value = true
}

function formatRelative(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return 'today'
  if (days === 1) return '1 day ago'
  return `${days}d ago`
}

function extractSummary(content: string): string {
  const colorCount = (content.match(/`#[0-9a-fA-F]{3,8}`/g) || []).length
  const fontMatch = content.match(/font-family[^;]*?['"]([^'"]+)['"]/i)
  const font = fontMatch ? fontMatch[1] : null
  const parts: string[] = []
  if (colorCount > 0) parts.push(`${colorCount} colors`)
  if (font) parts.push(`${font} font`)
  if (content.includes('Vuetify')) parts.push('Vuetify')
  return parts.length > 0 ? parts.join(' · ') : 'Design system extracted'
}

function renderMarkdown(md: string): string {
  if (!md) return ''
  const raw = marked.parse(md, { async: false }) as string
  return DOMPurify.sanitize(raw)
}
</script>

<style scoped>
.settings-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.settings-header {
  flex-shrink: 0;
}

.ds-card {
  border-color: rgba(var(--v-theme-on-surface), 0.08) !important;
}

.ds-card .v-btn {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
  font-size: 12px;
}

.preview-content {
  max-height: 500px;
  overflow-y: auto;
  padding: 16px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.7;
}

.preview-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12px;
}

.preview-content :deep(th),
.preview-content :deep(td) {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  padding: 6px 10px;
  text-align: left;
}

.preview-content :deep(th) {
  background: rgba(var(--v-theme-on-surface), 0.04);
  font-weight: 600;
}

.preview-content :deep(code) {
  background: rgba(var(--v-theme-on-surface), 0.07);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.87em;
}

.preview-content :deep(pre) {
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 6px;
  padding: 12px 16px;
  margin: 8px 0;
  overflow-x: auto;
}

.preview-content :deep(pre code) {
  background: none;
  padding: 0;
}

.preview-content :deep(h2) {
  font-size: 1.1em;
  margin: 16px 0 8px;
}

.preview-content :deep(h3) {
  font-size: 1em;
  margin: 12px 0 6px;
}
</style>
