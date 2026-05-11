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

<!--
  Tiny confirm dialog used for destructive row actions on /settings/code.
  Sits on top of v-model so callers can drive open/close from a ref and
  await the result through @confirm — no Promise plumbing required.
-->
<template>
  <v-dialog :model-value="modelValue" max-width="420" @update:model-value="onUpdate">
    <v-card color="surface">
      <v-card-title class="d-flex align-center ga-2 py-3">
        <v-icon :icon="icon" :color="tone" size="20" />
        <span class="text-body-1 font-weight-medium">{{ title }}</span>
      </v-card-title>
      <v-divider />
      <div class="pa-5 text-body-2">{{ message }}</div>
      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" class="text-none" @click="cancel">
          {{ cancelLabel }}
        </v-btn>
        <v-btn :color="tone" variant="flat" class="text-none" @click="confirm">
          {{ confirmLabel }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue: boolean
    title: string
    message: string
    confirmLabel?: string
    cancelLabel?: string
    tone?: 'primary' | 'error' | 'warning'
    icon?: string
  }>(),
  {
    confirmLabel: 'Confirm',
    cancelLabel: 'Cancel',
    tone: 'error',
    icon: 'mdi-alert-outline',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
  cancel: []
}>()

function onUpdate(v: boolean): void {
  emit('update:modelValue', v)
  if (!v) emit('cancel')
}

function confirm(): void {
  emit('confirm')
  emit('update:modelValue', false)
}

function cancel(): void {
  emit('cancel')
  emit('update:modelValue', false)
}
</script>
