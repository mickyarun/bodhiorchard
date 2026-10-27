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

<!-- Shared heading for every setup step: "Step n of N", title, one line. -->
<template>
  <header class="setup-step-header">
    <p class="setup-step-header__eyebrow">Step {{ step + 1 }} of {{ SETUP_STEPS.length }}</p>
    <h1 class="setup-step-header__title">{{ title }}</h1>
    <p v-if="description" class="setup-step-header__desc">{{ description }}</p>
  </header>
</template>

<script setup lang="ts">
import { SETUP_STEPS } from '@/components/setup/setupSteps'

defineProps<{ step: number; title: string; description?: string }>()
</script>

<style scoped>
.setup-step-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: var(--space-md, 1.5rem);
}

.setup-step-header__eyebrow {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-muted));
}

.setup-step-header__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 28px;
  line-height: 34px;
  font-weight: 600;
  letter-spacing: var(--tracking-display, -0.02em);
  color: rgb(var(--v-theme-on-background));
}

.setup-step-header__desc {
  margin: 0;
  font-size: 15px;
  line-height: 22px;
  color: rgb(var(--v-theme-ink-2));
  max-width: 560px;
}
</style>
