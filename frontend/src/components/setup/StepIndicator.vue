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

<!-- The wizard's step list. Vertical with descriptions in the side panel;
     on narrow screens it collapses to a row of numbered dots. Finished steps
     are buttons that jump back (until onboarding starts); upcoming steps are
     not interactive. -->
<template>
  <ol class="step-list" aria-label="Setup steps">
    <li
      v-for="(step, index) in SETUP_STEPS"
      :key="step.key"
      class="step-list__item"
      :class="`is-${stateOf(index)}`"
      :aria-current="index === currentStep ? 'step' : undefined"
    >
      <component
        :is="canJump(index) ? 'button' : 'div'"
        :type="canJump(index) ? 'button' : undefined"
        class="step-list__row"
        @click="canJump(index) && emit('go-to-step', index)"
      >
        <span class="step-list__dot" aria-hidden="true">
          <v-icon v-if="index < currentStep" icon="mdi-check" size="14" />
          <template v-else>{{ index + 1 }}</template>
        </span>
        <span class="step-list__text">
          <span class="step-list__title">{{ step.title }}</span>
          <span class="step-list__desc">{{ step.description }}</span>
        </span>
      </component>
    </li>
  </ol>
</template>

<script setup lang="ts">
import { SETUP_STEPS } from '@/components/setup/setupSteps'

// locked: finished steps can no longer be revisited (onboarding has started).
const props = defineProps<{ currentStep: number; locked?: boolean }>()

const emit = defineEmits<{ 'go-to-step': [step: number] }>()

function canJump(index: number): boolean {
  return index < props.currentStep && !props.locked
}

function stateOf(index: number): 'done' | 'current' | 'upcoming' {
  if (index < props.currentStep) return 'done'
  return index === props.currentStep ? 'current' : 'upcoming'
}
</script>

<style scoped>
/* Sits on the always-navy brand panel, so it uses the panel tokens. */
.step-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-list__row {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 12px;
  border: 0;
  border-radius: var(--radius-input, 8px);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
}

button.step-list__row {
  cursor: pointer;
}

button.step-list__row:hover {
  background: var(--color-panel-hover);
}

.step-list__dot {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: var(--radius-pill, 999px);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  border: 1.5px solid var(--color-panel-rule);
  color: var(--color-panel-ink-2);
}

.step-list__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-list__title {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-panel-ink-2);
}

.step-list__desc {
  font-size: 12px;
  color: var(--color-panel-muted);
}

.is-current .step-list__row {
  background: var(--color-panel-active);
}

.is-current .step-list__dot {
  border-color: var(--color-panel-accent);
  background: var(--color-panel-accent);
  color: var(--color-panel-accent-ink);
}

.is-current .step-list__title {
  color: var(--color-panel-ink);
  font-weight: 600;
}

.is-done .step-list__dot {
  border-color: var(--color-panel-accent);
  color: var(--color-panel-accent-2);
}

/* Narrow screens: a compact row of numbered dots, titles hidden. */
@media (max-width: 959px) {
  .step-list {
    flex-direction: row;
    justify-content: center;
    gap: 8px;
  }

  .step-list__row {
    padding: 4px;
  }

  .step-list__text {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
}
</style>
