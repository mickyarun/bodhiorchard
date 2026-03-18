<template>
  <div class="pa-6">
    <div class="text-h5 font-weight-bold mb-1">Dashboard</div>
    <div class="text-body-2 text-medium-emphasis mb-6">Overview of your development operations</div>

    <v-row>
      <!-- PRD summary -->
      <v-col cols="12" md="4">
        <v-card color="surface" class="pa-5">
          <div class="d-flex align-center ga-3 mb-3">
            <v-avatar size="40" color="primary" variant="tonal" rounded="lg">
              <v-icon icon="mdi-file-document-outline" />
            </v-avatar>
            <div>
              <div class="text-h5 font-weight-bold">{{ prdStore.prds.length }}</div>
              <div class="text-caption text-medium-emphasis">PRDs</div>
            </div>
          </div>
          <v-btn
            variant="tonal"
            color="primary"
            size="small"
            block
            to="/prds"
          >
            View Board
          </v-btn>
        </v-card>
      </v-col>

      <!-- Agents -->
      <v-col cols="12" md="4">
        <v-card color="surface" class="pa-5">
          <div class="d-flex align-center ga-3 mb-3">
            <v-avatar size="40" color="secondary" variant="tonal" rounded="lg">
              <v-icon icon="mdi-robot-outline" />
            </v-avatar>
            <div>
              <div class="text-h5 font-weight-bold">11</div>
              <div class="text-caption text-medium-emphasis">AI Agents</div>
            </div>
          </div>
          <v-chip variant="tonal" size="small" color="grey">Coming soon</v-chip>
        </v-card>
      </v-col>

      <!-- Team -->
      <v-col cols="12" md="4">
        <v-card color="surface" class="pa-5">
          <div class="d-flex align-center ga-3 mb-3">
            <v-avatar size="40" color="success" variant="tonal" rounded="lg">
              <v-icon icon="mdi-account-group-outline" />
            </v-avatar>
            <div>
              <div class="text-h5 font-weight-bold">-</div>
              <div class="text-caption text-medium-emphasis">Team Members</div>
            </div>
          </div>
          <v-chip variant="tonal" size="small" color="grey">Coming soon</v-chip>
        </v-card>
      </v-col>
    </v-row>

    <!-- Recent PRDs -->
    <div class="text-body-1 font-weight-medium mt-8 mb-3">Recent PRDs</div>
    <v-card v-if="prdStore.prds.length === 0" color="surface" class="pa-6 text-center">
      <div class="text-body-2 text-medium-emphasis">No PRDs yet. Create one from the PRD Board.</div>
      <v-btn color="primary" variant="tonal" size="small" class="mt-3" to="/prds">
        Go to PRD Board
      </v-btn>
    </v-card>
    <v-card v-else color="surface">
      <v-list density="compact">
        <v-list-item
          v-for="prd in recentPRDs"
          :key="prd.id"
          :to="`/prds/${prd.id}`"
        >
          <template #prepend>
            <span class="text-caption text-medium-emphasis mr-3" style="min-width: 56px;">
              PRD-{{ String(prd.prd_number).padStart(3, '0') }}
            </span>
          </template>
          <v-list-item-title class="text-body-2">{{ prd.title }}</v-list-item-title>
          <template #append>
            <v-chip :color="PRD_STATUS_COLORS[prd.status]" size="x-small" variant="tonal" label>
              {{ PRD_STATUS_LABELS[prd.status] }}
            </v-chip>
          </template>
        </v-list-item>
      </v-list>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { usePRDStore } from '@/stores/prd'
import { PRD_STATUS_LABELS, PRD_STATUS_COLORS } from '@/types'

const prdStore = usePRDStore()

const recentPRDs = computed(() => prdStore.prds.slice(0, 5))

onMounted(() => {
  prdStore.fetchPRDs()
})
</script>
