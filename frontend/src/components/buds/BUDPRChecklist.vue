<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import type { PRChecklistItem } from '@/types'
import { useBUDStore } from '@/stores/bud'

const props = defineProps<{ budId: string }>()

const budStore = useBUDStore()
const items = ref<PRChecklistItem[]>([])
const loading = ref(false)

async function loadChecklist() {
  loading.value = true
  items.value = await budStore.fetchPRChecklist(props.budId)
  loading.value = false
}

onMounted(loadChecklist)
watch(() => props.budId, loadChecklist)

function statusIcon(status: string) {
  switch (status) {
    case 'merged': return 'mdi-check-circle'
    case 'open': return 'mdi-source-pull'
    case 'no_pr': return 'mdi-circle-outline'
    default: return 'mdi-circle-outline'
  }
}

function statusColor(status: string) {
  switch (status) {
    case 'merged': return 'success'
    case 'open': return 'info'
    case 'no_pr': return 'grey'
    default: return 'grey'
  }
}
</script>

<template>
  <v-card variant="outlined" class="mb-4" v-if="items.length > 0">
    <v-card-title class="text-subtitle-1 d-flex align-center">
      <v-icon size="small" class="mr-2">mdi-source-pull</v-icon>
      PR Merge Checklist
    </v-card-title>
    <v-list density="compact">
      <v-list-item
        v-for="item in items"
        :key="item.repo_id"
      >
        <template #prepend>
          <v-icon :color="statusColor(item.status)" size="small">
            {{ statusIcon(item.status) }}
          </v-icon>
        </template>
        <v-list-item-title class="text-body-2">
          {{ item.repo_name }}
        </v-list-item-title>
        <template #append>
          <template v-if="item.pr">
            <v-chip
              size="x-small"
              :color="statusColor(item.status)"
              variant="tonal"
              class="mr-2"
            >
              PR #{{ item.pr.github_pr_number }}
              <span class="ml-1">{{ item.status }}</span>
            </v-chip>
            <v-btn
              icon
              size="x-small"
              variant="text"
              :href="item.pr.html_url"
              target="_blank"
            >
              <v-icon size="small">mdi-open-in-new</v-icon>
            </v-btn>
          </template>
          <v-chip v-else size="x-small" color="grey" variant="tonal">
            No PR
          </v-chip>
        </template>
      </v-list-item>
    </v-list>
    <v-progress-linear v-if="loading" indeterminate color="primary" />
  </v-card>
</template>
