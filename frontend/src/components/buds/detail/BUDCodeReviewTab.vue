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

<!-- Code review tab: not started before the stage, the live PR board
     during it, and a done note after. A running review agent shows in
     the page's agent banner, not here. -->
<template>
  <div v-if="!reached" class="review-state">
    <v-icon icon="mdi-code-tags-check" size="40" />
    <h3>Code review hasn't started</h3>
    <p>It begins when development is done and the BUD moves to Code review.</p>
  </div>
  <div v-else-if="status !== 'code_review'" class="review-state">
    <v-icon icon="mdi-check-circle-outline" size="40" color="success" />
    <h3>Code review is done</h3>
  </div>
  <BUDCodeReviewStatus v-else :bud-id="budId" @transitioned="emit('transitioned')" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BUDCodeReviewStatus from '@/components/buds/BUDCodeReviewStatus.vue'
import { BUD_STATUS_ORDER, type BUDStatus } from '@/types'

const props = defineProps<{ budId: string; status: BUDStatus }>()
// After an override BUDCodeReviewStatus has moved the BUD on; the page
// refetches and the status watcher opens the Testing tab.
const emit = defineEmits<{ transitioned: [] }>()

// Uses the canonical, unfiltered order: this is a "stage reached" check.
const reached = computed(() => BUD_STATUS_ORDER.indexOf(props.status) >= BUD_STATUS_ORDER.indexOf('code_review'))
</script>

<style scoped>
.review-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 24px;
  text-align: center;
  color: rgb(var(--v-theme-on-surface-variant));
}
.review-state h3 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}
.review-state p {
  margin: 0;
  font-size: 14px;
}
</style>
