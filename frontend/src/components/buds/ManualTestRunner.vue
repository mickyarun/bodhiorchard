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
  <div class="manual-test-runner">
    <!-- Empty state -->
    <div v-if="cases.length === 0" class="empty-state">
      <v-icon icon="mdi-clipboard-check-outline" size="40" class="opacity-40 mb-2" />
      <div class="text-body-2 text-medium-emphasis">No manual test cases generated yet.</div>
    </div>

    <template v-else>
      <!-- Toolbar: progress + filter chips + search + bulk actions -->
      <div class="runner-toolbar">
        <!-- Row 1: progress bar + completion stats -->
        <div class="progress-row">
          <v-progress-linear
            :model-value="(counts.completed / cases.length) * 100"
            :color="progressColor"
            height="8"
            rounded
          />
          <span class="progress-label">
            {{ counts.completed }}/{{ cases.length }} completed
            <span v-if="counts.completed > 0" class="text-medium-emphasis">
              · {{ passRate }}% pass
            </span>
          </span>
        </div>

        <!-- Row 2: filter chips + search + bulk menu -->
        <div class="filter-row">
          <v-chip-group
            v-model="activeFilter"
            mandatory
            selected-class="filter-active"
            class="filter-chips"
          >
            <v-chip value="all" size="small" variant="tonal">
              All <span class="chip-count">{{ cases.length }}</span>
            </v-chip>
            <v-chip value="pending" size="small" variant="tonal">
              Pending <span class="chip-count">{{ counts.pending }}</span>
            </v-chip>
            <v-chip value="pass" size="small" variant="tonal" color="success">
              <v-icon start size="14">mdi-check-circle</v-icon>
              Pass <span class="chip-count">{{ counts.pass }}</span>
            </v-chip>
            <v-chip value="fail" size="small" variant="tonal" color="error">
              <v-icon start size="14">mdi-close-circle</v-icon>
              Fail <span class="chip-count">{{ counts.fail }}</span>
            </v-chip>
            <v-chip value="blocked" size="small" variant="tonal" color="warning">
              <v-icon start size="14">mdi-block-helper</v-icon>
              Blocked <span class="chip-count">{{ counts.blocked }}</span>
            </v-chip>
            <v-chip value="skipped" size="small" variant="tonal">
              <v-icon start size="14">mdi-skip-next</v-icon>
              Skipped <span class="chip-count">{{ counts.skipped }}</span>
            </v-chip>
          </v-chip-group>

          <v-spacer />

          <v-text-field
            v-model="search"
            placeholder="Search ID, title, description…"
            prepend-inner-icon="mdi-magnify"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            class="search-input"
          />

          <v-menu location="bottom end">
            <template #activator="{ props: menuProps }">
              <v-btn
                v-bind="menuProps"
                icon="mdi-dots-vertical"
                variant="text"
                size="small"
                :disabled="counts.pending === 0"
              />
            </template>
            <v-list density="compact">
              <v-list-item
                prepend-icon="mdi-check-all"
                :title="`Mark remaining ${counts.pending} as Pass`"
                @click="bulkMarkRemaining('pass')"
              />
              <v-list-item
                prepend-icon="mdi-skip-next"
                :title="`Mark remaining ${counts.pending} as Skipped`"
                @click="bulkMarkRemaining('skipped')"
              />
            </v-list>
          </v-menu>
        </div>

        <!-- Row 3: keyboard shortcut hints (only when a case is open) -->
        <div v-if="openCaseId" class="shortcut-hints">
          <kbd>P</kbd> Pass
          <kbd>F</kbd> Fail
          <kbd>B</kbd> Blocked
          <kbd>S</kbd> Skip
          <kbd>N</kbd> Next pending
          <kbd>Esc</kbd> Close
        </div>
      </div>

      <!-- Test case list -->
      <div class="case-list">
        <div
          v-for="tc in filteredCases"
          :key="tc.id"
          :ref="el => setCaseRef(tc.id, el)"
          :class="['test-case-card', `result-${tc.result}`, { open: openCaseId === tc.id }]"
        >
          <!-- Collapsed header (always visible) -->
          <button
            type="button"
            class="case-header"
            :aria-expanded="openCaseId === tc.id"
            @click="toggleCase(tc.id)"
          >
            <v-icon
              :icon="resultIcon[tc.result]"
              :color="resultColor[tc.result]"
              size="20"
              class="result-icon"
            />
            <v-chip
              size="x-small"
              :color="priorityColor[tc.priority]"
              variant="tonal"
              class="priority-chip"
            >
              {{ tc.priority }}
            </v-chip>
            <span class="case-title">
              <strong>{{ tc.id }}</strong>: {{ tc.title }}
            </span>
            <v-spacer />
            <span v-if="tc.tester_name && tc.result !== 'pending'" class="tester-attribution">
              <v-icon icon="mdi-account-outline" size="12" />
              {{ tc.tester_name }}
              <span v-if="tc.tested_at" class="text-medium-emphasis">· {{ relativeTime(tc.tested_at) }}</span>
            </span>
            <v-chip size="x-small" variant="outlined" class="category-chip">
              {{ tc.category }}
            </v-chip>
            <v-icon
              :icon="openCaseId === tc.id ? 'mdi-chevron-up' : 'mdi-chevron-down'"
              size="18"
              class="chevron"
            />
          </button>

          <!-- Expanded body -->
          <v-expand-transition>
            <div v-if="openCaseId === tc.id" class="case-body">
              <div v-if="tc.description" class="case-section">
                <div class="section-label">Description</div>
                <div class="section-text">{{ tc.description }}</div>
              </div>

              <div v-if="tc.preconditions" class="case-section">
                <div class="section-label">Preconditions</div>
                <div class="section-text precondition-box">{{ tc.preconditions }}</div>
              </div>

              <div v-if="tc.steps?.length" class="case-section">
                <div class="section-label">Steps</div>
                <ol class="steps-list">
                  <li v-for="(step, i) in tc.steps" :key="i">{{ step }}</li>
                </ol>
              </div>

              <div v-if="tc.expected_result" class="case-section">
                <div class="section-label">Expected Result</div>
                <div class="section-text expected-box">{{ tc.expected_result }}</div>
              </div>

              <!-- Result buttons -->
              <div class="case-section">
                <div class="section-label">Test Result</div>
                <div class="result-buttons">
                  <v-btn
                    v-for="option in resultOptions"
                    :key="option.value"
                    :color="option.color"
                    :variant="tc.result === option.value ? 'flat' : 'tonal'"
                    size="default"
                    class="result-btn"
                    @click="setResult(tc.id, option.value)"
                  >
                    <v-icon start size="18">{{ option.icon }}</v-icon>
                    {{ option.label }}
                    <kbd class="shortcut-key">{{ option.key }}</kbd>
                  </v-btn>
                </div>
                <!-- Revert: only meaningful once a verdict exists. The
                     handler erases tester / timestamp / stale notes so
                     the case is genuinely untested again. -->
                <div v-if="tc.result !== 'pending'" class="reset-row">
                  <v-btn
                    variant="text"
                    size="small"
                    prepend-icon="mdi-restore"
                    @click="setResult(tc.id, 'pending')"
                  >
                    Reset to pending
                    <v-tooltip activator="parent" location="top">
                      Un-mark this test (e.g. after a regression). Tester and
                      timestamp will be cleared so it can be re-tested fresh.
                    </v-tooltip>
                  </v-btn>
                </div>
              </div>

              <!-- Inline notes -->
              <div class="case-section">
                <v-textarea
                  :model-value="notesDraft[tc.id] ?? ''"
                  label="Notes"
                  :placeholder="
                    tc.result === 'fail' || tc.result === 'blocked'
                      ? 'Describe the failure: what you saw, repro steps, suspected cause…'
                      : 'Optional notes…'
                  "
                  rows="2"
                  auto-grow
                  max-rows="8"
                  variant="outlined"
                  density="compact"
                  hide-details="auto"
                  @update:model-value="(v) => (notesDraft[tc.id] = v)"
                />
                <div class="notes-hint text-caption text-medium-emphasis">
                  Notes are saved when you click a result button.
                </div>
              </div>

              <!-- Evidence section (with drag-and-drop) -->
              <div
                class="evidence-section"
                :class="{ 'drag-over': dragOverCaseId === tc.id }"
                @dragenter.prevent="dragOverCaseId = tc.id"
                @dragover.prevent="dragOverCaseId = tc.id"
                @dragleave="handleDragLeave(tc.id, $event)"
                @drop.prevent="handleDrop(tc.id, $event)"
              >
                <div class="section-label d-flex align-center">
                  <span>Evidence</span>
                  <v-spacer />
                  <v-btn
                    size="x-small"
                    variant="text"
                    prepend-icon="mdi-upload"
                    @click="triggerUpload(tc.id)"
                  >
                    Upload
                  </v-btn>
                </div>

                <div
                  v-if="getEvidenceForCase(tc.id).length === 0"
                  class="empty-evidence"
                >
                  <v-icon icon="mdi-image-plus-outline" size="20" class="mr-2 opacity-60" />
                  Drag images or files here, or click Upload
                </div>

                <div v-else class="evidence-grid">
                  <EvidenceTile
                    v-for="ev in getEvidenceForCase(tc.id)"
                    :key="ev.id"
                    :evidence="ev"
                    :bud-id="budId"
                    @delete="emit('delete-evidence', ev.id)"
                    @preview="(url) => openLightbox(ev, url)"
                  />
                </div>
              </div>
            </div>
          </v-expand-transition>
        </div>

        <!-- No matches (filter/search too strict) -->
        <div v-if="filteredCases.length === 0" class="no-matches">
          <v-icon icon="mdi-filter-off-outline" size="32" class="opacity-40 mb-2" />
          <div class="text-body-2 text-medium-emphasis">
            No test cases match your filter{{ search ? ' or search' : '' }}.
          </div>
          <v-btn
            size="small"
            variant="text"
            prepend-icon="mdi-close"
            class="mt-2"
            @click="clearFilters"
          >
            Clear filters
          </v-btn>
        </div>
      </div>
    </template>

    <!-- Hidden multi-file input for uploads (click + drag-drop both use this) -->
    <input
      ref="fileInputRef"
      type="file"
      style="display: none"
      multiple
      accept="image/*,.pdf,.txt,.log"
      @change="handleFileSelected"
    />

    <!-- Image lightbox -->
    <v-dialog v-model="lightboxOpen" max-width="min(90vw, 1200px)">
      <v-card class="lightbox-card">
        <v-toolbar density="compact" color="transparent">
          <v-toolbar-title class="text-body-2">{{ lightboxEvidence?.filename }}</v-toolbar-title>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="lightboxOpen = false" />
        </v-toolbar>
        <v-img
          v-if="lightboxUrl"
          :src="lightboxUrl"
          :alt="lightboxEvidence?.filename"
          max-height="80vh"
          contain
        />
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import type { ManualTestCase, TestEvidence } from '@/types'
import EvidenceTile from './EvidenceTile.vue'

