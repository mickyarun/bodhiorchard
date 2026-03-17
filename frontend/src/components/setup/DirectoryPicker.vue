<template>
  <v-dialog v-model="dialogOpen" max-width="600" scrollable>
    <v-card color="surface">
      <v-card-title class="d-flex align-center ga-2 py-3">
        <v-icon icon="mdi-folder-open-outline" size="20" />
        <span class="text-body-1 font-weight-medium">Select Directory</span>
      </v-card-title>

      <!-- Breadcrumb path bar -->
      <div class="px-4 pb-2">
        <div class="path-bar d-flex align-center ga-1 pa-2 rounded">
          <v-btn
            icon="mdi-home"
            size="x-small"
            variant="text"
            density="compact"
            @click="navigateTo('')"
          />
          <template v-for="(segment, i) in pathSegments" :key="i">
            <v-icon icon="mdi-chevron-right" size="14" class="text-medium-emphasis" />
            <v-btn
              variant="text"
              density="compact"
              size="x-small"
              class="text-none"
              @click="navigateTo(segment.path)"
            >
              {{ segment.name }}
            </v-btn>
          </template>
        </div>
      </div>

      <v-divider />

      <!-- Directory listing -->
      <v-card-text class="pa-0" style="height: 360px; overflow-y: auto;">
        <div v-if="loading" class="d-flex justify-center align-center h-100">
          <v-progress-circular indeterminate color="primary" size="32" />
        </div>

        <div v-else-if="error" class="d-flex flex-column justify-center align-center h-100 pa-4">
          <v-icon icon="mdi-alert-circle-outline" size="40" color="error" class="mb-2" />
          <div class="text-body-2 text-medium-emphasis text-center">{{ error }}</div>
          <v-btn variant="text" size="small" class="mt-2" @click="navigateTo(parentPath || '')">
            Go back
          </v-btn>
        </div>

        <div v-else-if="directories.length === 0" class="d-flex flex-column justify-center align-center h-100 pa-4">
          <v-icon icon="mdi-folder-off-outline" size="40" class="text-medium-emphasis mb-2" />
          <div class="text-body-2 text-medium-emphasis">No subdirectories found</div>
        </div>

        <v-list v-else density="compact" class="py-0">
          <!-- Parent directory -->
          <v-list-item
            v-if="parentPath !== null"
            :value="parentPath"
            @click="navigateTo(parentPath!)"
            class="dir-item"
          >
            <template #prepend>
              <v-icon icon="mdi-arrow-up" size="20" class="text-medium-emphasis" />
            </template>
            <v-list-item-title class="text-body-2 text-medium-emphasis">..</v-list-item-title>
          </v-list-item>

          <v-list-item
            v-for="dir in directories"
            :key="dir.path"
            :value="dir.path"
            @click="navigateTo(dir.path)"
            class="dir-item"
          >
            <template #prepend>
              <v-icon
                :icon="dir.is_git_repo ? 'mdi-source-repository' : 'mdi-folder-outline'"
                :color="dir.is_git_repo ? 'primary' : undefined"
                size="20"
              />
            </template>
            <v-list-item-title class="text-body-2">{{ dir.name }}</v-list-item-title>
            <template #append>
              <v-chip
                v-if="dir.is_git_repo"
                size="x-small"
                variant="tonal"
                color="primary"
                class="ml-2"
              >
                git
              </v-chip>
              <v-btn
                icon="mdi-check"
                size="x-small"
                variant="text"
                color="primary"
                density="compact"
                @click.stop="selectDirectory(dir.path)"
              />
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>

      <v-divider />

      <!-- Actions -->
      <v-card-actions class="px-4 py-3">
        <div class="text-caption text-medium-emphasis text-truncate flex-grow-1">
          {{ currentPath }}
        </div>
        <v-btn variant="text" size="small" @click="dialogOpen = false">Cancel</v-btn>
        <v-btn
          variant="flat"
          color="primary"
          size="small"
          @click="selectDirectory(currentPath)"
        >
          Select This Folder
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import api from '@/services/api'

interface DirectoryEntry {
  name: string
  path: string
  is_git_repo: boolean
}

const emit = defineEmits<{
  select: [path: string]
}>()

const props = defineProps<{
  initialPath?: string
}>()

const dialogOpen = ref(false)
const loading = ref(false)
const error = ref('')
const currentPath = ref('')
const parentPath = ref<string | null>(null)
const directories = ref<DirectoryEntry[]>([])

const pathSegments = computed(() => {
  if (!currentPath.value) return []
  const parts = currentPath.value.split('/').filter(Boolean)
  return parts.map((name, i) => ({
    name,
    path: '/' + parts.slice(0, i + 1).join('/'),
  }))
})

watch(dialogOpen, (open) => {
  if (open) {
    navigateTo(props.initialPath || '')
  }
})

function open(): void {
  dialogOpen.value = true
}

async function navigateTo(path: string): Promise<void> {
  loading.value = true
  error.value = ''

  try {
    const { data } = await api.get('/setup/browse-directories', {
      params: { path },
    })
    currentPath.value = data.current_path
    parentPath.value = data.parent_path
    directories.value = data.directories
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } } }
    error.value = axiosErr.response?.data?.detail || 'Failed to list directories'
  } finally {
    loading.value = false
  }
}

function selectDirectory(path: string): void {
  emit('select', path)
  dialogOpen.value = false
}

defineExpose({ open })
</script>

<style scoped>
.path-bar {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow-x: auto;
  white-space: nowrap;
}

.dir-item {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  cursor: pointer;
}

.dir-item:hover {
  background: rgba(255, 255, 255, 0.04);
}
</style>
