<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Clone body of the Add dialog. Owns the URL input + queue list +
  private-auth toggle. Submit + cancel live in the dialog footer.
-->
<template>
  <div>
    <div class="text-body-2 font-weight-medium mb-1">Clone from GitHub</div>
    <div class="text-caption text-medium-emphasis mb-2">
      Paste an HTTPS or SSH URL. Press Enter or + to queue more before cloning.
    </div>

    <div class="d-flex align-center ga-2 mb-1">
      <v-text-field
        v-model="urlInput"
        :placeholder="urlPlaceholder"
        variant="outlined"
        density="compact"
        :error="urlInputInvalid"
        :error-messages="urlInputInvalid ? ['Use https://github.com/org/repo.git or git@github.com:org/repo.git'] : []"
        hide-details="auto"
        prepend-inner-icon="mdi-source-repository"
        :disabled="imp.running.value"
        @keydown.enter.prevent="enqueue"
      />
      <v-btn
        icon="mdi-plus"
        variant="tonal"
        color="primary"
        size="small"
        :disabled="!canEnqueue"
        @click="enqueue"
      />
    </div>
    <div
      v-if="urlInputKind && !urlInputInvalid"
      class="text-caption text-medium-emphasis mb-3 d-flex align-center ga-1"
    >
      <v-icon
        :icon="urlInputKind === 'ssh' ? 'mdi-shield-key-outline' : 'mdi-lock-outline'"
        size="12"
      />
      Detected {{ urlInputKind === 'ssh' ? 'SSH' : 'HTTPS' }} URL.
    </div>
    <div v-else class="mb-3" />

    <div
      v-if="imp.cloneItems.value.length === 0"
      class="empty-line text-caption text-medium-emphasis"
    >
      <v-icon icon="mdi-source-branch-plus" size="14" class="mr-1" />
      Queue is empty.
    </div>

    <div v-else class="d-flex flex-column ga-1">
      <div
        v-for="(item, idx) in imp.cloneItems.value"
        :key="item.source"
        class="clone-row d-flex align-center ga-2 px-2 py-1 rounded"
      >
        <v-icon
          :icon="iconFor(item.status)"
          :color="colorFor(item.status)"
          size="16"
          class="flex-grow-0 flex-shrink-0"
        />
        <div class="flex-grow-1 min-w-0">
          <div class="text-body-2 text-truncate">{{ displayName(item.source) }}</div>
          <div class="text-caption text-medium-emphasis text-truncate">
            {{ item.source }}
          </div>
          <div v-if="item.error" class="text-caption text-error text-truncate">
            {{ item.error }}
          </div>
        </div>
        <v-chip
          v-if="imp.isSshUrl(item.source)"
          size="x-small"
          variant="tonal"
          color="info"
        >
          SSH
        </v-chip>
        <v-btn
          icon="mdi-close"
          size="x-small"
          variant="text"
          density="compact"
          :disabled="item.status === 'running'"
          @click="imp.removeCloneItem(idx)"
        />
      </div>
    </div>

    <v-switch
      v-model="imp.usePrivateAuth.value"
      color="primary"
      density="compact"
      hide-details
      class="mt-3 private-toggle"
    >
      <template #label>
        <span class="text-caption">One or more repositories are private</span>
      </template>
    </v-switch>

    <RepoCloneAuthPanel
      v-if="imp.usePrivateAuth.value"
      :pat="imp.sharedPat.value"
      :has-https="hasQueuedHttps"
      :has-ssh="hasQueuedSsh"
      class="mt-2"
      @update:pat="imp.sharedPat.value = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import RepoCloneAuthPanel from './RepoCloneAuthPanel.vue'
import type { useRepoImport, ImportItemStatus } from '@/composables/useRepoImport'

const props = defineProps<{
  imp: ReturnType<typeof useRepoImport>
}>()

const urlInput = ref('')

const urlInputKind = computed(() => props.imp.classifyGitUrl(urlInput.value))
const urlInputInvalid = computed(
  () => urlInput.value.trim().length > 0 && urlInputKind.value === null,
)
const canEnqueue = computed(
  () => !!urlInput.value.trim() && !urlInputInvalid.value && !props.imp.running.value,
)

const urlPlaceholder = computed(() =>
  props.imp.cloneItems.value.length === 0
    ? 'https://github.com/org/repo.git'
    : 'Add another URL…',
)

// Drive the auth-panel layout from the actual queue contents (plus the
// in-flight typed URL once it's valid) so the user sees only the section
// they need.
const hasQueuedHttps = computed(
  () =>
    props.imp.cloneItems.value.some(i => !props.imp.isSshUrl(i.source))
    || (canEnqueue.value && urlInputKind.value === 'https'),
)
const hasQueuedSsh = computed(
  () =>
    props.imp.cloneItems.value.some(i => props.imp.isSshUrl(i.source))
    || (canEnqueue.value && urlInputKind.value === 'ssh'),
)

function enqueue(): void {
  if (urlInputInvalid.value) return
  if (props.imp.addCloneUrl(urlInput.value)) urlInput.value = ''
}

// Called by the parent dialog right before submitting so a typed-but-
// not-queued URL doesn't silently get dropped on the way out.
function flushPendingInput(): void {
  if (canEnqueue.value) enqueue()
}

defineExpose({ flushPendingInput })

function displayName(url: string): string {
  const cleaned = url.replace(/\.git\/?$/, '').replace(/\/$/, '')
  return cleaned.split(/[/:]/).pop() || cleaned
}

function iconFor(status: ImportItemStatus): string {
  return status === 'done'
    ? 'mdi-check-circle'
    : status === 'error'
      ? 'mdi-alert-circle-outline'
      : status === 'running'
        ? 'mdi-progress-download'
        : 'mdi-source-repository'
}

function colorFor(status: ImportItemStatus): string {
  return status === 'done'
    ? 'success'
    : status === 'error'
      ? 'error'
      : status === 'running'
        ? 'primary'
        : 'medium-emphasis'
}
</script>

<style scoped>
.empty-line {
  display: flex;
  align-items: center;
  padding: 12px;
  background: rgba(var(--v-theme-on-surface), 0.02);
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 6px;
}

.clone-row {
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

/* v-switch defaults its label to body text size (~14px). Match it to the
   surrounding 12px caption density so the toggle row doesn't visually
   dominate the section above it. */
.private-toggle :deep(.v-label) {
  opacity: 1;
  font-size: 12px;
  line-height: 1.4;
}
</style>
