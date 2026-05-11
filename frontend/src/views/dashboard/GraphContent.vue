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
  <div class="graph-content fill-height position-relative">
    <GraphCanvas
      ref="graphCanvasRef"
      :tree-data="treeData"
      @repo-click="onRepoClick"
      @feature-click="onFeatureClick"
    />

    <!-- Toolbar (hidden when detail panel is open) -->
    <GraphToolbar
      v-if="!selectedRepo && !selectedFeature"
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
    <Transition name="slide-panel">
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
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { TreeData } from '@/types/dashboard'
import GraphCanvas from '@/components/graph/GraphCanvas.vue'
import GraphDetailPanel from '@/components/graph/GraphDetailPanel.vue'
import GraphToolbar from '@/components/graph/GraphToolbar.vue'
import type { GraphRepoInfo, GraphFeatureInfo } from '@/engine/graph'

const props = defineProps<{
  treeData: TreeData
}>()

const emit = defineEmits<{
  'selection-change': [hasSelection: boolean]
}>()

const graphCanvasRef = ref<InstanceType<typeof GraphCanvas> | null>(null)
const selectedRepo = ref<GraphRepoInfo | null>(null)
const selectedFeature = ref<GraphFeatureInfo | null>(null)

const toolbarMembers = computed(() =>
  (props.treeData.members ?? []).map(m => ({
    userId: m.user_id,
    name: m.name,
  })),
)

const toolbarRepos = computed(() =>
  (props.treeData.repos ?? []).map(r => r.repo_name).sort(),
)

function onRepoClick(info: GraphRepoInfo): void {
  selectedRepo.value = info
  selectedFeature.value = null
  graphCanvasRef.value?.focusOnRepo(info.repoName)
  emit('selection-change', true)
}

function onFeatureClick(info: GraphFeatureInfo): void {
  selectedFeature.value = info
  selectedRepo.value = null
  emit('selection-change', true)
}

function onDeveloperHighlight(userId: string): void {
  graphCanvasRef.value?.highlightDeveloper(userId)
}

function backToOverview(): void {
  selectedRepo.value = null
  selectedFeature.value = null
  graphCanvasRef.value?.clearHighlight()
  graphCanvasRef.value?.resetView()
  emit('selection-change', false)
}

defineExpose({ backToOverview })
</script>

<style scoped>
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.slide-panel-enter-from,
.slide-panel-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
