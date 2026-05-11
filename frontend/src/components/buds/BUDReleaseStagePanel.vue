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
  <div class="release-stage-panel pa-4">
    <!-- Loading -->
    <div v-if="loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate size="24" width="2" />
    </div>

    <!-- Open PRs targeting this stage (shown in all states) -->
    <div v-if="!loading && data.openPRs.length" class="mb-4">
      <div class="text-overline text-medium-emphasis mb-2">
        Open PR{{ data.openPRs.length > 1 ? 's' : '' }} targeting {{ stageLabel }}
      </div>
      <div class="d-flex flex-column ga-2">
        <v-card
          v-for="pr in data.openPRs"
          :key="`open-${pr.repoName}-${pr.prNumber}`"
          variant="outlined"
          class="pa-3"
          color="warning"
        >
          <div class="d-flex align-center ga-3">
            <v-icon icon="mdi-source-pull" size="20" color="warning" />
            <div class="flex-grow-1 min-w-0">
              <div class="d-flex align-center ga-2">
                <a :href="pr.htmlUrl" target="_blank" rel="noopener" class="text-decoration-none font-weight-medium text-body-2">
                  #{{ pr.prNumber }}
                </a>
                <span class="text-caption text-medium-emphasis">{{ pr.repoName }}</span>
                <v-chip size="x-small" variant="tonal" color="warning">Open</v-chip>
              </div>
              <div v-if="pr.title" class="text-caption text-medium-emphasis text-truncate">{{ pr.title }}</div>
            </div>
            <div v-if="pr.authorLogin" class="text-caption">{{ pr.authorLogin }}</div>
          </div>
        </v-card>
      </div>
    </div>

    <!-- Empty state: not yet reached this stage -->
    <div v-else-if="data.status === 'not_reached'" class="empty-state">
      <v-icon :icon="stageIcon" size="48" color="primary" class="mb-3 opacity-40" />
      <div class="text-h6 font-weight-medium mb-2">{{ emptyTitle }}</div>
      <div class="text-body-2 text-medium-emphasis mb-4" style="max-width: 480px;">
        {{ emptyHint }}
      </div>

      <!-- Impacted repos with branch config status (empty state) -->
      <div v-if="repoStatusList.length" class="mb-4" style="width: 100%; max-width: 480px;">
        <div class="text-overline text-medium-emphasis mb-2">Repos involved in this BUD</div>
        <div class="d-flex flex-column ga-2">
          <div
            v-for="repo in repoStatusList"
            :key="repo.repoName"
            class="d-flex align-center ga-2 pa-2 rounded"
            style="border: 1px solid rgba(255,255,255,0.08)"
          >
            <v-icon icon="mdi-source-repository" size="18" />
            <span class="text-body-2 flex-grow-1">{{ repo.repoName }}</span>
            <v-chip
              v-if="repo.branch"
              size="x-small"
              variant="tonal"
              color="orange"
              prepend-icon="mdi-source-branch"
            >
              {{ repo.branch }}
            </v-chip>
            <v-chip v-else size="x-small" variant="tonal" color="warning">
              No {{ stageLabel }} branch
            </v-chip>
          </div>
        </div>
      </div>

      <div v-if="!hasStageBranchConfigured" class="d-flex justify-center">
        <v-btn
          variant="tonal"
          size="small"
          prepend-icon="mdi-cog-outline"
          to="/settings"
        >
          Configure {{ stageLabel }} branch
        </v-btn>
      </div>
    </div>

    <!-- Has events -->
    <template v-else>
      <!-- Status banner -->
      <v-alert
        :color="data.status === 'passed' ? 'grey' : 'success'"
        variant="tonal"
        density="compact"
        class="mb-4"
      >
        <div class="d-flex align-center ga-2">
          <v-icon :icon="data.status === 'passed' ? 'mdi-check-all' : 'mdi-check-circle-outline'" />
          <div class="flex-grow-1">
            <div class="font-weight-medium">{{ statusBannerTitle }}</div>
            <div v-if="data.firstReachedAt" class="text-caption text-medium-emphasis">
              First reached {{ formatDate(data.firstReachedAt) }}
            </div>
          </div>
        </div>
      </v-alert>

      <!-- Impacted repos with release status -->
      <div v-if="repoStatusList.length" class="mb-5">
        <div class="text-overline text-medium-emphasis mb-2">
          Repos involved in this BUD ({{ repoStatusList.length }})
        </div>
        <div class="d-flex flex-column ga-2">
          <div
            v-for="repo in repoStatusList"
            :key="repo.repoName"
            class="d-flex align-center ga-2 pa-2 rounded"
            style="border: 1px solid rgba(255,255,255,0.08)"
          >
            <v-icon
              :icon="repo.hasReleasePR ? 'mdi-check-circle' : 'mdi-clock-outline'"
              :color="repo.hasReleasePR ? 'success' : 'warning'"
              size="18"
            />
            <span class="text-body-2 flex-grow-1">{{ repo.repoName }}</span>
            <v-chip
              v-if="repo.branch"
              size="x-small"
              variant="tonal"
              :color="repo.hasReleasePR ? 'success' : 'orange'"
              prepend-icon="mdi-source-branch"
            >
              {{ repo.branch }}
            </v-chip>
            <v-chip v-else size="x-small" variant="tonal" color="warning">
              No {{ stageLabel }} branch
            </v-chip>
            <v-chip
              size="x-small"
              variant="tonal"
              :color="repo.hasReleasePR ? 'success' : 'grey'"
            >
              {{ repo.hasReleasePR ? 'Released' : 'Pending' }}
            </v-chip>
          </div>
        </div>
      </div>

      <!-- Release PRs -->
      <div v-if="data.releasePRs.length" class="mb-5">
        <div class="text-overline text-medium-emphasis mb-2">
          Release PR{{ data.releasePRs.length > 1 ? 's' : '' }} ({{ data.releasePRs.length }})
        </div>
        <div class="d-flex flex-column ga-2">
          <v-card
            v-for="pr in data.releasePRs"
            :key="`${pr.repoName}-${pr.prNumber}`"
            variant="outlined"
            class="pa-3"
          >
            <div class="d-flex align-center ga-3">
              <v-icon icon="mdi-source-pull" size="20" color="success" />
              <div class="flex-grow-1 min-w-0">
                <div class="d-flex align-center ga-2">
                  <a
                    :href="pr.htmlUrl"
                    target="_blank"
                    rel="noopener"
                    class="text-decoration-none font-weight-medium text-body-2"
                  >
                    #{{ pr.prNumber }}
                  </a>
                  <span class="text-caption text-medium-emphasis">{{ pr.repoName }}</span>
                </div>
                <div v-if="pr.title" class="text-caption text-medium-emphasis text-truncate">
                  {{ pr.title }}
                </div>
              </div>
              <div class="text-right">
                <div v-if="pr.authorLogin" class="text-caption">{{ pr.authorLogin }}</div>
                <div v-if="pr.mergedAt" class="text-caption text-medium-emphasis">
                  {{ formatDate(pr.mergedAt) }}
                </div>
              </div>
            </div>
          </v-card>
        </div>
      </div>

      <!-- BUD-owned commits in this release -->
      <div v-if="data.commits.length" class="mb-5">
        <div class="text-overline text-medium-emphasis mb-2">
          Commits from this BUD ({{ data.commits.length }})
        </div>
        <v-list density="compact" class="pa-0" bg-color="transparent">
          <v-list-item
            v-for="commit in data.commits"
            :key="commit.sha"
            class="px-0"
          >
            <template #prepend>
              <v-icon icon="mdi-source-commit" size="16" color="primary" class="mr-2" />
            </template>
            <v-list-item-title class="text-body-2">
              <code class="text-caption mr-2">{{ commit.shortSha }}</code>
              {{ commit.message || '(no message)' }}
            </v-list-item-title>
            <v-list-item-subtitle class="text-caption">
              {{ commit.repoName }}
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </div>

      <!-- Timeline mini-feed -->
      <v-expansion-panels v-if="data.events.length" variant="accordion" class="mt-2">
        <v-expansion-panel>
          <v-expansion-panel-title class="text-body-2">
            Timeline ({{ data.events.length }} event{{ data.events.length > 1 ? 's' : '' }})
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="d-flex flex-column ga-2">
              <div
                v-for="(event, idx) in data.events"
                :key="idx"
                class="d-flex align-center ga-2 text-caption"
              >
                <v-icon :icon="stageIcon" size="14" color="primary" />
                <a
                  :href="event.htmlUrl"
                  target="_blank"
                  rel="noopener"
                  class="text-decoration-none"
                >
                  #{{ event.prNumber }}
                </a>
                <span class="text-medium-emphasis">{{ event.repoName }}</span>
                <v-spacer />
                <span class="text-medium-emphasis">{{ formatDate(event.occurredAt) }}</span>
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import api from '@/services/api'
import { formatDateTime } from '@/utils/date'
import { subscribe, unsubscribe } from '@/services/socket'
import { useSettingsStore } from '@/stores/settings'
import type { BUDReleaseStage, ReleaseStage } from '@/types'

