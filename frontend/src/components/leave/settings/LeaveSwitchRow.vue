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

<!-- A labelled on/off setting with a line explaining what it does. -->
<template>
  <div class="switch-row">
    <label :for="id" class="switch-row__text">
      <span class="text-body-2 font-weight-medium d-block">{{ label }}</span>
      <span v-if="description" class="text-caption text-medium-emphasis d-block">{{ description }}</span>
    </label>
    <v-switch :id="id" v-model="value" :disabled="disabled" color="primary" density="compact" hide-details inset />
  </div>
</template>

<script setup lang="ts">
import { useId } from 'vue'

defineProps<{ label: string; description?: string; disabled?: boolean }>()
const value = defineModel<boolean>({ required: true })

const id = useId()
</script>

<style scoped>
.switch-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 0;
}
.switch-row__text {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.switch-row :deep(.v-switch) {
  flex: 0 0 auto;
}
</style>
