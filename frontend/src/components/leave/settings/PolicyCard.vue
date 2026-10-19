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

<!-- One leave policy in the settings list. The name is the button that
     opens it, stretched over the whole card; the menu sits above it. -->
<template>
  <v-card color="surface" border rounded="lg" class="pa-5 policy-card">
    <div class="d-flex align-center ga-2">
      <button type="button" class="policy-card__open text-body-1 font-weight-medium text-truncate" @click="emit('open')">
        {{ policy.name }}
      </button>
      <v-chip v-if="policy.is_default" size="x-small" color="primary" variant="tonal" label>Default</v-chip>
      <v-spacer />
      <v-menu location="bottom end">
        <template #activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            icon="mdi-dots-vertical"
            variant="text"
            size="small"
            class="policy-card__menu mr-n2"
            :loading="busy"
            :aria-label="`More actions for ${policy.name}`"
          />
        </template>
        <v-list density="comfortable" min-width="240">
          <v-list-item
            prepend-icon="mdi-star-outline"
            title="Make default"
            :disabled="policy.is_default"
            @click="emit('make-default')"
          />
          <v-list-item
            prepend-icon="mdi-delete-outline"
            title="Delete"
            :subtitle="blocker ?? undefined"
            :disabled="!!blocker"
            :base-color="blocker ? undefined : 'error'"
            @click="emit('delete')"
          />
        </v-list>
      </v-menu>
    </div>
    <div class="text-body-2 text-medium-emphasis">{{ region || 'No country set' }}</div>
    <div class="text-body-2 mt-4">{{ policyStatLine(policy) }}</div>
    <div class="text-caption text-medium-emphasis mt-1">{{ wfhRuleCaption(policy) }}</div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PolicyRead } from '@/types/leavePolicy'
import { deleteBlocker, policyStatLine, wfhRuleCaption } from '@/utils/leavePolicyDisplay'

const props = defineProps<{ policy: PolicyRead; region: string; busy?: boolean }>()
const emit = defineEmits<{ open: []; 'make-default': []; delete: [] }>()

const blocker = computed(() => deleteBlocker(props.policy))
</script>

<style scoped>
.policy-card {
  position: relative;
}
.policy-card:hover {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
}
.policy-card__open {
  appearance: none;
  border: none;
  background: none;
  padding: 0;
  color: inherit;
  text-align: left;
  cursor: pointer;
  min-width: 0;
}
/* The whole card is the click target. */
.policy-card__open::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
}
.policy-card__open:focus-visible {
  outline: none;
}
.policy-card__open:focus-visible::after {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.policy-card__menu {
  position: relative;
  z-index: 1;
}
</style>
