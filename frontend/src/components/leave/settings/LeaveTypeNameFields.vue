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

<!-- A leave type's name and code. The code follows the name until someone
     edits it (`codeTouched`, which the dialog resets each time it opens). -->
<template>
  <div class="name-row">
    <v-text-field v-model="name" label="Name" maxlength="100" autofocus v-bind="FIELD_PROPS" @update:model-value="syncCode" />
    <v-text-field v-model="code" label="Code" maxlength="10" v-bind="FIELD_PROPS" @update:model-value="codeTouched = true" />
  </div>
  <p class="text-caption text-medium-emphasis mt-2">
    The code is a short ID for reports, filled in from the name.
  </p>
</template>

<script setup lang="ts">
import { codeFromName } from '@/utils/leave'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const name = defineModel<string>('name', { required: true })
const code = defineModel<string>('code', { required: true })
const codeTouched = defineModel<boolean>('codeTouched', { required: true })

function syncCode(value: string): void {
  if (!codeTouched.value) code.value = codeFromName(value)
}
</script>

<style scoped>
.name-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 160px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 600px) {
  .name-row {
    grid-template-columns: 1fr;
  }
}
</style>
