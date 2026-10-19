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

<!-- A settings section: icon, title and caption over its content, with
     optional header actions on the right. -->
<template>
  <v-card tag="section" color="surface" border rounded="lg" class="pa-6 mb-6" :aria-labelledby="headingId">
    <header class="section-head" :class="{ 'mb-5': $slots.default }">
      <v-avatar size="36" color="surface-variant" rounded="lg">
        <v-icon :icon="icon" size="22" />
      </v-avatar>
      <div class="section-head__text">
        <h3 :id="headingId" class="text-body-1 font-weight-medium">{{ title }}</h3>
        <p v-if="caption" class="text-caption text-medium-emphasis">{{ caption }}</p>
      </div>
      <div v-if="$slots.actions" class="section-head__actions">
        <slot name="actions" />
      </div>
    </header>
    <slot />
  </v-card>
</template>

<script setup lang="ts">
import { useId } from 'vue'

defineProps<{ icon: string; title: string; caption?: string }>()

const headingId = useId()
</script>

<style scoped>
.section-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.section-head__text {
  flex: 1 1 240px;
  min-width: 0;
}
.section-head__text p {
  max-width: 72ch;
}
.section-head__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
