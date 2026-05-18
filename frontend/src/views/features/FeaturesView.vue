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
  <div class="features-view">
    <header class="features-view__head">
      <div class="features-view__title-block">
        <h1 class="features-view__title">Features</h1>
        <p class="features-view__subtitle">
          <strong>{{ store.total }}</strong>
          {{ store.total === 1 ? 'feature' : 'features' }}
          {{ subtitleScope }}
        </p>
      </div>

      <div class="features-view__controls">
        <v-text-field
          v-model="searchQuery"
          placeholder="Search features..."
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          class="features-view__search"
          @click:clear="onClearSearch"
        />
        <v-select
          v-model="selectedRepoId"
          :items="repoOptions"
          item-title="label"
          item-value="value"
          variant="outlined"
          density="compact"
          hide-details
          label="Repository"
          class="features-view__select"
          :disabled="activeRepos.length === 0"
        />
        <v-switch
          v-model="showDeactivated"
          color="primary"
          density="compact"
          hide-details
          inset
          class="features-view__toggle"
          label="Show deactivated"
        />
      </div>
    </header>

    <v-progress-linear
      :active="store.loading"
      indeterminate
      color="primary"
      class="features-view__progress"
      height="2"
    />

    <TopContributorsPanel
      v-if="selectedRepoId"
      :contributors="contributors"
      :loading="contributorsLoading"
    />

    <div v-if="store.loading && !hasLoadedOnce" class="features-view__initial-loading">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <v-alert v-if="store.error" type="error" variant="tonal" class="mb-4" closable>
      {{ store.error }}
    </v-alert>

    <template v-if="hasLoadedOnce">
      <div
        v-if="store.items.length === 0 && !store.loading"
        class="features-view__empty"
      >
        <v-icon
          icon="mdi-feature-search-outline"
          size="56"
          class="features-view__empty-icon"
        />
        <div class="features-view__empty-title">
          {{ searchQuery.trim() ? 'No matching features' : 'No features synthesised yet' }}
        </div>
        <div class="features-view__empty-body">
          {{
            searchQuery.trim()
              ? 'Try a different search term.'
              : 'Run a scan from Settings to index your repositories.'
          }}
        </div>
      </div>

      <div v-else class="features-view__grid">
        <FeatureCard v-for="feature in store.items" :key="feature.id" :feature="feature" />
      </div>

      <div v-if="pageCount > 1" class="features-view__pagination">
        <v-pagination
          v-model="page"
          :length="pageCount"
          :total-visible="7"
          density="comfortable"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { PAGE_SIZE, useFeaturesStore } from '@/stores/features'
import { useSettingsStore } from '@/stores/settings'
import type { RepoContributor, RepoInfo } from '@/types'
import FeatureCard from '@/components/features/FeatureCard.vue'
import TopContributorsPanel from '@/components/features/TopContributorsPanel.vue'

const store = useFeaturesStore()
const settingsStore = useSettingsStore()

const selectedRepoId = ref('')
const searchQuery = ref('')
const debouncedQuery = ref('')
const page = ref(1)
const hasLoadedOnce = ref(false)
// Off by default — the Features tab is normally a "what exists today"
// surface. Operators flip this on to audit what was removed and by
// whom; the toggle drives both the API filter and per-card styling.
const showDeactivated = ref(false)

let searchTimeout: ReturnType<typeof setTimeout> | null = null

const activeRepos = computed<RepoInfo[]>(() =>
  settingsStore.repos.filter((r) => r.status !== 'removed'),
)

const repoOptions = computed(() => [
  { label: 'All repos', value: '' },
  ...activeRepos.value.map((r) => ({ label: r.name, value: r.id })),
])

const pageCount = computed(() => Math.max(1, Math.ceil(store.total / PAGE_SIZE)))

// Header subtitle scopes the count to the active filter so a user
// drilling into one repo doesn't see "12 features across 7 repos".
const subtitleScope = computed(() => {
  const repoLabel = repoOptions.value.find((o) => o.value === selectedRepoId.value)?.label
  if (selectedRepoId.value && repoLabel) return `in ${repoLabel}`
  if (debouncedQuery.value) return `matching "${debouncedQuery.value}"`
  const n = activeRepos.value.length
  return `across ${n} ${n === 1 ? 'repo' : 'repos'}`
})

const contributors = computed<RepoContributor[]>(
  () => store.contributorsByRepo[selectedRepoId.value] ?? [],
)
const contributorsLoading = computed(
  () => !!selectedRepoId.value && !(selectedRepoId.value in store.contributorsByRepo),
)

async function reload(): Promise<void> {
  await store.fetchPage({
    page: page.value,
    repoId: selectedRepoId.value || undefined,
    q: debouncedQuery.value || undefined,
    includeInactive: showDeactivated.value,
  })
  if (selectedRepoId.value) {
    void store.fetchTopContributors(selectedRepoId.value)
  }
  hasLoadedOnce.value = true
}

function onClearSearch(): void {
  searchQuery.value = ''
}

watch(searchQuery, (q) => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    debouncedQuery.value = q.trim()
  }, 300)
})

// Filter changes reset to page 1; the page watcher fires the reload.
watch([selectedRepoId, debouncedQuery, showDeactivated], () => {
  if (page.value === 1) {
    void reload()
  } else {
    page.value = 1
  }
})

watch(page, () => {
  void reload()
})

onMounted(() => {
  void settingsStore.fetchRepos()
  void reload()
})
</script>

<style scoped>
.features-view {
  padding: 24px 28px 40px;
}

.features-view__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}
.features-view__title-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.features-view__title {
  margin: 0;
  font-size: 1.625rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.95);
  letter-spacing: -0.01em;
}
.features-view__subtitle {
  margin: 0;
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.55);
}
.features-view__subtitle strong {
  color: rgba(255, 255, 255, 0.85);
  font-weight: 600;
}

.features-view__controls {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
.features-view__search {
  min-width: 280px;
}
.features-view__select {
  min-width: 200px;
}
.features-view__toggle {
  /* Vuetify's v-switch has aggressive default margin/padding that
     ruin the rest of the header — strip them so the switch lines up
     with the other compact inputs. */
  margin: 0;
  flex: 0 0 auto;
  font-size: 0.85rem;
}
:deep(.features-view__toggle .v-label) {
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.7);
}

.features-view__progress {
  margin-bottom: 16px;
}

.features-view__initial-loading {
  display: flex;
  justify-content: center;
  padding: 56px 0;
}

.features-view__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 14px;
  align-content: start;
}

.features-view__pagination {
  display: flex;
  justify-content: center;
  margin-top: 28px;
}

.features-view__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 64px 24px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.015);
  border: 1px solid rgba(255, 255, 255, 0.06);
  text-align: center;
}
.features-view__empty-icon {
  color: rgba(255, 255, 255, 0.25);
  margin-bottom: 8px;
}
.features-view__empty-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.85);
}
.features-view__empty-body {
  font-size: 0.875rem;
  color: rgba(255, 255, 255, 0.5);
}
</style>
