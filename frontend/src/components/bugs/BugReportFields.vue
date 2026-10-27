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

<!-- The written part of a bug report: title, description, severity and the
     module or area it's in. -->
<template>
  <div class="bug-report-fields">
    <v-text-field
      v-model="title"
      :disabled="disabled"
      label="Title *"
      variant="outlined"
      density="compact"
      :rules="[(v: string) => !!v?.trim() || 'Title is required']"
    />
    <v-textarea
      v-model="description"
      :disabled="disabled"
      label="Description"
      variant="outlined"
      density="compact"
      rows="3"
      placeholder="Steps to reproduce, expected vs actual behaviour"
    />
    <div class="bug-report-fields__row">
      <v-select
        v-model="severity"
        :disabled="disabled"
        :items="SEVERITY_ITEMS"
        label="Severity"
        variant="outlined"
        density="compact"
      />
      <v-text-field
        v-model="module"
        :disabled="disabled"
        label="Module / Area"
        variant="outlined"
        density="compact"
        placeholder="e.g. payments, auth"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BugSeverity } from '@/types'
import { BUG_SEVERITY_OPTIONS } from '@/utils/bugList'

defineProps<{ disabled: boolean }>()

const title = defineModel<string>('title', { required: true })
const description = defineModel<string>('description', { required: true })
const severity = defineModel<BugSeverity>('severity', { required: true })
const module = defineModel<string>('module', { required: true })

// Least to most severe, as people read a dropdown.
const SEVERITY_ITEMS = [...BUG_SEVERITY_OPTIONS].reverse().map(o => ({ title: o.label, value: o.value }))
</script>

<style scoped>
.bug-report-fields {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bug-report-fields__row {
  display: flex;
  flex-wrap: wrap;
  gap: 0 12px;
}
.bug-report-fields__row > * {
  flex: 1 1 180px;
}
</style>
