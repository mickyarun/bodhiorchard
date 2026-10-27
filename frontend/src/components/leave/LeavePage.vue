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

<!-- Page frame shared by the leave screens: page padding, a 28px title with
     a one-line subtitle, and a trailing row of actions that wraps under the
     title on narrow screens. The page content goes in the default slot. -->
<template>
  <div class="leave-page">
    <header class="leave-page__head">
      <div class="leave-page__intro">
        <h1 class="leave-page__title">{{ title }}</h1>
        <p v-if="subtitle" class="leave-page__sub">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="leave-page__actions"><slot name="actions" /></div>
    </header>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<style scoped>
.leave-page {
  padding: 28px 36px 40px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.leave-page__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
}
.leave-page__intro {
  flex: 1 1 280px;
  min-width: 0;
}
.leave-page__title {
  margin: 0;
  font-size: 28px;
  line-height: 34px;
  font-weight: 600;
  letter-spacing: var(--tracking-display);
}
.leave-page__sub {
  margin: 4px 0 0;
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
.leave-page__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
@media (max-width: 600px) {
  .leave-page {
    padding: 20px 16px 32px;
  }
}
</style>
