<template>
  <div class="graph-test-view fill-height">
    <!-- Header -->
    <div class="graph-header d-flex align-center ga-3 px-4 py-2">
      <v-btn
        v-if="selectedRepo || selectedFeature"
        icon="mdi-arrow-left"
        variant="text"
        size="small"
        @click="backToOverview"
      />
      <div class="text-h6">
        {{ selectedRepo ? selectedRepo.repoName : 'Repo Graph' }}
      </div>
      <v-chip v-if="treeData && !selectedRepo" size="small" variant="tonal" color="primary">
        {{ treeData.repos.length }} repos
      </v-chip>
      <v-chip v-if="treeData && !selectedRepo" size="small" variant="tonal" color="info">
        {{ treeData.features.length }} features
      </v-chip>
      <v-chip v-if="treeData && !selectedRepo" size="small" variant="tonal" color="secondary">
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
        ref="graphCanvasRef"
        :tree-data="treeData"
        @repo-click="onRepoClick"
        @feature-click="onFeatureClick"
      />

      <!-- Toolbar (hidden when detail panel is open) -->
      <GraphToolbar
        v-if="treeData && !selectedRepo && !selectedFeature"
        :members="toolbarMembers"
        :repos="toolbarRepos"
        @toggle-cross-repo="v => graphCanvasRef?.setCrossRepoLinksVisible(v)"
        @toggle-bus-factor="v => graphCanvasRef?.setBusFactorVisible(v)"
        @toggle-status="v => graphCanvasRef?.setStatusOverlay(v)"
        @toggle-threats="v => graphCanvasRef?.setThreatOverlay(v)"
        @toggle-bud-badges="v => graphCanvasRef?.setBudBadgesVisible(v)"
        @filter-repo="v => graphCanvasRef?.filterByRepo(v)"
        @filter-developer="v => graphCanvasRef?.filterByDeveloper(v)"
      />

      <!-- Detail panel -->
      <Transition name="slide">
        <GraphDetailPanel
          v-if="selectedRepo || selectedFeature"
          :repo="selectedRepo"
          :feature="selectedFeature"
          :tree-data="treeData"
          @close="backToOverview"
          @developer-highlight="onDeveloperHighlight"
          @repo-focus="repo => graphCanvasRef?.focusOnRepo(repo)"
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
import GraphToolbar from '@/components/graph/GraphToolbar.vue'
import type { GraphRepoInfo, GraphFeatureInfo } from '@/engine/graph'

const dashboardStore = useDashboardStore()

const graphCanvasRef = ref<InstanceType<typeof GraphCanvas> | null>(null)
const selectedRepo = ref<GraphRepoInfo | null>(null)
const selectedFeature = ref<GraphFeatureInfo | null>(null)

const treeData = computed(() => dashboardStore.treeData)

const toolbarMembers = computed(() =>
  (treeData.value?.members ?? []).map(m => ({
    userId: m.user_id,
    name: m.name,
  }))
)

const toolbarRepos = computed(() =>
  (treeData.value?.repos ?? []).map(r => r.repo_name).sort()
)

function onRepoClick(info: GraphRepoInfo): void {
  selectedRepo.value = info
  selectedFeature.value = null
  graphCanvasRef.value?.focusOnRepo(info.repoName)
}

function onFeatureClick(info: GraphFeatureInfo): void {
  selectedFeature.value = info
  selectedRepo.value = null
}

function onDeveloperHighlight(userId: string): void {
  graphCanvasRef.value?.highlightDeveloper(userId)
}

function backToOverview(): void {
  selectedRepo.value = null
  selectedFeature.value = null
  graphCanvasRef.value?.clearHighlight()
  graphCanvasRef.value?.resetView()
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
