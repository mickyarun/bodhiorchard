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

    <v-dialog v-model="previewOpen" max-width="960">
      <v-card color="surface" class="pa-2">
        <img v-if="previewUrl" :src="previewUrl" class="preview-image" alt="Attachment preview" />
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AttachmentTile from '@/components/common/AttachmentTile.vue'
import { useBugAttachments } from '@/composables/useBugAttachments'
import { acceptAttribute, attachmentRejectionReason } from '@/utils/attachments'

/**
 * The attachment strip, in either of two modes:
 *
 * - **stored** (`bugId` set) — reads and writes through the API.
 * - **staged** (`bugId` null) — holds picked files in `v-model` until
 *   the parent has a bug to attach them to. The create dialog needs
 *   this because attachments are keyed on a bug that doesn't exist
 *   until the user hits "Report Bug".
 *
 * Both modes render the same strip, so a reporter sees no difference
 * between attaching before and after the bug is filed.
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

const attachments = useBugAttachments()
const { items, limits, loading, uploading } = attachments

const fileInput = ref<HTMLInputElement | null>(null)
const localError = ref<string | null>(null)
const previewOpen = ref(false)
const previewUrl = ref<string | null>(null)

const isStaging = computed(() => !props.bugId)

// Both modes read the org's real limits: stored mode gets them with
// the list, staging mode fetches them on mount (there is no bug to
// list). `limits` starts at the shipped defaults, so the picker is
// usable during that first round-trip.
const effectiveLimits = computed(() => limits.value)

const count = computed(() => (isStaging.value ? props.modelValue.length : items.value.length))
const isFull = computed(() => count.value >= effectiveLimits.value.maxFilesPerBug)
const accept = computed(() => acceptAttribute(effectiveLimits.value))
const hint = computed(
  () =>
    `Up to ${effectiveLimits.value.maxFilesPerBug} files, ${effectiveLimits.value.maxFileMb} MB each ` +
    `(${effectiveLimits.value.acceptedExtensions.join(', ')}).`,
)

// One message slot, fed by whichever layer failed — a client-side
// rejection, a failed request, or a tile that couldn't fetch its blob.
const message = computed({
  get: () => localError.value ?? attachments.error.value,
  set: (value: string | null) => {
    localError.value = value
    if (value === null) attachments.clearError()
  },
})

interface Tile {
  key: string
  filename: string
  mimeType: string
  sizeBytes: number
  fetchPath: string | null
  file: File | null
}

const tiles = computed<Tile[]>(() => {
  if (isStaging.value) {
    return props.modelValue.map((file, index) => ({
      key: `${index}-${file.name}-${file.lastModified}`,
      filename: file.name,
      mimeType: file.type,
      sizeBytes: file.size,
      fetchPath: null,
      file,
    }))
  }
  return items.value.map((a) => ({
    key: a.id,
    filename: a.filename,
    mimeType: a.mimeType,
    sizeBytes: a.sizeBytes,
    fetchPath: attachments.downloadPath(props.bugId as string, a.id),
    file: null,
  }))
})

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

  if (isStaging.value) stageFiles(picked)
  else await uploadFiles(picked)
}

function stageFiles(picked: File[]): void {
  const next = [...props.modelValue]
  for (const file of picked) {
    const reason = attachmentRejectionReason(file, effectiveLimits.value, next.length)
    if (reason) {
      message.value = reason
      break
    }
    next.push(file)
  }
  emit('update:modelValue', next)
}

async function uploadFiles(picked: File[]): Promise<void> {
  await attachments.uploadMany(props.bugId as string, picked)
}

function removeTile(tile: Tile): void {
  message.value = null
  if (isStaging.value) {
    emit(
      'update:modelValue',
      props.modelValue.filter((f) => f !== tile.file),
    )
    return
  }
  void attachments.remove(props.bugId as string, tile.key)
}

/**
 * Upload the staged files to a bug that now exists.
 *
 * Called by the create dialog once `createBug` returns an id. Files
 * that land are dropped from the staged list; any that fail stay put
 * and visible, with the reason in the message slot, so the reporter
 * can retry them instead of losing them on close.
 *
 * @returns True when every staged file was stored.
 */
async function flush(bugId: string): Promise<boolean> {
  if (!props.modelValue.length) return true
  const stored = await attachments.uploadMany(bugId, props.modelValue)
  // uploadMany stops at the first failure, so the successes are always
  // the leading slice of what was staged.
  const remaining = props.modelValue.slice(stored.length)
  emit('update:modelValue', remaining)
  return remaining.length === 0
}

defineExpose({ flush })

function openPreview(url: string | null): void {
  if (!url) return
  previewUrl.value = url
  previewOpen.value = true
}

// Reload whenever the panel switches to a different bug, and clear any
// message left over from the previous one.
watch(
  () => props.bugId,
  (bugId) => {
    localError.value = null
    attachments.clearError()
    // A bug's list response carries the limits; without one, fetch
    // them on their own so the staged picker validates against the
    // org's real caps rather than the shipped defaults.
    if (bugId) void attachments.load(bugId)
    else void attachments.loadLimits()
  },
  { immediate: true },
)
</script>

<style scoped>
.preview-image {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 4px;
}
</style>
