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
  <div class="d-flex align-center justify-center flex-wrap ga-1 mb-8">
    <template v-for="(step, index) in steps" :key="step.key">
      <div
        class="d-flex flex-column align-center"
        :class="{ 'cursor-pointer': index < currentStep }"
        style="min-width: 64px;"
        @click="index < currentStep ? emit('go-to-step', index) : undefined"
      >
        <v-avatar
          :size="40"
          :color="index <= currentStep ? 'primary' : 'surface-variant'"
          :class="{ 'step-glow': index === currentStep }"
        >
          <v-icon
            :icon="index < currentStep ? 'mdi-check' : step.icon"
            :size="20"
            :color="index <= currentStep ? 'white' : 'grey'"
          />
        </v-avatar>
        <span
          class="text-caption mt-1 text-center"
          :class="index === currentStep ? 'text-primary font-weight-medium' : 'text-grey'"
          style="font-size: 0.7rem; line-height: 1.2;"
        >
          {{ step.title }}
        </span>
      </div>
      <v-divider
        v-if="index < steps.length - 1"
        class="align-self-start mt-5 mx-1"
        :color="index < currentStep ? 'primary' : 'rgba(255,255,255,0.1)'"
        :thickness="2"
        style="max-width: 32px; min-width: 16px; flex: 1;"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { StepDefinition } from '@/types/setup'

defineProps<{
  currentStep: number
}>()

const emit = defineEmits<{
  'go-to-step': [step: number]
}>()

const steps: StepDefinition[] = [
  { title: 'Welcome', icon: 'mdi-hand-wave-outline', key: 'welcome' },
  { title: 'Org', icon: 'mdi-domain', key: 'organization' },
  { title: 'Admin', icon: 'mdi-account-key-outline', key: 'admin' },
  { title: 'AI Engine', icon: 'mdi-robot-outline', key: 'ai-config' },
  { title: 'Repo', icon: 'mdi-source-repository', key: 'source-code' },
  { title: 'Launch', icon: 'mdi-rocket-launch-outline', key: 'review' },
]
</script>
