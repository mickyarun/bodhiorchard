<template>
  <div
    ref="containerRef"
    class="playcanvas-canvas"
  >
    <div
      v-if="initError"
      class="playcanvas-canvas__error"
    >
      {{ initError }}
    </div>
    <div
      v-if="tooltipText"
      class="playcanvas-canvas__tooltip"
      :style="{ left: tooltipPos.x + 'px', top: tooltipPos.y + 'px' }"
    >
      {{ tooltipText }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { TreeData } from '@/types/dashboard'
import { GardenEngine } from '@/engine/index'
import type { EngineData, RepoHealth, ThreatSeverity, BUDStatus, RelType } from '@/engine/types'

const props = defineProps<{
  treeData: TreeData
}>()

const emit = defineEmits<{
  (e: 'scene-ready'): void
  (e: 'tree-click', info: { repoName: string }): void
  (e: 'developer-click', info: { name: string; modelName: string }): void
  (e: 'house-click', info: { name: string }): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const tooltipText = ref<string | null>(null)
const tooltipPos = ref({ x: 0, y: 0 })

let engine: GardenEngine | null = null
let resizeObserver: ResizeObserver | null = null
let resizeTimer: ReturnType<typeof setTimeout> | null = null

/**
 * Adapt TreeData (app type) to EngineData (engine type).
 * This adapter is the only place app types touch engine types.
 */
function adaptTreeData(data: TreeData): EngineData {
  return {
    repos: data.repos.map(r => ({
      repo_name: r.repo_name,
      repo_path: r.repo_path,
      branches: r.branches.map(b => ({
        name: b.name,
        file_count: b.file_count,
        commit_count: b.commit_count,
        health: b.health as RepoHealth,
        bug_count: b.bug_count,
        leaves: b.leaves.map(l => ({
          path: l.path,
          age_days: l.age_days,
          color: l.color,
          branch_name: l.branch_name,
          has_bug: l.has_bug,
        })),
      })),
      total_files: r.total_files,
      total_commits: r.total_commits,
      health: r.health as RepoHealth,
      growth_stage: r.growth_stage,
    })),
    features: data.features.map(f => ({
      title: f.title,
      status: f.status,
      source_ref: f.source_ref,
      branch_name: f.branch_name,
      repo_name: f.repo_name,
      from_bud: f.from_bud,
    })),
    buds: data.buds.map(b => ({
      bud_number: b.bud_number,
      title: b.title,
      status: b.status as BUDStatus,
      branch_name: b.branch_name,
      repo_name: b.repo_name,
    })),
    threats: data.threats.map(t => ({
      id: t.id,
      title: t.title,
      severity: t.severity as ThreatSeverity,
      module: t.module,
      branch_name: t.branch_name,
    })),
    members: data.members.map(m => ({
      user_id: m.user_id,
      name: m.name,
      email: m.email,
      avatar_url: m.avatar_url,
      care_pct: m.care_pct,
      top_modules: m.top_modules,
      character_model: m.character_model,
      presence: m.presence,
    })),
    agent_activity: data.agent_activity.map(a => ({
      agent_name: a.agent_name,
      action: a.action,
      timestamp: a.timestamp,
      status: a.status,
    })),
    relationships: (data.relationships ?? []).map(r => ({
      source_branch: r.source_branch,
      target_branch: r.target_branch,
      source_repo: r.source_repo,
      target_repo: r.target_repo,
      rel_type: r.rel_type as RelType,
      weight: r.weight,
    })),
    feature_skills: (data.feature_skills ?? []).map(s => ({
      feature_title: s.feature_title,
      developer_count: s.developer_count,
      developers: s.developers,
      top_developer_name: s.top_developer_name ?? null,
    })),
  }
}

async function initEngine(): Promise<void> {
  if (!containerRef.value) return

  // Clean up previous engine
  if (engine) {
    engine.destroy()
    engine = null
  }

  const w = containerRef.value.clientWidth || 1200
  const h = containerRef.value.clientHeight || 800

  engine = new GardenEngine()
  await engine.init(containerRef.value, w, h, {
    onSceneReady: () => emit('scene-ready'),
    onTreeClick: (info) => emit('tree-click', { repoName: info.repoName }),
    onDeveloperClick: (info) => emit('developer-click', {
      name: info.name,
      modelName: info.modelName,
    }),
    onHouseClick: (info) => emit('house-click', { name: info.name }),
    onHover: (tip) => {
      if (tip) {
        tooltipText.value = tip.text
        tooltipPos.value = { x: tip.screenX + 12, y: tip.screenY - 20 }
      } else {
        tooltipText.value = null
      }
    },
  })

  await engine.setData(adaptTreeData(props.treeData))
}

function onResize(): void {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (!engine || !containerRef.value) return
    const w = containerRef.value.clientWidth
    const h = containerRef.value.clientHeight
    engine.resize(w, h)
  }, 200)
}

const initError = ref<string | null>(null)

onMounted(async () => {
  try {
    await initEngine()
  } catch (err) {
    console.error('[PlayCanvasCanvas] Failed to initialize 3D engine:', err)
    initError.value = 'Failed to load 3D scene. Please refresh the page.'
  }

  if (containerRef.value) {
    resizeObserver = new ResizeObserver(onResize)
    resizeObserver.observe(containerRef.value)
  }
})

watch(
  () => props.treeData,
  async () => {
    if (engine) {
      try {
        await engine.setData(adaptTreeData(props.treeData))
      } catch (err) {
        console.error('[PlayCanvasCanvas] Failed to update scene data:', err)
      }
    }
  },
  { deep: true },
)

/** Toggle relationship arc visibility. */
function toggleArcs(): boolean {
  return engine?.toggleArcs() ?? false
}

defineExpose({ toggleArcs })

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (resizeTimer) {
    clearTimeout(resizeTimer)
  }
  if (engine) {
    engine.destroy()
    engine = null
  }
})
</script>

<style scoped>
.playcanvas-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 400px;
}

.playcanvas-canvas :deep(canvas) {
  display: block;
}

.playcanvas-canvas__error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #ef5350;
  font-size: 14px;
  text-align: center;
  z-index: 10;
}

.playcanvas-canvas__tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  white-space: pre-line;
  z-index: 10;
  max-width: 250px;
}
</style>
