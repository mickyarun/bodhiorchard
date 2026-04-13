<template>
  <div class="pa-6" style="max-width: 1200px; margin: 0 auto;">
    <!-- Header -->
    <div class="d-flex align-center mb-5">
      <div>
        <div class="text-h5 font-weight-bold">Bugs</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ bugsStore.total }} bug{{ bugsStore.total !== 1 ? 's' : '' }} reported
        </div>
      </div>
      <v-spacer />
      <v-btn color="error" variant="flat" prepend-icon="mdi-bug-outline" @click="showCreate = true">
        Report Bug
      </v-btn>
    </div>

    <!-- Filters -->
    <div class="d-flex ga-3 mb-4 flex-wrap">
      <v-select
        v-model="filterStatus"
        :items="statusOptions"
        label="Status"
        variant="outlined"
        density="compact"
        clearable
        style="max-width: 180px"
      />
      <v-select
        v-model="filterSeverity"
        :items="severityOptions"
        label="Severity"
        variant="outlined"
        density="compact"
        clearable
        style="max-width: 180px"
      />
    </div>

    <!-- Loading -->
    <div v-if="bugsStore.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate size="32" />
    </div>

    <!-- Empty state -->
    <div v-else-if="bugsStore.bugs.length === 0" class="text-center py-12">
      <v-icon icon="mdi-bug-check-outline" size="64" color="success" class="mb-3 opacity-40" />
      <div class="text-h6 font-weight-medium mb-2">No bugs found</div>
      <div class="text-body-2 text-medium-emphasis">
        {{ hasFilters ? 'Try adjusting your filters.' : 'No bugs have been reported yet.' }}
      </div>
    </div>

    <!-- Bug list -->
    <div v-else class="d-flex flex-column ga-2">
      <v-card
        v-for="bug in bugsStore.bugs"
        :key="bug.id"
        variant="outlined"
        class="pa-4"
        style="cursor: pointer"
        @click="openBug(bug)"
      >
        <div class="d-flex align-center ga-3">
          <v-chip :color="BUG_SEVERITY_COLORS[bug.severity]" size="x-small" variant="tonal">
            {{ bug.severity }}
          </v-chip>
          <div class="flex-grow-1 min-w-0">
            <div class="text-body-1 font-weight-medium text-truncate">{{ bug.title }}</div>
            <div class="d-flex align-center ga-2 text-caption text-medium-emphasis">
              <span v-if="bug.module">{{ bug.module }}</span>
              <span v-if="bug.budNumber">BUD-{{ String(bug.budNumber).padStart(3, '0') }}</span>
              <span>{{ bug.reporterName || 'Unknown' }}</span>
              <span>{{ formatDate(bug.createdAt) }}</span>
            </div>
          </div>
          <v-chip
            :color="bug.bugType === 'production' ? 'error' : 'info'"
            size="x-small"
            variant="tonal"
            class="mr-1"
          >
            {{ bug.bugType }}
          </v-chip>
          <v-chip :color="BUG_STATUS_COLORS[bug.status]" size="small" variant="tonal">
            {{ bug.status }}
          </v-chip>
        </div>
      </v-card>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="d-flex justify-center mt-4">
      <v-pagination
        v-model="currentPage"
        :length="totalPages"
        density="compact"
        @update:model-value="onPageChange"
      />
    </div>

    <!-- Bug detail dialog -->
    <v-dialog v-model="showDetail" max-width="600">
      <v-card v-if="bugsStore.currentBug" color="surface" class="pa-6">
        <div class="d-flex align-center ga-2 mb-3">
          <v-chip :color="BUG_SEVERITY_COLORS[bugsStore.currentBug.severity]" size="small" variant="tonal">
            {{ bugsStore.currentBug.severity }}
          </v-chip>
          <v-chip :color="BUG_STATUS_COLORS[bugsStore.currentBug.status]" size="small" variant="tonal">
            {{ bugsStore.currentBug.status }}
          </v-chip>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showDetail = false" />
        </div>

        <div class="text-h6 font-weight-bold mb-2">{{ bugsStore.currentBug.title }}</div>

        <div v-if="bugsStore.currentBug.description" class="text-body-2 mb-4" style="white-space: pre-wrap;">
          {{ bugsStore.currentBug.description }}
        </div>

        <div class="d-flex flex-column ga-2 text-caption text-medium-emphasis mb-4">
          <div v-if="bugsStore.currentBug.module">
            <strong>Module:</strong> {{ bugsStore.currentBug.module }}
          </div>
          <div class="d-flex align-center ga-2">
            <strong>Linked BUD:</strong>
            <template v-if="bugsStore.currentBug.budNumber">
              <v-chip
                size="small"
                variant="tonal"
                color="primary"
                closable
                @click:close="unlinkBud"
              >
                BUD-{{ String(bugsStore.currentBug.budNumber).padStart(3, '0') }}
                <span v-if="bugsStore.currentBug.budTitle" class="ml-1 text-truncate" style="max-width: 200px;">
                  {{ bugsStore.currentBug.budTitle }}
                </span>
              </v-chip>
            </template>
            <template v-else>
              <v-autocomplete
                v-model="linkBudId"
                :items="budItems"
                item-title="label"
                item-value="value"
                variant="outlined"
                density="compact"
                placeholder="Search BUDs..."
                hide-details
                clearable
                style="max-width: 280px"
                @update:model-value="onLinkBud"
              />
            </template>
          </div>
          <div><strong>Reporter:</strong> {{ bugsStore.currentBug.reporterName || 'Unknown' }}</div>
          <div v-if="bugsStore.currentBug.assigneeName">
            <strong>Assignee:</strong> {{ bugsStore.currentBug.assigneeName }}
          </div>
          <div><strong>Created:</strong> {{ formatDate(bugsStore.currentBug.createdAt) }}</div>
          <div v-if="bugsStore.currentBug.resolvedAt">
            <strong>Resolved:</strong> {{ formatDate(bugsStore.currentBug.resolvedAt) }}
          </div>
        </div>

        <!-- Quick status change -->
        <div class="d-flex ga-2">
          <v-btn
            v-for="s in quickStatuses"
            :key="s.value"
            :color="BUG_STATUS_COLORS[s.value]"
            variant="tonal"
            size="small"
            :disabled="bugsStore.currentBug.status === s.value"
            @click="changeStatus(s.value)"
          >
            {{ s.label }}
          </v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- Create dialog -->
    <BugCreateDialog v-model="showCreate" @created="onCreated" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { useBugsStore } from '@/stores/bugs'
