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

<!-- One leave policy in the settings list. -->
<template>
  <v-card color="surface" rounded="lg" class="pa-5 policy-card" @click="emit('open')">
    <div class="d-flex align-center ga-2">
      <span class="text-body-1 font-weight-bold text-truncate">{{ policy.name }}</span>
      <v-chip v-if="policy.is_default" size="x-small" color="primary" variant="tonal" label>
        Default
      </v-chip>
    </div>
    <div class="text-body-2 text-medium-emphasis mt-1">{{ region || 'No country set' }}</div>
    <div class="text-caption text-medium-emphasis mt-1">
      {{ policy.employee_count }} {{ policy.employee_count === 1 ? 'employee' : 'employees' }}
    </div>
    <div class="d-flex justify-end ga-1 mt-3">
      <v-btn
        v-if="!policy.is_default && policy.employee_count === 0"
        variant="text"
        size="small"
        color="error"
        @click.stop="emit('delete')"
      >
        Delete
      </v-btn>
      <v-btn v-if="!policy.is_default" variant="text" size="small" :loading="busy" @click.stop="emit('make-default')">
        Make default
      </v-btn>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import type { PolicyRead } from '@/types/leavePolicy'

defineProps<{ policy: PolicyRead; region: string; busy?: boolean }>()
const emit = defineEmits<{ open: []; 'make-default': []; delete: [] }>()
</script>

<style scoped>
.policy-card {
  cursor: pointer;
}
</style>
