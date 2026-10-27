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

<!-- New BUD form. Shared by the board and the dashboard; on success it
     opens the new BUD. -->
<template>
  <v-dialog v-model="open" max-width="560">
    <v-card color="surface" class="pa-6">
      <h2 class="bud-create__title mb-4">New BUD</h2>
      <v-text-field
        v-model="form.title.value"
        label="Title"
        placeholder="e.g. Payment retry logic"
        autofocus
        class="mb-3"
        :rules="[v => !!v?.trim() || 'Title is required']"
        @keyup.enter="form.submit"
      />
      <v-textarea
        v-model="form.description.value"
        label="Description (optional)"
        placeholder="Brief description or requirements..."
        rows="4"
      />

      <!-- Priority drives the assignment scorer and the yield-offer flow. -->
      <div class="d-flex align-center ga-3 mb-3">
        <span id="bud-create-priority" class="bud-create__label">Priority</span>
        <AppPillToggle
          v-model="form.priority.value"
          :options="PRIORITY_OPTIONS"
          size="sm"
          aria-labelledby="bud-create-priority"
        />
      </div>

      <v-expansion-panels v-model="form.openPanels.value" variant="accordion" multiple class="mt-3">
        <v-expansion-panel value="advanced">
          <v-expansion-panel-title>
            <v-icon icon="mdi-tune-variant" size="20" class="mr-2" />
            Advanced settings
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <p class="bud-create__hint mb-3">
              Pick which phases our AI agent should auto-run. Anything left off, you drive
              yourself via the section editors (typically using your local AI through
              <strong>Settings → MCP Connect</strong>).
            </p>
            <div class="d-flex flex-column ga-2 mb-4">
              <v-switch
                v-for="stage in CREATE_STAGES"
                :key="`gen-${stage.value}`"
                v-model="form.autoGenerate.value[stage.value]"
                :label="`Auto-generate ${stage.label}`"
                density="compact"
                hide-details
              />
            </div>
            <AppCallout
              v-if="form.autoGenerate.value.closed === false"
              variant="warning"
              eyebrow="Learning recap disabled"
              class="mb-4"
            >
              Without the post-close recap, this BUD's per-phase actuals still feed the velocity
              rollup that powers future estimates — but you lose the written retrospective and
              the trend signal that recap embeddings provide to similar BUDs.
            </AppCallout>
            <v-progress-circular v-if="form.skillsLoading.value" indeterminate size="20" class="my-3" />
            <div v-else class="d-flex flex-column ga-3">
              <v-select
                v-for="stage in CREATE_STAGES"
                :key="stage.value"
                v-model="form.stageSkillPicks.value[stage.value]"
                :label="`${stage.label} skill`"
                :items="form.skillsForStage(stage.agentType)"
                item-title="label"
                item-value="id"
                density="compact"
                hide-details
                :disabled="!form.autoGenerate.value[stage.value]"
              />
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <AppCallout v-if="form.error.value" variant="error" class="mt-4">{{ form.error.value }}</AppCallout>

      <v-card-actions class="pa-0 mt-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="form.creating.value"
          :disabled="!form.title.value.trim()"
          @click="form.submit"
        >
          Create
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import { CREATE_STAGES, useBudCreateForm } from '@/composables/useBudCreateForm'
import { BUD_PRIORITIES } from '@/types'

const PRIORITY_OPTIONS = BUD_PRIORITIES.map(p => ({ label: p, value: p }))

const open = defineModel<boolean>({ required: true })
const form = useBudCreateForm(open)
</script>

<style scoped>
.bud-create__title {
  font-size: var(--text-md);
  font-weight: 600;
}
.bud-create__label {
  min-width: 70px;
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
.bud-create__hint {
  font-size: var(--text-xs);
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
