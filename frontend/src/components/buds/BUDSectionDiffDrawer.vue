<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 -->

<!-- Per-section "Google Docs" version-history drawer.

     Opens from the section toolbar (Requirements / Tech Spec / Design /
     Testing / Code Review). Lists versions scoped to that section's
     phase only, so the user sees only edits that affect what they're
     looking at. Selecting a version renders a unified line-level diff
     between THAT snapshot and the current BUD content, with green
     additions and red deletions in the gutter. A Restore button on
     each selected version POSTs to /buds/{id}/revert/{phase}/{v},
     which produces a new ``source='revert'`` row server-side — the
     history is append-only so the action is itself reversible.

     The cross-phase audit view ("everything that ever changed across
     all phases, with source badges") still lives behind the History
     button in the page header — different audience, different
     question. -->
<template>
  <v-navigation-drawer
    v-model="open"
    location="right"
    temporary
    width="900"
    class="diff-drawer"
  >
    <div class="diff-drawer__header">
      <div class="d-flex align-center ga-2">
        <v-icon icon="mdi-text-box-search-outline" size="20" />
        <div>
          <div class="text-subtitle-1 font-weight-bold">{{ sectionLabel }} history</div>
          <div class="text-caption text-medium-emphasis">
            Showing edits to <strong>{{ sectionLabel }}</strong> only ·
            {{ phase }} phase
          </div>
        </div>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
      </div>
    </div>

    <div class="diff-drawer__body">
      <!-- Left rail — version list scoped to this phase. -->
      <aside class="diff-rail">
        <div v-if="loading && !versions.length" class="diff-rail__empty">
          <v-progress-circular indeterminate size="20" />
        </div>
        <div v-else-if="!versions.length" class="diff-rail__empty">
          <v-icon icon="mdi-clock-outline" size="22" class="text-medium-emphasis" />
          <div class="text-caption text-medium-emphasis text-center mt-1">
            No history for this section yet.
          </div>
        </div>
        <button
          v-for="v in versions"
          :key="v.id"
          type="button"
          class="diff-rail__item"
          :class="{ 'diff-rail__item--active': selectedVersion?.id === v.id }"
          @click="selectVersion(v)"
        >
          <div class="d-flex align-center ga-2">
            <v-chip
              :color="sourceColor(v.source)"
              size="x-small"
              variant="tonal"
              class="font-weight-bold text-uppercase"
            >
              {{ v.source }}
            </v-chip>
            <span class="text-body-2 font-weight-medium">v{{ v.version_no }}</span>
          </div>
          <div class="text-caption text-medium-emphasis mt-1">
            {{ relativeTime(v.edited_at) }}
          </div>
          <div v-if="v.reason" class="text-caption text-medium-emphasis mt-1 diff-rail__reason">
            {{ v.reason }}
          </div>
        </button>
      </aside>

      <!-- Right pane — diff viewer. -->
      <section class="diff-pane">
        <header class="diff-pane__header">
          <div class="text-body-2">
            <template v-if="selectedVersion">
              Comparing
              <strong>v{{ selectedVersion.version_no }}</strong>
              ({{ relativeTime(selectedVersion.edited_at) }})
              → <strong>current</strong>
            </template>
            <template v-else>
              Select a version on the left to see what changed.
            </template>
          </div>
          <div v-if="diffStats" class="diff-stats">
            <span class="diff-stats__added">+{{ diffStats.added }}</span>
            <span class="diff-stats__removed">−{{ diffStats.removed }}</span>
          </div>
          <v-spacer />
          <v-tooltip :text="restoreDisabledReason || 'Restore this version'" location="top">
            <template #activator="{ props: tipProps }">
              <span v-bind="tipProps">
                <v-btn
                  size="small"
                  color="warning"
                  variant="flat"
                  prepend-icon="mdi-undo"
                  :disabled="!selectedVersion || !!restoreDisabledReason"
                  :loading="restoring"
                  @click="confirmRestore = true"
                >
                  Restore
                </v-btn>
              </span>
            </template>
          </v-tooltip>
        </header>

        <div v-if="loadingDetail" class="diff-pane__placeholder">
          <v-progress-circular indeterminate size="28" />
        </div>
        <div v-else-if="!selectedVersion" class="diff-pane__placeholder">
          <v-icon icon="mdi-arrow-left-circle-outline" size="32" class="text-medium-emphasis" />
          <div class="text-body-2 text-medium-emphasis mt-2">
            Pick a version on the left to view the diff.
          </div>
        </div>
        <div v-else-if="diffLines.length === 0" class="diff-pane__placeholder">
          <v-icon icon="mdi-equal-box" size="28" class="text-medium-emphasis" />
          <div class="text-body-2 text-medium-emphasis mt-2">
            No content changes between this version and the current text.
          </div>
        </div>
        <div v-else class="diff-pane__body">
          <div
            v-for="(line, idx) in diffLines"
            :key="idx"
            class="diff-line"
            :class="diffLineClass(line.type)"
          >
            <span class="diff-line__marker">{{ markerFor(line.type) }}</span>
            <span class="diff-line__text">{{ line.text || ' ' }}</span>
          </div>
        </div>
      </section>
    </div>

    <v-dialog v-model="confirmRestore" max-width="460">
      <v-card class="pa-5">
        <div class="text-h6 font-weight-bold mb-2">
          Restore {{ sectionLabel }} to v{{ selectedVersion?.version_no }}?
        </div>
        <p class="text-body-2 text-medium-emphasis mb-4">
          The current content will be replaced with this version's content.
          A new <code>revert</code> entry is added so today's version is NOT
          destroyed — you can switch back to it from this drawer later.
        </p>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmRestore = false">Cancel</v-btn>
          <v-btn color="warning" variant="flat" :loading="restoring" @click="doRestore">
            Restore
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="2500"
      location="bottom"
    >
      {{ snackbar.text }}
    </v-snackbar>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { diffLines as diffLinesFn } from 'diff'
import { computed, ref, watch } from 'vue'
import api from '@/services/api'

interface BUDVersionSummary {
  id: string
  phase: string
  version_no: number
  source: 'ui' | 'mcp' | 'agent' | 'migration' | 'revert'
  edited_by: string | null
  mcp_token_id: string | null
  reason: string | null
  edited_at: string
}

interface BUDVersionDetail extends BUDVersionSummary {
  // Snapshot is a JSONB blob; the keys we care about per phase are
  // resolved through ``snapshotKey`` below. Other keys exist (title,
  // assignee_id, etc.) but the diff viewer is scoped to the active
  // section's content field — cross-phase audit lives in the header
  // History dialog.
  snapshot: Record<string, unknown>
}

interface Props {
  modelValue: boolean
  budId: string
  budStatus: string
  // The active section the toolbar was clicked from. We translate this
  // to a (phase, snapshot key) pair locally — kept here rather than
  // passed in so adding a new section only touches this component.
  section: 'requirements' | 'tech-spec' | 'design' | 'testing' | 'code-review'
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  reverted: []
}>()

// Two-way bind via the v-navigation-drawer's v-model.
const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// Section → (phase, snapshot key). DESIGN snaps under the sentinel
// ``__design_html`` because design content lives in bud_designs, not
// bud_documents — see backend/app/repositories/bud_version.py.
const SECTION_MAP: Record<
  Props['section'],
  { phase: string; label: string; field: string; format: 'markdown' | 'html' | 'json' }
> = {
  requirements: {
    phase: 'bud',
    label: 'Requirements',
    field: 'requirements_md',
    format: 'markdown',
  },
  'tech-spec': {
    phase: 'tech_arch',
    label: 'Tech Spec',
    field: 'tech_spec_md',
    format: 'markdown',
  },
  design: { phase: 'design', label: 'Design', field: '__design_html', format: 'html' },
  testing: { phase: 'testing', label: 'Test Plan', field: 'test_plan_md', format: 'markdown' },
  'code-review': {
    phase: 'code_review',
    label: 'Code Review',
    field: 'code_review_comments',
    format: 'json',
  },
}

const sectionConfig = computed(() => SECTION_MAP[props.section])
const phase = computed(() => sectionConfig.value.phase)
const sectionLabel = computed(() => sectionConfig.value.label)

const versions = ref<BUDVersionSummary[]>([])
const loading = ref(false)
const selectedVersion = ref<BUDVersionDetail | null>(null)
const loadingDetail = ref(false)
const currentContent = ref<string>('')

const restoring = ref(false)
const confirmRestore = ref(false)

const snackbar = ref<{ show: boolean; text: string; color: 'success' | 'error' }>({
  show: false,
  text: '',
  color: 'success',
})

function notify(text: string, color: 'success' | 'error' = 'success'): void {
  snackbar.value = { show: true, text, color }
}

function sourceColor(source: BUDVersionSummary['source']): string {
  switch (source) {
    case 'ui':
      return 'primary'
    case 'mcp':
      return 'deep-purple'
    case 'agent':
      return 'success'
    case 'migration':
      return 'grey'
    case 'revert':
      return 'warning'
  }
}

const RELATIVE_THRESHOLDS = [
  { limit: 60, divisor: 1, unit: 'sec' },
  { limit: 3_600, divisor: 60, unit: 'min' },
  { limit: 86_400, divisor: 3_600, unit: 'hr' },
  { limit: 604_800, divisor: 86_400, unit: 'd' },
]

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const seconds = Math.max(0, Math.floor(ms / 1000))
  for (const { limit, divisor, unit } of RELATIVE_THRESHOLDS) {
    if (seconds < limit) {
      const n = Math.max(1, Math.floor(seconds / divisor))
      return `${n} ${unit} ago`
    }
  }
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

// Stringify the snapshot field for line-by-line diff. JSON arrays
// (code_review_comments) are pretty-printed so the diff is readable;
// markdown and HTML pass through verbatim.
function stringifyForDiff(value: unknown, format: 'markdown' | 'html' | 'json'): string {
  if (value == null) return ''
  if (format === 'json') {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

interface DiffLine {
  type: 'added' | 'removed' | 'context'
  text: string
}

const diffLines = computed<DiffLine[]>(() => {
  if (!selectedVersion.value) return []
  const cfg = sectionConfig.value
  const oldText = stringifyForDiff(selectedVersion.value.snapshot[cfg.field], cfg.format)
  const newText = currentContent.value
  if (oldText === newText) return []
  const chunks = diffLinesFn(oldText, newText)
  const out: DiffLine[] = []
  for (const chunk of chunks) {
    const lines = chunk.value.replace(/\n$/, '').split('\n')
    const type: DiffLine['type'] = chunk.added
      ? 'added'
      : chunk.removed
        ? 'removed'
        : 'context'
    for (const line of lines) {
      out.push({ type, text: line })
    }
  }
  return out
})

const diffStats = computed<{ added: number; removed: number } | null>(() => {
  if (!selectedVersion.value) return null
  let added = 0
  let removed = 0
  for (const line of diffLines.value) {
    if (line.type === 'added') added += 1
    else if (line.type === 'removed') removed += 1
  }
  if (added === 0 && removed === 0) return null
  return { added, removed }
})

function diffLineClass(type: DiffLine['type']): string {
  return `diff-line--${type}`
}

function markerFor(type: DiffLine['type']): string {
  if (type === 'added') return '+'
  if (type === 'removed') return '−'
  return ' '
}

const restoreDisabledReason = computed<string | null>(() => {
  if (props.budStatus === 'closed' || props.budStatus === 'discarded') {
    return 'Cannot restore on a closed or discarded BUD.'
  }
  if (selectedVersion.value?.source === 'migration') {
    return 'Backfill baseline — restoring would set the section to its initial state.'
  }
  return null
})

async function loadVersions(): Promise<void> {
  loading.value = true
  selectedVersion.value = null
  try {
    const { data } = await api.get<BUDVersionSummary[]>(
      `/v1/buds/${props.budId}/versions`,
      { params: { limit: 200 } },
    )
    versions.value = data.filter((v) => v.phase === phase.value)
  } catch (err) {
    notify(err instanceof Error ? err.message : 'Failed to load history', 'error')
  } finally {
    loading.value = false
  }
}

async function fetchCurrentContent(): Promise<void> {
  const cfg = sectionConfig.value
  try {
    if (cfg.format === 'html') {
      // Design content lives in bud_designs — pull the BUD-level row.
      const { data } = await api.get<{ designs: Array<{ repo_id: string | null; design_html: string | null }> }>(
        `/v1/buds/${props.budId}/designs`,
      )
      const budLevel = data.designs.find((d) => d.repo_id == null)
      currentContent.value = budLevel?.design_html ?? ''
    } else {
      const { data } = await api.get<Record<string, unknown>>(`/v1/buds/${props.budId}`)
      currentContent.value = stringifyForDiff(data[cfg.field], cfg.format)
    }
  } catch (err) {
    notify(err instanceof Error ? err.message : 'Failed to load current content', 'error')
    currentContent.value = ''
  }
}

async function selectVersion(v: BUDVersionSummary): Promise<void> {
  loadingDetail.value = true
  try {
    const { data } = await api.get<BUDVersionDetail>(
      `/v1/buds/${props.budId}/versions/${v.phase}/${v.version_no}`,
    )
    selectedVersion.value = data
  } catch (err) {
    notify(err instanceof Error ? err.message : 'Failed to load version', 'error')
  } finally {
    loadingDetail.value = false
  }
}

async function doRestore(): Promise<void> {
  if (!selectedVersion.value) return
  const target = selectedVersion.value
  restoring.value = true
  try {
    await api.post(`/v1/buds/${props.budId}/revert/${target.phase}/${target.version_no}`)
    notify(`Restored ${sectionLabel.value} to v${target.version_no}`)
    confirmRestore.value = false
    emit('reverted')
    // Refresh both the version list (a new revert row landed) and the
    // current content baseline (the diff against subsequent versions
    // now compares against the restored text).
    await Promise.all([loadVersions(), fetchCurrentContent()])
  } catch (err) {
    notify(err instanceof Error ? err.message : 'Restore failed', 'error')
  } finally {
    restoring.value = false
  }
}

// Reload everything whenever the drawer opens or the section the user
// clicked from changes (e.g. they close the drawer, switch tabs, then
// reopen).
watch(
  () => [props.modelValue, props.section],
  ([opened]) => {
    if (!opened) return
    void loadVersions()
    void fetchCurrentContent()
  },
  { immediate: true },
)
</script>

<style scoped>
.diff-drawer {
  display: flex;
  flex-direction: column;
}
.diff-drawer__header {
  padding: 14px 16px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgb(var(--v-theme-surface));
}
.diff-drawer__body {
  display: grid;
  grid-template-columns: 240px 1fr;
  height: calc(100vh - 64px);
  min-height: 0;
}
.diff-rail {
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  overflow-y: auto;
  padding: 8px;
  background: rgba(var(--v-theme-on-surface), 0.02);
}
.diff-rail__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 12px;
  gap: 6px;
}
.diff-rail__item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  margin-bottom: 4px;
  border-radius: 6px;
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.12s ease;
}
.diff-rail__item:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.diff-rail__item--active {
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgba(var(--v-theme-primary), 0.4);
}
.diff-rail__reason {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.diff-pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.diff-pane__header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgb(var(--v-theme-surface));
  flex-wrap: wrap;
}
.diff-pane__placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 12px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.diff-pane__body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
  font-family: var(--v-font-family-monospace, 'Menlo', monospace);
  font-size: 13px;
  line-height: 1.55;
}
.diff-stats {
  display: inline-flex;
  gap: 8px;
  font-family: var(--v-font-family-monospace, 'Menlo', monospace);
  font-size: 12px;
  font-weight: 600;
}
.diff-stats__added {
  color: rgb(var(--v-theme-success));
}
.diff-stats__removed {
  color: rgb(var(--v-theme-error));
}
.diff-line {
  display: grid;
  grid-template-columns: 28px 1fr;
  padding: 1px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.diff-line__marker {
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.4);
  user-select: none;
}
.diff-line__text {
  min-width: 0;
}
.diff-line--added {
  background: rgba(46, 160, 67, 0.16);
}
.diff-line--added .diff-line__marker {
  color: rgb(var(--v-theme-success));
}
.diff-line--removed {
  background: rgba(248, 81, 73, 0.16);
}
.diff-line--removed .diff-line__marker {
  color: rgb(var(--v-theme-error));
}
.diff-line--removed .diff-line__text {
  text-decoration: line-through;
  opacity: 0.85;
}
.diff-line--context {
  background: transparent;
}
</style>
