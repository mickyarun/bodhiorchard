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
      <BugCommentItem
        v-for="comment in bugsStore.comments"
        :key="comment.id"
        :comment="comment"
        :editing="editingId === comment.id"
        :can-modify="canModify(comment)"
        @edit="editingId = comment.id"
        @cancel="editingId = null"
        @save="saveEdit(comment.id, $event)"
        @delete="onDelete(comment.id)"
      />
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
import type { BugComment } from '@/types'
import BugCommentItem from './BugCommentItem.vue'

const props = defineProps<{
  bugId: string | null
}>()

const bugsStore = useBugsStore()
const authStore = useAuthStore()
const { canCommentOnBugs, canEditBugs } = usePermissions()

const newBody = ref('')
const posting = ref(false)
const editingId = ref<string | null>(null)

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

function canModify(comment: BugComment): boolean {
  if (comment.deletedAt) return false
  if (!authStore.user) return false
  if (comment.authorId === authStore.user.id) return true
  return canEditBugs.value
}

async function saveEdit(commentId: string, body: string): Promise<void> {
  if (!props.bugId || !body) return
  const updated = await bugsStore.editComment(props.bugId, commentId, body)
  if (updated) editingId.value = null
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
