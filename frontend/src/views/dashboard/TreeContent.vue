<template>
  <div class="tree-content fill-height position-relative overflow-hidden">
    <PlayCanvasCanvas
      ref="canvasRef"
      :tree-data="displayData"
      @tree-click="(info) => onTreeClick(info.repoName)"
      @developer-click="(info) => onDeveloperClick({ name: info.name, modelName: info.modelName, isAgent: false, careMode: null, member: null, clipNames: [] })"
      @house-click="(info) => onHouseClick({ name: info.name, activity: 'home' })"
    />
    <TreeLegend v-if="!selectedRepo && !selectedDeveloper && !selectedHouse" />

    <!-- Tree detail panel -->
    <Transition name="slide-panel">
      <TreeDetailPanel
        v-if="selectedRepo && !selectedDeveloper"
        :repo="selectedRepo"
        :features="selectedFeatures"
        :developers="selectedDevelopers"
        @close="deselectTree"
      />
    </Transition>

    <!-- Developer detail panel -->
    <Transition name="slide-panel">
      <DeveloperDetailPanel
        v-if="selectedDeveloper"
        :info="selectedDeveloper"
        @close="deselectDeveloper"
      />
    </Transition>

    <!-- House detail panel -->
    <Transition name="slide-panel">
      <HouseDetailPanel
        v-if="selectedHouse"
        :house-info="selectedHouse"
        :member="displayData.members.find(m => m.name === selectedHouse!.name)"
        @close="deselectHouse"
      />
    </Transition>

  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TreeData, RepoLimbData } from '@/types/dashboard'
import type { CharacterInfo, HouseInfo } from '@/components/tree/types'
import PlayCanvasCanvas from '@/components/tree/PlayCanvasCanvas.vue'
import TreeDetailPanel from '@/components/tree/TreeDetailPanel.vue'
import DeveloperDetailPanel from '@/components/tree/DeveloperDetailPanel.vue'
import HouseDetailPanel from '@/components/tree/HouseDetailPanel.vue'
import TreeLegend from '@/components/tree/TreeLegend.vue'

const props = defineProps<{
  displayData: TreeData
}>()

const canvasRef = ref<InstanceType<typeof PlayCanvasCanvas> | null>(null)
const selectedRepo = ref<RepoLimbData | null>(null)
const selectedDeveloper = ref<CharacterInfo | null>(null)
const selectedHouse = ref<HouseInfo | null>(null)

// ─── Computed ────────────────────────────────────

const selectedFeatures = computed(() => {
  if (!selectedRepo.value) return []
  const repoName = selectedRepo.value.repo_name
  const branchNames = new Set(selectedRepo.value.branches.map(b => b.name))
  return props.displayData.features.filter(f => {
    if (f.repo_name) return f.repo_name === repoName
    return f.branch_name && branchNames.has(f.branch_name)
  })
})

const selectedDevelopers = computed(() => {
  if (!selectedRepo.value) return []
  const branchNames = new Set(selectedRepo.value.branches.map(b => b.name))
  return props.displayData.members.filter(m =>
    m.top_modules.some(mod => branchNames.has(mod)),
  )
})

// ─── Click Handlers ──────────────────────────────

function onTreeClick(repoName: string | null): void {
  if (selectedDeveloper.value) deselectDeveloper()
  if (selectedHouse.value) deselectHouse()

  if (!repoName) { deselectTree(); return }
  if (selectedRepo.value?.repo_name === repoName) { deselectTree(); return }

  const repo = props.displayData.repos.find(r => r.repo_name === repoName)
  if (!repo) return
  selectedRepo.value = repo
  canvasRef.value?.focusOnRepo(repoName)
}

function onDeveloperClick(info: CharacterInfo): void {
  if (selectedRepo.value) deselectTree()
  if (selectedHouse.value) deselectHouse()
  if (selectedDeveloper.value?.name === info.name) { deselectDeveloper(); return }
  selectedDeveloper.value = info
}

function onHouseClick(houseInfo: HouseInfo): void {
  if (selectedRepo.value) deselectTree()
  if (selectedDeveloper.value) deselectDeveloper()
  if (selectedHouse.value?.name === houseInfo.name) { deselectHouse(); return }
  selectedHouse.value = houseInfo
}

function deselectTree(): void {
  selectedRepo.value = null
  canvasRef.value?.clearFocus()
}
function deselectDeveloper(): void { selectedDeveloper.value = null }
function deselectHouse(): void { selectedHouse.value = null }

// Deselect if the selected repo is no longer in the data
watch(() => props.displayData, () => {
  if (selectedRepo.value) {
    const still = props.displayData.repos.some(r => r.repo_name === selectedRepo.value!.repo_name)
    if (!still) deselectTree()
  }
})

defineExpose({
  /** Returns new visibility state */
  toggleArcs: () => canvasRef.value?.toggleArcs(),
})
</script>

<style scoped>
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
