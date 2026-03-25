<template>
  <div class="dashboard-view fill-height d-flex flex-column">
    <!-- Shared header -->
    <div class="d-flex align-center ga-3 px-4 py-3" style="flex-shrink: 0; flex-wrap: wrap;">
      <div class="text-h6 font-weight-bold mr-2">Dashboard</div>

      <!-- View mode toggle -->
      <v-btn-toggle v-model="viewMode" density="compact" mandatory variant="outlined" divided>
        <v-btn value="tree" size="small">
          <v-icon icon="mdi-pine-tree" size="16" class="mr-1" />
          Garden
        </v-btn>
        <v-btn value="graph" size="small">
          <v-icon icon="mdi-graph-outline" size="16" class="mr-1" />
          Graph
        </v-btn>
      </v-btn-toggle>

      <!-- Stat chips -->
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

      <!-- Tree-mode controls -->
      <template v-if="viewMode === 'tree'">
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
            <v-list-item title="Select All" @click="selectAllRepos">
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
      </template>

      <!-- Graph-mode controls -->
      <template v-if="viewMode === 'graph'">
        <v-btn
          v-if="graphHasSelection"
          icon="mdi-arrow-left"
          variant="text"
          size="small"
          @click="graphContentRef?.backToOverview()"
        />
      </template>

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

    <!-- Canvas area -->
    <div v-else class="flex-grow-1 position-relative overflow-hidden">
      <Transition name="fade" mode="out-in">
        <TreeContent
          v-if="viewMode === 'tree' && displayData"
          key="tree"
          ref="treeContentRef"
          :display-data="displayData"
        />
        <GraphContent
          v-else-if="viewMode === 'graph' && displayData"
          key="graph"
          ref="graphContentRef"
          :tree-data="displayData"
          @selection-change="v => graphHasSelection = v"
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

    <!-- Setup checklist widget -->
    <SetupChecklist />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import type { TreeData } from '@/types/dashboard'
import TreeContent from './TreeContent.vue'
import GraphContent from './GraphContent.vue'
import SetupChecklist from '@/components/SetupChecklist.vue'

const route = useRoute()
const router = useRouter()
const store = useDashboardStore()

// ─── View Mode ───────────────────────────────────

const viewMode = ref<'tree' | 'graph'>('tree')
const graphHasSelection = ref(false)
const treeContentRef = ref<InstanceType<typeof TreeContent> | null>(null)
const graphContentRef = ref<InstanceType<typeof GraphContent> | null>(null)

// Init from URL
if (route.query.view === 'graph') viewMode.value = 'graph'

// Sync to URL (replace, not push — don't pollute history)
watch(viewMode, (mode) => {
  graphHasSelection.value = false
  showRelations.value = false
  router.replace({
    query: { ...route.query, view: mode === 'tree' ? undefined : mode },
  })
})

// ─── Shared State ────────────────────────────────

const showRelations = ref(false)
const visibleRepos = ref<string[]>([])

const repoNames = computed<string[]>(() => {
  if (!store.treeData) return []
  return store.treeData.repos.map(r => r.repo_name)
})

// Initialize visibleRepos when data changes
watch(repoNames, (names) => {
  if (names.length > 0 && (visibleRepos.value.length === 0
    || !visibleRepos.value.every(r => names.includes(r)))) {
    visibleRepos.value = [...names]
  }
}, { immediate: true })

// Filtered data — only includes repos the user has selected
const displayData = computed<TreeData | null>(() => {
  const data = store.treeData
  if (!data) return null
  if (visibleRepos.value.length === repoNames.value.length) return data

  const visibleSet = new Set(visibleRepos.value)

  const filteredRepos = data.repos.filter(r => visibleSet.has(r.repo_name))

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

function toggleRelationships(): void {
  const visible = treeContentRef.value?.toggleArcs() ?? !showRelations.value
  showRelations.value = visible
}

function selectAllRepos(): void {
  if (visibleRepos.value.length === repoNames.value.length) {
    visibleRepos.value = []
  } else {
    visibleRepos.value = [...repoNames.value]
  }
}

// ─── Data Fetch ──────────────────────────────────

onMounted(() => {
  store.fetchTreeData()
})
</script>

<style scoped>
.dashboard-view {
  background: rgb(var(--v-theme-surface));
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
