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

<template>
  <div class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="text-h5 font-weight-bold bo-display">BUD Board</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ filteredCount }} of {{ budStore.buds.length }} document{{ budStore.buds.length !== 1 ? 's' : '' }}
        </div>
      </div>
      <div class="d-flex align-center ga-2 board-filters">
        <v-text-field
          v-model="nameFilter"
          placeholder="Filter by title or BUD-###"
          prepend-inner-icon="mdi-magnify"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          clearable
          single-line
          class="board-filter-search"
        />
        <v-select
          v-model="assigneeFilter"
          :items="assigneeOptions"
          item-title="label"
          item-value="value"
          placeholder="All assignees"
          prepend-inner-icon="mdi-account-outline"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          clearable
          single-line
          class="board-filter-assignee"
        />
        <v-select
          v-model="teamFilter"
          :items="teamOptions"
          item-title="label"
          item-value="value"
          :placeholder="teamFilterPlaceholder"
          :disabled="teamOptions.length === 0"
          prepend-inner-icon="mdi-account-group-outline"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          clearable
          single-line
          class="board-filter-team"
        />
        <v-select
          v-model="priorityFilter"
          :items="priorityFilterOptions"
          item-title="label"
          item-value="value"
          placeholder="All priorities"
          prepend-inner-icon="mdi-flag-outline"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          clearable
          single-line
          class="board-filter-priority"
        />
        <v-tooltip text="Sort cards by priority (P0 first) within each column" location="bottom">
          <template #activator="{ props: tipProps }">
            <v-btn
              v-bind="tipProps"
              :icon="sortByPriority ? 'mdi-sort-descending' : 'mdi-sort-variant'"
              variant="text"
              size="small"
              :color="sortByPriority ? 'primary' : undefined"
              @click="sortByPriority = !sortByPriority"
            />
          </template>
        </v-tooltip>
        <!-- Discarded BUDs are hidden by default — they're terminal and
             clutter the active pipeline. This toggle appends a Discarded
             column so they stay reachable for review, audit and restore.
             Labelled rather than icon-only: it sits in a row of icon
             buttons where a bare bin glyph reads as "delete", not
             "show the discarded ones". -->
        <v-tooltip :text="showDiscarded ? 'Hide discarded BUDs' : 'Show discarded BUDs'" location="bottom">
          <template #activator="{ props: tipProps }">
            <v-btn
              v-bind="tipProps"
              :prepend-icon="showDiscarded ? 'mdi-delete' : 'mdi-delete-outline'"
              variant="text"
              size="small"
              :color="showDiscarded ? 'primary' : undefined"
              @click="showDiscarded = !showDiscarded"
            >
              Discarded
            </v-btn>
          </template>
        </v-tooltip>
        <!-- Customize lifecycle stages — same permission gate as the
             settings route. Visible to users who can actually change
             the UAT toggle / framework; hidden for plain viewers. -->
        <v-tooltip v-if="canViewQAAutomation" text="Customize QA framework & lifecycle stages" location="bottom">
          <template #activator="{ props: tipProps }">
            <v-btn
              v-bind="tipProps"
              icon="mdi-cog-outline"
              variant="text"
              size="small"
              :to="{ name: 'settings-qa-automation' }"
            />
          </template>
        </v-tooltip>
        <v-btn v-if="canCreateBuds" color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
          New BUD
        </v-btn>
      </div>
    </div>

    <!-- Yield-offer notices addressed to the current user (or every
         org-wide offer if the viewer has team:manage). Renders nothing
         when there are no pending offers. -->
    <YieldOfferNotice />

    <!-- Loading -->
    <div v-if="budStore.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error -->
    <v-alert v-else-if="budStore.error" type="error" variant="tonal" class="mb-4">
      {{ budStore.error }}
      <template #append>
        <v-btn variant="text" size="small" @click="budStore.fetchBUDs()">Retry</v-btn>
      </template>
    </v-alert>

    <!-- Empty state -->
    <v-card
      v-else-if="budStore.buds.length === 0"
      class="pa-12 text-center"
      color="surface"
    >
      <v-icon icon="mdi-seed-outline" size="64" class="text-medium-emphasis mb-4" />
      <div class="text-h6 mb-2">No BUDs yet</div>
      <div class="text-body-2 text-medium-emphasis mb-6">
        Create your first Business Understanding Document to plant a seed.
      </div>
      <v-btn v-if="canCreateBuds" color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        Create BUD
      </v-btn>
    </v-card>

    <!-- Kanban Board -->
    <div v-else class="board-container">
      <div class="board-scroll">
        <div
          v-for="status in boardColumns"
          :key="status"
          class="board-column"
        >
          <!-- Column header — a ruled section head (Workbench rhythm):
               uppercase tracked label + a flat count badge, hairline beneath. -->
          <div class="column-header d-flex align-center justify-space-between pb-2 mb-3">
            <span class="column-title">{{ BUD_STATUS_LABELS[status] }}</span>
            <v-chip
              :color="BUD_STATUS_COLORS[status]"
              size="x-small"
              variant="flat"
              label
            >
              {{ filteredBudsByStatus[status]?.length || 0 }}
            </v-chip>
          </div>

          <!-- Cards -->
          <div class="column-cards">
            <v-card
              v-for="bud in filteredBudsByStatus[status]"
              :key="bud.id"
              class="bud-card pa-4 mb-2"
              color="surface"
              :to="`/buds/${bud.id}`"
            >
              <!-- Row 1: BUD number + priority chip + complexity dots -->
              <div class="d-flex align-center justify-space-between mb-1">
                <div class="d-flex align-center ga-2">
                  <div class="text-caption text-medium-emphasis">
                    BUD-{{ String(bud.bud_number).padStart(3, '0') }}
                  </div>
                  <v-chip
                    size="x-small"
                    variant="tonal"
                    :color="priorityColor(bud.priority)"
                    :title="`Priority ${bud.priority}`"
                    label
                  >
                    {{ bud.priority }}
                  </v-chip>
                </div>
                <div v-if="bud.complexity" class="d-flex ga-1">
                  <span
                    v-for="i in 5"
                    :key="i"
                    class="complexity-dot"
                    :class="i <= (bud.complexity ?? 0) ? 'dot-filled' : 'dot-empty'"
                  />
                </div>
              </div>

              <!-- Row 2: Title + bug badge -->
              <div class="d-flex align-center mb-2">
                <div class="text-body-2 font-weight-medium flex-grow-1 text-truncate">{{ bud.title }}</div>
                <v-chip
                  v-if="bud.open_bug_count > 0"
                  size="x-small"
                  variant="tonal"
                  color="error"
                  prepend-icon="mdi-bug-outline"
                  class="ml-2 flex-shrink-0"
                  @click.stop="$router.push(`/bugs?budId=${bud.id}`)"
                >
                  {{ bud.open_bug_count }}
                </v-chip>
              </div>

              <!-- Row 3: Phase deadline + go-live (only if estimates exist) -->
              <div v-if="bud.current_phase_deadline" class="text-caption mb-1" :class="deadlineColor(bud.current_phase_deadline)">
                ▸ Phase: {{ formatDate(bud.current_phase_deadline) }}
              </div>
              <div v-if="bud.status === 'closed'" class="text-caption text-success mb-2">
                ▸ Released: {{ formatDate(bud.updated_at) }}
              </div>
              <!-- Discarded cards carry their own restore affordance so a
                   BUD can be brought back without opening it first. The
                   card is a router-link, hence .stop.prevent on the button. -->
              <div v-else-if="bud.status === 'discarded'" class="d-flex align-center justify-space-between mb-2">
                <span class="text-caption text-error">
                  ▸ Discarded: {{ formatDate(bud.updated_at) }}
                </span>
                <v-btn
                  v-if="canEditBuds"
                  variant="text"
                  size="x-small"
                  color="primary"
                  prepend-icon="mdi-restore"
                  @click.stop.prevent="restoreDialog?.open(bud)"
                >
                  Restore
                </v-btn>
              </div>
              <div v-else-if="bud.prod_p70_date" class="text-caption text-medium-emphasis mb-2">
                ▸ Live: {{ formatDate(bud.prod_p70_date) }} (70%)
              </div>

              <!-- Row 4: Progress bar + date/avatar -->
              <v-progress-linear
                :model-value="phaseProgress(bud.status)"
                height="3"
                rounded
                color="primary"
                bg-color="surface-variant"
                class="mb-2"
              />
              <div class="d-flex align-center justify-space-between">
                <div class="text-caption text-medium-emphasis">
                  {{ formatDate(bud.updated_at) }}
                </div>
                <v-avatar
                  v-if="bud.assignee_name"
                  size="22"
                  color="primary"
                  variant="tonal"
                  :title="bud.assignee_name"
                >
                  <span class="text-caption" style="font-size: 10px;">{{ initials(bud.assignee_name) }}</span>
                </v-avatar>
              </div>
            </v-card>

            <div
              v-if="!filteredBudsByStatus[status]?.length"
              class="text-caption text-medium-emphasis text-center pa-4"
              style="opacity: 0.4;"
            >
              {{ nameFilter ? 'No matches' : 'No items' }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <BUDCreateDialog v-model="showCreateDialog" />

    <!-- Confirmation + result snackbar for restoring a discarded BUD.
         Shared with the BUD detail page so both entry points behave
         identically. -->
    <BUDRestoreDialog ref="restoreDialog" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { useNotificationStore } from '@/stores/notifications'
import { storeToRefs } from 'pinia'
import { useSettingsStore } from '@/stores/settings'
import { useTeamsStore } from '@/stores/teams'
import { BUD_STATUS_LABELS, BUD_STATUS_COLORS, BUD_PRIORITIES } from '@/types'
import type { BUDStatus, BUDPriority } from '@/types'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import { usePermissions } from '@/composables/usePermissions'
import BUDCreateDialog from '@/components/buds/BUDCreateDialog.vue'
import BUDRestoreDialog from '@/components/buds/BUDRestoreDialog.vue'
import YieldOfferNotice from '@/components/buds/YieldOfferNotice.vue'

// Theme-token color for each priority. Used by the chip on each card
// AND by the filter / sort surface so the visual contract is identical
// across the board.
const PRIORITY_COLORS: Record<BUDPriority, string> = {
  P0: 'error',
  P1: 'warning',
  P2: 'on-surface-variant',
  P3: 'on-surface-variant',
}
const PRIORITY_WEIGHTS: Record<BUDPriority, number> = { P0: 0, P1: 1, P2: 2, P3: 3 }

const budStore = useBUDStore()
const settingsStore = useSettingsStore()
const teamsStore = useTeamsStore()

const nameFilter = ref('')
// Sentinel value (string, not null) for the "Unassigned" option — v-select's
// `clearable` resets to null, which we treat as "no filter".
const UNASSIGNED = '__unassigned__'
const assigneeFilter = ref<string | null>(null)
const priorityFilter = ref<BUDPriority | null>(null)
const teamFilter = ref<string | null>(null)
const sortByPriority = ref(false)
// Off by default: discarded BUDs are terminal and excluded from the
// active pipeline; flip on to surface them as a trailing column.
const showDiscarded = ref(false)

// Team filter options + placeholder. When no teams exist yet, the
// dropdown is disabled with a placeholder pointing at Settings →
// Teams so the user knows where to configure them.
const teamOptions = computed(() =>
  teamsStore.activeTeams.map(t => ({ value: t.id, label: t.name })),
)
const teamFilterPlaceholder = computed(() =>
  teamOptions.value.length === 0
    ? 'No teams configured — Settings → Teams'
    : 'All teams',
)

// Lazy-load the selected team's full member list (the summary list
// doesn't carry members). The filter computed waits until detail is
// in the store before narrowing — otherwise the board would briefly
// show "no matches" while the fetch resolves.
watch(teamFilter, async (id) => {
  if (id && !teamsStore.detailsById[id]) {
    await teamsStore.fetchTeam(id)
  }
})

const selectedTeamMemberIds = computed(() => {
  if (!teamFilter.value) return null
  const detail = teamsStore.detailsById[teamFilter.value]
  if (!detail) return new Set<string>()  // still loading; show nothing
  return new Set(detail.members.map(m => m.user_id))
})

// Dropdown options derived from the currently-loaded buds so we only show
// assignees that actually exist on the board. "Unassigned" is appended
// only if at least one BUD has no assignee.
const assigneeOptions = computed(() => {
  const seen = new Map<string, string>()
  let hasUnassigned = false
  for (const bud of budStore.buds) {
    if (bud.assignee_id && bud.assignee_name) seen.set(bud.assignee_id, bud.assignee_name)
    else hasUnassigned = true
  }
  const opts = [...seen.entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label))
  if (hasUnassigned) opts.push({ value: UNASSIGNED, label: 'Unassigned' })
  return opts
})

