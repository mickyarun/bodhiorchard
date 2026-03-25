<template>
  <v-card
    class="graph-detail-panel"
    elevation="8"
    @wheel.stop
    @pointerdown.stop
    @mousedown.stop
    @click.stop
  >
    <v-card-title class="d-flex align-center justify-space-between pa-4 pb-2">
      <span class="text-h6 text-truncate" :title="panelTitle">
        {{ panelTitle }}
      </span>
      <v-btn icon="mdi-close" variant="text" size="small" @click="emit('close')" />
    </v-card-title>

    <v-divider />

    <!-- Repo detail -->
    <template v-if="repo">
      <div class="pa-4 pb-2">
        <div class="d-flex align-center ga-2 mb-2">
          <v-chip :color="healthColor(repo.health)" size="small" label>
            {{ repo.health }}
          </v-chip>
          <v-chip variant="outlined" size="small" label>
            {{ repo.growthStage }}
          </v-chip>
        </div>

        <div class="text-body-2 mb-2">
          <div class="d-flex justify-space-between mb-1">
            <span class="text-medium-emphasis">Files</span>
            <span>{{ repo.totalFiles.toLocaleString() }}</span>
          </div>
          <div class="d-flex justify-space-between">
            <span class="text-medium-emphasis">Commits</span>
            <span>{{ repo.totalCommits.toLocaleString() }}</span>
          </div>
        </div>
      </div>

      <v-divider />

      <!-- Features section with search -->
      <div class="pa-4 pt-3">
        <div class="d-flex align-center justify-space-between mb-2">
          <div class="text-subtitle-2">Features ({{ repoFeatures.length }})</div>
          <div v-if="repoFeatureCounts" class="d-flex ga-1">
            <v-chip
              v-for="(count, status) in repoFeatureCounts"
              :key="status"
              :color="statusColor(status as string)"
              size="x-small"
              label
              variant="tonal"
            >
              {{ count }}
            </v-chip>
          </div>
        </div>

        <!-- Search -->
        <v-text-field
          v-if="repoFeatures.length > 3"
          v-model="featureSearch"
          placeholder="Search features..."
          density="compact"
          variant="outlined"
          hide-details
          prepend-inner-icon="mdi-magnify"
          clearable
          class="mb-2"
        />

        <!-- Feature list -->
        <div class="feature-scroll">
          <div
            v-for="feat in filteredFeatures"
            :key="feat.title"
            class="feature-row d-flex align-center ga-2 py-2 px-2"
          >
            <div
              class="feature-dot"
              :style="{ background: statusDotColor(feat.status) }"
            />
            <div class="flex-grow-1 text-body-2 text-truncate">
              {{ feat.title }}
            </div>
            <v-chip
              :color="statusColor(feat.status)"
              size="x-small"
              label
              variant="tonal"
              class="flex-shrink-0"
            >
              {{ formatStatus(feat.status) }}
            </v-chip>
          </div>
          <div v-if="filteredFeatures.length === 0" class="text-body-2 text-medium-emphasis pa-2">
            {{ featureSearch ? 'No matching features.' : 'No features found.' }}
          </div>
        </div>
      </div>
    </template>

    <!-- Feature detail -->
    <template v-if="feature">
      <v-card-text class="pa-4">
        <div class="d-flex align-center ga-2 mb-3 flex-wrap">
          <v-chip :color="statusColor(feature.status)" size="small" label>
            {{ formatStatus(feature.status) }}
          </v-chip>
          <v-chip
            v-if="feature.linkedRepos && feature.linkedRepos.length > 1"
            size="small"
            color="cyan"
            variant="tonal"
            prepend-icon="mdi-link-variant"
          >
            {{ feature.linkedRepos.length }} repos
          </v-chip>
          <v-chip
            v-if="feature.fromBud"
            size="small"
            color="success"
            variant="outlined"
            prepend-icon="mdi-seed-outline"
          >
            BUD #{{ feature.fromBud }}
          </v-chip>
        </div>

        <!-- Linked Repos -->
        <div v-if="feature.linkedRepos && feature.linkedRepos.length > 0" class="mb-3">
          <div class="text-subtitle-2 mb-1">Repositories</div>
          <div class="d-flex ga-1 flex-wrap">
            <v-chip
              v-for="repo in feature.linkedRepos"
              :key="repo"
              size="small"
              :variant="repo === feature.repoName ? 'flat' : 'outlined'"
              :color="repo === feature.repoName ? 'primary' : undefined"
              label
              class="cursor-pointer"
              @click="emit('repo-focus', repo)"
            >
              {{ repo }}
            </v-chip>
          </div>
        </div>
        <div v-else-if="feature.repoName" class="mb-3">
          <span class="text-body-2 text-medium-emphasis">{{ feature.repoName }}</span>
        </div>

        <!-- Code Locations -->
        <div v-if="feature.codeLocations && Object.keys(feature.codeLocations).length > 0" class="mb-3">
          <div class="text-subtitle-2 mb-1">Code Locations</div>
          <div v-for="(paths, layer) in feature.codeLocations" :key="layer" class="mb-1">
            <v-chip size="x-small" label variant="tonal" class="mb-1">{{ layer }}</v-chip>
            <div
              v-for="path in paths"
              :key="path"
              class="text-caption text-medium-emphasis code-path"
            >
              {{ path }}
            </div>
          </div>
        </div>

        <div v-if="feature.sourceRef" class="text-body-2 text-medium-emphasis mb-3">
          Source: {{ feature.sourceRef }}
        </div>

        <!-- Skilled Members -->
        <template v-if="members.length > 0">
          <div class="text-subtitle-2 mb-2 mt-4">Skilled Team Members</div>
          <v-list density="compact" class="pa-0">
            <v-list-item
              v-for="member in members"
              :key="member.user_id"
              class="px-0 cursor-pointer"
              @click="emit('developer-highlight', member.user_id)"
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
import { computed, ref } from 'vue'
import type { GraphRepoInfo, GraphFeatureInfo } from '@/engine/graph'
import type { TreeData, FeatureItem } from '@/types/dashboard'

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
  (e: 'developer-highlight', userId: string): void
  (e: 'repo-focus', repoName: string): void
}>()

