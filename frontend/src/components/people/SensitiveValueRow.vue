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
    <div class="value-row__label">{{ label }}</div>
    <div class="value-row__value">
      <span v-if="shown !== null" class="revealed">{{ shown || '—' }}</span>
      <span v-else :class="{ 'value-row__unset': !value.is_set }">{{ maskLabel(value) }}</span>
      <template v-if="shown !== null">
        <v-btn size="small" variant="outlined" density="comfortable" :aria-label="`Hide ${label}`" @click="hide">
          Hide
        </v-btn>
        <span class="value-row__timer">Hides in {{ remaining }}s</span>
      </template>
      <v-btn
        v-else-if="canReveal && value.is_set"
        size="small"
        variant="outlined"
        density="comfortable"
        prepend-icon="mdi-eye-outline"
        :loading="revealing"
        :aria-label="`Reveal ${label}`"
        @click="show"
      >
        Reveal
      </v-btn>
    </div>
    <div v-if="error" class="value-row__error">{{ error }}</div>
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
let unmounted = false

function hide(): void {
  shown.value = null
  if (timer) clearInterval(timer)
  timer = null
}

async function show(): Promise<void> {
  revealing.value = true
  const result = await props.reveal()
  revealing.value = false
  // Left the tab while the reveal was in flight: don't hold the value.
  if (unmounted) return
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

onBeforeUnmount(() => {
  unmounted = true
  hide()
})
</script>

<style scoped>
.value-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.value-row__label {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.value-row__value {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 10px;
  font-size: 14px;
  overflow-wrap: anywhere;
}
.value-row__unset,
.value-row__timer {
  color: rgb(var(--v-theme-on-surface-variant));
}
.value-row__timer {
  font-size: 12px;
}
.value-row__error {
  font-size: 12px;
  color: rgb(var(--v-theme-error));
}
.revealed {
  font-family: var(--font-mono);
}
</style>