type ManualResult = ManualTestCase['result']
// ``SetResult`` covers every result the UI can write to a case — the
// four terminal verdicts AND ``pending``, which is the explicit revert
// path used when a previous Pass/Fail needs to be re-tested. The
// backend schema accepts the same five values.
type SetResult = ManualResult
type FilterValue = 'all' | ManualResult

const props = defineProps<{
  cases: ManualTestCase[]
  evidence: TestEvidence[]
  budId: string
}>()

const emit = defineEmits<{
  (e: 'update-result', testCaseId: string, result: SetResult, notes?: string): void
  (e: 'upload-evidence', testCaseId: string, file: File): void
  (e: 'delete-evidence', evidenceId: string): void
}>()

// ── UI state ──────────────────────────────────────────────────────────

const activeFilter = ref<FilterValue>('all')
const search = ref('')
const openCaseId = ref<string | null>(null)
const dragOverCaseId = ref<string | null>(null)
const uploadTargetCaseId = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

// Notes buffer — one draft per case id. Populated from tc.notes when the
// card opens; flushed to backend via the update-result emit when a result
// button is clicked. Unflushed drafts are intentionally ephemeral.
const notesDraft = reactive<Record<string, string>>({})

// Lightbox state
const lightboxOpen = ref(false)
const lightboxEvidence = ref<TestEvidence | null>(null)
const lightboxUrl = ref<string | null>(null)

