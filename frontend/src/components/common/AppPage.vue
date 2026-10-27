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

<!-- Page frame: the page padding, a 28px title with a one-line subtitle,
     and a trailing row of controls that wraps under the title on narrow
     screens. Page content goes in the default slot.

       <AppPage title="Bugs" subtitle="4 open">
         <template #actions><v-btn …>Report a bug</v-btn></template>
         …
       </AppPage>

     The #subtitle slot replaces the subtitle prop when it needs markup. -->
<template>
  <div class="app-page">
    <header class="app-page__head">
      <div class="app-page__intro">
        <h1 class="app-page__title">{{ title }}</h1>
        <p v-if="subtitle || $slots.subtitle" class="app-page__sub">
          <slot name="subtitle">{{ subtitle }}</slot>
        </p>
      </div>
      <div v-if="$slots.actions" class="app-page__actions"><slot name="actions" /></div>
    </header>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<style scoped>
.app-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  min-height: 100%;
  padding: 28px 36px 40px;
  background: rgb(var(--v-theme-background));
}
.app-page__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
}
.app-page__intro {
  flex: 1 1 280px;
  min-width: 0;
}
.app-page__title {
  margin: 0;
  font-size: 28px;
  line-height: 34px;
  font-weight: 600;
  letter-spacing: var(--tracking-display);
}
.app-page__sub {
  margin: 4px 0 0;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.app-page__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
@media (max-width: 600px) {
  .app-page {
    padding: 20px 16px 32px;
  }
  .app-page__title {
    font-size: 24px;
    line-height: 30px;
  }
}
</style>
