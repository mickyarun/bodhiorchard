<template>
  <v-card
    class="graph-detail-panel"
    elevation="8"
  >
    <v-card-title class="d-flex align-center justify-space-between pa-4">
      <span class="text-h6 text-truncate">
        {{ panelTitle }}
      </span>
      <v-btn icon="mdi-close" variant="text" size="small" @click="emit('close')" />
    </v-card-title>

    <v-divider />

    <!-- Repo detail -->
    <template v-if="repo">
      <v-card-text class="pa-4">
        <div class="d-flex align-center ga-2 mb-3">
          <v-chip :color="healthColor(repo.health)" size="small" label>
            {{ repo.health }}
          </v-chip>
          <v-chip variant="outlined" size="small" label>
            {{ repo.growthStage }}
          </v-chip>
        </div>

        <div class="text-body-2 mb-3">
          <div class="d-flex justify-space-between mb-1">
            <span class="text-medium-emphasis">Files</span>
            <span>{{ repo.totalFiles.toLocaleString() }}</span>
          </div>
          <div class="d-flex justify-space-between">
            <span class="text-medium-emphasis">Commits</span>
            <span>{{ repo.totalCommits.toLocaleString() }}</span>
          </div>
        </div>

        <template v-if="repoFeatureCounts">
          <div class="text-subtitle-2 mb-2">Features</div>
          <div class="d-flex ga-2 flex-wrap">
            <v-chip
              v-for="(count, status) in repoFeatureCounts"
              :key="status"
              :color="statusColor(status as string)"
              size="small"
              label
            >
              {{ status }}: {{ count }}
            </v-chip>
          </div>
        </template>
      </v-card-text>
    </template>

    <!-- Feature detail -->
    <template v-if="feature">
      <v-card-text class="pa-4">
        <div class="d-flex align-center ga-2 mb-3">
          <v-chip :color="statusColor(feature.status)" size="small" label>
            {{ feature.status.replace('_', ' ') }}
          </v-chip>
          <span v-if="feature.repoName" class="text-body-2 text-medium-emphasis">
            {{ feature.repoName }}
          </span>
        </div>

        <div v-if="feature.sourceRef" class="text-body-2 text-medium-emphasis mb-3">
          Source: {{ feature.sourceRef }}
        </div>

        <div v-if="feature.fromBud" class="mb-3">
          <v-chip
            size="small"
            color="success"
            variant="outlined"
            prepend-icon="mdi-seed-outline"
          >
            From BUD #{{ feature.fromBud }}
          </v-chip>
        </div>

        <!-- Skilled Members -->
        <template v-if="members.length > 0">
          <div class="text-subtitle-2 mb-2 mt-4">Skilled Team Members</div>
          <v-list density="compact" class="pa-0">
            <v-list-item
              v-for="member in members"
              :key="member.user_id"
              class="px-0"
            >
              <template #prepend>
                <v-avatar size="28" color="primary" variant="tonal" class="mr-2">
                  <span class="text-caption">{{ initials(member.name) }}</span>
                </v-avatar>
              </template>
              <v-list-item-title class="text-body-2">
                {{ member.name }}
              </v-list-item-title>
              <v-list-item-subtitle class="text-caption">
                {{ member.matchingModules.join(', ') }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </template>
        <div v-else class="text-body-2 text-medium-emphasis mt-4">
          No matching skill profiles found.
        </div>
      </v-card-text>
    </template>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { GraphRepoInfo, GraphFeatureInfo } from '@/engine/graph'
import type { TreeData } from '@/types/dashboard'

interface SkilledMember {
  user_id: string
  name: string
  matchingModules: string[]
}

const props = defineProps<{
  repo: GraphRepoInfo | null
  feature: GraphFeatureInfo | null
  treeData: TreeData | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const panelTitle = computed(() => {
  if (props.repo) return props.repo.repoName
  if (props.feature) return props.feature.title
  return ''
})

function healthColor(health: string): string {
  const map: Record<string, string> = {
    thriving: 'success', healthy: 'info', dormant: 'grey', wilted: 'warning',
  }
  return map[health] ?? 'grey'
}

function statusColor(status: string): string {
  const map: Record<string, string> = {
    planned: 'blue', in_progress: 'orange', implemented: 'green',
  }
  return map[status] ?? 'grey'
}

function initials(name: string): string {
  if (!name.trim()) return '?'
  return name.split(' ').filter(w => w.length > 0).map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

const repoFeatureCounts = computed(() => {
  if (!props.repo || !props.treeData) return null
  const counts: Record<string, number> = {}
  for (const f of props.treeData.features) {
    if (f.repo_name === props.repo.repoName) {
      counts[f.status] = (counts[f.status] || 0) + 1
    }
  }
  return Object.keys(counts).length > 0 ? counts : null
})

/** Match members whose top_modules overlap with the feature's branch_name or title. */
const members = computed<SkilledMember[]>(() => {
  if (!props.feature || !props.treeData) return []

  const featureBranch = props.feature.branchName?.toLowerCase() ?? ''
  const featureTitle = props.feature.title.toLowerCase()
  const featureRepo = props.feature.repoName?.toLowerCase() ?? ''

  const result: SkilledMember[] = []

  for (const m of props.treeData.members) {
    const matchingModules: string[] = []

    for (const mod of m.top_modules) {
      const modLower = mod.toLowerCase()
      if (
        (featureBranch && modLower.includes(featureBranch)) ||
        (featureBranch && featureBranch.includes(modLower)) ||
        modLower.includes(featureTitle) ||
        featureTitle.includes(modLower) ||
        (featureRepo && modLower.includes(featureRepo))
      ) {
        matchingModules.push(mod)
      }
    }

    if (matchingModules.length > 0) {
      result.push({
        user_id: m.user_id,
        name: m.name,
        matchingModules,
      })
    }
  }

  return result
})
</script>

<style scoped>
.graph-detail-panel {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 340px;
  max-height: calc(100% - 32px);
  overflow-y: auto;
  z-index: 20;
  background: rgba(var(--v-theme-surface), 0.95);
  backdrop-filter: blur(8px);
}
</style>
