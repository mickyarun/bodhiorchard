<template>
  <div class="tree-dashboard fill-height d-flex flex-column">
    <!-- Stat chips header -->
    <div class="d-flex align-center ga-3 px-4 py-3" style="flex-shrink: 0; flex-wrap: wrap;">
      <div class="text-h6 font-weight-bold mr-2">Living Garden</div>

      <v-chip v-if="displayData" size="small" variant="tonal" color="primary" prepend-icon="mdi-seed-outline">
        {{ totalBUDs }} BUDs
      </v-chip>
      <v-chip v-if="displayData" size="small" variant="tonal" color="success" prepend-icon="mdi-leaf">
        {{ displayData.total_features }} Features
      </v-chip>
      <v-chip v-if="displayData" size="small" variant="tonal" color="purple" prepend-icon="mdi-account-group-outline">
        {{ displayData.members.length }} Members
      </v-chip>
      <v-chip v-if="displayData && displayData.threats.length > 0" size="small" variant="tonal" color="error" prepend-icon="mdi-bug-outline">
        {{ displayData.threats.length }} Threats
      </v-chip>

      <v-spacer />

      <!-- Repo filter -->
      <v-select
        v-if="repoNames.length > 1"
        v-model="visibleRepos"
        :items="repoNames"
        label="Repos"
        variant="outlined"
        density="compact"
        multiple
        hide-details
        style="max-width: 260px; min-width: 160px;"
        prepend-inner-icon="mdi-source-repository"
      >
        <template #prepend-item>
          <v-list-item
            title="Select All"
            @click="selectAllRepos"
          >
            <template #prepend>
              <v-checkbox-btn
                :model-value="visibleRepos.length === repoNames.length"
                :indeterminate="visibleRepos.length > 0 && visibleRepos.length < repoNames.length"
              />
            </template>
          </v-list-item>
          <v-divider />
        </template>
        <template #selection="{ index }">
          <span v-if="index === 0" class="text-body-2">
            {{ visibleRepos.length === repoNames.length ? 'All repos' : `${visibleRepos.length} repos` }}
          </span>
        </template>
      </v-select>

      <!-- Relationship arcs toggle -->
      <v-btn
        v-if="displayData && displayData.relationships && displayData.relationships.length > 0"
        :color="showRelations ? 'info' : undefined"
        size="small"
        variant="tonal"
        prepend-icon="mdi-vector-polyline"
        @click="toggleRelationships"
      >
        {{ showRelations ? 'Relations ON' : 'Relations' }}
      </v-btn>

      <v-btn
        icon="mdi-refresh"
        size="small"
        variant="text"
        :loading="store.loading"
        @click="store.fetchTreeData(true)"
      />
    </div>

    <!-- Loading state -->
    <div v-if="store.loading && !displayData" class="flex-grow-1 d-flex align-center justify-center">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error state -->
    <v-alert v-else-if="store.error" type="error" class="ma-4" closable>
      {{ store.error }}
    </v-alert>

    <!-- Canvas -->
    <div v-else class="flex-grow-1 position-relative overflow-hidden">
      <PlayCanvasCanvas
        v-if="displayData"
        ref="canvasRef"
        :tree-data="displayData"
        @scene-ready="onSceneReady"
        @tree-click="(info) => onTreeClick(info.repoName)"
        @developer-click="(info) => onDeveloperClick({ name: info.name, modelName: info.modelName, isAgent: false, careMode: null, member: null, clipNames: [] })"
        @house-click="(info) => onHouseClick({ name: info.name, activity: 'home' })"
      />
      <TreeLegend v-if="displayData && !selectedRepo && !selectedDeveloper && !selectedHouse" />

      <!-- Tree detail panel (slides in from right) -->
      <Transition name="slide-panel">
        <TreeDetailPanel
          v-if="selectedRepo && !selectedDeveloper && displayData"
          :repo="selectedRepo"
          :features="selectedFeatures"
          :developers="selectedDevelopers"
          @close="deselectTree"
        />
      </Transition>

      <!-- Developer detail panel (slides in from right) -->
      <Transition name="slide-panel">
        <DeveloperDetailPanel
          v-if="selectedDeveloper"
          ref="devPanelRef"
          :info="selectedDeveloper"
          @close="deselectDeveloper"
        />
      </Transition>

      <!-- House detail panel (slides in from right) -->
      <Transition name="slide-panel">
        <HouseDetailPanel
          v-if="selectedHouse"
          :house-info="selectedHouse"
          :member="displayData?.members.find(m => m.name === selectedHouse!.name)"
          @close="deselectHouse"
        />
      </Transition>

      <div v-if="!displayData" class="d-flex align-center justify-center fill-height">
        <div class="text-center text-medium-emphasis">
          <v-icon icon="mdi-tree-outline" size="64" class="mb-3" />
          <div class="text-body-1">No tree data yet</div>
          <div class="text-body-2">Add repositories in Settings to see your garden</div>
        </div>
      </div>
    </div>

    <!-- Tooltip overlay -->
    <TreeTooltip
      v-if="tooltipData"
      :data="tooltipData"
      :position="tooltipPosition"
      @close="tooltipData = null"
    />

    <!-- Setup checklist widget -->
    <SetupChecklist />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'
