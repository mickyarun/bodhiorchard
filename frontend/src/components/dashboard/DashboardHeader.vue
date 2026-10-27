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

<!-- Dashboard header: greeting, the view switch (Overview, Graph, Garden),
     the standup panel toggle and the one primary action, New BUD. Wraps to
     two rows on narrow screens. -->
<template>
  <header class="dash-header">
    <div class="dash-header__intro">
      <h1 class="dash-header__title">{{ greeting }}</h1>
      <p class="dash-header__sub">{{ subtitle }}</p>
    </div>
    <div class="dash-header__tools">
      <AppPillToggle v-model="view" :options="VIEW_OPTIONS" aria-label="Dashboard view" />
      <v-btn variant="outlined" :aria-pressed="standupOpen" @click="emit('standup')">Standup</v-btn>
      <v-btn v-if="canCreate" color="primary" variant="flat" prepend-icon="mdi-plus" @click="emit('new-bud')">
        New BUD
      </v-btn>
    </div>
  </header>
</template>

<script setup lang="ts">
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import type { DashboardViewMode } from '@/composables/useDashboardViewMode'

const VIEW_OPTIONS: { label: string; value: DashboardViewMode }[] = [
  { label: 'Overview', value: 'overview' },
  { label: 'Graph', value: 'graph' },
  { label: 'Garden', value: 'garden' },
]

defineProps<{
  greeting: string
  subtitle: string
  standupOpen: boolean
  canCreate: boolean
}>()

const view = defineModel<DashboardViewMode>({ required: true })
const emit = defineEmits<{ standup: []; 'new-bud': [] }>()
</script>

<style scoped>
.dash-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
}
.dash-header__intro {
  flex: 1 1 280px;
  min-width: 0;
}
.dash-header__title {
  margin: 0;
  font-size: 28px;
  line-height: 34px;
  font-weight: 600;
  letter-spacing: var(--tracking-display);
}
.dash-header__sub {
  margin: 4px 0 0;
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
.dash-header__tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
@media (max-width: 600px) {
  .dash-header__title {
    font-size: 24px;
    line-height: 30px;
  }
}
</style>
