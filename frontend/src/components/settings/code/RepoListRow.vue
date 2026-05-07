<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Single repository row used by RepoList. Owns its own action-menu busy
  state and bubbles destructive intent to the parent so the confirm
  dialog stays mounted once at list level.

  During an active scan: the branch-chip strip is replaced with the
  per-repo phase track, the row checkbox is locked, and the action
  menu is hidden — every edit path is gated by RepoList's `isLocked`.
-->
<template>
  <div
    class="repo-row d-flex align-start ga-2 px-5 py-3"
    :class="{ 'is-divider': hasDivider, 'is-ignored': repo.status === 'ignored' }"
  >
    <v-checkbox-btn
      v-if="selectable"
      :model-value="selected"
      color="primary"
      density="compact"
      hide-details
      class="row-checkbox flex-grow-0 flex-shrink-0"
      :disabled="isLocked || repo.status !== 'active'"
      @update:model-value="emit('toggle-select', repo)"
    />

    <v-avatar
      size="32"
      rounded="lg"
      :color="repo.status === 'active' ? 'primary' : 'surface-variant'"
      variant="tonal"
      class="row-avatar flex-grow-0 flex-shrink-0"
    >
      <v-icon icon="mdi-source-repository" size="18" />
    </v-avatar>

    <div class="row-content flex-grow-1 min-w-0">
      <div class="d-flex align-center ga-2 flex-wrap">
        <div class="text-body-2 font-weight-medium text-truncate">{{ repo.name }}</div>
        <RepoSetupStatusChip :repo="repo" />
        <v-chip
          v-if="repo.status === 'ignored'"
          size="x-small"
          variant="tonal"
          color="warning"
        >
          Ignored
        </v-chip>
      </div>
      <div class="text-caption text-medium-emphasis text-truncate row-path">{{ repo.path }}</div>

      <div class="d-flex align-center ga-2 mt-2 flex-wrap">
        <ScanRowTrack v-if="run" :run="run" />
        <template v-else>
          <BranchChip
            icon="mdi-source-branch"
            :label="repo.mainBranch"
            fallback="Set main"
            :disabled="isLocked"
            @click="onEditBranches"
          />
          <v-icon icon="mdi-arrow-right" size="12" class="text-medium-emphasis" />
          <BranchChip
            icon="mdi-source-branch"
            :label="repo.developBranch"
            fallback="Set develop"
            :disabled="isLocked"
            @click="onEditBranches"
          />
          <template v-if="uatEnabled">
            <v-icon icon="mdi-arrow-right" size="12" class="text-medium-emphasis" />
            <BranchChip
              icon="mdi-source-branch"
              :label="repo.uatBranch"
              fallback="Set UAT"
              muted
              :disabled="isLocked"
              @click="onEditBranches"
            />
          </template>
        </template>
      </div>

      <RepoClassificationChips :repo="repo" />

      <div
        v-if="!run && lastScan"
        class="d-flex align-center ga-2 mt-1 last-scan-summary"
      >
        <v-chip
          :color="lastScan.color"
          size="x-small"
          variant="tonal"
          density="compact"
        >
          <v-icon :icon="lastScan.icon" size="12" start />
          {{ lastScan.label }}
        </v-chip>
        <span class="text-caption text-medium-emphasis">
          {{ lastScan.relativeTime }}
        </span>
        <span
          v-if="lastScan.featureCount !== null"
          class="text-caption text-medium-emphasis d-flex align-center ga-1"
        >
          <v-icon icon="mdi-lightbulb-outline" size="12" />
          {{ lastScan.featureCount }} {{ lastScan.featureCount === 1 ? 'feature' : 'features' }}
        </span>
      </div>
    </div>

    <div class="d-flex align-center ga-1 row-actions flex-grow-0 flex-shrink-0">
      <div class="text-caption text-medium-emphasis text-no-wrap d-flex align-center ga-1">
        <v-icon icon="mdi-lightbulb-outline" size="14" />
        {{ repo.featureCount }}
      </div>
      <RepoRowMenu
        v-if="!isLocked"
        :status="repo.status"
        :disabled="busy"
        @select="onMenuSelect"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import BranchChip from './BranchChip.vue'
import RepoClassificationChips from './RepoClassificationChips.vue'
import RepoRowMenu, { type RepoRowMenuId } from './RepoRowMenu.vue'
import RepoSetupStatusChip from './RepoSetupStatusChip.vue'
import ScanRowTrack from './ScanRowTrack.vue'
import {
  type LastScanSummary,
  STATUS_PRESENTATION,
  formatRelative,
} from './repoListRow.util'
import type { RepoInfo } from '@/types'
import type { RepoRunRow } from '@/stores/reposcanv2Scans'

const props = defineProps<{
  repo: RepoInfo
  selectable: boolean
  selected: boolean
  uatEnabled: boolean
  busy: boolean
  hasDivider: boolean
  isLocked: boolean
  run: RepoRunRow | null
}>()

const emit = defineEmits<{
  'toggle-select': [repo: RepoInfo]
  'edit-branches': [repo: RepoInfo]
  'toggle-status': [repo: RepoInfo]
  'request-remove': [repo: RepoInfo]
}>()

/** Render-ready summary of the most recent ScanRepoRun for this repo.
 *  Falls back to `null` when the repo has never been scanned, in which
 *  case the row only shows the branch chips. */
const lastScan = computed<LastScanSummary | null>(() => {
  const status = props.repo.lastScanStatus ?? null
  const finished = props.repo.lastScanFinishedAt ?? null
  const started = props.repo.lastScanStartedAt ?? null
  const ts = finished ?? started ?? props.repo.lastScanned
  if (!status && !ts) return null
  const presentation = STATUS_PRESENTATION[status ?? 'done']
  return {
    label: presentation.label,
    color: presentation.color,
    icon: presentation.icon,
    relativeTime: ts ? formatRelative(ts) : 'never',
    featureCount: props.repo.lastScanFeatureCount ?? null,
  }
})

function onEditBranches(): void {
  if (props.isLocked) return
  emit('edit-branches', props.repo)
}

function onMenuSelect(id: RepoRowMenuId): void {
  if (id === 'edit-branches') emit('edit-branches', props.repo)
  else if (id === 'toggle-status') emit('toggle-status', props.repo)
  else if (id === 'remove') emit('request-remove', props.repo)
}
</script>

<style scoped>
.repo-row.is-divider {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.repo-row.is-ignored {
  opacity: 0.6;
}

.row-checkbox {
  margin-top: -2px;
}

.row-avatar {
  margin-top: 2px;
}

.row-content {
  /* min-w-0 is the critical bit — without it the truncated path forces
     this flex item to expand and pushes the visible name off-center. */
  text-align: left;
}

.row-path {
  max-width: 100%;
}

.row-actions {
  margin-top: 2px;
}
</style>
