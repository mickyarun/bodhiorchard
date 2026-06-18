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
    <div class="d-flex align-center mb-5">
      <div>
        <div class="text-h5 font-weight-bold bo-display">Bugs</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ bugsStore.boardTotal }} bug{{ bugsStore.boardTotal !== 1 ? 's' : '' }}
          <span class="ml-2">— {{ scopeLabel }}</span>
        </div>
      </div>
      <v-spacer />
      <AppPillToggle
        v-model="scope"
        :options="scopeOptions"
        size="sm"
        class="mr-3"
        @update:model-value="loadBoard"
      />
      <v-btn
        v-if="canReportBugs"
        color="error"
        variant="flat"
        prepend-icon="mdi-bug-outline"
        @click="showCreate = true"
      >
        Report Bug
      </v-btn>
    </div>

    <!-- Filters -->
    <div class="d-flex ga-3 mb-4 flex-wrap">
      <v-select
        v-model="filterSeverity"
        :items="severityOptions"
        label="Severity"
        variant="outlined"
        density="compact"
        clearable
        style="max-width: 180px"
        @update:model-value="loadBoard"
      />
    </div>

    <!-- Loading -->
    <div v-if="bugsStore.boardLoading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate size="32" />
    </div>

    <!-- Empty -->
    <v-card
      v-else-if="bugsStore.boardTotal === 0"
      class="pa-12 text-center"
      color="surface"
    >
      <v-icon icon="mdi-bug-check-outline" size="64" color="success" class="mb-4 opacity-50" />
      <div class="text-h6 mb-2">No bugs on the board</div>
      <div class="text-body-2 text-medium-emphasis mb-6">
        {{ filterSeverity ? 'Try clearing your filters.' : 'Nothing reported yet — quality is holding.' }}
      </div>
      <v-btn
        v-if="canReportBugs"
        color="error"
        prepend-icon="mdi-bug-outline"
        @click="showCreate = true"
      >
        Report Bug
      </v-btn>
    </v-card>

    <!-- Kanban -->
    <div v-else class="board-container">
      <div class="board-scroll">
        <div
          v-for="status in bugsStore.boardColumns"
          :key="status"
          class="board-column"
        >
          <div class="column-header d-flex align-center justify-space-between pb-2 mb-3">
            <span class="column-title">{{ BUG_STATUS_LABELS[status] }}</span>
            <v-chip
              :color="BUG_STATUS_COLORS[status]"
              size="x-small"
              variant="flat"
              label
            >
              {{ bugsStore.board[status]?.length || 0 }}
            </v-chip>
          </div>

          <draggable
            :list="bugsStore.board[status]"
            group="bugs"
            item-key="id"
            :animation="180"
            :disabled="!canEditBugs || dragLocked"
            class="column-cards"
            @change="(evt: DragChangeEvent) => onDragChange(status, evt)"
          >
            <template #item="{ element }: { element: BugListItem }">
              <v-card
                class="bug-card pa-3 mb-2 cursor-pointer"
                color="surface"
                @click="openBug(element)"
              >
                <div class="d-flex align-center ga-2 mb-1">
                  <span class="text-caption text-medium-emphasis font-weight-medium">
                    BUG-{{ String(element.bugNumber).padStart(3, '0') }}
                  </span>
                  <v-chip
                    :color="BUG_SEVERITY_COLORS[element.severity]"
                    size="x-small"
                    variant="tonal"
                  >
                    {{ element.severity }}
                  </v-chip>
                  <v-chip
                    v-if="element.bugType === 'production'"
                    size="x-small"
                    variant="tonal"
                    color="error"
                  >
                    prod
                  </v-chip>
                </div>
                <div class="text-body-2 font-weight-medium mb-1 text-truncate">{{ element.title }}</div>
                <div v-if="element.featureTitle" class="text-caption text-medium-emphasis text-truncate mb-2">
                  ▸ {{ element.featureTitle }}
                </div>
                <div class="d-flex align-center justify-space-between">
                  <div class="d-flex align-center ga-2 text-caption text-medium-emphasis">
                    <span>{{ formatDateTime(element.updatedAt) }}</span>
                    <span v-if="element.commentCount > 0">
                      <v-icon icon="mdi-comment-text-outline" size="12" />
                      {{ element.commentCount }}
                    </span>
                  </div>
                  <v-avatar
                    v-if="element.assigneeName"
                    size="22"
                    color="primary"
                    variant="tonal"
                    :title="element.assigneeName"
                  >
                    <span class="text-caption" style="font-size: 10px;">
                      {{ initials(element.assigneeName) }}
                    </span>
                  </v-avatar>
                </div>
              </v-card>
            </template>
          </draggable>

          <div
            v-if="!bugsStore.board[status]?.length"
            class="text-caption text-medium-emphasis text-center pa-4"
            style="opacity: 0.4;"
          >
            No items
          </div>
        </div>
      </div>
    </div>

    <!-- Detail drawer -->
    <v-navigation-drawer
      v-model="showDetail"
      location="right"
      width="600"
      temporary
    >
      <div class="pa-4">
        <BugDetailPanel @close="showDetail = false" />
      </div>
    </v-navigation-drawer>

    <!-- Create dialog -->
    <BugCreateDialog
      v-model="showCreate"
      :default-bug-type="scope === 'testing' ? 'testing' : 'production'"
      @created="onCreated"
    />

    <!-- Error snackbar -->
    <v-snackbar
      v-model="errorOpen"
      color="error"
      location="bottom right"
      :timeout="4000"
      @update:model-value="onErrorSnackbarChange"
    >
      {{ bugsStore.error }}
    </v-snackbar>

    <!-- Drag confirm dialog -->
    <v-dialog v-model="confirmOpen" max-width="420">
      <v-card color="surface" class="pa-5">
        <div class="text-h6 font-weight-bold mb-2">{{ confirmTitle }}</div>
        <div class="text-body-2 mb-4">{{ confirmBody }}</div>
        <div class="d-flex justify-end ga-2">
          <v-btn variant="text" @click="cancelConfirm">Cancel</v-btn>
          <v-btn color="primary" variant="flat" @click="acceptConfirm">Confirm</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import draggable from 'vuedraggable'
