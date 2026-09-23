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
  <div class="attachment-tile" :class="{ 'is-image': showsThumbnail }">
    <!-- Image: thumbnail, click opens the full-size preview. -->
    <button
      v-if="showsThumbnail"
      type="button"
      class="tile-surface tile-image"
      :disabled="!objectUrl"
      :aria-label="`Preview ${filename}`"
      @click="$emit('preview', objectUrl)"
    >
      <img v-if="objectUrl" :src="objectUrl" :alt="filename" />
      <v-icon v-else-if="errored" icon="mdi-image-broken-variant" size="24" />
      <v-progress-circular v-else indeterminate size="18" width="2" />
    </button>

    <!-- Everything else: file-type icon, click downloads. -->
    <button
      v-else
      type="button"
      class="tile-surface tile-file"
      :aria-label="`Download ${filename}`"
      @click="download"
    >
      <v-icon :icon="icon" size="28" />
    </button>

    <div class="tile-meta">
      <div class="tile-filename" :title="filename">{{ filename }}</div>
      <div v-if="sizeBytes" class="tile-size">{{ formatFileSize(sizeBytes) }}</div>
    </div>

    <v-btn
      v-if="removable"
      class="remove-btn"
      icon
      size="x-small"
      variant="flat"
      density="comfortable"
      :aria-label="removeLabel || `Remove ${filename}`"
      @click.stop="$emit('remove')"
    >
      <v-icon size="14">mdi-close</v-icon>
      <v-tooltip activator="parent" location="top">{{ removeTooltip }}</v-tooltip>
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import api from '@/services/api'
import { attachmentIcon, formatFileSize, isPreviewableImage } from '@/utils/attachments'
import { extractApiError } from '@/utils/errors'

/** Request budget for fetching an attachment's bytes (2 minutes). */
const BLOB_TIMEOUT_MS = 120_000

const props = withDefaults(
  defineProps<{
    filename: string
    mimeType: string
    sizeBytes?: number
    /**
     * Authenticated API path to fetch the bytes from. Used for stored
     * attachments; leave unset for a locally staged `file`.
     */
    fetchPath?: string | null
    /**
     * A file the user just picked but which hasn't been uploaded yet —
     * previewed straight from the browser with no network round-trip.
     */
    file?: File | null
    removable?: boolean
    /**
     * Copy for the remove affordance. Surfaces that already had their
     * own wording pass it so adopting this tile doesn't silently
     * reword their UI; everything else gets the generic default.
     */
    removeLabel?: string
    removeTooltip?: string
  }>(),
  {
    sizeBytes: 0,
    fetchPath: null,
    file: null,
    removable: true,
    removeLabel: '',
    removeTooltip: 'Remove',
  },
)

const emit = defineEmits<{
  (e: 'remove'): void
  (e: 'preview', objectUrl: string | null): void
  /**
   * Surfaces fetch failures (download 500, expired token, network
   * outage) so the parent can render them in its own error slot rather
   * than leaving the user with a broken-image icon and no explanation.
   */
  (e: 'error', message: string): void
}>()

// Object URLs must be revoked or the blob stays in browser memory for
// the page's lifetime. Every tile allocates one, so a bug with ten
// screenshots opened repeatedly adds up.
const objectUrl = ref<string | null>(null)
const errored = ref(false)

const showsThumbnail = computed(() => isPreviewableImage(props.mimeType))
const icon = computed(() => attachmentIcon(props.mimeType))

function releaseObjectUrl(): void {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = null
  }
}

async function fetchBlob(): Promise<Blob> {
  // A staged file is already in memory — no request needed.
  if (props.file) return props.file
  if (!props.fetchPath) throw new Error('No source for this attachment')
  // The download endpoint is Bearer-gated, so a plain <img src="/api/…">
  // won't work: the browser doesn't attach the Authorization header to
  // image requests. Fetch through the API client (whose interceptor
  // does) and turn the result into an object URL.
  const { data } = await api.get<Blob>(props.fetchPath, {
    responseType: 'blob',
    // The API client defaults to 30s, which suits JSON but not a
    // multi-megabyte download on a slow link - an attachment at the
    // 25 MB ceiling would abort mid-transfer and surface as a bogus
    // "couldn't load preview". Overridden per-request rather than
    // raising the global default, which exists to stop slow API calls
    // hanging the UI.
    timeout: BLOB_TIMEOUT_MS,
  })
  return data
}

function describeFailure(err: unknown, action: 'preview' | 'download'): string {
  const verb = action === 'preview' ? 'load a preview for' : 'download'
  const answered = !!(err && typeof err === 'object' && 'response' in err && err.response)
  if (!answered) {
    // Nothing came back at all. `extractApiError` would return its own
    // full sentence here, which reads badly nested inside this one.
    return `Couldn't ${verb} "${props.filename}" — check your connection.`
  }
  // `extractApiError` reads the backend's `{"detail": ...}`, which the
  // API client's interceptor restores even for `responseType: 'blob'`
  // requests. Without that the user would only ever see axios's generic
  // "Request failed with status code 404" instead of the reason the
  // route actually gave ("Evidence not found", a storage misconfig...).
  return `Couldn't ${verb} "${props.filename}" (${extractApiError(err, 'server error')}).`
}

async function loadThumbnail(): Promise<void> {
  errored.value = false
  try {
    const blob = await fetchBlob()
    releaseObjectUrl()
    objectUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    errored.value = true
    const message = describeFailure(err, 'preview')
    // Keep the original error in the console: the parent only renders
    // the formatted string, so without this a "couldn't load preview"
    // report leaves nothing to diagnose from.
    console.error(message, err)
    emit('error', message)
  }
}

async function download(): Promise<void> {
  // Fetch-then-click: <a download> only works on a URL reachable
  // without extra headers, so we build one from the authenticated blob,
  // click it, then revoke.
  try {
    const blob = await fetchBlob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = props.filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    const message = describeFailure(err, 'download')
    console.error(message, err)
    emit('error', message)
  }
}

// Re-fetch when the tile is pointed at a different file — the strip
// reuses tiles as attachments are added and removed.
watch(
  () => [props.fetchPath, props.file, showsThumbnail.value] as const,
  () => {
    if (showsThumbnail.value) void loadThumbnail()
    else releaseObjectUrl()
  },
  { immediate: true },
)

onBeforeUnmount(releaseObjectUrl)
</script>

<style scoped>
.attachment-tile {
  position: relative;
  width: 104px;
  height: 104px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  display: flex;
  flex-direction: column;
}

.attachment-tile:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
}

.tile-surface {
  all: unset;
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: transparent;
}

.tile-surface:disabled {
  cursor: default;
}

.tile-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.tile-file {
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.tile-meta {
  padding: 4px 6px;
  background: rgba(var(--v-theme-surface), 0.9);
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.tile-filename {
  font-size: 10px;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: rgba(var(--v-theme-on-surface), 0.75);
}

.tile-size {
  font-size: 9px;
  line-height: 1.2;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

/* Persistently visible rather than hover-only: hover discovery leaves
 * touch users unable to find the remove affordance at all. */
.remove-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.55) !important;
  color: white !important;
  border: 1px solid rgba(255, 255, 255, 0.2);
  transition: background 0.15s ease, transform 0.1s ease;
}

.remove-btn:hover {
  background: rgba(var(--v-theme-error), 0.95) !important;
  transform: scale(1.08);
}
</style>