import type { RepoLimbData, TreeData } from '@/types/dashboard'
import type { CharacterInfo } from '@/components/tree/types'
import type { HouseInfo } from '@/components/tree/types'
import PlayCanvasCanvas from '@/components/tree/PlayCanvasCanvas.vue'
import TreeDetailPanel from '@/components/tree/TreeDetailPanel.vue'
import DeveloperDetailPanel from '@/components/tree/DeveloperDetailPanel.vue'
import HouseDetailPanel from '@/components/tree/HouseDetailPanel.vue'
import SetupChecklist from '@/components/SetupChecklist.vue'
import TreeLegend from '@/components/tree/TreeLegend.vue'
import TreeTooltip from '@/components/tree/TreeTooltip.vue'

const store = useDashboardStore()

const showRelations = ref(false)
const visibleRepos = ref<string[]>([])
const selectedRepo = ref<RepoLimbData | null>(null)
const selectedDeveloper = ref<CharacterInfo | null>(null)
const selectedHouse = ref<HouseInfo | null>(null)
const canvasRef = ref<InstanceType<typeof PlayCanvasCanvas> | null>(null)
const devPanelRef = ref<InstanceType<typeof DeveloperDetailPanel> | null>(null)

const activeData = computed(() => store.treeData)

/** All repo names from the active data source */
const repoNames = computed<string[]>(() => {
  if (!activeData.value) return []
  return activeData.value.repos.map(r => r.repo_name)
})

/** Initialize visibleRepos when data changes */
watch(repoNames, (names) => {
  // Only reset if we have new repos that don't match current selection
  if (names.length > 0 && (visibleRepos.value.length === 0
    || !visibleRepos.value.every(r => names.includes(r)))) {
    visibleRepos.value = [...names]
  }
}, { immediate: true })

/** Filtered data — only includes repos the user has selected */
const displayData = computed<TreeData | null>(() => {
  const data = activeData.value
  if (!data) return null
  if (visibleRepos.value.length === repoNames.value.length) return data

  const visibleSet = new Set(visibleRepos.value)

  const filteredRepos = data.repos.filter(r => visibleSet.has(r.repo_name))

  // Filter by repo_name when available (unambiguous), fall back to branch_name
  const visibleBranches = new Set<string>()
  for (const repo of filteredRepos) {
    for (const branch of repo.branches) {
      visibleBranches.add(branch.name)
    }
  }

  const filteredFeatures = data.features.filter(f => {
    if (f.repo_name) return visibleSet.has(f.repo_name)
    return !f.branch_name || visibleBranches.has(f.branch_name)
  })
  const filteredBuds = data.buds.filter(b => {
    if (b.repo_name) return visibleSet.has(b.repo_name)
    return !b.branch_name || visibleBranches.has(b.branch_name)
  })
  const filteredThreats = data.threats.filter(t =>
    !t.branch_name || visibleBranches.has(t.branch_name))
  const filteredRelationships = (data.relationships ?? []).filter(r =>
    visibleSet.has(r.source_repo) && visibleSet.has(r.target_repo))

  return {
    ...data,
    repos: filteredRepos,
    branches: filteredRepos.flatMap(r => r.branches),
    features: filteredFeatures,
    total_features: filteredFeatures.length,
    buds: filteredBuds,
    threats: filteredThreats,
    relationships: filteredRelationships,
  }
})