// Case ref map for scrollIntoView on auto-advance. Vue 3's :ref callback
// may pass either an Element (HTML tags) or a ComponentPublicInstance
// (Vue components). Our v-for target is a plain <div>, so we only ever
// receive Element or null — but TypeScript requires the broader type.
const caseRefs = new Map<string, HTMLElement>()
function setCaseRef(id: string, el: Element | ComponentPublicInstance | null): void {
  if (el && el instanceof HTMLElement) {
    caseRefs.set(id, el)
  } else {
    caseRefs.delete(id)
  }
}

// ── Lookup tables ─────────────────────────────────────────────────────

const resultColor: Record<ManualResult, string> = {
  pending: 'grey',
  pass: 'success',
  fail: 'error',
  blocked: 'warning',
  skipped: 'grey',
}

const resultIcon: Record<ManualResult, string> = {
  pending: 'mdi-circle-outline',
  pass: 'mdi-check-circle',
  fail: 'mdi-close-circle',
  blocked: 'mdi-block-helper',
  skipped: 'mdi-skip-next-circle-outline',
}

const priorityColor: Record<ManualTestCase['priority'], string> = {
  critical: 'error',
  high: 'warning',
  medium: 'info',
  low: 'grey',
}

const resultOptions: { value: SetResult; label: string; icon: string; color: string; key: string }[] = [
  { value: 'pass', label: 'Pass', icon: 'mdi-check-circle', color: 'success', key: 'P' },
  { value: 'fail', label: 'Fail', icon: 'mdi-close-circle', color: 'error', key: 'F' },
  { value: 'blocked', label: 'Blocked', icon: 'mdi-block-helper', color: 'warning', key: 'B' },
  { value: 'skipped', label: 'Skip', icon: 'mdi-skip-next', color: 'grey', key: 'S' },
]

