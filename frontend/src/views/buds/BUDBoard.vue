<template>
  <div class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="text-h5 font-weight-bold">BUD Board</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ budStore.buds.length }} document{{ budStore.buds.length !== 1 ? 's' : '' }}
        </div>
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        New BUD
      </v-btn>
    </div>

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
      <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        Create BUD
      </v-btn>
    </v-card>

    <!-- Kanban Board -->
    <div v-else class="board-container">
      <div class="board-scroll">
        <div
          v-for="status in BUD_STATUS_ORDER.filter(s => s !== 'discarded')"
          :key="status"
          class="board-column"
        >
          <!-- Column header -->
          <div class="column-header d-flex align-center justify-space-between pa-3 mb-2">
            <div class="d-flex align-center ga-2">
              <v-chip
                :color="BUD_STATUS_COLORS[status]"
                size="x-small"
                variant="flat"
                label
              >
                {{ budStore.budsByStatus[status]?.length || 0 }}
              </v-chip>
              <span class="text-body-2 font-weight-medium">{{ BUD_STATUS_LABELS[status] }}</span>
            </div>
          </div>

          <!-- Cards -->
          <div class="column-cards">
            <v-card
              v-for="bud in budStore.budsByStatus[status]"
              :key="bud.id"
              class="bud-card pa-4 mb-2 cursor-pointer"
              color="surface"
              @click="openBUD(bud.id)"
            >
              <!-- Row 1: BUD number + complexity dots -->
              <div class="d-flex align-center justify-space-between mb-1">
                <div class="text-caption text-medium-emphasis">
                  BUD-{{ String(bud.bud_number).padStart(3, '0') }}
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

              <!-- Row 2: Title -->
              <div class="text-body-2 font-weight-medium mb-2">{{ bud.title }}</div>

              <!-- Row 3: Phase deadline + go-live (only if estimates exist) -->
              <div v-if="bud.current_phase_deadline" class="text-caption mb-1" :class="deadlineColor(bud.current_phase_deadline)">
                ▸ Phase: {{ formatDate(bud.current_phase_deadline) }}
              </div>
              <div v-if="bud.prod_p70_date" class="text-caption text-medium-emphasis mb-2">
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
              v-if="!budStore.budsByStatus[status]?.length"
              class="text-caption text-medium-emphasis text-center pa-4"
              style="opacity: 0.4;"
            >
              No items
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create BUD Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="500">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 font-weight-bold mb-4">New BUD</div>
        <v-text-field
          v-model="newTitle"
          label="Title"
          placeholder="e.g. Payment retry logic"
          autofocus
          class="mb-3"
          :rules="[v => !!v?.trim() || 'Title is required']"
          @keyup.enter="createBUD"
        />
        <v-textarea
          v-model="newContent"
          label="Description (optional)"
          placeholder="Brief description or requirements..."
          rows="4"
          variant="outlined"
        />
        <v-card-actions class="pa-0 mt-2">
          <v-spacer />
          <v-btn variant="text" @click="showCreateDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="creating"
            :disabled="!newTitle.trim()"
            @click="createBUD"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { BUD_STATUS_ORDER, BUD_STATUS_LABELS, BUD_STATUS_COLORS } from '@/types'
import type { BUDStatus } from '@/types'

const router = useRouter()
const budStore = useBUDStore()

const showCreateDialog = ref(false)
const newTitle = ref('')
const newContent = ref('')
const creating = ref(false)

onMounted(() => {
  budStore.fetchBUDs()
})

function openBUD(id: string): void {
  router.push(`/buds/${id}`)
}

async function createBUD(): Promise<void> {
  if (!newTitle.value.trim()) return
  creating.value = true
  const bud = await budStore.createBUD(newTitle.value.trim(), newContent.value.trim() || undefined)
  creating.value = false
  if (bud) {
    showCreateDialog.value = false
    newTitle.value = ''
    newContent.value = ''
    router.push(`/buds/${bud.id}`)
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

const ACTIVE_PHASE_COUNT = BUD_STATUS_ORDER.filter(
  s => s !== 'discarded' && s !== 'closed',
).length

function phaseProgress(status: BUDStatus): number {
  const idx = BUD_STATUS_ORDER.indexOf(status)
  return idx >= 0 ? Math.min(100, ((idx + 1) / ACTIVE_PHASE_COUNT) * 100) : 0
}

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

.column-header {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
}

.column-cards {
  min-height: 100px;
}

.bud-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.15s ease;
}

.bud-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
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
  background: rgba(255, 255, 255, 0.12);
}
</style>
