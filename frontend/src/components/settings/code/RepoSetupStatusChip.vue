<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

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
  <v-tooltip v-if="state" location="top" max-width="480">
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
    <!-- Use a slot (not the :text prop) so newlines in setupLastError
         render as line breaks via white-space: pre-wrap. -->
    <span class="repo-setup-tooltip">{{ state.tooltip }}</span>
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

// DEBUG: when the last setup attempt failed, the backend stamps the
// row with the captured stderr. Prepend it to whichever tooltip the
// state machine picked so prod operators can diagnose stuck rows
// without log access. Removed when setup-PR is stable.
function withDebugError(base: string, err: string | null | undefined): string {
  if (!err) return base
  return `${base}\n\nLast push error:\n${err}`
}

const state = computed<ChipState | null>(() => {
  const r = props.repo
  const err = r.setupLastError
  // Merged path — no chip needed. Either filesystem says files are on
  // main (legacy detection still in place) or the webhook flipped the
  // PR state to merged.
  if (r.setupStatus === 'merged' || r.setupPrState === 'merged') return null

  if (r.setupPrState === 'open' && r.setupPrUrl) {
    return {
      label: err ? 'Setup PR open ⚠' : 'Setup PR open',
      color: err ? 'warning' : 'primary',
      icon: 'mdi-source-pull',
      tooltip: withDebugError(TOOLTIP_PR_OPEN, err),
      href: r.setupPrUrl,
    }
  }

  if (r.setupPrState === 'closed') {
    return {
      label: 'Setup PR closed — re-scan',
      color: 'error',
      icon: 'mdi-source-pull',
      tooltip: withDebugError(TOOLTIP_PR_CLOSED, err),
      href: null,
    }
  }

  if (r.setupBranchPushedAt && r.setupCompareUrl) {
    return {
      label: 'Open PR on GitHub',
      color: 'warning',
      icon: 'mdi-source-pull',
      tooltip: withDebugError(TOOLTIP_MANUAL, err),
      href: r.setupCompareUrl,
    }
  }

  return {
    label: err ? 'Setup pending ⚠' : 'Setup pending',
    color: err ? 'error' : 'grey',
    icon: 'mdi-link-off',
    tooltip: withDebugError(TOOLTIP_PENDING, err),
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
.repo-setup-tooltip {
  /* DEBUG: preserves \n in setupLastError so the multi-line stderr
     renders readably. Remove with the rest of the debug surface. */
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.4;
}
</style>
