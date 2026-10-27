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

<!-- Where the BUD sits in the lifecycle: done stages ticked, the current
     one ringed, the rest hollow. On narrow screens only the current
     stage keeps its name. -->
<template>
  <ol class="stage-stepper" aria-label="Stages">
    <li
      v-for="(step, i) in steps"
      :key="step.status"
      class="stage-stepper__step"
      :class="`stage-stepper__step--${step.state}`"
      :aria-current="step.state === 'current' ? 'step' : undefined"
    >
      <span class="stage-stepper__mark">
        <v-icon v-if="step.state === 'done'" icon="mdi-check" size="13" />
      </span>
      <span class="stage-stepper__name">
        {{ step.label }}<span v-if="step.state !== 'current'" class="d-sr-only">, {{ STATE_TEXT[step.state] }}</span>
      </span>
      <span v-if="i < steps.length - 1" class="stage-stepper__line" aria-hidden="true" />
    </li>
  </ol>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BUDStatus } from '@/types'
import { stageSteps, type StepState } from '@/utils/budDetail'

const props = defineProps<{
  phaseOrder: readonly BUDStatus[]
  status: BUDStatus
}>()

const STATE_TEXT: Record<StepState, string> = { done: 'done', current: 'current', todo: 'not started' }

const steps = computed(() => stageSteps(props.phaseOrder, props.status))
</script>

<style scoped>
.stage-stepper {
  list-style: none;
  margin: 0;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
.stage-stepper__step {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 0;
  min-width: 0;
}
.stage-stepper__step:last-child {
  flex: 0 0 auto;
}
.stage-stepper__mark {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  box-sizing: border-box;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 2px solid rgb(var(--v-theme-rule));
  color: rgb(var(--v-theme-on-primary));
}
.stage-stepper__step--done .stage-stepper__mark {
  border: 0;
  background: rgb(var(--v-theme-primary));
}
.stage-stepper__step--current .stage-stepper__mark {
  border: 6px solid rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-surface));
}
.stage-stepper__name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  color: rgb(var(--v-theme-on-surface-variant));
}
.stage-stepper__step--done .stage-stepper__name {
  color: rgb(var(--v-theme-on-surface));
}
.stage-stepper__step--current .stage-stepper__name {
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}
.stage-stepper__line {
  flex-grow: 1;
  height: 2px;
  min-width: 12px;
  margin: 0 10px;
  border-radius: 2px;
  background: rgb(var(--v-theme-rule));
}
.stage-stepper__step--done .stage-stepper__line {
  background: rgb(var(--v-theme-primary));
}
/* Not enough room for every name: keep only the current stage's. */
@container bud-page (max-width: 960px) {
  .stage-stepper__step:not(.stage-stepper__step--current) .stage-stepper__name {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }
  .stage-stepper__step--current {
    flex: 0 0 auto;
  }
  .stage-stepper__line {
    margin: 0 6px;
    min-width: 6px;
  }
}
/* Phone width: smaller marks and hairline gaps so eight stages still fit. */
@container bud-page (max-width: 560px) {
  .stage-stepper {
    padding: 12px 14px;
  }
  .stage-stepper__step {
    gap: 6px;
  }
  .stage-stepper__mark {
    width: 18px;
    height: 18px;
  }
  .stage-stepper__step--current .stage-stepper__mark {
    border-width: 5px;
  }
  .stage-stepper__line {
    margin: 0 2px;
    min-width: 0;
  }
}
</style>