interface ImpactedRepo {
  repo_id?: string
  repo_name: string
}

const props = defineProps<{
  budId: string
  stage: ReleaseStage
  /** Whether ANY impacted repo of this BUD has the relevant branch configured.
   *  Drives the empty-state CTA. Pass through from the parent. */
  hasStageBranchConfigured?: boolean
  /** BUD's impacted repos — shown with their branch config status. */
  impactedRepos?: ImpactedRepo[] | null
}>()

const settingsStore = useSettingsStore()

// Build a per-repo view: repo name + configured branch for this stage
const repoStatusList = computed(() => {
  const repos = props.impactedRepos ?? []
  return repos.map((r) => {
    const tracked = settingsStore.repos.find((tr) => tr.id === r.repo_id)
    const branch =
      props.stage === 'uat' ? tracked?.uatBranch : tracked?.mainBranch
    return {
      repoName: r.repo_name,
      branch: branch ?? null,
      hasReleasePR: data.value.releasePRs.some(
        (pr) => pr.repoName === r.repo_name,
      ),
    }
  })
})

const loading = ref(true)
const data = ref<BUDReleaseStage>({
  budId: props.budId,
  stage: props.stage,
  status: 'not_reached',
  firstReachedAt: null,
  releasePRs: [],
  openPRs: [],
  commits: [],
  events: [],
})