// ── Derived state ─────────────────────────────────────────────────────

const counts = computed(() => {
  const c = { pending: 0, pass: 0, fail: 0, blocked: 0, skipped: 0, completed: 0 }
  for (const tc of props.cases) {
    c[tc.result]++
    if (tc.result !== 'pending') c.completed++
  }
  return c
})

const passRate = computed(() => {
  if (counts.value.completed === 0) return 0
  return Math.round((counts.value.pass / counts.value.completed) * 100)
})

const progressColor = computed(() => {
  if (props.cases.length === 0) return 'grey'
  const pct = (counts.value.completed / props.cases.length) * 100
  if (pct === 100) return counts.value.fail === 0 ? 'success' : 'warning'
  if (pct > 50) return 'primary'
  return 'warning'
})

const filteredCases = computed(() => {
  let list = props.cases
  if (activeFilter.value !== 'all') {
    list = list.filter((c) => c.result === activeFilter.value)
  }
  if (search.value.trim()) {
    const q = search.value.toLowerCase()
    list = list.filter(
      (c) =>
        c.id.toLowerCase().includes(q) ||
        c.title.toLowerCase().includes(q) ||
        (c.description ?? '').toLowerCase().includes(q),
    )
  }
  return list
})

function getEvidenceForCase(caseId: string): TestEvidence[] {
  return props.evidence.filter((e) => e.test_case_id === caseId)
}

// ── Case open/close + auto-advance ────────────────────────────────────

function toggleCase(caseId: string): void {
  if (openCaseId.value === caseId) {
    openCaseId.value = null
  } else {
    openCaseId.value = caseId
    // Populate the notes draft from saved notes so the textarea shows
    // existing content when reopening a previously-tested case.
    const tc = props.cases.find((c) => c.id === caseId)
    notesDraft[caseId] = tc?.notes ?? ''
  }
}

