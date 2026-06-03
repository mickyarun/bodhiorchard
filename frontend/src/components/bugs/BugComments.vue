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
    <div class="text-subtitle-2 font-weight-medium mb-2 d-flex align-center ga-2">
      <v-icon icon="mdi-comment-text-outline" size="18" />
      <span>Comments</span>
      <v-chip v-if="activeCount > 0" size="x-small" variant="tonal" color="primary">
        {{ activeCount }}
      </v-chip>
    </div>

    <div v-if="bugsStore.commentsLoading" class="d-flex justify-center py-3">
      <v-progress-circular indeterminate size="20" />
    </div>

    <div v-else-if="bugsStore.comments.length === 0" class="text-caption text-medium-emphasis pa-3 text-center">
      No comments yet. Be the first.
    </div>

    <div v-else class="d-flex flex-column ga-2 mb-3">
      <div
        v-for="comment in bugsStore.comments"
        :key="comment.id"
        class="comment-row pa-2"
        :class="{ 'comment-tombstone': !!comment.deletedAt }"
      >
        <div class="d-flex align-center ga-2 mb-1">
          <v-avatar size="20" color="primary" variant="tonal">
            <span style="font-size: 9px;">{{ initials(comment.authorName) }}</span>
          </v-avatar>
          <span class="text-caption font-weight-medium">{{ comment.authorName || 'Unknown' }}</span>
          <span class="text-caption text-medium-emphasis">{{ formatDateTime(comment.createdAt) }}</span>
          <span v-if="comment.editedAt && !comment.deletedAt" class="text-caption text-medium-emphasis">
            (edited)
          </span>
          <v-spacer />
          <template v-if="canModify(comment)">
            <v-btn
              v-if="editingId !== comment.id"
              icon="mdi-pencil"
              size="x-small"
              variant="text"
              density="compact"
              @click="startEdit(comment)"
            />
            <v-btn
              icon="mdi-delete-outline"
              size="x-small"
              variant="text"
              density="compact"
              color="error"
              @click="onDelete(comment.id)"
            />
          </template>
        </div>

        <div v-if="comment.deletedAt" class="text-caption text-medium-emphasis fst-italic">
          [deleted]
        </div>
        <div v-else-if="editingId === comment.id" class="d-flex flex-column ga-2">
          <v-textarea
            v-model="editDraft"
            variant="outlined"
            density="compact"
            rows="2"
            hide-details
            autofocus
          />
          <div class="d-flex ga-2 justify-end">
            <v-btn variant="text" size="small" @click="cancelEdit">Cancel</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              size="small"
              :disabled="!editDraft.trim() || editDraft === comment.body"
              @click="saveEdit(comment.id)"
            >Save</v-btn>
          </div>
        </div>
        <div v-else class="text-body-2" style="white-space: pre-wrap;">{{ comment.body }}</div>
      </div>
    </div>

    <v-textarea
      v-if="canComment"
      v-model="newBody"
      label="Add a comment"
      variant="outlined"
      density="compact"
      rows="2"
      hide-details
      class="mb-2"
      :disabled="posting"
    />
    <div v-if="canComment" class="d-flex justify-end">
      <v-btn
        color="primary"
        variant="flat"
        size="small"
        :disabled="!newBody.trim() || posting"
        :loading="posting"
        @click="onPost"
      >
        Post
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useBugsStore } from '@/stores/bugs'
import { usePermissions } from '@/composables/usePermissions'
import { formatDateTime } from '@/utils/date'
import type { BugComment } from '@/types'

const props = defineProps<{
  bugId: string | null
}>()

const bugsStore = useBugsStore()
const authStore = useAuthStore()
const { canCommentOnBugs, canEditBugs } = usePermissions()

const newBody = ref('')
const posting = ref(false)
const editingId = ref<string | null>(null)
const editDraft = ref('')

const canComment = computed(() => canCommentOnBugs.value)

const activeCount = computed(
  () => bugsStore.comments.filter((c) => !c.deletedAt).length,
)

watch(
  () => props.bugId,
  async (id) => {
    if (id) {
      await bugsStore.fetchComments(id)
    } else {
      bugsStore.comments = []
    }
    editingId.value = null
    newBody.value = ''
  },
  { immediate: true },
)

function initials(name: string | null | undefined): string {
  if (!name) return '?'
  return name
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

function canModify(comment: BugComment): boolean {
  if (comment.deletedAt) return false
  if (!authStore.user) return false
  if (comment.authorId === authStore.user.id) return true
  return canEditBugs.value
}

function startEdit(comment: BugComment): void {
  editingId.value = comment.id
  editDraft.value = comment.body
}

function cancelEdit(): void {
  editingId.value = null
  editDraft.value = ''
}

async function saveEdit(commentId: string): Promise<void> {
  if (!props.bugId || !editDraft.value.trim()) return
  const updated = await bugsStore.editComment(props.bugId, commentId, editDraft.value.trim())
  if (updated) cancelEdit()
}

async function onDelete(commentId: string): Promise<void> {
  if (!props.bugId) return
  await bugsStore.deleteComment(props.bugId, commentId)
}

async function onPost(): Promise<void> {
  if (!props.bugId || !newBody.value.trim()) return
  posting.value = true
  const added = await bugsStore.addComment(props.bugId, newBody.value.trim())
  posting.value = false
  if (added) newBody.value = ''
}
</script>

<style scoped>
.comment-row {
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
}
.comment-tombstone {
  background: rgba(255, 255, 255, 0.01);
  opacity: 0.7;
}
.fst-italic { font-style: italic; }
</style>
