<template>
  <div
    ref="containerRef"
    class="graph-canvas"
  >
    <div
      v-if="initError"
      class="graph-canvas__error"
    >
      {{ initError }}
    </div>
    <div
      v-if="tooltipText"
      class="graph-canvas__tooltip"
      :style="{ left: tooltipPos.x + 'px', top: tooltipPos.y + 'px' }"
    >
      {{ tooltipText }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { TreeData } from '@/types/dashboard'
import type { EngineData, EngineFeatureSkill, RepoHealth, ThreatSeverity, BUDStatus, RelType } from '@/engine/types'
import { GraphEngine } from '@/engine/graph'
import type { GraphRepoInfo, GraphFeatureInfo } from '@/engine/graph'

const props = defineProps<{
  treeData: TreeData | null
}>()

const emit = defineEmits<{
  (e: 'repo-click', info: GraphRepoInfo): void
  (e: 'feature-click', info: GraphFeatureInfo): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const tooltipText = ref<string | null>(null)
const tooltipPos = ref({ x: 0, y: 0 })
const initError = ref<string | null>(null)

let engine: GraphEngine | null = null
let resizeObserver: ResizeObserver | null = null
let resizeTimer: ReturnType<typeof setTimeout> | null = null

/** Adapt TreeData (app type) to EngineData (engine type). */
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
      linked_repos: f.linked_repos ?? [],
      code_locations: f.code_locations ?? null,
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
    feature_skills: (data.feature_skills ?? []).map((s): EngineFeatureSkill => ({
      feature_title: s.feature_title,
      developer_count: s.developer_count,
      developers: s.developers,
      top_developer_name: s.top_developer_name ?? null,
    })),
  }
}

async function initEngine(): Promise<void> {
  if (!containerRef.value) return

  if (engine) {
    engine.destroy()
    engine = null
  }

  const w = containerRef.value.clientWidth || 1200
  const h = containerRef.value.clientHeight || 800

  engine = new GraphEngine()
  await engine.init(containerRef.value, w, h, {
    onRepoClick: (info) => emit('repo-click', info),
    onFeatureClick: (info) => emit('feature-click', info),
    onHover: (tip) => {
      if (tip) {
        tooltipText.value = tip.text
        tooltipPos.value = { x: tip.screenX + 12, y: tip.screenY - 20 }
      } else {
        tooltipText.value = null
      }
    },
  })

  if (props.treeData) {
    await engine.setData(adaptTreeData(props.treeData))
  }
}

function onResize(): void {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (!engine || !containerRef.value) return
    engine.resize(containerRef.value.clientWidth, containerRef.value.clientHeight)
  }, 200)
}

onMounted(async () => {
  try {
    await initEngine()
  } catch (err) {
    console.error('[GraphCanvas] Failed to initialize graph engine:', err)
    initError.value = 'Failed to load 3D graph. Please refresh the page.'
  }

  if (containerRef.value) {
    resizeObserver = new ResizeObserver(onResize)
    resizeObserver.observe(containerRef.value)
  }
})

// Shallow watch — only triggers when the treeData reference changes (not nested mutations)
let dataUpdateTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => props.treeData,
  (newData) => {
    if (!engine || !newData) return
    // Debounce to avoid rapid rebuilds
    if (dataUpdateTimer) clearTimeout(dataUpdateTimer)
    dataUpdateTimer = setTimeout(async () => {
      try {
        await engine!.setData(adaptTreeData(newData))
      } catch (err) {
        console.error('[GraphCanvas] Failed to update graph data:', err)
      }
    }, 300)
  },
)

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (resizeTimer) clearTimeout(resizeTimer)
  if (dataUpdateTimer) clearTimeout(dataUpdateTimer)
  if (engine) {
    engine.destroy()
    engine = null
  }
})

/** Expose engine methods to parent for camera control and overlays. */
defineExpose({
  focusOnRepo(repoName: string) {
    engine?.focusOnNode(`repo_${repoName}`)
  },
  resetView() {
    engine?.resetView()
  },
  setCrossRepoLinksVisible(visible: boolean) {
    engine?.setCrossRepoLinksVisible(visible)
  },
  setBusFactorVisible(visible: boolean) {
    engine?.setBusFactorVisible(visible)
  },
  highlightDeveloper(userId: string) {
    engine?.highlightDeveloper(userId)
  },
  clearHighlight() {
    engine?.clearHighlight()
  },
  setStatusOverlay(active: boolean) {
    engine?.setStatusOverlay(active)
  },
  setThreatOverlay(active: boolean) {
    engine?.setThreatOverlay(active)
  },
  filterByDeveloper(userId: string | null) {
    engine?.filterByDeveloper(userId)
  },
  setBudBadgesVisible(visible: boolean) {
    engine?.setBudBadgesVisible(visible)
  },
})
</script>

<style scoped>
.graph-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 400px;
}

.graph-canvas :deep(canvas) {
  display: block;
}

.graph-canvas__error {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #ef5350;
  font-size: 14px;
  text-align: center;
  z-index: 10;
}

.graph-canvas__tooltip {
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
