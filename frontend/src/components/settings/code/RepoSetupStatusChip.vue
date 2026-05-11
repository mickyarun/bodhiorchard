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

<!--
  Tiny status chip rendered next to the repo name in RepoListRow. Five
  states, derived from RepoInfo:

    1. setupStatus === 'merged' OR setupPrState === 'merged'
         → no chip (clean state — files are on main)
    2. setupPrState === 'open'
         → blue "Setup PR open ↗" linking to setupPrUrl
    3. setupPrState === 'closed'
         → red "Setup PR closed — re-scan"
    4. setupBranchPushedAt + setupCompareUrl, no setupPrState
         → amber "Open PR on GitHub ↗" linking to setupCompareUrl
           (GitHub App not connected — user opens PR manually)
    5. otherwise (typically setupStatus === 'not_setup', no scan yet)
         → grey "Setup pending"

  Anchors are emitted on the chip itself so a single click hits both the
  visual target and the link target.
-->
<template>
  <v-tooltip v-if="state" location="top" :text="state.tooltip" max-width="280">
    <template #activator="{ props: tipProps }">
      <v-chip
        v-bind="tipProps"
        :color="state.color"
        size="x-small"
        variant="tonal"
        :prepend-icon="state.icon"
        :href="state.href ?? undefined"
        :target="state.href ? '_blank' : undefined"
        :rel="state.href ? 'noopener' : undefined"
        class="repo-setup-chip ml-1"
      >
        {{ state.label }}
      </v-chip>
    </template>
  </v-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RepoInfo } from '@/types'

const props = defineProps<{ repo: RepoInfo }>()

interface ChipState {
  label: string
  color: string
  icon: string
  tooltip: string
  href: string | null
}

const TOOLTIP_PR_OPEN = 'Bodhiorchard MCP setup PR is open. Merge it to enable activity tracking.'
const TOOLTIP_PR_CLOSED
  = 'The previous setup PR was closed without merging. Re-scan this repo to push a fresh branch.'
const TOOLTIP_MANUAL = (
  'GitHub App not connected for this org — the setup branch was pushed but no PR was opened. '
  + 'Open it manually here, or configure the App in Settings → Integrations to automate this.'
)
const TOOLTIP_PENDING
  = 'First scan will push `bodhiorchard/init-setup` and (if GitHub App is connected) raise the setup PR.'

const state = computed<ChipState | null>(() => {
  const r = props.repo
  // Merged path — no chip needed. Either filesystem says files are on
  // main (legacy detection still in place) or the webhook flipped the
  // PR state to merged.
  if (r.setupStatus === 'merged' || r.setupPrState === 'merged') return null

  if (r.setupPrState === 'open' && r.setupPrUrl) {
    return {
      label: 'Setup PR open',
      color: 'primary',
      icon: 'mdi-source-pull',
      tooltip: TOOLTIP_PR_OPEN,
      href: r.setupPrUrl,
    }
  }

  if (r.setupPrState === 'closed') {
    return {
      label: 'Setup PR closed — re-scan',
      color: 'error',
      icon: 'mdi-source-pull',
      tooltip: TOOLTIP_PR_CLOSED,
      href: null,
    }
  }

  if (r.setupBranchPushedAt && r.setupCompareUrl) {
    return {
      label: 'Open PR on GitHub',
      color: 'warning',
      icon: 'mdi-source-pull',
      tooltip: TOOLTIP_MANUAL,
      href: r.setupCompareUrl,
    }
  }

  return {
    label: 'Setup pending',
    color: 'grey',
    icon: 'mdi-link-off',
    tooltip: TOOLTIP_PENDING,
    href: null,
  }
})
</script>

<style scoped>
.repo-setup-chip {
  /* Chips inside an anchor render as inline-flex; reset the underline
     in case the surrounding theme adds one to anchors. */
  text-decoration: none;
}
</style>
