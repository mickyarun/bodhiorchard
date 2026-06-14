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
<!-- Renders the open question for any of the three types and emits a submit. -->
<script setup lang="ts">
import { computed, ref } from 'vue'

import type { QuizQuestionPublic, QuizResponse } from '@/types/quiz'

const props = defineProps<{
  question: QuizQuestionPublic
  submitting: boolean
}>()

const emit = defineEmits<{ submit: [response: QuizResponse] }>()

const selectedIndex = ref<number | null>(null)
const textValue = ref('')

const choices = computed<string[]>(() => (props.question.payload.choices as string[]) ?? [])
const scrambled = computed<string>(() => (props.question.payload.scrambled as string) ?? '')
const hint = computed<string>(() => (props.question.payload.hint as string) ?? '')

const canSubmit = computed(() => {
  if (props.question.questionType === 'multiple_choice') return selectedIndex.value !== null
  return textValue.value.trim().length > 0
})

function submit(): void {
  if (!canSubmit.value || props.submitting) return
  const response: QuizResponse =
    props.question.questionType === 'multiple_choice'
      ? { index: selectedIndex.value as number }
      : { text: textValue.value.trim() }
  emit('submit', response)
}
</script>

<template>
  <div>
    <p class="quiz-prompt">{{ question.prompt }}</p>

    <!-- Multiple choice: selectable answer tiles -->
    <div v-if="question.questionType === 'multiple_choice'" class="quiz-choices">
      <button
        v-for="(choice, i) in choices"
        :key="i"
        type="button"
        class="quiz-choice"
        :class="{ 'quiz-choice--active': selectedIndex === i }"
        :disabled="submitting"
        @click="selectedIndex = i"
      >
        <span class="quiz-choice__bullet">{{ String.fromCharCode(65 + i) }}</span>
        <span>{{ choice }}</span>
      </button>
    </div>

    <!-- Scramble: show the jumbled letters, type the unscrambled answer -->
    <div v-else-if="question.questionType === 'scramble'">
      <div class="quiz-scramble">
        <span v-for="(ch, i) in scrambled.split('')" :key="i" class="quiz-scramble__tile">
          {{ ch }}
        </span>
      </div>
      <v-text-field
        v-model="textValue"
        label="Unscramble it"
        variant="outlined"
        density="comfortable"
        :disabled="submitting"
        hide-details
        @keyup.enter="submit"
      />
    </div>

    <!-- Fill in the blank: a single answer field with an optional hint -->
    <div v-else>
      <v-text-field
        v-model="textValue"
        label="Your answer"
        :hint="hint || undefined"
        persistent-hint
        variant="outlined"
        density="comfortable"
        :disabled="submitting"
        @keyup.enter="submit"
      />
    </div>

    <v-btn
      class="mt-4"
      color="primary"
      block
      size="large"
      :loading="submitting"
      :disabled="!canSubmit"
      @click="submit"
    >
      Lock in answer
    </v-btn>
  </div>
</template>

<style scoped>
.quiz-prompt {
  font-size: var(--text-md);
  font-weight: 600;
  line-height: 1.35;
  margin-bottom: var(--space-md);
}
.quiz-choices {
  display: flex;
  flex-direction: column;
  gap: var(--space-2xs);
}
.quiz-choice {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  text-align: left;
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--color-rule);
  border-radius: var(--radius-input);
  background: var(--color-paper-2);
  color: var(--color-ink);
  transition:
    border-color var(--dur-short) var(--ease-out),
    background var(--dur-short) var(--ease-out),
    transform var(--dur-short) var(--ease-out);
}
.quiz-choice:hover:not(:disabled) {
  border-color: var(--color-accent);
  transform: translateY(-1px);
}
.quiz-choice--active {
  border-color: var(--color-accent);
  background: var(--color-paper-3);
}
.quiz-choice__bullet {
  display: grid;
  place-items: center;
  min-width: 1.75rem;
  height: 1.75rem;
  border-radius: var(--radius-pill);
  background: var(--color-paper);
  font-weight: 700;
  font-size: var(--text-sm);
}
.quiz-scramble {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3xs);
  margin-bottom: var(--space-sm);
}
.quiz-scramble__tile {
  display: grid;
  place-items: center;
  min-width: 2.25rem;
  height: 2.5rem;
  border-radius: var(--radius-input);
  background: var(--color-paper-3);
  font-family: var(--font-mono);
  font-size: var(--text-md);
  font-weight: 700;
  text-transform: uppercase;
}
</style>