const totalBUDs = computed(() => {
  if (!displayData.value) return 0
  const s = displayData.value.bud_stages
  return s.bud + s.design + s.development + s.testing + s.uat + s.prod + s.closed + s.discarded
})

// ─── Tree Selection ──────────────────────────────────

/** Features belonging to the selected repo */
const selectedFeatures = computed(() => {
  if (!selectedRepo.value || !displayData.value) return []
  const repoName = selectedRepo.value.repo_name
  // Match by repo_name first, fallback to branch_name membership
  const branchNames = new Set(selectedRepo.value.branches.map(b => b.name))
  return displayData.value.features.filter(f => {
    if (f.repo_name) return f.repo_name === repoName
    return f.branch_name && branchNames.has(f.branch_name)
  })
})

/** Developers who work on the selected repo (top_modules overlap with branches) */
const selectedDevelopers = computed(() => {
  if (!selectedRepo.value || !displayData.value) return []
  const branchNames = new Set(selectedRepo.value.branches.map(b => b.name))
  return displayData.value.members.filter(m =>
    m.top_modules.some(mod => branchNames.has(mod)),
  )
})

function onHouseClick(houseInfo: HouseInfo): void {
  if (selectedRepo.value) deselectTree()
  if (selectedDeveloper.value) deselectDeveloper()

  if (selectedHouse.value?.name === houseInfo.name) {
    deselectHouse()
    return
  }

  selectedHouse.value = houseInfo
}

function deselectHouse(): void {
  selectedHouse.value = null
}

function onTreeClick(repoName: string | null): void {
  if (selectedDeveloper.value) deselectDeveloper()
  if (selectedHouse.value) deselectHouse()

  if (!repoName) {
    deselectTree()
    return
  }

  if (selectedRepo.value?.repo_name === repoName) {
    deselectTree()
    return
  }

  const repo = displayData.value?.repos.find(r => r.repo_name === repoName)
  if (!repo) return

  selectedRepo.value = repo
}

function deselectTree(): void {
  selectedRepo.value = null
}

function onDeveloperClick(info: CharacterInfo): void {
  if (selectedRepo.value) deselectTree()
  if (selectedHouse.value) deselectHouse()

  if (selectedDeveloper.value?.name === info.name) {
    deselectDeveloper()
    return
  }

  selectedDeveloper.value = info
}

function deselectDeveloper(): void {
  selectedDeveloper.value = null
}

// Close detail panel if the selected repo is filtered out
watch(visibleRepos, () => {
  if (selectedRepo.value && !visibleRepos.value.includes(selectedRepo.value.repo_name)) {
    deselectTree()
  }
})

// ─── Other Controls ──────────────────────────────────

function onSceneReady(): void {
  // PlayCanvas engine is ready
}

function toggleRelationships(): void {
  const visible = canvasRef.value?.toggleArcs() ?? !showRelations.value
  showRelations.value = visible
}

function selectAllRepos(): void {
  if (visibleRepos.value.length === repoNames.value.length) {
    visibleRepos.value = []
  } else {
    visibleRepos.value = [...repoNames.value]
  }
}

const tooltipData = ref<Record<string, unknown> | null>(null)
const tooltipPosition = ref({ x: 0, y: 0 })

onMounted(() => {
  store.fetchTreeData()
})
</script>

<style scoped>
.tree-dashboard {
  background: rgb(var(--v-theme-surface));
}

/* Panel slide-in transition */
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}
.slide-panel-enter-from,
.slide-panel-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
