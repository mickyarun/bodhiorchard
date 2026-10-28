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
  <div>
    <div class="d-flex align-center ga-2 mb-2">
      <span class="text-caption text-medium-emphasis font-weight-medium">Attachments</span>
      <span class="text-caption text-disabled">{{ count }} / {{ effectiveLimits.maxFilesPerBug }}</span>
      <v-spacer />
      <v-btn
        v-if="!readonly"
        size="small"
        variant="text"
        prepend-icon="mdi-paperclip"
        :disabled="isFull || uploading"
        :loading="uploading"
        @click="openFilePicker"
      >
        Attach
      </v-btn>
    </div>

    <AppCallout v-if="message" variant="warning" class="mb-3">
      {{ message }}
    </AppCallout>

    <div v-if="loading" class="text-caption text-disabled">Loading attachments…</div>

    <div v-else-if="count" class="d-flex flex-wrap ga-2">
      <AttachmentTile
        v-for="tile in tiles"
        :key="tile.key"
        :filename="tile.filename"
        :mime-type="tile.mimeType"
        :size-bytes="tile.sizeBytes"
        :fetch-path="tile.fetchPath"
        :file="tile.file"
        :removable="!readonly"
        @remove="removeTile(tile)"
        @preview="openPreview"
        @error="message = $event"
      />
    </div>

    <div v-else class="text-caption text-disabled">
      {{ readonly ? 'No attachments.' : hint }}
    </div>

    <div v-if="!readonly && count" class="text-caption text-disabled mt-2">{{ hint }}</div>

    <!-- Hidden native picker. `multiple` lets a reporter grab a whole
      screenshot set in one go; files past the remaining slots are
      rejected individually with a reason rather than silently dropped. -->
    <input
      ref="fileInput"
      type="file"
      multiple
      :accept="accept"
      class="d-none"
      @change="onFilesPicked"
    />

    <AttachmentPreviewDialog v-model="previewOpen" :url="previewUrl" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AttachmentTile from '@/components/common/AttachmentTile.vue'
import { useAttachmentStrip } from '@/composables/useAttachmentStrip'
import AttachmentPreviewDialog from './AttachmentPreviewDialog.vue'

/**
 * The attachment strip. With `bugId` set it reads and writes through the
 * API; with `bugId` null it holds picked files in `v-model` until the
 * parent has a bug to attach them to (see useAttachmentStrip).
 */
const props = withDefaults(
  defineProps<{
    bugId?: string | null
    /** Staged files — only meaningful while `bugId` is null. */
    modelValue?: File[]
    readonly?: boolean
  }>(),
  { bugId: null, modelValue: () => [], readonly: false },
)

const emit = defineEmits<{ (e: 'update:modelValue', files: File[]): void }>()

const {
  loading, uploading, effectiveLimits, count, isFull, accept, hint, message, tiles,
  addFiles, removeTile, flush,
} = useAttachmentStrip({
  bugId: () => props.bugId,
  staged: () => props.modelValue,
  setStaged: files => emit('update:modelValue', files),
})

const fileInput = ref<HTMLInputElement | null>(null)
const previewOpen = ref(false)
const previewUrl = ref<string | null>(null)

function openFilePicker(): void {
  message.value = null
  fileInput.value?.click()
}

async function onFilesPicked(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const picked = Array.from(input.files ?? [])
  // Reset immediately so re-picking the same file fires `change` again.
  input.value = ''
  if (!picked.length) return
  await addFiles(picked)
}

defineExpose({ flush })

function openPreview(url: string | null): void {
  if (!url) return
  previewUrl.value = url
  previewOpen.value = true
}
</script>
