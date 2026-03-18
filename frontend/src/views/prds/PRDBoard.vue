<template>
  <div class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="text-h5 font-weight-bold">PRD Board</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ prdStore.prds.length }} document{{ prdStore.prds.length !== 1 ? 's' : '' }}
        </div>
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        New PRD
      </v-btn>
    </div>

    <!-- Loading -->
    <div v-if="prdStore.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error -->
    <v-alert v-else-if="prdStore.error" type="error" variant="tonal" class="mb-4">
      {{ prdStore.error }}
      <template #append>
        <v-btn variant="text" size="small" @click="prdStore.fetchPRDs()">Retry</v-btn>
      </template>
    </v-alert>

    <!-- Empty state -->
    <v-card
      v-else-if="prdStore.prds.length === 0"
      class="pa-12 text-center"
      color="surface"
    >
      <v-icon icon="mdi-file-document-plus-outline" size="64" class="text-medium-emphasis mb-4" />
      <div class="text-h6 mb-2">No PRDs yet</div>
      <div class="text-body-2 text-medium-emphasis mb-6">
        Create your first Product Requirements Document to get started.
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        Create PRD
      </v-btn>
    </v-card>

    <!-- Kanban Board -->
    <div v-else class="board-container">
      <div class="board-scroll">
        <div
          v-for="status in PRD_STATUS_ORDER"
          :key="status"
          class="board-column"
        >
          <!-- Column header -->
          <div class="column-header d-flex align-center justify-space-between pa-3 mb-2">
            <div class="d-flex align-center ga-2">
              <v-chip
                :color="PRD_STATUS_COLORS[status]"
                size="x-small"
                variant="flat"
                label
              >
                {{ prdStore.prdsByStatus[status]?.length || 0 }}
              </v-chip>
              <span class="text-body-2 font-weight-medium">{{ PRD_STATUS_LABELS[status] }}</span>
            </div>
          </div>

          <!-- Cards -->
          <div class="column-cards">
            <v-card
              v-for="prd in prdStore.prdsByStatus[status]"
              :key="prd.id"
              class="prd-card pa-4 mb-2 cursor-pointer"
              color="surface"
              @click="openPRD(prd.id)"
            >
              <div class="text-caption text-medium-emphasis mb-1">
                PRD-{{ String(prd.prd_number).padStart(3, '0') }}
              </div>
              <div class="text-body-2 font-weight-medium mb-2">{{ prd.title }}</div>
              <div class="text-caption text-medium-emphasis">
                {{ formatDate(prd.updated_at) }}
              </div>
            </v-card>

            <div
              v-if="!prdStore.prdsByStatus[status]?.length"
              class="text-caption text-medium-emphasis text-center pa-4"
              style="opacity: 0.4;"
            >
              No items
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create PRD Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="500">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 font-weight-bold mb-4">New PRD</div>
        <v-text-field
          v-model="newTitle"
          label="Title"
          placeholder="e.g. Payment retry logic"
          autofocus
          class="mb-3"
          :rules="[v => !!v?.trim() || 'Title is required']"
          @keyup.enter="createPRD"
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
            @click="createPRD"
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
import { usePRDStore } from '@/stores/prd'
import { PRD_STATUS_ORDER, PRD_STATUS_LABELS, PRD_STATUS_COLORS } from '@/types'

const router = useRouter()
const prdStore = usePRDStore()

const showCreateDialog = ref(false)
const newTitle = ref('')
const newContent = ref('')
const creating = ref(false)

onMounted(() => {
  prdStore.fetchPRDs()
})

function openPRD(id: string): void {
  router.push(`/prds/${id}`)
}

async function createPRD(): Promise<void> {
  if (!newTitle.value.trim()) return
  creating.value = true
  const prd = await prdStore.createPRD(newTitle.value.trim(), newContent.value.trim() || undefined)
  creating.value = false
  if (prd) {
    showCreateDialog.value = false
    newTitle.value = ''
    newContent.value = ''
    router.push(`/prds/${prd.id}`)
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
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

.prd-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.15s ease;
}

.prd-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
}
</style>
