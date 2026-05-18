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
  <div class="dashboard-view fill-height d-flex flex-column">
    <!-- Shared header — single-line, horizontally scrollable on narrow
         screens (iPad portrait / small laptops) so controls don't
         wrap to a second row and chew up canvas vertical space. -->
    <div class="dashboard-view__header d-flex align-center ga-3 px-4 py-3">
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
      <v-chip
        v-if="displayData"
        size="small"
        variant="tonal"
        :color="showStandup ? 'warning' : undefined"
        prepend-icon="mdi-calendar-clock-outline"
        style="cursor: pointer;"
        @click="showStandup = !showStandup"
      >
        Standup
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
          v-if="viewMode === 'tree' && store.treeData"
          key="tree"
          ref="treeContentRef"
          :display-data="store.treeData"
          :visible-repos="visibleRepos"
          @zone-enter="onZoneEnter"
          @zone-exit="onZoneExit"
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
          <img src="/assets/bodhiorchard-logo.png" width="64" height="64" alt="" class="mb-3" style="border-radius: 50%; opacity: 0.6;" />
          <div class="text-body-1">No tree data yet</div>
          <div class="text-body-2">Add repositories in Settings to see your garden</div>
        </div>
      </div>

      <!-- Standup overlay panel -->
      <Transition name="slide-panel">
        <StandupPanel v-if="showStandup" @close="showStandup = false" />
      </Transition>

      <!-- Takeover hint overlay -->
      <div
        v-if="viewMode === 'tree' && displayData && !isTakeover"
        class="takeover-hint"
      >
        Press <kbd>T</kbd> to take control
      </div>
      <div
        v-if="isTakeover"
        class="takeover-hint"
      >
        <kbd>ESC</kbd> to exit
      </div>
    </div>

    <!-- Setup checklist widget -->
    <SetupChecklist />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import type { TreeData } from '@/types/dashboard'
import TreeContent from './TreeContent.vue'
import GraphContent from './GraphContent.vue'
import SetupChecklist from '@/components/SetupChecklist.vue'
import StandupPanel from '@/components/standup/StandupPanel.vue'

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
const showStandup = ref(false)
const isTakeover = ref(false)
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

  // Features count by distinct title — the backend emits one row per repo a
  // feature touches (primary + linked backends) so the graph view can draw
  // cross-repo arcs, but the user-facing total should count each feature once.
  const uniqueFeatureTitles = new Set(filteredFeatures.map(f => f.title))

  return {
    ...data,
    repos: filteredRepos,
    branches: filteredRepos.flatMap(r => r.branches),
    features: filteredFeatures,
    total_features: uniqueFeatureTitles.size,
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

function toggleTakeover(): void {
  const ref = treeContentRef.value
  if (!ref) return
  if (ref.isInControl()) {
    // In takeover OR interior — exit to overview
    if (ref.isTakeover()) ref.exitTakeover()
    else ref.exitHouse()  // interior mode
  } else {
    ref.takeoverCharacter()
  }
  // Sync state after async operations settle
  setTimeout(() => {
    isTakeover.value = treeContentRef.value?.isInControl() ?? false
  }, 100)
}

function onKeyDown(e: KeyboardEvent): void {
  // T key toggles takeover when not typing in an input
  if (e.key === 't' || e.key === 'T') {
    const tag = (e.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
    if (viewMode.value === 'tree') toggleTakeover()
  }
}

function onZoneEnter(zone: string): void {
  if (zone === 'pavilion') showStandup.value = true
}

function onZoneExit(zone: string): void {
  if (zone === 'pavilion') showStandup.value = false
}

function selectAllRepos(): void {
  if (visibleRepos.value.length === repoNames.value.length) {
    visibleRepos.value = []
  } else {
    visibleRepos.value = [...repoNames.value]
  }
}

// ─── Data Fetch + takeover state sync ───────────

let takeoverSyncInterval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  store.fetchTreeData()
  window.addEventListener('keydown', onKeyDown)

  // Poll control state every 500ms so the hint stays in sync
  // when state changes via auto-exit, door entry, ESC, etc.
  takeoverSyncInterval = setInterval(() => {
    const engineState = treeContentRef.value?.isInControl() ?? false
    if (engineState !== isTakeover.value) {
      isTakeover.value = engineState
    }
  }, 500)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  if (takeoverSyncInterval !== null) {
    clearInterval(takeoverSyncInterval)
    takeoverSyncInterval = null
  }
})
</script>

<style scoped>
.dashboard-view {
  background: rgb(var(--v-theme-surface));
}

/* Keep the header on a single line — chips/selects scroll horizontally
   instead of wrapping, so the canvas below keeps its full height. */
.dashboard-view__header {
  flex-shrink: 0;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
  -webkit-overflow-scrolling: touch;
}

.dashboard-view__header > * {
  flex-shrink: 0;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.slide-panel-enter-from,
.slide-panel-leave-to {
  transform: translateX(40px);
  opacity: 0;
}

.takeover-hint {
  position: absolute;
  bottom: 16px;
  left: 16px;
  z-index: 10;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(15, 20, 30, 0.55);
  backdrop-filter: blur(8px);
  color: rgba(255, 255, 255, 0.85);
  font-size: 12px;
  pointer-events: none;
  user-select: none;
}

/* On touch devices the "Press T" hint is misleading — there's no
   keyboard and PlayCanvasCanvas already renders an on-screen
   "Take control" button in its place. */
@media (hover: none) and (pointer: coarse) {
  .takeover-hint {
    display: none;
  }
}

.takeover-hint kbd {
  display: inline-block;
  padding: 1px 6px;
  margin: 0 2px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.1);
  font-family: inherit;
  font-weight: 600;
}
</style>