const priorityFilterOptions = BUD_PRIORITIES.map(p => ({ label: p, value: p }))

// Filter buds by title (case-insensitive substring) OR by BUD reference
// like "BUD-014" / "014" / "14", AND by assignee. Applied after the store's
// status grouping so kanban columns stay intact and the filter is purely
// visual.
const filteredBudsByStatus = computed<Record<string, typeof budStore.buds>>(() => {
  const q = nameFilter.value?.trim().toLowerCase() ?? ''
  const assignee = assigneeFilter.value
  const priority = priorityFilter.value
  const teamMembers = selectedTeamMemberIds.value
  const sort = sortByPriority.value
  const grouped = budStore.budsByStatus
  if (!q && !assignee && !priority && !teamMembers && !sort) return grouped
  const numericQ = q.replace(/^bud-?/, '').replace(/^0+/, '')
  const out: Record<string, typeof budStore.buds> = {}
  for (const status of Object.keys(grouped)) {
    const filtered = grouped[status].filter((bud) => {
      if (assignee === UNASSIGNED && bud.assignee_id) return false
      if (assignee && assignee !== UNASSIGNED && bud.assignee_id !== assignee) return false
      if (priority && bud.priority !== priority) return false
      // Team filter: show only BUDs whose current assignee is in the
      // selected team. Unassigned BUDs are excluded by design — if
      // nobody owns it, there's no team to attribute it to.
      if (teamMembers !== null) {
        if (!bud.assignee_id || !teamMembers.has(bud.assignee_id)) return false
      }
      if (!q) return true
      if (bud.title?.toLowerCase().includes(q)) return true
      const num = String(bud.bud_number)
      return numericQ !== '' && num.includes(numericQ)
    })
    out[status] = sort
      ? [...filtered].sort((a, b) => PRIORITY_WEIGHTS[a.priority] - PRIORITY_WEIGHTS[b.priority])
      : filtered
  }
  return out
})

