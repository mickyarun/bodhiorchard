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

<script setup lang="ts">
// Toolbar button that becomes disabled with an explanatory tooltip when
// the BUD is out of the section's owning phase. v-btn cannot accept
// tooltip activator bindings directly when wrapped, so the span sits
// between v-tooltip's activator and v-btn — that pattern was duplicated
// across Edit + Import in BUDSectionToolbar before this extraction.
defineProps<{
  disabled: boolean
  tooltip: string
  // When true the tooltip is suppressed (e.g. while an agent run owns
  // the BUD — the user gets a different banner for that state).
  tooltipDisabled: boolean
}>()
defineEmits<{ click: [] }>()
</script>

<template>
  <v-tooltip :disabled="tooltipDisabled" location="bottom" :text="tooltip">
    <template #activator="{ props: tipProps }">
      <span v-bind="tipProps">
        <v-btn
          variant="text"
          size="small"
          class="toolbar-btn"
          :disabled="disabled"
          @click="$emit('click')"
        >
          <slot />
        </v-btn>
      </span>
    </template>
  </v-tooltip>
</template>
