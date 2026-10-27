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

<!-- Confirms deleting a BUD for good. -->
<template>
  <v-dialog v-model="open" max-width="420">
    <v-card color="surface" class="pa-6">
      <h2 class="delete-dialog__title">Delete this BUD?</h2>
      <p class="delete-dialog__text">{{ budRef(bud.bud_number) }}: {{ bud.title }} will be deleted permanently.</p>
      <v-card-actions class="pa-0">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="error" variant="flat" @click="emit('confirm')">Delete</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { budRef, type BUDListItem } from '@/types'

defineProps<{ bud: BUDListItem }>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ confirm: [] }>()
</script>

<style scoped>
.delete-dialog__title {
  margin: 0 0 8px;
  font-size: var(--text-md);
  font-weight: 600;
}
.delete-dialog__text {
  margin: 0 0 16px;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