const filteredCount = computed(() =>
  Object.values(filteredBudsByStatus.value).reduce((n, list) => n + list.length, 0),
)

const showCreateDialog = ref(false)

onMounted(() => {
  budStore.fetchBUDs()
  // usePhaseOrder() reads budStages.uatEnabled to decide whether the UAT
  // column shows. Without this fetch a cold page load uses the default
  // (UAT enabled) regardless of what the org has saved.
  if (!settingsStore.connectionsLoaded) settingsStore.fetchConnections()
  // Team summaries power the board's Team filter dropdown. Cheap
  // single-page list; member detail is lazy-loaded only when the user
  // actually picks a team.
  if (teamsStore.teams.length === 0) teamsStore.fetchTeams(false)
})

// Re-fetch the BUD list when a job-completion notification arrives.
// Without this the board doesn't reflect newly-completed agent work
// (status badges, agent banners, design counters) until the user
// hits browser refresh — the bell IS updated via useNotificationSocket
// because the badge shows, but the board cards stayed stale.
const notificationStore = useNotificationStore()
const { items: notificationItems } = storeToRefs(notificationStore)
watch(
  () => notificationItems.value.length,
  (newLen, oldLen) => {
    if (newLen > (oldLen ?? 0)) {
      void budStore.fetchBUDs()
    }
  },
)

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