import { useBugsStore } from '@/stores/bugs'
import { usePermissions } from '@/composables/usePermissions'
import {
  BUG_SEVERITY_COLORS,
  BUG_STATUS_COLORS,
  BUG_STATUS_LABELS,
  type BugListItem,
  type BugStatusValue,
} from '@/types'
import { formatDateTime } from '@/utils/date'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import BugCreateDialog from './BugCreateDialog.vue'
import BugDetailPanel from '@/components/bugs/BugDetailPanel.vue'

type DragChangeEvent =
  | { added: { newIndex: number; element: BugListItem } }
  | { removed: { oldIndex: number; element: BugListItem } }
  | { moved: { newIndex: number; oldIndex: number; element: BugListItem } }

const route = useRoute()
const router = useRouter()
const bugsStore = useBugsStore()
const { canReportBugs, canEditBugs } = usePermissions()

const scope = ref<'production' | 'testing' | 'all'>('production')
const showCreate = ref(false)
const showDetail = ref(false)
const filterSeverity = ref<string | null>(null)
const dragLocked = ref(false)

const confirmOpen = ref(false)
const confirmTitle = ref('')
const confirmBody = ref('')
const pendingMove = ref<{
  bug: BugListItem
  from: BugStatusValue
  to: BugStatusValue
} | null>(null)

const severityOptions = [
  { title: 'Critical', value: 'critical' },
  { title: 'High', value: 'high' },
  { title: 'Medium', value: 'medium' },
  { title: 'Low', value: 'low' },
]

