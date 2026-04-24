<template>
  <div class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="text-h5 font-weight-bold">Features &amp; Knowledge</div>
        <div class="text-body-2 text-medium-emphasis">
          Browse scanned knowledge items, features, and code documentation
        </div>
      </div>
    </div>

    <!-- Repo filter + Search -->
    <div class="d-flex align-center ga-3 mb-5 flex-wrap">
      <v-spacer />

      <v-select
        v-if="repos.length > 1"
        v-model="selectedRepoId"
        :items="repoOptions"
        item-title="label"
        item-value="value"
        variant="outlined"
        density="compact"
        hide-details
        style="max-width: 200px;"
        label="Repository"
      />

      <v-text-field
        v-model="searchQuery"
        placeholder="Search by title..."
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 320px;"
        @click:clear="onClearSearch"
      />
    </div>

    <!-- Loading indicator (keeps grid visible to avoid flash) -->
    <v-progress-linear
      :active="store.loading"
      indeterminate
      color="primary"
      class="mb-2"
      height="2"
    />

    <!-- Initial loading spinner (first load only, before any items) -->
    <div v-if="store.loading && !hasLoadedOnce" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error -->
    <v-alert v-if="store.error" type="error" variant="tonal" class="mb-4" closable>
      {{ store.error }}
    </v-alert>

    <!-- Results -->
    <template v-if="hasLoadedOnce">
      <!-- Empty state -->
      <v-card
        v-if="store.items.length === 0 && !store.loading"
        class="pa-12 text-center"
        color="surface"
      >
        <v-icon
          icon="mdi-lightbulb-off-outline"
          size="64"
          class="text-medium-emphasis mb-4"
        />
        <div class="text-h6 mb-2">
          {{ searchQuery.trim() ? 'No matching knowledge items' : 'No knowledge items found' }}
        </div>
        <div class="text-body-2 text-medium-emphasis">
          {{
            searchQuery.trim()
              ? 'Try a different search term.'
              : 'Run a scan from Settings to index your repository.'
          }}
        </div>
      </v-card>

      <!-- Item cards -->
      <div v-else class="knowledge-grid">
        <v-card
          v-for="item in store.items"
          :key="item.id"
          class="knowledge-card pa-4 cursor-pointer"
          color="surface"
          @click="toggleExpand(item.id)"
        >
          <div class="d-flex align-center ga-2 mb-2 flex-wrap">
            <v-chip size="x-small" variant="tonal" color="primary" label>
              {{ item.category }}
            </v-chip>
            <v-chip
              v-if="item.featureStatus"
              size="x-small"
              variant="flat"
              :color="FEATURE_STATUS_COLORS[item.featureStatus] || 'grey'"
              label
            >
              {{ item.featureStatus }}
            </v-chip>
            <v-chip
              v-for="name in getRepoNames(item)"
              :key="name"
              size="x-small"
              variant="tonal"
              color="cyan"
              label
              prepend-icon="mdi-source-repository"
            >
              {{ name }}
            </v-chip>
          </div>

          <div class="text-body-2 font-weight-medium mb-1">{{ item.title }}</div>

          <div
            v-if="item.source || item.sourceRef"
            class="text-caption text-medium-emphasis mb-2"
          >
            {{ item.source }}{{ item.sourceRef ? ` · ${item.sourceRef}` : '' }}
          </div>

          <!-- Tags -->
          <div v-if="item.tags?.length" class="d-flex ga-1 flex-wrap mb-2">
            <v-chip
              v-for="tag in item.tags.slice(0, 5)"
              :key="tag"
              size="x-small"
              variant="outlined"
            >
              {{ tag }}
            </v-chip>
          </div>

          <!-- Expanded content -->
          <v-expand-transition>
            <div v-if="expandedRow === getRowIndex(item.id)" class="mt-3">
              <v-divider class="mb-3" />
              <pre class="text-body-2 content-block">{{ item.content || 'No content' }}</pre>
            </div>
          </v-expand-transition>
        </v-card>
      </div>

      <!-- Pagination -->
      <div v-if="pageCount > 1" class="d-flex justify-center mt-6">
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
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useKnowledgeStore, PAGE_SIZE } from '@/stores/knowledge'
import { useSettingsStore } from '@/stores/settings'
import {
  FEATURE_STATUS_COLORS,
  type KnowledgeItem,
  type RepoInfo,
} from '@/types'

