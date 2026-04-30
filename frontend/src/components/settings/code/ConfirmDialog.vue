<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

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
