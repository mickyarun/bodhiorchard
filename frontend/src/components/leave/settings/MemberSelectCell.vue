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

<!-- Row checkbox in the people table. A row that can't be moved (your own,
     unless you own the org) shows why on hover or focus. -->
<template>
  <v-tooltip v-if="!selectable" :text="OWN_POLICY_HINT" location="top">
    <template #activator="{ props: tip }">
      <span v-bind="tip" tabindex="0" :aria-label="`${name}: ${OWN_POLICY_HINT}`">
        <v-checkbox-btn disabled density="compact" />
      </span>
    </template>
  </v-tooltip>
  <v-checkbox-btn
    v-else
    :model-value="selected"
    density="compact"
    :aria-label="`Select ${name}`"
    @update:model-value="emit('toggle')"
  />
</template>

<script setup lang="ts">
import { OWN_POLICY_HINT } from '@/utils/policyMembers'

defineProps<{ name: string; selectable: boolean; selected: boolean }>()
const emit = defineEmits<{ toggle: [] }>()
</script>
