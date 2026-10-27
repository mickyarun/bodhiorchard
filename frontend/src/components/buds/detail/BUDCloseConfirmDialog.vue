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

<!-- Asks before a BUD moves to Closed: closing runs the close-out (XP,
     SP, learning recap) and a closed BUD can't be reopened. -->
<template>
  <v-dialog v-model="open" max-width="440">
    <v-card color="surface" class="pa-6">
      <h2 class="close-dialog__title">Close this BUD?</h2>
      <p class="close-dialog__text">
        Closing runs the close-out: contributor XP, shipped SP and the learning recap. It can't be undone, and
        a closed BUD can't move to another stage.
      </p>
      <v-card-actions class="pa-0">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" variant="flat" @click="emit('confirm')">Close BUD</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ confirm: [] }>()
</script>

<style scoped>
.close-dialog__title {
  margin: 0 0 8px;
  font-size: var(--text-md);
  font-weight: 600;
}
.close-dialog__text {
  margin: 0 0 16px;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
