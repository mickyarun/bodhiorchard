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

<!-- First-run setup: a navy brand panel with the step list on the left,
     the current step on the right. Below 960px the panel becomes a top bar
     with a compact row of step dots. -->
<template>
  <div class="setup-shell">
    <aside class="setup-shell__panel">
      <BrandLogo :size="30" inverse />
      <StepIndicator
        class="setup-shell__steps"
        :current-step="setupStore.currentStep"
        :locked="setupStore.finalizeDone"
        @go-to-step="setupStore.goToStep"
      />
      <p class="setup-shell__note">
        Self-hosted — your code and data stay on your own servers.
      </p>
    </aside>
    <main class="setup-shell__content">
      <div class="setup-shell__inner">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import BrandLogo from '@/components/common/BrandLogo.vue'
import StepIndicator from '@/components/setup/StepIndicator.vue'
import { useSetupStore } from '@/stores/setup'

const setupStore = useSetupStore()
</script>

<style scoped>
.setup-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  background: rgb(var(--v-theme-background));
}

.setup-shell__panel {
  position: sticky;
  top: 0;
  height: 100vh;
  box-sizing: border-box;
  padding: var(--space-lg, 2rem) var(--space-md, 1.5rem);
  display: flex;
  flex-direction: column;
  gap: var(--space-xl, 3rem);
  background: var(--color-panel);
  color: var(--color-panel-ink);
}

.setup-shell__steps {
  flex-grow: 1;
}

.setup-shell__note {
  margin: 0;
  font-size: 13px;
  line-height: 19px;
  color: var(--color-panel-muted);
}

.setup-shell__content {
  min-width: 0;
  padding: var(--space-2xl, 4.5rem) var(--space-xl, 3rem) var(--space-xl, 3rem);
}

.setup-shell__inner {
  max-width: 680px;
  margin-inline: auto;
}

@media (max-width: 959px) {
  .setup-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .setup-shell__panel {
    position: static;
    height: auto;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm, 1rem);
    padding: var(--space-sm, 1rem);
  }

  .setup-shell__steps {
    flex-grow: 0;
  }

  .setup-shell__note {
    display: none;
  }

  /* Mark only: the wordmark and six step dots don't fit side by side. */
  .setup-shell__panel :deep(.brand-logo__name) {
    display: none;
  }

  .setup-shell__content {
    padding: var(--space-lg, 2rem) var(--space-sm, 1rem);
  }
}
</style>
