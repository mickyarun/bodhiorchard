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

<!-- "Finish setting up": progress through the workspace setup steps, the
     next step with a button to it, live scan progress, and the full list
     on demand. Hidden once every step is done or the user hides it. -->
<template>
  <AppPanel v-if="setup.visible.value" title="Finish setting up">
    <template #action>
      <span class="setup-card__count">{{ setup.doneCount.value }} of {{ setup.steps.value.length }}</span>
      <v-btn
        icon="mdi-close"
        variant="text"
        size="x-small"
        aria-label="Hide setup card"
        class="ml-1"
        @click="setup.dismiss"
      />
    </template>

    <v-progress-linear
      :model-value="percent"
      color="primary"
      bg-color="surface-variant"
      bg-opacity="1"
      height="6"
      rounded
      :aria-label="`Setup ${percent}% complete`"
    />

    <div v-if="setup.scanning.value" class="setup-card__scan">
      <div class="setup-card__line">
        {{ setup.scanLabel.value }} · {{ Math.round(setup.scanProgress.value) }}%
      </div>
      <ScanPhaseTimeline v-if="setup.phases.value.length" :phases="setup.phases.value" />
    </div>
    <p v-else-if="next" class="setup-card__line">
      Next: <strong>{{ next.label }}</strong>. {{ next.why }}
      <template v-if="next.route && !canDo(next)">An admin can finish this step.</template>
    </p>

    <AppCallout v-if="setup.warnings.value.length" variant="warning" class="mt-3">
      <div v-for="(w, i) in setup.warnings.value" :key="`${w.repo}-${w.phase}-${i}`" class="mb-1">
        <strong>{{ w.repo }}</strong> · {{ w.phase }}: {{ w.summary }}
        <span v-if="w.hint"> {{ w.hint }}</span>
      </div>
    </AppCallout>

    <div class="setup-card__actions">
      <v-btn
        v-if="setup.scanFailed.value"
        variant="outlined"
        prepend-icon="mdi-refresh"
        :loading="setup.resuming.value"
        @click="setup.resumeScan"
      >
        Resume scan
      </v-btn>
      <v-btn v-else-if="next && canDo(next)" variant="outlined" :to="next.route">{{ next.label }}</v-btn>
      <v-btn variant="text" :aria-expanded="showAll" @click="showAll = !showAll">
        {{ showAll ? 'Hide steps' : 'See all steps' }}
      </v-btn>
    </div>

    <ul v-if="showAll" class="setup-card__steps">
      <li v-for="step in setup.steps.value" :key="step.key" class="setup-card__step">
        <v-icon
          :icon="step.done ? 'mdi-check-circle' : 'mdi-circle-outline'"
          :color="step.done ? 'success' : 'muted'"
          size="18"
          aria-hidden="true"
        />
        <router-link v-if="!step.done && canDo(step)" :to="step.route!">{{ step.label }}</router-link>
        <span v-else :class="{ 'setup-card__done': step.done }">{{ step.label }}</span>
        <span v-if="step.optional" class="setup-card__optional">Optional</span>
        <span class="d-sr-only">{{ step.done ? 'done' : 'not done' }}</span>
      </li>
    </ul>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPanel from '@/components/common/AppPanel.vue'
import ScanPhaseTimeline from '@/components/scan/ScanPhaseTimeline.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useSetupChecklist } from '@/composables/useSetupChecklist'
import type { SetupStep } from '@/utils/setupChecklist'

const setup = useSetupChecklist()
const { hasPermission } = usePermissions()

/** Whether this person can open the page where the step is done. */
function canDo(step: SetupStep): boolean {
  return !!step.route && (!step.permission || hasPermission(step.permission))
}
const showAll = ref(false)

const next = computed(() => setup.nextStep.value)
const percent = computed(() => {
  const total = setup.steps.value.length
  return total ? Math.round((setup.doneCount.value / total) * 100) : 0
})
</script>

<style scoped>
.setup-card__count {
  font-weight: 400;
  color: rgb(var(--v-theme-on-surface-variant));
}
.setup-card__line {
  margin: 12px 0 0;
  font-size: var(--text-sm);
  line-height: 1.45;
  color: rgb(var(--v-theme-ink-2));
}
.setup-card__scan {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.setup-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.setup-card__steps {
  list-style: none;
  margin: 12px 0 0;
  padding: 12px 0 0;
  border-top: 1px solid rgb(var(--v-theme-rule));
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: var(--text-sm);
}
.setup-card__step {
  display: flex;
  align-items: center;
  gap: 8px;
}
.setup-card__step a {
  color: var(--color-accent-text);
  text-decoration: none;
}
.setup-card__done {
  color: rgb(var(--v-theme-on-surface-variant));
}
.setup-card__optional {
  margin-left: auto;
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
