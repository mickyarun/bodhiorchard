<template>
  <div class="graph-test-view fill-height">
    <!-- Header -->
    <div class="graph-header d-flex align-center ga-3 px-4 py-2">
      <div class="text-h6">Repo Graph</div>
      <v-chip v-if="treeData" size="small" variant="tonal" color="primary">
        {{ treeData.repos.length }} repos
      </v-chip>
      <v-chip v-if="treeData" size="small" variant="tonal" color="info">
        {{ treeData.features.length }} features
      </v-chip>
      <v-chip v-if="treeData" size="small" variant="tonal" color="secondary">
        {{ treeData.members.length }} members
      </v-chip>
      <v-spacer />
      <v-btn
        variant="text"
        icon="mdi-refresh"
        size="small"
        :loading="dashboardStore.loading"
        @click="refresh"
      />
    </div>

    <!-- Loading state -->
    <div v-if="dashboardStore.loading && !treeData" class="d-flex align-center justify-center fill-height">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error state -->
    <div v-else-if="dashboardStore.error" class="d-flex align-center justify-center fill-height">
      <v-alert type="error" variant="tonal" class="ma-4">
        {{ dashboardStore.error }}
      </v-alert>
    </div>

    <!-- Graph canvas -->
    <div v-else class="graph-body position-relative">
      <GraphCanvas
        v-if="treeData"
        :tree-data="treeData"
        @repo-click="onRepoClick"
        @feature-click="onFeatureClick"
      />

      <!-- Legend -->
      <div class="graph-legend">
        <v-card variant="tonal" class="pa-3" density="compact">
          <div class="text-caption font-weight-bold mb-2">Legend</div>
          <div class="d-flex flex-column ga-1">
            <div class="d-flex align-center ga-2">
              <div class="legend-dot" style="width: 12px; height: 12px; border: 2px solid rgba(255,255,255,0.5);" />
              <span class="text-caption">Repo (unique color each)</span>
            </div>
            <div class="d-flex align-center ga-2">
              <div class="legend-dot" style="width: 8px; height: 8px; border: 2px solid rgba(255,255,255,0.3);" />
              <span class="text-caption">Feature (lighter tint of repo)</span>
            </div>
            <div class="d-flex align-center ga-2">
              <div class="legend-line" />
              <span class="text-caption">Curved arc = connection</span>
            </div>
          </div>
        </v-card>
      </div>

      <!-- Detail panel -->
      <Transition name="slide">
        <GraphDetailPanel
          v-if="selectedRepo || selectedFeature"
          :repo="selectedRepo"
          :feature="selectedFeature"
          :tree-data="treeData"
          @close="clearSelection"
        />
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'
import GraphCanvas from '@/components/graph/GraphCanvas.vue'
import GraphDetailPanel from '@/components/graph/GraphDetailPanel.vue'
import type { GraphRepoInfo, GraphFeatureInfo } from '@/engine/graph'

const dashboardStore = useDashboardStore()

const selectedRepo = ref<GraphRepoInfo | null>(null)
const selectedFeature = ref<GraphFeatureInfo | null>(null)

const treeData = computed(() => dashboardStore.treeData)

function onRepoClick(info: GraphRepoInfo): void {
  selectedRepo.value = info
  selectedFeature.value = null
}

function onFeatureClick(info: GraphFeatureInfo): void {
  selectedFeature.value = info
  selectedRepo.value = null
}

function clearSelection(): void {
  selectedRepo.value = null
  selectedFeature.value = null
}

async function refresh(): Promise<void> {
  await dashboardStore.fetchTreeData(true)
}

onMounted(async () => {
  if (!dashboardStore.treeData) {
    await dashboardStore.fetchTreeData()
  }
})
</script>

<style scoped>
.graph-test-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.graph-header {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.graph-body {
  flex: 1;
  min-height: 0;
}

.graph-legend {
  position: absolute;
  bottom: 16px;
  left: 16px;
  z-index: 10;
}

.legend-dot {
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-line {
  width: 20px;
  height: 2px;
  background: rgba(255, 255, 255, 0.4);
  border-radius: 1px;
  flex-shrink: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
