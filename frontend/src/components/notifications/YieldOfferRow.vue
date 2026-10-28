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

<!-- A pending yield offer: one BUD waiting on another person's lower-
     priority BUD. Its target can accept or reject; admins can reassign
     any offer that isn't theirs. Same layout as a notification row. -->
<template>
  <li class="n-row n-row--unread">
    <span class="n-row__icon n-row__icon--warning" aria-hidden="true">
      <v-icon icon="mdi-flag-outline" size="18" />
    </span>
    <div class="n-row__text">
      <span class="n-row__title">
        {{ budRef(offer.incoming_bud_number ?? 0) }} ({{ offer.incoming_bud_priority }})
        waits on {{ budRef(offer.yieldable_bud_number ?? 0) }} ({{ offer.yieldable_bud_priority }})
      </span>
      <p class="n-row__body">
        <template v-if="mine">Your lower-priority BUD can be set aside for it.</template>
        <template v-else>Offered to {{ targetName }}.</template>
      </p>
      <div class="n-row__inline">
        <template v-if="mine">
          <v-btn size="small" variant="tonal" color="primary" :loading="busy" @click="emit('accept')">Accept</v-btn>
          <v-btn size="small" variant="outlined" :disabled="busy" @click="emit('reject')">Reject</v-btn>
        </template>
        <v-btn v-if="canReassign" size="small" variant="outlined" :disabled="busy" @click="emit('reassign')">
          Reassign…
        </v-btn>
      </div>
    </div>
  </li>
</template>

<script setup lang="ts">
import { budRef, type YieldOffer } from '@/types'

defineProps<{
  offer: YieldOffer
  /** The viewer is the offer's target. */
  mine: boolean
  canReassign: boolean
  targetName: string
  busy: boolean
}>()

const emit = defineEmits<{ accept: []; reject: []; reassign: [] }>()
</script>

<style scoped src="./notification-row.css"></style>
