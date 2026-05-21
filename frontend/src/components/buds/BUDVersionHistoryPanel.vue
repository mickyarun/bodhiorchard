<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 -->

<!-- Edit-history viewer + revert UI for a BUD. Lists rows fetched from
     GET /buds/{id}/versions, newest first. Each row exposes its source
     (ui / mcp / agent / migration / revert) so an operator can pivot
     on "who edited what when"; the revert button posts to
     /buds/{id}/revert/{phase}/{v} and reloads. Reverts are append-only
     — they produce a new source='revert' row instead of destroying
     history. -->
<template>
  <div class="version-history">
    <div class="d-flex align-center ga-2 mb-3">
      <v-icon icon="mdi-history" size="20" />
      <div class="text-subtitle-1 font-weight-medium">Edit history</div>
      <v-spacer />
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-refresh"
        :loading="loading"
        @click="load"
      >
        Refresh
      </v-btn>
    </div>

    <v-alert
      v-if="loadError"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-3"
    >
      Couldn't load history — {{ loadError }}
    </v-alert>

    <v-card v-if="!versions.length && !loading" variant="outlined" class="pa-6 text-center">
      <v-icon icon="mdi-clock-outline" size="32" class="text-medium-emphasis mb-2" />
      <div class="text-body-2 text-medium-emphasis">
        No history yet. Edits will appear here once someone modifies this BUD.
      </div>
    </v-card>

    <v-card v-else variant="outlined">
      <v-list lines="three" density="comfortable" class="version-list">
        <template v-for="(v, idx) in versions" :key="v.id">
          <v-list-item :class="{ 'version-list__revert': v.source === 'revert' }">
            <template #prepend>
              <v-avatar :color="sourceMeta(v.source).color" size="32" rounded>
                <v-icon :icon="sourceMeta(v.source).icon" size="18" color="white" />
              </v-avatar>
            </template>

            <v-list-item-title class="d-flex align-center ga-2 flex-wrap">
              <strong>{{ formatPhase(v.phase) }} · v{{ v.version_no }}</strong>
              <v-chip
                :color="sourceMeta(v.source).color"
                size="x-small"
                variant="tonal"
                class="text-uppercase"
              >
                {{ v.source }}
              </v-chip>
              <span class="text-caption text-medium-emphasis">
                {{ relativeTime(v.edited_at) }}
              </span>
            </v-list-item-title>

            <v-list-item-subtitle class="mt-1">
              <span v-if="v.edited_by" class="text-body-2">
                Edited by user <code class="actor-code">{{ shortId(v.edited_by) }}</code>
              </span>
              <span v-else class="text-body-2 text-medium-emphasis">
                System write (no user)
              </span>
              <span v-if="v.mcp_token_id" class="text-caption text-medium-emphasis ml-2">
                · via MCP token <code class="actor-code">{{ shortId(v.mcp_token_id) }}</code>
              </span>
              <div v-if="v.reason" class="text-caption text-medium-emphasis mt-1">
                {{ v.reason }}
              </div>
            </v-list-item-subtitle>

            <template #append>
              <v-tooltip
                :text="
                  revertDisabledReason(v) ||
                  `Restore content from ${formatPhase(v.phase)} v${v.version_no}`
                "
                location="top"
              >
                <template #activator="{ props: tipProps }">
                  <span v-bind="tipProps">
                    <v-btn
                      size="small"
                      variant="tonal"
                      color="warning"
                      prepend-icon="mdi-undo"
                      :disabled="!!revertDisabledReason(v)"
                      :loading="revertingId === v.id"
                      @click="confirmRevert(v)"
                    >
                      Revert
                    </v-btn>
                  </span>
                </template>
              </v-tooltip>
            </template>
          </v-list-item>
          <v-divider v-if="idx < versions.length - 1" />
        </template>
      </v-list>
    </v-card>

    <v-alert
      type="info"
      variant="tonal"
      density="compact"
      class="mt-3"
    >
      Reverts are content-only — they restore BUD section text and (in
      DESIGN phase) the wireframe HTML, but do NOT rewind embeddings,
      linked-feature parsing, or downstream agents. The next normal edit
      re-derives those from the restored content.
    </v-alert>

    <v-dialog v-model="confirmDialog" max-width="460">
      <v-card class="pa-5">
        <div class="text-h6 font-weight-bold mb-2">
          Revert to {{ pendingRevert ? formatPhase(pendingRevert.phase) : '' }}
          v{{ pendingRevert?.version_no }}?
        </div>
        <p class="text-body-2 text-medium-emphasis mb-4">
          This restores the BUD's content as it was when this version was
          captured ({{ pendingRevert ? relativeTime(pendingRevert.edited_at) : '' }}).
          A new <code>revert</code> entry is added — your current content is
          NOT destroyed and can be re-applied later.
        </p>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="cancelRevert">Cancel</v-btn>
          <v-btn color="warning" variant="flat" :loading="!!revertingId" @click="doRevert">
            Revert
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'

