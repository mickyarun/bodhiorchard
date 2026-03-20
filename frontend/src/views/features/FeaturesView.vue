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

    <!-- Category chips + Search -->
    <div class="d-flex align-center ga-3 mb-5 flex-wrap">
      <v-chip-group v-model="selectedCategoryIdx" mandatory>
        <v-chip
          v-for="cat in KNOWLEDGE_CATEGORIES"
          :key="cat.value"
          variant="tonal"
          filter
        >
          {{ cat.label }}
        </v-chip>
      </v-chip-group>

      <v-spacer />

      <v-text-field
        v-model="searchQuery"
        placeholder="Semantic search..."
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 320px;"
        @click:clear="onClearSearch"
      />
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error -->
    <v-alert v-if="store.error" type="error" variant="tonal" class="mb-4" closable>
      {{ store.error }}
    </v-alert>

    <!-- Search indicator -->
    <v-progress-linear
      v-if="store.searching"
      indeterminate
      color="primary"
      class="mb-4"
    />

    <!-- Results -->
    <template v-if="!store.loading">
      <!-- Empty state -->
      <v-card
        v-if="displayItems.length === 0 && !store.searching"
        class="pa-12 text-center"
        color="surface"
      >
        <v-icon
          icon="mdi-lightbulb-off-outline"
          size="64"
          class="text-medium-emphasis mb-4"
        />
        <div class="text-h6 mb-2">No knowledge items found</div>
        <div class="text-body-2 text-medium-emphasis">
          Run a scan from Settings to index your repository.
        </div>
      </v-card>

      <!-- Item cards -->
      <div v-else class="knowledge-grid">
        <v-card
          v-for="item in displayItems"
          :key="item.id"
          class="knowledge-card pa-4 cursor-pointer"
          color="surface"
          @click="toggleExpand(item.id)"
        >
          <div class="d-flex align-center ga-2 mb-2">
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
              v-if="'score' in item"
              size="x-small"
              variant="outlined"
              color="success"
            >
              {{ ((item as KnowledgeSearchResult).score * 100).toFixed(0) }}%
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
            <div v-if="expandedId === item.id" class="mt-3">
              <v-divider class="mb-3" />
              <pre class="text-body-2 content-block">{{ item.content || 'No content' }}</pre>
            </div>
          </v-expand-transition>
        </v-card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/knowledge'
import {
  KNOWLEDGE_CATEGORIES,
  FEATURE_STATUS_COLORS,
  type KnowledgeSearchResult,
} from '@/types'

const store = useKnowledgeStore()

const selectedCategoryIdx = ref(0)
const searchQuery = ref('')
const expandedId = ref<string | null>(null)

let searchTimeout: ReturnType<typeof setTimeout> | null = null

const selectedCategory = computed(
  () => KNOWLEDGE_CATEGORIES[selectedCategoryIdx.value]?.value || '',
)

const displayItems = computed(() =>
  searchQuery.value.trim() ? store.searchResults : store.items,
)

function toggleExpand(id: string): void {
  expandedId.value = expandedId.value === id ? null : id
}

function onClearSearch(): void {
  searchQuery.value = ''
  store.fetchItems(selectedCategory.value || undefined)
}

// Debounced search
watch(searchQuery, (q) => {
  if (searchTimeout) clearTimeout(searchTimeout)
  if (!q?.trim()) {
    store.fetchItems(selectedCategory.value || undefined)
    return
  }
  searchTimeout = setTimeout(() => {
    store.searchItems(q, selectedCategory.value || undefined)
  }, 400)
})

// Category change
watch(selectedCategoryIdx, () => {
  searchQuery.value = ''
  store.fetchItems(selectedCategory.value || undefined)
})

onMounted(() => {
  store.fetchItems()
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