const store = useKnowledgeStore()
const settingsStore = useSettingsStore()

const selectedRepoId = ref('')
const searchQuery = ref('')
const page = ref(1)
const expandedRow = ref<number | null>(null)
const columnsPerRow = ref(3)
const hasLoadedOnce = ref(false)

let searchTimeout: ReturnType<typeof setTimeout> | null = null

const repos = computed<RepoInfo[]>(() =>
  settingsStore.repos.filter((r) => r.status !== 'removed'),
)

const repoOptions = computed(() => [
  { label: 'All repos', value: '' },
  ...repos.value.map((r) => ({ label: r.name, value: r.id })),
])

const pageCount = computed(() => Math.max(1, Math.ceil(store.total / PAGE_SIZE)))

async function reload(): Promise<void> {
  await store.fetchItems({
    page: page.value,
    repoId: selectedRepoId.value || undefined,
    q: searchQuery.value.trim() || undefined,
  })
  hasLoadedOnce.value = true
}

// ─── Repo name resolution ─────────────────────
const repoMap = computed(() => {
  const map = new Map<string, string>()
  for (const r of repos.value) map.set(r.id, r.name)
  return map
})

function getRepoNames(item: KnowledgeItem): string[] {
  if (!item.repoIds?.length) return []
  return item.repoIds.map(id => repoMap.value.get(id) ?? '').filter(Boolean)
}

// ─── Row-expand logic ─────────────────────────
function getRowIndex(id: string): number {
  const idx = store.items.findIndex(i => i.id === id)
  return Math.floor(idx / columnsPerRow.value)
}

function toggleExpand(id: string): void {
  const row = getRowIndex(id)
  expandedRow.value = expandedRow.value === row ? null : row
}

function updateColumns(): void {
  const grid = document.querySelector('.knowledge-grid') as HTMLElement | null
  if (grid) {
    columnsPerRow.value = getComputedStyle(grid)
      .gridTemplateColumns.split(' ').length
  }
}

let resizeObserver: ResizeObserver | null = null

function onClearSearch(): void {
  searchQuery.value = ''
}

// Debounce the search query; any filter change (including the debounced query)
// resets to page 1 via a single watcher, and only one reload fires per change.
const debouncedQuery = ref('')

watch(searchQuery, (q) => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    debouncedQuery.value = q.trim()
  }, 300)
})

// Filter change (repo or debounced query) → page 1; reload via page watcher
// when that changes state, or directly when we were already on page 1.
watch([selectedRepoId, debouncedQuery], () => {
  expandedRow.value = null
  if (page.value === 1) {
    reload()
  } else {
    page.value = 1
  }
})

watch(page, () => {
  expandedRow.value = null
  reload()
})

onMounted(() => {
  settingsStore.fetchRepos()
  reload()

  // Track actual CSS grid column count for row-expand
  requestAnimationFrame(() => {
    const grid = document.querySelector('.knowledge-grid') as HTMLElement | null
    if (grid) {
      updateColumns()
      resizeObserver = new ResizeObserver(updateColumns)
      resizeObserver.observe(grid)
    }
  })
})

onUnmounted(() => {
  resizeObserver?.disconnect()
})
</script>

<style scoped>
.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 12px;
}

.knowledge-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.15s ease;
}

.knowledge-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
}

.content-block {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.03);
  padding: 12px;
  border-radius: 8px;
  font-family: inherit;
}
</style>
