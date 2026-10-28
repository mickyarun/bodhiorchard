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

<!-- One bug comment: author, time, edit/delete controls and the body,
     or an inline editor while ``editing``. The thread owns which comment
     is being edited and does the saving. -->
<template>
  <div class="comment-row pa-2" :class="{ 'comment-tombstone': !!comment.deletedAt }">
    <div class="d-flex align-center ga-2 mb-1">
      <AppMonogram :name="comment.authorName" :size="20" />
      <span class="text-caption font-weight-medium">{{ comment.authorName || 'Unknown' }}</span>
      <span class="text-caption text-medium-emphasis">{{ formatDateTime(comment.createdAt) }}</span>
      <span v-if="comment.editedAt && !comment.deletedAt" class="text-caption text-medium-emphasis">
        (edited)
      </span>
      <v-spacer />
      <template v-if="canModify">
        <v-btn
          v-if="!editing"
          icon="mdi-pencil"
          size="x-small"
          variant="text"
          density="compact"
          aria-label="Edit comment"
          @click="startEdit"
        />
        <v-btn
          icon="mdi-delete-outline"
          size="x-small"
          variant="text"
          density="compact"
          color="error"
          aria-label="Delete comment"
          @click="emit('delete')"
        />
      </template>
    </div>

    <div v-if="comment.deletedAt" class="text-caption text-medium-emphasis fst-italic">
      [deleted]
    </div>
    <div v-else-if="editing" class="d-flex flex-column ga-2">
      <v-textarea
        v-model="draft"
        variant="outlined"
        density="compact"
        rows="2"
        hide-details
        autofocus
      />
      <div class="d-flex ga-2 justify-end">
        <v-btn variant="text" size="small" @click="emit('cancel')">Cancel</v-btn>
        <v-btn
          variant="outlined"
          size="small"
          :disabled="!draft.trim() || draft === comment.body"
          @click="emit('save', draft.trim())"
        >Save</v-btn>
      </div>
    </div>
    <div v-else class="text-body-2" style="white-space: pre-wrap;">{{ comment.body }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppMonogram from '@/components/common/AppMonogram.vue'
import type { BugComment } from '@/types'
import { formatDateTime } from '@/utils/date'

const props = defineProps<{ comment: BugComment; editing: boolean; canModify: boolean }>()
const emit = defineEmits<{
  edit: []
  cancel: []
  save: [body: string]
  delete: []
}>()

const draft = ref('')

function startEdit(): void {
  draft.value = props.comment.body
  emit('edit')
}
</script>

<style scoped>
.comment-row {
  border-radius: 6px;
  background: rgb(var(--v-theme-surface-bright));
}
.comment-tombstone {
  background: rgb(var(--v-theme-surface-bright));
  opacity: 0.7;
}
.fst-italic { font-style: italic; }
</style>
