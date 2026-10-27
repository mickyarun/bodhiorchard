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

<!-- The Graph or Garden canvas in a bordered frame, with its loading and
     empty states, live race matches and the takeover hint. Exposes the
     garden's controls so the dashboard can drive takeover and links. -->
<template>
  <div class="canvas-stage">
    <div v-if="loading && !data" class="canvas-stage__state">
      <v-progress-circular indeterminate color="primary" aria-label="Loading the code map" />
    </div>
    <div v-else-if="!data" class="canvas-stage__state">
      <BrandLogo :size="48" :show-text="false" class="canvas-stage__mark" />
      <p class="canvas-stage__title">No code map yet</p>
      <p class="canvas-stage__hint">
        Add a repository in <router-link to="/settings/code">Settings</router-link> and run a scan.
      </p>
    </div>
    <Transition v-else name="fade" mode="out-in">
      <TreeContent
        v-if="mode === 'garden' && treeData"
        key="garden"
        ref="treeRef"
        :display-data="treeData"
        :visible-repos="visibleRepos"
        @zone-enter="zone => emit('zone', zone, true)"
        @zone-exit="zone => emit('zone', zone, false)"
      />
      <GraphContent
        v-else-if="mode === 'graph'"
        key="graph"
        ref="graphRef"
        :tree-data="data"
        @selection-change="v => emit('graph-selection', v)"
      />
    </Transition>

    <LiveMatchesPanel />

    <div v-if="mode === 'garden' && data" class="canvas-stage__hint-chip">
      <template v-if="inControl"><kbd>Esc</kbd> to exit</template>
      <template v-else>Press <kbd>T</kbd> to take control</template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import BrandLogo from '@/components/common/BrandLogo.vue'
import LiveMatchesPanel from '@/components/minigames/LiveMatchesPanel.vue'
import type { DashboardViewMode } from '@/composables/useDashboardViewMode'
import type { TreeData } from '@/types/dashboard'
import GraphContent from './GraphContent.vue'
import TreeContent from './TreeContent.vue'

defineProps<{
  mode: DashboardViewMode
  loading: boolean
  /** The code map narrowed to the picked repositories (graph). */
  data: TreeData | null
  /** The full code map; the garden filters by ``visibleRepos`` itself. */
  treeData: TreeData | null
  visibleRepos: string[]
  inControl: boolean
}>()

const emit = defineEmits<{
  zone: [zone: string, entered: boolean]
  'graph-selection': [selected: boolean]
}>()

const treeRef = ref<InstanceType<typeof TreeContent> | null>(null)
const graphRef = ref<InstanceType<typeof GraphContent> | null>(null)

defineExpose({
  toggleArcs: () => treeRef.value?.toggleArcs(),
  takeoverCharacter: () => treeRef.value?.takeoverCharacter(),
  exitTakeover: () => treeRef.value?.exitTakeover(),
  exitHouse: () => treeRef.value?.exitHouse(),
  isTakeover: () => treeRef.value?.isTakeover() ?? false,
  isInControl: () => treeRef.value?.isInControl() ?? false,
  backToOverview: () => graphRef.value?.backToOverview(),
})
</script>

<style scoped>
.canvas-stage {
  position: relative;
  flex: 1 1 auto;
  min-height: 420px;
  overflow: hidden;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
}
.canvas-stage__state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 24px;
  text-align: center;
}
.canvas-stage__mark {
  justify-content: center;
  margin-bottom: 8px;
  opacity: 0.6;
}
.canvas-stage__title {
  margin: 0;
  font-weight: 600;
}
.canvas-stage__hint {
  margin: 0;
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
.canvas-stage__hint a {
  color: var(--color-accent-text);
}
.canvas-stage__hint-chip {
  position: absolute;
  left: 16px;
  bottom: 16px;
  z-index: 10;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-surface));
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  pointer-events: none;
  user-select: none;
}
.canvas-stage__hint-chip kbd {
  display: inline-block;
  margin: 0 2px;
  padding: 1px 6px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 4px;
  font: 600 12px var(--font-body);
}
/* No keyboard on touch screens; the canvas shows its own takeover button. */
@media (hover: none) and (pointer: coarse) {
  .canvas-stage__hint-chip {
    display: none;
  }
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--dur-short) ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
