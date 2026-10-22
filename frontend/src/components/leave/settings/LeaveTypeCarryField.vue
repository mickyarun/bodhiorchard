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

<!-- Whether a type's unused days carry into the next leave year, and how many. -->
<template>
  <div class="carry">
    <LeaveSwitchRow
      v-model="carries"
      label="Carry unused days into next year"
      :description="carries ? 'On the first day of the new leave year, up to this many unused days move across. The rest lapse.' : 'Unused days lapse when the leave year ends.'"
    />
    <v-text-field
      v-if="carries"
      v-model.number="upTo"
      label="Up to"
      type="number"
      min="0.5"
      max="365"
      step="0.5"
      suffix="days"
      class="up-to"
      v-bind="FIELD_PROPS"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LeaveSwitchRow from '@/components/leave/settings/LeaveSwitchRow.vue'
import type { Decimalish } from '@/types/leave'
import { toNumberOrNull } from '@/utils/leave'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const DEFAULT_CAP = 5

const cap = defineModel<Decimalish | null>({ required: true })

const carries = computed<boolean>({
  get: () => cap.value !== null,
  set: on => {
    cap.value = on ? DEFAULT_CAP : null
  },
})

const upTo = computed<number | null>({
  get: () => (cap.value === '' ? null : toNumberOrNull(cap.value)),
  set: value => {
    // Empty while typing stays empty (not null, which would switch carrying off).
    cap.value = typeof value === 'number' ? value : ''
  },
})
</script>

<style scoped>
.carry {
  align-self: stretch;
}
.up-to {
  max-width: 220px;
  margin-top: 4px;
}
</style>