const featureSearch = ref('')

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

function statusDotColor(status: string): string {
  const map: Record<string, string> = {
    planned: '#42A5F5', in_progress: '#FFA726', implemented: '#66BB6A',
  }
  return map[status] ?? '#9E9E9E'
}

function formatStatus(status: string): string {
  return status.replace(/_/g, ' ')
}

function initials(name: string): string {
  if (!name.trim()) return '?'
  return name.split(' ').filter(w => w.length > 0).map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

/** All features belonging to the selected repo. */
const repoFeatures = computed<FeatureItem[]>(() => {
  if (!props.repo || !props.treeData) return []
  return props.treeData.features.filter(f => f.repo_name === props.repo!.repoName)
})

/** Features filtered by search. */
const filteredFeatures = computed<FeatureItem[]>(() => {
  const q = featureSearch.value?.toLowerCase().trim()
  if (!q) return repoFeatures.value
  return repoFeatures.value.filter(f =>
    f.title.toLowerCase().includes(q) ||
    f.status.toLowerCase().includes(q) ||
    (f.branch_name?.toLowerCase().includes(q) ?? false)
  )
})

const repoFeatureCounts = computed(() => {
  if (!props.repo || !props.treeData) return null
  const counts: Record<string, number> = {}
  for (const f of repoFeatures.value) {
    counts[f.status] = (counts[f.status] || 0) + 1
  }
  return Object.keys(counts).length > 0 ? counts : null
})

/** Find skilled developers for this feature using backend-computed feature_skills. */
const members = computed<SkilledMember[]>(() => {
  if (!props.feature || !props.treeData) return []

  // 1. Try backend-computed feature_skills (most accurate)
  const skillSummary = props.treeData.feature_skills?.find(
    s => s.feature_title === props.feature!.title
  )

  if (skillSummary && skillSummary.developers.length > 0) {
    const memberMap = new Map(props.treeData.members.map(m => [m.user_id, m]))
    return skillSummary.developers
      .map(uid => {
        const m = memberMap.get(uid)
        if (!m) return null
        return {
          user_id: uid,
          name: m.name,
          matchingModules: m.top_modules.slice(0, 3),
        }
      })
      .filter((x): x is SkilledMember => x !== null)
  }

  // 2. Fallback: fuzzy match top_modules against feature branch/title
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
  width: 360px;
  max-height: calc(100% - 32px);
  display: flex;
  flex-direction: column;
  z-index: 20;
  background: rgba(var(--v-theme-surface), 0.95);
  backdrop-filter: blur(8px);
}

.feature-scroll {
  max-height: 400px;
  overflow-y: auto;
}

.feature-row {
  border-radius: 4px;
  transition: background 0.15s ease;
}

.feature-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.code-path {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  padding-left: 8px;
  line-height: 1.6;
}

.feature-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
