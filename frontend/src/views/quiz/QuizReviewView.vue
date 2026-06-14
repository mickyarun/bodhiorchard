<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->
<!-- Admin review queue: approve / edit / reject AI-drafted questions. -->
<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'

import AppCallout from '@/components/common/AppCallout.vue'
import { useQuizReviewStore } from '@/stores/quizReview'
import type { QuizReviewItem } from '@/types/quiz'

const store = useQuizReviewStore()
const editing = reactive<Record<string, { prompt: string; explanation: string }>>({})

const drafts = computed(() => store.queue.filter(q => q.status === 'draft'))
const approved = computed(() => store.queue.filter(q => q.status === 'approved'))

function answerText(q: QuizReviewItem): string {
  if (q.questionType === 'multiple_choice') {
    const choices = (q.payload.choices as string[]) ?? []
    return choices[q.answerKey.correct_index as number] ?? ''
  }
  return (q.answerKey.answer as string) ?? ''
}

function startEdit(q: QuizReviewItem): void {
  editing[q.id] = { prompt: q.prompt, explanation: q.explanation }
}
async function saveEdit(id: string): Promise<void> {
  if (await store.editQuestion(id, editing[id])) delete editing[id]
}
async function regenerate(): Promise<void> {
  await store.regenerate()
}

onMounted(() => store.fetchQueue())
</script>

<template>
  <v-container class="py-6" style="max-width: 860px">
    <header class="d-flex align-center justify-space-between mb-4">
      <div>
        <h1 class="text-h5 font-weight-bold">Quiz Review</h1>
        <p class="text-medium-emphasis mb-0">Approve questions before they go live to the team.</p>
      </div>
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" @click="regenerate">
        Generate more
      </v-btn>
    </header>

    <AppCallout
      v-if="approved.length < 2"
      variant="warning"
      icon="mdi-alert-outline"
      title="Approved queue is low"
      class="mb-4"
    >
      Approve a few questions so upcoming quiz days don't get skipped.
    </AppCallout>

    <v-alert v-if="store.error" type="error" variant="tonal" density="compact" class="mb-4">
      {{ store.error }}
    </v-alert>

    <div v-if="!store.loading && !drafts.length && !approved.length" class="text-center py-10">
      <v-icon size="44" color="medium-emphasis">mdi-clipboard-text-outline</v-icon>
      <p class="text-h6 mt-3">Nothing to review</p>
      <p class="text-medium-emphasis">Click "Generate more" to draft a question now.</p>
    </div>

    <h2 v-if="drafts.length" class="text-subtitle-1 font-weight-bold mb-2">
      Drafts ({{ drafts.length }})
    </h2>
    <v-card v-for="q in drafts" :key="q.id" class="mb-3" rounded="lg" variant="outlined">
      <v-card-text>
        <div class="d-flex ga-2 mb-2">
          <v-chip size="x-small" color="primary" variant="tonal">{{ q.questionType }}</v-chip>
          <v-chip size="x-small" variant="tonal">{{ q.difficulty }}</v-chip>
          <v-chip v-if="q.category" size="x-small" variant="text">{{ q.category }}</v-chip>
        </div>

        <template v-if="editing[q.id]">
          <v-textarea
            v-model="editing[q.id].prompt"
            label="Prompt"
            rows="2"
            auto-grow
            variant="outlined"
            density="compact"
            class="mb-2"
          />
          <v-textarea
            v-model="editing[q.id].explanation"
            label="Explanation"
            rows="2"
            auto-grow
            variant="outlined"
            density="compact"
          />
          <div class="d-flex ga-2">
            <v-btn size="small" color="primary" @click="saveEdit(q.id)">Save</v-btn>
            <v-btn size="small" variant="text" @click="delete editing[q.id]">Cancel</v-btn>
          </div>
        </template>

        <template v-else>
          <p class="text-body-1 font-weight-medium mb-1">{{ q.prompt }}</p>
          <p class="text-body-2 mb-1">
            <strong>Answer:</strong> <span class="text-success">{{ answerText(q) }}</span>
          </p>
          <p class="text-body-2 text-medium-emphasis mb-3">{{ q.explanation }}</p>
          <div class="d-flex ga-2">
            <v-btn size="small" color="success" variant="flat" @click="store.approve(q.id)">
              Approve
            </v-btn>
            <v-btn size="small" variant="tonal" @click="startEdit(q)">Edit</v-btn>
            <v-btn size="small" color="error" variant="text" @click="store.reject(q.id)">
              Reject
            </v-btn>
          </div>
        </template>
      </v-card-text>
    </v-card>

    <h2 v-if="approved.length" class="text-subtitle-1 font-weight-bold mb-2 mt-6">
      Approved &amp; ready ({{ approved.length }})
    </h2>
    <v-card v-for="q in approved" :key="q.id" class="mb-2" rounded="lg" variant="tonal">
      <v-card-text class="d-flex align-center ga-3 py-2">
        <span class="text-body-2 quiz-approved__prompt">{{ q.prompt }}</span>
        <v-chip size="x-small" color="success" variant="flat" class="flex-shrink-0">
          approved
        </v-chip>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<style scoped>
/* Let the prompt take remaining width and wrap, so the chip never clips. */
.quiz-approved__prompt {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