interface BUDVersion {
  id: string
  phase: string
  version_no: number
  source: 'ui' | 'mcp' | 'agent' | 'migration' | 'revert'
  edited_by: string | null
  mcp_token_id: string | null
  reason: string | null
  edited_at: string
}

interface Props {
  budId: string
  budStatus: string
}

const props = defineProps<Props>()

const versions = ref<BUDVersion[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)

const confirmDialog = ref(false)
const pendingRevert = ref<BUDVersion | null>(null)
const revertingId = ref<string | null>(null)

const snackbar = ref<{ show: boolean; text: string; color: 'success' | 'error' }>({
  show: false,
  text: '',
  color: 'success',
})

// Terminal-status BUDs cannot be reverted server-side (the REST handler
// rejects with 400). Mirror that here so the disabled tooltip is
// informative instead of letting the user click into a 400.
const terminalStatus = computed(
  () => props.budStatus === 'closed' || props.budStatus === 'discarded',
)

function sourceMeta(source: BUDVersion['source']): { color: string; icon: string } {
  switch (source) {
    case 'ui':
      return { color: 'primary', icon: 'mdi-account-edit' }
    case 'mcp':
      return { color: 'deep-purple', icon: 'mdi-robot-outline' }
    case 'agent':
      return { color: 'success', icon: 'mdi-auto-fix' }
    case 'migration':
      return { color: 'grey', icon: 'mdi-database-arrow-up-outline' }
    case 'revert':
      return { color: 'warning', icon: 'mdi-undo' }
  }
}

function formatPhase(phase: string): string {
  return phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function shortId(uuid: string): string {
  return uuid.slice(0, 8)
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

function revertDisabledReason(v: BUDVersion): string | null {
  if (terminalStatus.value) {
    return 'Cannot revert a closed or discarded BUD.'
  }
  if (v.source === 'migration') {
    return 'Backfill baseline — reverting would restore an empty starting state.'
  }
  return null
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = null
  try {
    const { data } = await api.get<BUDVersion[]>(`/v1/buds/${props.budId}/versions`)
    versions.value = data
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : 'Unknown error'
  } finally {
    loading.value = false
  }
}

function confirmRevert(v: BUDVersion): void {
  pendingRevert.value = v
  confirmDialog.value = true
}

function cancelRevert(): void {
  confirmDialog.value = false
  pendingRevert.value = null
}

function notify(text: string, color: 'success' | 'error' = 'success'): void {
  snackbar.value = { show: true, text, color }
}

async function doRevert(): Promise<void> {
  if (!pendingRevert.value) return
  const target = pendingRevert.value
  revertingId.value = target.id
  try {
    await api.post(
      `/v1/buds/${props.budId}/revert/${target.phase}/${target.version_no}`,
    )
    notify(`Restored ${formatPhase(target.phase)} v${target.version_no}`)
    confirmDialog.value = false
    pendingRevert.value = null
    await load()
    // Surface the change to the parent so it can refetch the BUD body.
    emit('reverted')
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Revert failed'
    notify(`Revert failed — ${message}`, 'error')
  } finally {
    revertingId.value = null
  }
}

const emit = defineEmits<(e: 'reverted') => void>()

onMounted(load)
</script>

<style scoped>
.version-list {
  background: transparent;
}
.version-list__revert {
  background: rgba(var(--v-theme-warning), 0.04);
}
.actor-code {
  background: rgba(var(--v-theme-on-surface), 0.06);
  padding: 1px 6px;
  border-radius: 3px;
  font-family: var(--v-font-family-monospace, 'Menlo', monospace);
  font-size: 11px;
}
</style>