async function scrollCaseIntoView(caseId: string): Promise<void> {
  await nextTick()
  const el = caseRefs.get(caseId)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

function findNextPending(fromCaseId: string): ManualTestCase | undefined {
  // Advance through the CURRENTLY FILTERED list so auto-advance respects
  // the active filter. If the user is filtering to "pending" and marks a
  // case as pass, it drops out of the filtered list — the "next" is then
  // the case that now occupies the current index.
  const list = filteredCases.value
  const idx = list.findIndex((c) => c.id === fromCaseId)
  // Try after-current first
  for (let i = idx + 1; i < list.length; i++) {
    if (list[i].result === 'pending') return list[i]
  }
  // Wrap to before-current — useful when the tester jumps around
  for (let i = 0; i < idx; i++) {
    if (list[i].result === 'pending') return list[i]
  }
  return undefined
}

function setResult(caseId: string, result: SetResult): void {
  const notes = notesDraft[caseId]?.trim() || undefined
  emit('update-result', caseId, result, notes)
  // Auto-advance to the next pending case. The optimistic update in the
  // composable has already mutated tc.result, so filteredCases will
  // re-compute before we read it.
  nextTick(() => {
    const next = findNextPending(caseId)
    if (next) {
      openCaseId.value = next.id
      notesDraft[next.id] = next.notes ?? ''
      scrollCaseIntoView(next.id)
    } else {
      openCaseId.value = null
    }
  })
}

function bulkMarkRemaining(result: SetResult): void {
  // Fire parallel PATCHes for all pending cases. Each case is a distinct
  // row by test_case_id, so there's no row-level race between them.
  for (const tc of props.cases) {
    if (tc.result === 'pending') {
      emit('update-result', tc.id, result)
    }
  }
  openCaseId.value = null
}

function clearFilters(): void {
  activeFilter.value = 'all'
  search.value = ''
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diffMs = Date.now() - then
  const sec = Math.round(diffMs / 1000)
  if (sec < 60) return 'just now'
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.round(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.round(hr / 24)
  if (day < 7) return `${day}d ago`
  return new Date(iso).toLocaleDateString()
}

// ── Evidence upload (click + drag-drop share the same flow) ───────────

function triggerUpload(caseId: string): void {
  uploadTargetCaseId.value = caseId
  fileInputRef.value?.click()
}

function handleFileSelected(event: Event): void {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (files && uploadTargetCaseId.value) {
    for (const file of Array.from(files)) {
      emit('upload-evidence', uploadTargetCaseId.value, file)
    }
  }
  input.value = ''
}

function handleDragLeave(caseId: string, event: DragEvent): void {
  // dragleave fires when crossing between children too — only clear if we
  // actually left the evidence section.
  const related = event.relatedTarget as Node | null
  const current = event.currentTarget as HTMLElement
  if (!related || !current.contains(related)) {
    if (dragOverCaseId.value === caseId) dragOverCaseId.value = null
  }
}

function handleDrop(caseId: string, event: DragEvent): void {
  dragOverCaseId.value = null
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return
  for (const file of Array.from(files)) {
    emit('upload-evidence', caseId, file)
  }
}

// ── Lightbox ──────────────────────────────────────────────────────────

function openLightbox(evidence: TestEvidence, blobUrl: string | null): void {
  if (!blobUrl) return // thumbnail not ready yet — just skip the open
  lightboxEvidence.value = evidence
  lightboxUrl.value = blobUrl
  lightboxOpen.value = true
}

// ── Keyboard shortcuts ────────────────────────────────────────────────

function handleKeydown(e: KeyboardEvent): void {
  if (!openCaseId.value) return

  // Never hijack typing inside a text input or textarea — otherwise
  // pressing "P" in the notes field would mark the case as pass.
  const target = e.target as HTMLElement | null
  if (target) {
    const tag = target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable) return
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return

  const openCase = props.cases.find((c) => c.id === openCaseId.value)
  if (!openCase) return

  const key = e.key.toLowerCase()
  switch (key) {
    case 'p':
      e.preventDefault()
      setResult(openCase.id, 'pass')
      break
    case 'f':
      e.preventDefault()
      setResult(openCase.id, 'fail')
      break
    case 'b':
      e.preventDefault()
      setResult(openCase.id, 'blocked')
      break
    case 's':
      e.preventDefault()
      setResult(openCase.id, 'skipped')
      break
    case 'n': {
      e.preventDefault()
      const next = findNextPending(openCase.id)
      if (next) {
        openCaseId.value = next.id
        notesDraft[next.id] = next.notes ?? ''
        scrollCaseIntoView(next.id)
      }
      break
    }
    case 'escape':
      e.preventDefault()
      openCaseId.value = null
      break
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})

// If the active filter hides the currently open case, close it so the
// keyboard shortcuts don't act on an invisible target.
watch(filteredCases, (list) => {
  if (openCaseId.value && !list.some((c) => c.id === openCaseId.value)) {
    openCaseId.value = null
  }
})
</script>

<style scoped>
.manual-test-runner {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 16px;
  text-align: center;
}

/* ── Toolbar ────────────────────────────────────────────────────────── */

.runner-toolbar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 16px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
}

.progress-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-row :deep(.v-progress-linear) {
  flex: 1;
}

.progress-label {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.75);
  white-space: nowrap;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-chips {
  flex: 0 1 auto;
}

.filter-chips :deep(.v-slide-group__content) {
  gap: 6px;
}

.chip-count {
  margin-left: 4px;
  padding: 1px 6px;
  background: rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  font-size: 10px;
  font-weight: 600;
}

.filter-active .chip-count {
  background: rgba(var(--v-theme-on-surface), 0.2);
}

.search-input {
  min-width: 200px;
  max-width: 280px;
}

.shortcut-hints {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  padding-top: 4px;
  border-top: 1px dashed rgba(var(--v-theme-on-surface), 0.08);
}

.shortcut-hints kbd {
  display: inline-block;
  padding: 1px 6px;
  margin-right: 4px;
  background: rgba(var(--v-theme-on-surface), 0.1);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 3px;
  font-family: ui-monospace, monospace;
  font-size: 10px;
  font-weight: 600;
}

/* ── Case list ──────────────────────────────────────────────────────── */

.case-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.test-case-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-left-width: 4px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(var(--v-theme-surface), 1);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.test-case-card.result-pending {
  border-left-color: rgba(var(--v-theme-on-surface), 0.2);
}
.test-case-card.result-pass {
  border-left-color: rgb(var(--v-theme-success));
}
.test-case-card.result-fail {
  border-left-color: rgb(var(--v-theme-error));
}
.test-case-card.result-blocked {
  border-left-color: rgb(var(--v-theme-warning));
}
.test-case-card.result-skipped {
  border-left-color: rgba(var(--v-theme-on-surface), 0.25);
}

.test-case-card.open {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
}

/* ── Case header ────────────────────────────────────────────────────── */

.case-header {
  all: unset;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  width: 100%;
  box-sizing: border-box;
  cursor: pointer;
}

.case-header:hover {
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.case-header:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.result-icon {
  flex-shrink: 0;
}

.priority-chip {
  flex-shrink: 0;
  text-transform: capitalize;
}

.case-title {
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.92);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}

.tester-attribution {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.75);
  flex-shrink: 0;
}

