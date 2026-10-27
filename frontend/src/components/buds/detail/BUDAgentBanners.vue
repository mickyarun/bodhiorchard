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

<!-- Agent progress on the BUD detail page.

     The design stage runs one Claude job per repo, each with its own job
     id, so every design being generated gets its own banner and Cancel
     (a task-level cancel could only stop one of them). Other agents (PRD,
     tech spec, code review, phase workers) share one banner, which stays
     off during the design stage where the per-design banners already say
     everything. A failed agent task gets a retry callout. -->
<template>
  <div v-for="design in generatingDesigns" :key="design.id" class="agent-banner">
    <div class="agent-banner__row">
      <v-icon icon="mdi-palette-outline" size="20" color="primary" />
      <div class="agent-banner__text">
        <span class="agent-banner__name">Designer agent</span>
        <span class="agent-banner__msg">Generating wireframe for {{ design.repo_name || 'the default repo' }}</span>
      </div>
      <v-progress-linear indeterminate color="primary" height="3" rounded class="agent-banner__progress" />
      <v-btn
        size="small"
        variant="outlined"
        :loading="cancellingDesignId === design.id"
        @click="emit('cancel-design', design.id)"
      >
        Cancel
      </v-btn>
    </div>
  </div>

  <div v-if="agentRunning" class="agent-banner">
    <div class="agent-banner__row">
      <v-icon icon="mdi-robot-outline" size="20" color="primary" />
      <div class="agent-banner__text">
        <span class="agent-banner__name">{{ agentName || 'AI agent' }}</span>
        <span class="agent-banner__msg">{{ agentStatusMessage || 'Working…' }}</span>
      </div>
      <v-progress-linear indeterminate color="primary" height="3" rounded class="agent-banner__progress" />
      <v-btn v-if="canCancelAgent" size="small" variant="outlined" :loading="cancellingAgent" @click="emit('cancel-agent')">
        Cancel
      </v-btn>
    </div>
  </div>

  <AppCallout v-if="failedTask" variant="error" title="Agent task failed">
    <div v-if="failedTask.error_message">{{ failedTask.error_message }}</div>
    <div>Attempt {{ failedTask.attempt }}</div>
    <template #actions>
      <v-btn size="small" variant="outlined" prepend-icon="mdi-refresh" @click="emit('retry', failedTask.id)">Retry</v-btn>
    </template>
  </AppCallout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import type { BUDAgentTask, BUDDesign } from '@/types'
import '@/components/buds/agent-banner.css'

const props = defineProps<{
  generatingDesigns: BUDDesign[]
  agentRunning: boolean
  agentName?: string
  agentStatusMessage?: string
  task: BUDAgentTask | null
  cancellingDesignId: string | null
  cancellingAgent: boolean
}>()

const emit = defineEmits<{
  'cancel-design': [designId: string]
  'cancel-agent': []
  retry: [taskId: string]
}>()

const canCancelAgent = computed(() => Boolean(props.task?.job_id))
const failedTask = computed(() => (props.task?.status === 'failed' ? props.task : null))
</script>