import { BUG_SEVERITY_COLORS, BUG_STATUS_COLORS } from '@/types'
import type { BugListItem, BugRead, BugStatusValue } from '@/types'
import { formatDateTime } from '@/utils/date'
import BugCreateDialog from './BugCreateDialog.vue'

const route = useRoute()
const budStore = useBUDStore()
const bugsStore = useBugsStore()

// Pre-populate filter from URL query (e.g. /bugs?budId=xxx from BUD board badge)
const filterBudId = ref<string | null>((route.query.budId as string) || null)

const showCreate = ref(false)
const linkBudId = ref<string | null>(null)

// BUD items for the autocomplete — loaded once when detail opens
const budItems = computed(() =>
  budStore.buds.map((b) => ({
    label: `BUD-${String(b.bud_number).padStart(3, '0')}: ${b.title}`,
    value: b.id,
  })),
)
const showDetail = ref(false)
const filterStatus = ref<string | null>(null)
const filterSeverity = ref<string | null>(null)
const currentPage = ref(1)

const formatDate = formatDateTime

const hasFilters = computed(() => !!filterStatus.value || !!filterSeverity.value)
const totalPages = computed(() => Math.ceil(bugsStore.total / bugsStore.pageSize))

const statusOptions = [
  { title: 'Open', value: 'open' },
  { title: 'In Progress', value: 'in-progress' },
  { title: 'Blocked', value: 'blocked' },
  { title: 'Resolved', value: 'resolved' },
  { title: 'Closed', value: 'closed' },
]

const severityOptions = [
  { title: 'Critical', value: 'critical' },
  { title: 'High', value: 'high' },
  { title: 'Medium', value: 'medium' },
  { title: 'Low', value: 'low' },
]

const quickStatuses: { value: BugStatusValue; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'in-progress', label: 'In Progress' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
]

function loadBugs(): void {
  bugsStore.fetchBugs({
    status: filterStatus.value || undefined,
    severity: filterSeverity.value || undefined,
    budId: filterBudId.value || undefined,
    page: currentPage.value,
  })
}

async function openBug(bug: BugListItem): Promise<void> {
  await bugsStore.fetchBug(bug.id)
  linkBudId.value = bugsStore.currentBug?.budId || null
  // Always refresh BUD list so new BUDs appear in the autocomplete
  await budStore.fetchBUDs()
  showDetail.value = true
}

async function onLinkBud(budId: string | null): Promise<void> {
  if (!bugsStore.currentBug || !budId) return
  await bugsStore.updateBug(bugsStore.currentBug.id, { budId })
}

async function unlinkBud(): Promise<void> {
  if (!bugsStore.currentBug) return
  linkBudId.value = null
  await bugsStore.updateBug(bugsStore.currentBug.id, { budId: null })
}

async function changeStatus(newStatus: BugStatusValue): Promise<void> {
  if (!bugsStore.currentBug) return
  await bugsStore.updateBug(bugsStore.currentBug.id, { status: newStatus })
}

function onCreated(_bug: BugRead): void {
  loadBugs()
}

function onPageChange(page: number): void {
  currentPage.value = page
  loadBugs()
}

watch([filterStatus, filterSeverity], () => {
  currentPage.value = 1
  loadBugs()
})

onMounted(() => loadBugs())
</script>

<style scoped>
.min-w-0 { min-width: 0; }
</style>
