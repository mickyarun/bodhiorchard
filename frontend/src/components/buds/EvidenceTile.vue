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
  <div class="evidence-tile" :class="{ 'is-image': isImage, 'is-loading': loading }">
    <!-- Image thumbnail -->
    <button
      v-if="isImage"
      type="button"
      class="tile-surface tile-image"
      :disabled="!blobUrl"
      :aria-label="`Preview ${evidence.filename}`"
      @click="$emit('preview', blobUrl)"
    >
      <img v-if="blobUrl" :src="blobUrl" :alt="evidence.filename" />
      <v-icon v-else-if="errored" icon="mdi-image-broken-variant" size="24" />
      <v-progress-circular v-else indeterminate size="18" width="2" />
    </button>

    <!-- Non-image: file icon tile. Click = download. -->
    <button
      v-else
      type="button"
      class="tile-surface tile-file"
      :aria-label="`Download ${evidence.filename}`"
      @click="downloadFile"
    >
      <v-icon :icon="fileIcon" size="28" />
    </button>

    <div class="tile-meta">
      <div class="tile-filename" :title="evidence.filename">{{ evidence.filename }}</div>
    </div>

    <v-btn
      class="delete-btn"
      icon="mdi-close"
      size="x-small"
      variant="flat"
      density="comfortable"
      color="surface-variant"
      aria-label="Delete evidence"
      @click.stop="$emit('delete')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { TestEvidence } from '@/types'

const props = defineProps<{
  evidence: TestEvidence
  budId: string
}>()

const emit = defineEmits<{
  (e: 'delete'): void
  (e: 'preview', blobUrl: string | null): void
  // Surfaces fetch failures (download endpoint 500, thumbnail load
  // refusal, network outage, expired token) so the parent panel can
  // render the same error banner used by upload / delete instead of
  // leaving the user with a broken-image icon and no explanation.
  (e: 'error', message: string): void
}>()

const authStore = useAuthStore()

// blobUrl is an object URL created from a fetched blob. Object URLs must
// be revoked on unmount to avoid leaking browser memory — every tile
// allocates one, so over a long test-run session this adds up.
const blobUrl = ref<string | null>(null)
const loading = ref(false)
const errored = ref(false)

const isImage = computed(() => props.evidence.mime_type.startsWith('image/'))

const fileIcon = computed(() => {
  const mime = props.evidence.mime_type
  if (mime === 'application/pdf') return 'mdi-file-pdf-box'
  if (mime.startsWith('text/')) return 'mdi-file-document-outline'
  if (mime.startsWith('video/')) return 'mdi-file-video-outline'
  if (mime.startsWith('audio/')) return 'mdi-file-music-outline'
  return 'mdi-file-outline'
})

async function fetchBlob(): Promise<Blob> {
  // The evidence download endpoint is auth-gated with a Bearer token, so a
  // plain <img src="/api/..."> won't work — the browser doesn't attach the
  // Authorization header to img requests. We fetch manually and turn the
  // result into an object URL.
  const resp = await fetch(
    `/api/v1/buds/${props.budId}/qa/evidence/${props.evidence.id}`,
    {
      headers: { Authorization: `Bearer ${authStore.token}` },
    },
  )
  if (!resp.ok) {
    // Try to lift the backend's ``{"detail": "..."}`` so a 404
    // ("Evidence not found") or 500 (storage backend issue) reaches
    // the user rather than degrading silently to a broken-image icon.
    let detail = `HTTP ${resp.status}`
    try {
      const body = await resp.clone().json()
      if (body?.detail) detail = String(body.detail)
    }
    catch { /* non-JSON body — keep the status fallback */ }
    throw new Error(detail)
  }
  return await resp.blob()
}

function describeFetchError(err: unknown, action: 'thumbnail' | 'download'): string {
  const reason = err instanceof Error ? err.message : 'unknown error'
  const verb = action === 'thumbnail' ? 'load preview for' : 'download'
  return `Couldn't ${verb} "${props.evidence.filename}" (${reason}).`
}

async function loadThumbnail(): Promise<void> {
  loading.value = true
  errored.value = false
  try {
    const blob = await fetchBlob()
    blobUrl.value = URL.createObjectURL(blob)
  }
  catch (e) {
    errored.value = true
    const message = describeFetchError(e, 'thumbnail')
    console.error(message, e)
    emit('error', message)
  }
  finally {
    loading.value = false
  }
}

async function downloadFile(): Promise<void> {
  // Fetch-then-click pattern: browsers download via <a download> only when
  // the href is reachable without extra headers. We build an object URL
  // from the authenticated blob, click, then revoke.
  try {
    const blob = await fetchBlob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = props.evidence.filename
    a.click()
    URL.revokeObjectURL(url)
  }
  catch (e) {
    const message = describeFetchError(e, 'download')
    console.error(message, e)
    emit('error', message)
  }
}

onMounted(() => {
  if (isImage.value) {
    void loadThumbnail()
  }
})

onBeforeUnmount(() => {
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = null
  }
})
</script>

<style scoped>
.evidence-tile {
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

.evidence-tile:hover {
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

.delete-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.evidence-tile:hover .delete-btn,
.evidence-tile:focus-within .delete-btn {
  opacity: 1;
}
</style>
