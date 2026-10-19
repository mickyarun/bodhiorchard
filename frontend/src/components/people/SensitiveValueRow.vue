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

<!-- One masked value with Reveal. A revealed value hides itself again after
     REVEAL_SECONDS; every reveal is in the person's access log. -->
<template>
  <div class="value-row">
    <div class="value-row__label text-caption text-medium-emphasis">{{ label }}</div>
    <div class="value-row__value">
      <span v-if="shown !== null" class="revealed">{{ shown || '—' }}</span>
      <span v-else :class="{ 'text-medium-emphasis': !value.is_set }">{{ maskLabel(value) }}</span>
    </div>
    <div class="value-row__action">
      <template v-if="shown !== null">
        <span class="text-caption text-medium-emphasis mr-2">Hides in {{ remaining }}s</span>
        <v-btn size="small" variant="text" @click="hide">Hide</v-btn>
      </template>
      <v-btn
        v-else-if="canReveal && value.is_set"
        size="small"
        variant="text"
        prepend-icon="mdi-eye-outline"
        :loading="revealing"
        :aria-label="`Show ${label}`"
        @click="show"
      >
        Show
      </v-btn>
    </div>
    <div v-if="error" class="value-row__error text-caption text-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import type { MaskedValue } from '@/types/employeeRecords'
import { maskLabel, REVEAL_SECONDS } from '@/utils/employeeRecords'

const props = defineProps<{
  label: string
  value: MaskedValue
  canReveal: boolean
  reveal: () => Promise<{ value: string | null } | { error: string }>
}>()

const shown = ref<string | null>(null)
const remaining = ref(REVEAL_SECONDS)
const revealing = ref(false)
const error = ref('')
let timer: ReturnType<typeof setInterval> | null = null

function hide(): void {
  shown.value = null
  if (timer) clearInterval(timer)
  timer = null
}

async function show(): Promise<void> {
  revealing.value = true
  const result = await props.reveal()
  revealing.value = false
  if ('error' in result) {
    error.value = result.error
    return
  }
  error.value = ''
  shown.value = result.value ?? ''
  remaining.value = REVEAL_SECONDS
  timer = setInterval(() => {
    remaining.value -= 1
    if (remaining.value <= 0) hide()
  }, 1000)
}

onBeforeUnmount(hide)
</script>

<style scoped>
.value-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) auto;
  align-items: center;
  gap: 4px 16px;
  padding: 10px 0;
  border-bottom: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
}
.value-row__value {
  overflow-wrap: anywhere;
}
.value-row__error {
  grid-column: 2 / -1;
}
.revealed {
  font-family: var(--font-mono, ui-monospace, monospace);
}
@media (max-width: 600px) {
  .value-row {
    grid-template-columns: 1fr auto;
  }
  .value-row__label {
    grid-column: 1 / -1;
  }
}
</style>
