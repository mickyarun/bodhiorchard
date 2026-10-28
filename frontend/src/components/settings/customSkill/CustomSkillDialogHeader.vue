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

<!-- Title bar of the "New custom skill" dialog, with its close button. -->
<template>
  <header class="dialog-header">
    <div class="dialog-icon">
      <v-icon icon="mdi-robot-happy-outline" size="20" />
    </div>
    <div class="dialog-title-wrap">
      <h3 class="dialog-title">New custom skill</h3>
      <div class="dialog-sub">
        Plugs in alongside the seeded defaults. Promote to default
        when ready.
      </div>
    </div>
    <v-btn
      icon="mdi-close"
      variant="text"
      size="small"
      density="comfortable"
      @click="emit('close')"
    />
  </header>
</template>

<script setup lang="ts">
const emit = defineEmits<{ close: [] }>()
</script>

<style scoped>
.dialog-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  flex-shrink: 0;
}

.dialog-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.14);
  color: rgb(var(--v-theme-primary));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.dialog-icon .v-icon { color: rgb(var(--v-theme-primary)); }

.dialog-title-wrap { flex: 1; min-width: 0; }
.dialog-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 2px;
  color: rgb(var(--v-theme-on-surface));
}
.dialog-sub {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  line-height: 1.45;
}
</style>
