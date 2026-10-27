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

<!-- Nothing mapped yet: what the page is for, the three steps to get there
     (marked done / next from the org's repositories) and one action for
     people who can set repositories up. -->
<template>
  <section class="features-empty" aria-labelledby="features-empty-title">
    <span class="features-empty__icon" aria-hidden="true"><v-icon icon="mdi-lightbulb-outline" size="26" /></span>
    <div class="features-empty__intro">
      <h2 id="features-empty-title">No features mapped yet</h2>
      <p>
        Connect a repository and Glideship reads the code to list every feature it finds. New BUDs then link
        to the features they change, so nobody builds the same thing twice.
      </p>
    </div>
    <ol class="features-empty__steps">
      <li v-for="(step, i) in steps" :key="step.key" class="features-empty__step" :class="`features-empty__step--${step.state}`">
        <span class="features-empty__state">
          <span class="features-empty__num" aria-hidden="true">
            <v-icon v-if="step.state === 'done'" icon="mdi-check" size="14" />
            <template v-else>{{ i + 1 }}</template>
          </span>
          {{ SETUP_STATE_LABEL[step.state] }}
        </span>
        <span class="features-empty__step-title">{{ step.title }}</span>
        <span class="features-empty__step-body">{{ step.body }}</span>
      </li>
    </ol>
    <v-btn v-if="canConfigure" color="primary" variant="flat" :to="{ name: 'settings-code' }">
      {{ connected ? 'Open code settings' : 'Connect a repository' }}
    </v-btn>
    <p v-else class="features-empty__hint">Ask an admin to connect a repository.</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RepoInfo } from '@/types'
import { featureSetupSteps, SETUP_STATE_LABEL } from '@/utils/featureSetup'

const props = defineProps<{ repos: RepoInfo[]; canConfigure: boolean }>()

const steps = computed(() => featureSetupSteps(props.repos))
const connected = computed(() => steps.value[0].state === 'done')
</script>

<style scoped>
.features-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 28px;
  padding: 56px 48px;
  text-align: center;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
.features-empty__icon {
  width: 56px;
  height: 56px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  color: var(--color-accent-text);
  background: var(--color-accent-soft);
}
.features-empty__intro {
  max-width: 560px;
}
.features-empty__intro h2 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
}
.features-empty__intro p,
.features-empty__hint {
  margin: 0;
  font-size: 15px;
  line-height: 22px;
  color: rgb(var(--v-theme-ink-2));
}
.features-empty__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  width: 100%;
  max-width: 860px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  text-align: left;
}
.features-empty__step {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  background: rgb(var(--v-theme-background));
  --step: var(--v-theme-on-surface-variant);
}
.features-empty__step--next {
  background: var(--color-accent-soft);
  --step: var(--v-theme-primary);
}
.features-empty__step--done {
  --step: var(--v-theme-success);
}
.features-empty__state {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--step));
}
.features-empty__step--next .features-empty__state {
  color: var(--color-accent-text);
}
.features-empty__num {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 12px;
  color: rgb(var(--v-theme-ink-2));
  background: rgb(var(--v-theme-rule));
}
.features-empty__step--next .features-empty__num {
  color: rgb(var(--v-theme-on-primary));
  background: rgb(var(--v-theme-primary));
}
.features-empty__step--done .features-empty__num {
  color: rgb(var(--v-theme-success));
  background: rgba(var(--v-theme-success), 0.16);
}
.features-empty__step-title {
  font-size: 15px;
  font-weight: 600;
}
.features-empty__step-body {
  font-size: 13px;
  line-height: 19px;
  color: rgb(var(--v-theme-on-surface-variant));
}
@media (max-width: 760px) {
  .features-empty {
    padding: 32px 20px;
  }
  .features-empty__steps {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
