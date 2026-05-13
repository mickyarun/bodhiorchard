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
import { watch } from 'vue'
import { useEstimates } from '@/composables/useEstimates'
import type { BUDStatus } from '@/types'
import BUDEstimateTimeline from './BUDEstimateTimeline.vue'

const props = defineProps<{
  budId: string
  currentPhase: BUDStatus
}>()

const {
  budEstimates, estimatesLoading, recalculating,
  overrideDialogOpen, overridePhase, overrideDate, overrideReason,
  loadEstimates, handleRecalculate, openOverrideDialog, submitOverride,
} = useEstimates(() => props.budId)

// Auto-load whenever the BUD identity changes. The parent can also
// trigger reloads via the exposed loadEstimates (after status changes,
// agent runs, webhooks) — both paths funnel through the same composable.
watch(() => props.budId, (id) => { if (id) void loadEstimates() }, { immediate: true })

defineExpose({ loadEstimates })
</script>

<template>
  <div class="bud-estimation-section">
    <BUDEstimateTimeline
      :estimates="budEstimates"
      :current-phase="currentPhase"
      :loading="estimatesLoading"
      :recalculating="recalculating"
      class="mt-4"
      @recalculate="handleRecalculate"
      @override-phase="openOverrideDialog"
    />

    <v-dialog v-model="overrideDialogOpen" max-width="420">
      <v-card color="surface" class="pa-5">
        <div class="text-subtitle-1 font-weight-medium mb-3">
          Override {{ overridePhase }} deadline
        </div>
        <v-text-field
          v-model="overrideDate"
          label="New deadline"
          type="date"
          class="mb-3"
        />
        <v-textarea
          v-model="overrideReason"
          label="Reason (required)"
          rows="3"
          :rules="[v => !!v?.trim() || 'Reason is required']"
        />
        <v-card-actions class="pa-0 mt-2">
          <v-spacer />
          <v-btn variant="text" @click="overrideDialogOpen = false">Cancel</v-btn>
          <v-btn
            color="warning"
            variant="flat"
            :disabled="!overrideDate || !overrideReason.trim()"
            @click="submitOverride"
          >
            Override
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
