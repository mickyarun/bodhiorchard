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
<!-- Quiz overlay launched from the dashboard garden (mirrors MiniGameHub). -->
<script setup lang="ts">
import { computed, watch } from 'vue'

import QuizCountdown from '@/components/quiz/QuizCountdown.vue'
import QuizPlay from '@/components/quiz/QuizPlay.vue'
import QuizReveal from '@/components/quiz/QuizReveal.vue'
import { useQuizStore } from '@/stores/quiz'
import type { QuizResponse } from '@/types/quiz'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const store = useQuizStore()

// Refresh state whenever the hub opens — the window may have closed since the
// dashboard last loaded, and the recap (past Q&A + next quiz) is loaded lazily.
watch(
  () => props.modelValue,
  open => {
    if (open) {
      void store.fetchActive()
      void store.fetchRecap()
    }
  }
)

function fmtNext(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const TYPE_LABEL: Record<string, string> = {
  multiple_choice: 'Multiple choice',
  scramble: 'Scramble',
  fill_blank: 'Fill in the blank',
}

const phase = computed<'loading' | 'reveal' | 'answered' | 'play' | 'none'>(() => {
  if (store.loading && !store.active) return 'loading'
  if (store.reveal) return 'reveal'
  if (store.active && store.active.alreadyAnswered) return 'answered'
  if (store.active) return 'play'
  return 'none'
})

async function onSubmit(response: QuizResponse): Promise<void> {
  if (store.active) await store.submitAnswer(store.active.id, response)
}

function close(value: boolean): void {
  if (!value) emit('update:modelValue', false)
}
</script>

<template>
  <v-dialog :model-value="props.modelValue" max-width="560" @update:model-value="close">
    <v-card rounded="xl" class="quiz-hub">
      <div class="d-flex align-center justify-space-between px-5 pt-4">
        <div class="d-flex align-center ga-2">
          <v-icon color="primary">mdi-head-question-outline</v-icon>
          <span class="text-subtitle-1 font-weight-bold">Company Quiz</span>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" @click="close(false)" />
      </div>

      <v-card-text class="px-5 pb-5 pt-2">
        <template v-if="phase === 'loading'">
          <v-skeleton-loader type="article, actions" />
        </template>

        <template v-else-if="phase === 'none'">
          <div class="text-center mb-4">
            <v-icon size="40" color="medium-emphasis">mdi-clock-outline</v-icon>
            <p class="text-subtitle-1 font-weight-medium mt-2 mb-0">No quiz open right now</p>
            <p class="text-medium-emphasis mb-0">
              <template v-if="store.recap?.nextQuizAt">
                Next quiz: {{ fmtNext(store.recap.nextQuizAt) }}
              </template>
              <template v-else>No upcoming quiz scheduled.</template>
            </p>
          </div>

          <template v-if="store.recap && store.recap.items.length">
            <div class="text-overline text-medium-emphasis mb-1">This month</div>
            <div class="recap-list">
              <div v-for="(it, i) in store.recap.items" :key="i" class="recap-item">
                <div class="d-flex align-center justify-space-between mb-1">
                  <span class="text-caption text-medium-emphasis">{{ fmtDate(it.quizDate) }}</span>
                  <span class="d-flex align-center ga-2">
                    <v-chip
                      size="x-small"
                      variant="tonal"
                      :color="
                        it.youAnswered ? (it.youCorrect ? 'success' : 'error') : undefined
                      "
                    >
                      {{ it.youAnswered ? (it.youCorrect ? 'You ✓' : 'You ✗') : 'Missed' }}
                    </v-chip>
                    <span class="text-caption text-medium-emphasis">
                      {{ it.percentCorrect }}% got it
                    </span>
                  </span>
                </div>
                <p class="text-body-2 font-weight-medium mb-1">{{ it.prompt }}</p>
                <p class="text-body-2 mb-1">
                  ✅ <span class="text-success">{{ it.correctAnswer }}</span>
                </p>
                <p class="text-caption text-medium-emphasis mb-0">{{ it.explanation }}</p>
              </div>
            </div>
          </template>
          <p v-else class="text-center text-medium-emphasis">No quizzes yet this month.</p>
        </template>

        <template v-else-if="phase === 'reveal' && store.reveal">
          <div class="d-flex align-center mb-3">
            <v-chip size="small" color="primary" variant="tonal" class="mr-2">
              {{ TYPE_LABEL[store.reveal.questionType] }}
            </v-chip>
            <span class="text-medium-emphasis text-body-2">Revealed</span>
          </div>
          <p class="text-h6 font-weight-bold mb-4">{{ store.reveal.prompt }}</p>
          <QuizReveal :reveal="store.reveal" />
        </template>

        <template v-else-if="phase === 'answered' && store.active">
          <div class="text-center py-8">
            <v-icon size="44" color="success">mdi-check-circle-outline</v-icon>
            <p class="text-h6 mt-3 mb-1">Answer locked in</p>
            <p class="text-medium-emphasis mb-3">
              The answer and explanation drop when the window closes.
            </p>
            <QuizCountdown :target="store.active.revealAt" label="Reveal in" />
          </div>
        </template>

        <template v-else-if="phase === 'play' && store.active">
          <div class="d-flex align-center justify-space-between mb-3">
            <div>
              <v-chip size="small" color="primary" variant="tonal" class="mr-2">
                {{ TYPE_LABEL[store.active.question.questionType] }}
              </v-chip>
              <v-chip size="small" variant="tonal">{{ store.active.question.difficulty }}</v-chip>
            </div>
            <QuizCountdown
              variant="ring"
              :start="store.active.openAt"
              :target="store.active.revealAt"
              label="left"
            />
          </div>
          <QuizPlay
            :key="store.active.question.id"
            :question="store.active.question"
            :submitting="store.submitting"
            @submit="onSubmit"
          />
        </template>

        <v-alert v-if="store.error" type="error" variant="tonal" class="mt-4" density="compact">
          {{ store.error }}
        </v-alert>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.quiz-hub {
  border: 1px solid var(--color-rule);
  background:
    radial-gradient(120% 80% at 0% 0%, var(--color-paper-3), transparent 60%), var(--color-paper-2);
}
.recap-list {
  max-height: 360px;
  overflow-y: auto;
}
.recap-item {
  padding: var(--space-xs) 0;
  border-bottom: 1px solid var(--color-rule);
}
.recap-item:last-child {
  border-bottom: none;
}
</style>
