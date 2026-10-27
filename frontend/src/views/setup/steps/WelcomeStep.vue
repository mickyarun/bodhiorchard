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
  <div class="welcome-step">
    <SetupStepHeader
      :step="0"
      title="Welcome to Glideship"
      description="Agents handle the specs, estimates, reviews and test plans. Your team keeps the decisions. Setup takes about five minutes."
    />

    <ul class="welcome-step__list">
      <li v-for="item in points" :key="item.title" class="welcome-step__item">
        <span class="welcome-step__icon" aria-hidden="true">
          <v-icon :icon="item.icon" size="20" />
        </span>
        <span class="welcome-step__text">
          <span class="welcome-step__title">{{ item.title }}</span>
          <span class="welcome-step__desc">{{ item.description }}</span>
        </span>
      </li>
    </ul>

    <p class="welcome-step__next">
      Next you'll name your workspace, create an admin, connect the AI engine and add a repository.
    </p>

    <v-btn color="primary" size="large" append-icon="mdi-arrow-right" @click="emit('getStarted')">
      Get started
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import SetupStepHeader from '@/components/setup/SetupStepHeader.vue'

const emit = defineEmits<{
  getStarted: []
}>()

const points = [
  {
    icon: 'mdi-account-group-outline',
    title: 'People decide, agents do the busywork',
    description: 'Every agent step is reviewed by a person before work moves on.',
  },
  {
    icon: 'mdi-arrow-right-circle-outline',
    title: 'Idea to production in one flow',
    description: 'A Slack message becomes a scoped BUD, then a spec, code, tests and a release.',
  },
  {
    icon: 'mdi-source-branch',
    title: 'Reads your real code',
    description: 'Agents run on your own machines with full context of your repositories.',
  },
]
</script>

<style scoped>
.welcome-step__list {
  list-style: none;
  margin: 0 0 var(--space-md, 1.5rem);
  padding: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: var(--radius-card, 10px);
  background: rgb(var(--v-theme-surface));
}

.welcome-step__item {
  display: flex;
  gap: 14px;
  padding: 18px 20px;
}

.welcome-step__item + .welcome-step__item {
  border-top: 1px solid rgb(var(--v-theme-rule));
}

.welcome-step__icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-input, 8px);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-accent-soft);
  color: var(--color-accent-text);
}

.welcome-step__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.welcome-step__title {
  font-size: 15px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
}

.welcome-step__desc {
  font-size: 14px;
  line-height: 20px;
  color: rgb(var(--v-theme-ink-2));
}

.welcome-step__next {
  margin: 0 0 var(--space-md, 1.5rem);
  font-size: 14px;
  color: rgb(var(--v-theme-muted));
}
</style>
