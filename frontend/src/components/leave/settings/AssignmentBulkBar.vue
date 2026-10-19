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

<!-- Sticky bar while people are selected: move them to a policy, or clear
     the selection. -->
<template>
  <v-slide-y-reverse-transition>
    <div v-if="count" class="bulk-bar" role="region" aria-label="Selected people">
      <span class="text-body-2 font-weight-medium">{{ count }} selected</span>
      <v-spacer />
      <v-menu location="top end">
        <template #activator="{ props: menuProps }">
          <v-btn v-bind="menuProps" color="primary" variant="flat" append-icon="mdi-menu-up">
            Move to policy…
          </v-btn>
        </template>
        <v-list density="comfortable" min-width="240" aria-label="Policies">
          <v-list-item
            v-for="policy in policies"
            :key="policy.id"
            :title="policy.name"
            :subtitle="policy.is_default ? 'Default policy' : undefined"
            @click="emit('move', policy)"
          />
        </v-list>
      </v-menu>
      <v-btn variant="text" @click="emit('clear')">Clear</v-btn>
    </div>
  </v-slide-y-reverse-transition>
</template>

<script setup lang="ts">
import type { PolicyRead } from '@/types/leavePolicy'

defineProps<{ count: number; policies: PolicyRead[] }>()
const emit = defineEmits<{ move: [policy: PolicyRead]; clear: [] }>()
</script>

<style scoped>
.bulk-bar {
  position: sticky;
  bottom: 16px;
  z-index: 5;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
  padding: 10px 12px 10px 16px;
  border-radius: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
}
</style>
