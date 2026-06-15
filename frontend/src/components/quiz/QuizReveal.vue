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
<!-- The payoff screen: correct answer, your result, social proof, explanation. -->
<script setup lang="ts">
import { computed } from 'vue'

import AppCallout from '@/components/common/AppCallout.vue'
import type { QuizReveal } from '@/types/quiz'

const props = defineProps<{ reveal: QuizReveal }>()

const correctAnswer = computed<string>(() => {
  const key = props.reveal.answerKey
  if (props.reveal.questionType === 'multiple_choice') {
    const choices = (props.reveal.payload.choices as string[]) ?? []
    const idx = key.correct_index as number
    return choices[idx] ?? ''
  }
  return (key.answer as string) ?? ''
})

const aliases = computed<string[]>(() => (props.reveal.answerKey.aliases as string[]) ?? [])
const got = computed(() => props.reveal.yourAnswer?.isCorrect ?? null)
</script>

<template>
  <div>
    <AppCallout
      v-if="got !== null"
      :variant="got ? 'success' : 'warning'"
      :icon="got ? 'mdi-check-decagram' : 'mdi-emoticon-neutral-outline'"
      :title="got ? `You nailed it — +${reveal.yourAnswer?.points} pts` : 'Not this time'"
    >
      {{ reveal.percentCorrect }}% of the team got this one right.
    </AppCallout>
    <AppCallout v-else variant="info" icon="mdi-account-off-outline" title="You sat this one out">
      {{ reveal.percentCorrect }}% of the team got it right.
    </AppCallout>

    <div class="reveal-answer mt-4">
      <span class="reveal-answer__label">Correct answer</span>
      <span class="reveal-answer__value">{{ correctAnswer }}</span>
      <span v-if="aliases.length" class="reveal-answer__aliases">
        also accepted: {{ aliases.join(', ') }}
      </span>
    </div>

    <p class="reveal-explanation mt-3">{{ reveal.explanation }}</p>

    <div class="reveal-stats mt-4">
      <div class="reveal-bar">
        <div class="reveal-bar__fill" :style="{ width: `${reveal.percentCorrect}%` }" />
      </div>
      <span class="reveal-stats__caption">
        {{ reveal.correctAnswers }} of {{ reveal.totalAnswers }} correct
      </span>
    </div>
  </div>
</template>

<style scoped>
.reveal-answer {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.reveal-answer__label {
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-muted);
}
.reveal-answer__value {
  font-size: var(--text-md);
  font-weight: 700;
  color: var(--color-accent);
}
.reveal-answer__aliases {
  font-size: var(--text-sm);
  color: var(--color-muted);
}
.reveal-explanation {
  color: var(--color-ink-2);
  line-height: 1.5;
}
.reveal-bar {
  height: 8px;
  border-radius: var(--radius-pill);
  background: var(--color-paper-3);
  overflow: hidden;
}
.reveal-bar__fill {
  height: 100%;
  background: var(--color-success);
  transition: width var(--dur-mid) var(--ease-out);
}
.reveal-stats__caption {
  display: block;
  margin-top: var(--space-3xs);
  font-size: var(--text-sm);
  color: var(--color-muted);
}
</style>