.category-chip {
  flex-shrink: 0;
  text-transform: capitalize;
}

.chevron {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

/* ── Case body ──────────────────────────────────────────────────────── */

.case-body {
  padding: 4px 16px 16px 16px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.case-section {
  margin-top: 14px;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-bottom: 6px;
}

.section-text {
  font-size: 13px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.precondition-box {
  background: rgba(255, 193, 7, 0.08);
  border-left: 3px solid rgba(255, 193, 7, 0.6);
  padding: 8px 12px;
  border-radius: 0 4px 4px 0;
}

.expected-box {
  background: rgba(76, 175, 80, 0.08);
  border-left: 3px solid rgba(76, 175, 80, 0.6);
  padding: 8px 12px;
  border-radius: 0 4px 4px 0;
}

.steps-list {
  padding-left: 22px;
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}
.steps-list li {
  margin-bottom: 4px;
}

/* ── Result buttons ─────────────────────────────────────────────────── */

.result-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.result-btn {
  text-transform: none;
  letter-spacing: 0;
}

.reset-row {
  margin-top: 6px;
  display: flex;
  justify-content: flex-end;
}

.shortcut-key {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 6px;
  background: rgba(0, 0, 0, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 3px;
  font-family: ui-monospace, monospace;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.2;
}

.notes-hint {
  margin-top: 4px;
}

/* ── Evidence section ───────────────────────────────────────────────── */

.evidence-section {
  margin-top: 14px;
  padding: 12px;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 8px;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.evidence-section.drag-over {
  background: rgba(var(--v-theme-primary), 0.08);
  border-color: rgb(var(--v-theme-primary));
  border-style: solid;
}

.empty-evidence {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.evidence-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 10px;
}

/* ── No-matches state ───────────────────────────────────────────────── */

.no-matches {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 16px;
  text-align: center;
}

/* ── Lightbox ───────────────────────────────────────────────────────── */

.lightbox-card :deep(.v-img) {
  background: rgba(0, 0, 0, 0.85);
}
</style>
