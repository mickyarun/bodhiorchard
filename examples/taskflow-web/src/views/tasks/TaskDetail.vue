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
  <div v-if="task" class="task-detail">
    <h1>{{ task.title }}</h1>
    <div class="meta">
      <span class="status">{{ task.status }}</span>
      <span class="priority" :class="task.priority">{{ task.priority }}</span>
    </div>
    <p class="description">{{ task.description }}</p>

    <section class="comments">
      <h2>Comments ({{ comments.length }})</h2>
      <div v-for="c in comments" :key="c.id" class="comment">
        <strong>{{ c.author_id }}</strong>
        <p>{{ c.body }}</p>
      </div>
      <form @submit.prevent="addComment">
        <textarea v-model="newComment" placeholder="Add a comment..." />
        <button type="submit">Post</button>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/services/api'

const route = useRoute()
const taskId = route.params.id as string
const task = ref<Record<string, unknown> | null>(null)
const comments = ref<Array<{ id: number; body: string; author_id: number }>>([])
const newComment = ref('')

onMounted(async () => {
  const [taskRes, commentsRes] = await Promise.all([
    api.get(`/tasks/${taskId}`),
    api.get(`/tasks/${taskId}/comments`),
  ])
  task.value = taskRes.data
  comments.value = commentsRes.data
})

async function addComment() {
  if (!newComment.value.trim()) return
  const { data } = await api.post(`/tasks/${taskId}/comments`, { body: newComment.value })
  comments.value.unshift(data)
  newComment.value = ''
}
</script>
