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

<!-- Confirm dialog for the Agent Prompts page's reset and delete actions.
     The default slot is the body text; Cancel closes through v-model. -->
<template>
  <v-dialog v-model="open" max-width="420">
    <v-card class="confirm-card">
      <div class="confirm-icon" :class="tone === 'warning' ? 'confirm-icon-warn' : 'confirm-icon-err'">
        <v-icon :icon="icon" size="24" />
      </div>
      <h3 class="confirm-title">{{ title }}</h3>
      <p class="confirm-body">
        <slot />
      </p>
      <div class="confirm-actions">
        <v-btn variant="text" class="text-none" @click="open = false">
          Cancel
        </v-btn>
        <v-btn
          :color="tone"
          variant="flat"
          class="text-none"
          :loading="loading"
          @click="emit('confirm')"
        >
          {{ confirmLabel }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  icon: string
  tone: 'warning' | 'error'
  title: string
  confirmLabel: string
  loading: boolean
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ confirm: [] }>()
</script>

<style scoped>
.confirm-card { padding: 24px; }
.confirm-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}
.confirm-icon-warn {
  background: rgba(var(--v-theme-warning), 0.16);
  color: rgb(var(--v-theme-warning));
}
.confirm-icon-err {
  background: rgba(var(--v-theme-error), 0.16);
  color: rgb(var(--v-theme-error));
}
.confirm-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 6px;
  color: rgb(var(--v-theme-on-surface));
}
.confirm-body {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  line-height: 1.55;
  margin: 0 0 18px;
}
.confirm-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