const scopeOptions: { label: string; value: 'production' | 'testing' | 'all' }[] = [
  { label: 'Production', value: 'production' },
  { label: 'Testing', value: 'testing' },
  { label: 'All', value: 'all' },
]

const errorOpen = ref(false)
watch(
  () => bugsStore.error,
  (err) => {
    errorOpen.value = !!err
  },
)

// Clear the underlying error once the snackbar closes so the next
// identical-message failure still produces a null→string transition
// (and re-opens the snackbar).
function onErrorSnackbarChange(open: boolean): void {
  if (!open) bugsStore.error = null
}

const scopeLabel = computed(() =>
  scope.value === 'production'
    ? 'Production'
    : scope.value === 'testing'
      ? 'Testing'
      : 'All bugs',
)

onMounted(() => {
  const queryScope = route.query.scope as string | undefined
  if (queryScope === 'testing' || queryScope === 'all') {
    scope.value = queryScope
  }
  loadBoard()
})

async function loadBoard(): Promise<void> {
  await bugsStore.fetchBoard({
    bugType: scope.value,
    severity: filterSeverity.value || undefined,
    featureId: (route.query.featureId as string) || undefined,
  })
}

async function openBug(bug: BugListItem): Promise<void> {
  await bugsStore.fetchBug(bug.id)
  showDetail.value = true
}

function onCreated(): void {
  loadBoard()
}

function initials(name: string | null | undefined): string {
  if (!name) return '?'
  return name
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

// vuedraggable fires `added` on the receiving column and `removed` on
// the source column; the move itself is the `added` event. We commit
// once per drop via the `added` branch (target column owns the patch).
async function onDragChange(column: BugStatusValue, evt: DragChangeEvent): Promise<void> {
  if (!('added' in evt)) return
  const card = evt.added.element
  const from = card.status
  const to = column
  if (from === to) return

  if (needsConfirm(to)) {
    pendingMove.value = { bug: card, from, to }
    confirmTitle.value = to === 'closed' ? 'Close this bug?' : 'Mark as resolved?'
    confirmBody.value =
      to === 'closed'
        ? 'Closed bugs leave the active board. Reopen via the detail panel if needed.'
        : 'A resolved bug is awaiting QA validation; the assignee should be notified.'
    confirmOpen.value = true
    return
  }
  await commitMove(card, to)
}

function needsConfirm(to: BugStatusValue): boolean {
  return to === 'resolved' || to === 'closed'
}

async function commitMove(card: BugListItem, to: BugStatusValue): Promise<void> {
  dragLocked.value = true
  await bugsStore.moveBugStatus({ ...card }, to)
  dragLocked.value = false
  // The store reverts the optimistic move on failure, so a stale board
  // is enough — no extra fetch needed.
}

async function acceptConfirm(): Promise<void> {
  if (!pendingMove.value) return
  const { bug, to } = pendingMove.value
  confirmOpen.value = false
  await commitMove(bug, to)
  pendingMove.value = null
}

async function cancelConfirm(): Promise<void> {
  // Revert by re-fetching the board — the optimistic move already
  // happened, the user is rejecting it.
  confirmOpen.value = false
  pendingMove.value = null
  await loadBoard()
}

watch(
  () => route.query.scope,
  (q) => {
    if ((q === 'production' || q === 'testing' || q === 'all') && q !== scope.value) {
      scope.value = q
      loadBoard()
    }
  },
)

watch(scope, (val) => {
  if (route.query.scope !== val) {
    router.replace({ query: { ...route.query, scope: val } })
  }
})
</script>

<style scoped>
.board-container {
  width: 100%;
  overflow: hidden;
}
.board-scroll {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 12px;
}
.board-column {
  flex: 0 0 280px;
  min-width: 280px;
  max-width: 320px;
}
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
  min-height: 80px;
  border-radius: 6px;
  padding: 4px;
}
.bug-card {
  border-left: 3px solid rgb(var(--v-theme-rule));
}
.cursor-pointer { cursor: pointer; }
</style>
