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

<!-- Read-only label/value list used inside the employee profile cards:
     each label sits above its value. An empty value with an action (e.g.
     "Add") reads "Not added"; without one it is a dash. -->
<template>
  <dl class="field-grid">
    <div v-for="field in fields" :key="field.label" class="field-grid__item">
      <dt class="field-grid__label">
        {{ field.label }}
        <v-icon
          v-if="field.locked"
          icon="mdi-lock-outline"
          size="12"
          class="ml-1"
          :title="lockedHint"
          :aria-label="lockedHint"
        />
      </dt>
      <dd class="field-grid__value" :class="{ 'field-grid__value--empty': !field.value }">
        <span>{{ field.value || (field.action ? 'Not added' : '—') }}</span>
        <v-btn
          v-if="field.action"
          variant="text"
          size="small"
          density="compact"
          color="primary"
          class="field-grid__action"
          :aria-label="field.action.ariaLabel"
          @click="field.action.run"
        >
          {{ field.action.label }}
        </v-btn>
      </dd>
    </div>
  </dl>
</template>

<script setup lang="ts">
export interface GridField {
  label: string
  value: string | null | undefined
  /** Shown with a lock: the viewer can see but not change it. */
  locked?: boolean
  /** A text button beside the value, e.g. "Change" or "Add". */
  action?: { label: string; ariaLabel: string; run: () => void }
}

withDefaults(defineProps<{ fields: GridField[]; lockedHint?: string }>(), {
  lockedHint: 'Managed by HR',
})
</script>

<style scoped>
.field-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
}
.field-grid__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.field-grid__label {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  display: flex;
  align-items: center;
}
.field-grid__value {
  margin: 0;
  font-size: 14px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  overflow-wrap: anywhere;
}
.field-grid__value--empty > span {
  color: rgb(var(--v-theme-on-surface-variant));
}
.field-grid__action {
  margin-left: -4px;
}
</style>
