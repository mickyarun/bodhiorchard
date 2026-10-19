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

<!-- Read-only label/value grid used across the employee profile tabs.
     Two columns of pairs on wide screens, one pair per row on narrow. -->
<template>
  <dl class="field-grid">
    <template v-for="field in fields" :key="field.label">
      <dt class="field-grid__label">
        {{ field.label }}
        <v-icon
          v-if="field.locked"
          icon="mdi-lock-outline"
          size="12"
          class="ml-1"
          :title="lockedHint"
        />
      </dt>
      <dd class="field-grid__value" :class="{ 'field-grid__value--empty': !field.value }">
        {{ field.value || '—' }}
      </dd>
    </template>
  </dl>
</template>

<script setup lang="ts">
export interface GridField {
  label: string
  value: string | null | undefined
  /** Shown with a lock: the viewer can see but not change it. */
  locked?: boolean
}

withDefaults(defineProps<{ fields: GridField[]; lockedHint?: string }>(), {
  lockedHint: 'Managed by HR',
})
</script>

<style scoped>
.field-grid {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr) 160px minmax(0, 1fr);
  gap: 12px 24px;
  margin: 0;
}
.field-grid__label {
  font-size: 12px;
  color: rgb(var(--v-theme-muted, var(--v-theme-on-surface)));
  opacity: 0.85;
}
.field-grid__value {
  margin: 0;
  font-size: 14px;
  overflow-wrap: anywhere;
}
.field-grid__value--empty {
  opacity: 0.5;
}
@media (max-width: 900px) {
  .field-grid {
    grid-template-columns: 140px minmax(0, 1fr);
  }
}
@media (max-width: 600px) {
  .field-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 2px 0;
  }
  .field-grid__value {
    margin-bottom: 10px;
  }
}
</style>
