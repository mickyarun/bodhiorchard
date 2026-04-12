<template>
  <v-card variant="outlined" class="pa-4">
    <div class="d-flex align-center mb-3">
      <v-icon icon="mdi-bug-outline" size="20" class="mr-2" />
      <span class="text-subtitle-2 font-weight-medium">Bugs</span>
      <v-chip v-if="bugs.length" size="x-small" variant="tonal" color="error" class="ml-2">
        {{ bugs.length }}
      </v-chip>
      <v-spacer />
      <v-btn
        variant="tonal"
        size="small"
        color="error"
        prepend-icon="mdi-bug-outline"
        @click="showCreate = true"
      >
        Report Bug
      </v-btn>
    </div>

    <div v-if="loading" class="d-flex justify-center py-4">
      <v-progress-circular indeterminate size="20" width="2" />
    </div>
    <div v-else-if="bugs.length === 0" class="text-caption text-medium-emphasis text-center py-2">
      No bugs linked to this BUD
    </div>
    <div v-else class="d-flex flex-column ga-1">
      <div
        v-for="bug in bugs"
        :key="bug.id"
        class="d-flex align-center ga-2 pa-2 rounded"
        style="border: 1px solid rgba(255,255,255,0.06); cursor: pointer"
        @click="$router.push('/bugs')"
      >
        <v-chip :color="BUG_SEVERITY_COLORS[bug.severity]" size="x-small" variant="tonal">
          {{ bug.severity }}
        </v-chip>
        <span class="text-body-2 flex-grow-1 text-truncate">{{ bug.title }}</span>
        <v-chip :color="BUG_STATUS_COLORS[bug.status]" size="x-small" variant="tonal">
          {{ bug.status }}
        </v-chip>
      </div>
    </div>

    <BugCreateDialog
      v-model="showCreate"
      :bud-id="budId"
      @created="loadBugs"
    />
  </v-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useBugsStore } from '@/stores/bugs'
import { BUG_SEVERITY_COLORS, BUG_STATUS_COLORS } from '@/types'
import type { BugListItem } from '@/types'
import BugCreateDialog from '@/views/bugs/BugCreateDialog.vue'

const props = defineProps<{
  budId: string
}>()

const bugsStore = useBugsStore()
const bugs = ref<BugListItem[]>([])
const loading = ref(false)
const showCreate = ref(false)

async function loadBugs(): Promise<void> {
  loading.value = true
  bugs.value = await bugsStore.fetchBugsForBud(props.budId)
  loading.value = false
}

onMounted(() => loadBugs())
</script>
