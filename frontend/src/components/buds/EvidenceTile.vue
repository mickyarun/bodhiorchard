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
  <AttachmentTile
    :filename="evidence.filename"
    :mime-type="evidence.mime_type"
    :fetch-path="`/v1/buds/${budId}/qa/evidence/${evidence.id}`"
    remove-label="Delete evidence. Upload a replacement after deleting."
    remove-tooltip="Delete, then re-upload to replace"
    @remove="$emit('delete')"
    @preview="(url) => $emit('preview', url)"
    @error="(message) => $emit('error', message)"
  />
</template>

<script setup lang="ts">
import AttachmentTile from '@/components/common/AttachmentTile.vue'
import type { TestEvidence } from '@/types'

/**
 * QA-evidence adapter over the shared {@link AttachmentTile}.
 *
 * The tile owns everything visual and every fetch: thumbnail vs icon,
 * authenticated blob loading, object-URL lifecycle, download. This
 * component only maps an evidence row onto the tile's props and keeps
 * the QA-specific delete wording, which differs from the generic
 * "Remove" because replacing evidence here means delete-then-re-upload.
 *
 * ``size_bytes`` is deliberately not passed: the evidence API doesn't
 * return it, and the tile hides the size line when it is absent — so
 * these tiles look exactly as they did before the refactor.
 */
defineProps<{
  evidence: TestEvidence
  budId: string
}>()

defineEmits<{
  (e: 'delete'): void
  (e: 'preview', objectUrl: string | null): void
  (e: 'error', message: string): void
}>()
</script>
