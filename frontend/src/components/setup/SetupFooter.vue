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

<!-- Wizard footer: Back · "n of N" · Continue — one primary action, always
     in the same place. Continue is hidden on the last step, where the step
     itself owns the final action. -->
<template>
  <div class="setup-footer">
    <v-btn variant="text" prepend-icon="mdi-arrow-left" :disabled="step === 0 || backLocked" @click="emit('back')">
      Back
    </v-btn>
    <span class="setup-footer__count">{{ step + 1 }} of {{ SETUP_STEPS.length }}</span>
    <v-btn
      v-if="step < SETUP_STEPS.length - 1"
      color="primary"
      append-icon="mdi-arrow-right"
      :loading="busy"
      @click="emit('next')"
    >
      Continue
    </v-btn>
    <span v-else />
  </div>
</template>

<script setup lang="ts">
import { SETUP_STEPS } from '@/components/setup/setupSteps'

// backLocked: earlier steps can no longer change (onboarding has started).
defineProps<{ step: number; busy: boolean; backLocked?: boolean }>()

const emit = defineEmits<{ back: []; next: [] }>()
</script>

<style scoped>
.setup-footer {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding-top: var(--space-sm, 1rem);
  border-top: 1px solid rgb(var(--v-theme-rule));
}

.setup-footer > :first-child {
  justify-self: start;
}

.setup-footer > :last-child {
  justify-self: end;
}

.setup-footer__count {
  font-size: 13px;
  color: rgb(var(--v-theme-muted));
}
</style>