function priorityColor(priority: BUDPriority): string {
  return PRIORITY_COLORS[priority]
}

// Phase order filtered by org settings (e.g. UAT may be disabled). The
// kanban columns and progress-bar denominator both use this so the board
// reacts when the org toggles UAT off, without a page reload.
const { phaseOrder } = usePhaseOrder()
const { canViewQAAutomation, canCreateBuds, canEditBuds } = usePermissions()
const boardColumns = computed<BUDStatus[]>(() =>
  phaseOrder.value.filter(s => s !== 'discarded' || showDiscarded.value),
)
const activePhaseCount = computed<number>(
  () => phaseOrder.value.filter(s => s !== 'discarded' && s !== 'closed').length,
)

function phaseProgress(status: BUDStatus): number {
  // Use the filtered phaseOrder for both numerator and denominator so the
  // progress bar is consistent regardless of whether UAT is enabled.
  const idx = phaseOrder.value.indexOf(status)
  return idx >= 0 ? Math.min(100, ((idx + 1) / activePhaseCount.value) * 100) : 0
}

// Restore flow for discarded BUDs lives in BUDRestoreDialog — the board
// only needs a handle to open it. The BUD detail page mounts the same
// component, so the confirmation, the store call and the "restored to X"
// snackbar stay in one place.
const restoreDialog = ref<InstanceType<typeof BUDRestoreDialog> | null>(null)

function deadlineColor(deadline: string): string {
  const days = (new Date(deadline).getTime() - Date.now()) / 86400000
  if (days < 0) return 'text-error'
  if (days < 2) return 'text-warning'
  return 'text-medium-emphasis'
}
</script>

<style scoped>
.board-container {
  overflow-x: auto;
}

.board-scroll {
  display: flex;
  gap: 12px;
  min-width: max-content;
  padding-bottom: 8px;
}

.board-column {
  width: 260px;
  min-width: 260px;
  flex-shrink: 0;
}

/* Ruled section head, not a filled box — reads as a column boundary. */
.column-header {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.column-title {
  font-size: var(--text-xs, 0.8rem);
  font-weight: 600;
  letter-spacing: var(--tracking-label, 0.08em);
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface-variant));
}

.column-cards {
  min-height: 100px;
}

.bud-card {
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: var(--radius-card, 10px);
  transition: border-color var(--dur-short, 150ms) var(--ease-out, ease),
              transform var(--dur-short, 150ms) var(--ease-out, ease);
}

.bud-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.55);
  transform: translateY(-2px);
}

.complexity-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.dot-filled {
  background: rgb(var(--v-theme-primary));
}

.dot-empty {
  background: rgb(var(--v-theme-rule));
}

.board-filters :deep(.v-field) {
  background: rgb(var(--v-theme-surface-bright));
  border-radius: var(--radius-input, 8px);
}
.board-filters :deep(.v-field--focused) {
  background: rgb(var(--v-theme-surface-light));
}
.board-filter-search {
  width: 260px;
}
.board-filter-assignee {
  width: 200px;
}

</style>