const stageLabel = computed(() => (props.stage === 'uat' ? 'UAT' : 'Production'))
const stageIcon = computed(() =>
  props.stage === 'uat' ? 'mdi-flask-outline' : 'mdi-rocket-launch-outline',
)

const emptyTitle = computed(() =>
  props.stage === 'uat' ? 'Not yet reached UAT' : 'Not yet promoted to production',
)
const emptyHint = computed(() => {
  if (props.stage === 'uat') {
    return props.hasStageBranchConfigured
      ? 'When this BUD\'s commits are merged into the UAT branch, the release PR and timestamp will appear here.'
      : 'No impacted repo has a UAT branch configured. Set one in Settings \u2192 Repositories to start tracking UAT releases.'
  }
  return props.hasStageBranchConfigured
    ? 'When this BUD\'s commits are merged into the production (main) branch, the release PR and timestamp will appear here.'
    : 'No impacted repo has a production branch configured. Set one in Settings \u2192 Repositories to start tracking prod releases.'
})

const statusBannerTitle = computed(() => {
  if (data.value.status === 'passed') {
    return `Passed ${stageLabel.value} \u2014 promoted onward`
  }
  return props.stage === 'uat' ? 'In UAT' : 'In Production'
})

const formatDate = formatDateTime

async function load(): Promise<void> {
  loading.value = true
  try {
    const { data: payload } = await api.get<BUDReleaseStage>(
      `/v1/buds/${props.budId}/release-stages/${props.stage}`,
    )
    data.value = payload
  } catch {
    // Leave the default empty state on failure \u2014 the API endpoint
    // is read-only and any error here is recoverable on next refresh.
  } finally {
    loading.value = false
  }
}

const topic = computed(() => `bud:${props.budId}:activity`)
const targetEvent = computed(() => `merged_to_${props.stage}`)

function onActivity(payload: unknown): void {
  if (typeof payload !== 'object' || payload === null) return
  const eventType = (payload as { event_type?: string }).event_type
  // Refresh on: this stage's merge events, next-stage events (for
  // in_stage \u2192 passed), and PR lifecycle events (to show open PRs).
  if (
    eventType === targetEvent.value
    || eventType === 'pr_opened'
    || eventType === 'pr_merged'
    || eventType === 'pr_closed'
    || (props.stage === 'uat' && eventType === 'merged_to_prod')
  ) {
    load()
  }
}

onMounted(() => {
  load()
  subscribe(topic.value, onActivity)
})

onUnmounted(() => {
  unsubscribe(topic.value, onActivity)
})

// Re-fetch + re-subscribe when the parent swaps budId or stage
// (BUDDetail uses the same component for both UAT and Prod tabs).
watch(
  () => [props.budId, props.stage] as const,
  ([newBud, newStage], [oldBud, oldStage]) => {
    if (newBud !== oldBud || newStage !== oldStage) {
      unsubscribe(`bud:${oldBud}:activity`, onActivity)
      load()
      subscribe(topic.value, onActivity)
    }
  },
)
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4rem 1rem;
  text-align: center;
}
.min-w-0 {
  min-width: 0;
}
</style>
