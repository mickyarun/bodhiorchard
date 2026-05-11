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
  <v-dialog v-model="dialogOpen" max-width="600" scrollable>
    <v-card color="surface">
      <v-card-title class="d-flex align-center ga-2 py-3">
        <v-icon icon="mdi-folder-open-outline" size="20" />
        <span class="text-body-1 font-weight-medium">Select Repositories</span>
        <v-spacer />
        <v-chip
          v-if="selectedPaths.size > 0"
          size="small"
          variant="tonal"
          color="primary"
        >
          {{ selectedPaths.size }} selected
        </v-chip>
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

      <!-- Selected repos chips -->
      <div v-if="selectedPaths.size > 0" class="px-4 pb-2">
        <div class="d-flex ga-1 flex-wrap">
          <v-chip
            v-for="p in selectedPaths"
            :key="p"
            closable
            size="small"
            variant="tonal"
            color="primary"
            @click:close="selectedPaths.delete(p); triggerReactivity()"
          >
            <v-icon icon="mdi-source-repository" size="14" start />
            {{ p.split('/').pop() }}
            <v-tooltip activator="parent" location="top" :text="p" />
          </v-chip>
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
            class="dir-item"
            @click="navigateTo(parentPath!)"
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
            class="dir-item"
            @click="dir.is_git_repo ? toggleRepo(dir.path) : navigateTo(dir.path)"
          >
            <template #prepend>
              <!-- Checkbox for git repos, folder icon for regular dirs -->
              <v-checkbox-btn
                v-if="dir.is_git_repo"
                :model-value="selectedPaths.has(dir.path)"
                color="primary"
                density="compact"
                class="me-1"
                @click.stop
                @update:model-value="toggleRepo(dir.path)"
              />
              <v-icon
                v-else
                icon="mdi-folder-outline"
                size="20"
                class="me-1"
              />
              <v-icon
                :icon="dir.is_git_repo ? 'mdi-source-repository' : ''"
                :color="dir.is_git_repo ? 'primary' : undefined"
                size="20"
                :class="{ 'invisible': !dir.is_git_repo }"
              />
            </template>
            <v-list-item-title class="text-body-2">
              {{ dir.name }}
              <span v-if="dir.is_git_repo && dir.has_sub_repos" class="text-caption text-medium-emphasis ml-1">
                (contains repos)
              </span>
            </v-list-item-title>
            <v-list-item-subtitle v-if="dir.is_git_repo" class="text-caption">
              Git repository
            </v-list-item-subtitle>
            <template #append>
              <v-chip
                v-if="dir.has_sub_repos"
                size="x-small"
                variant="tonal"
                color="warning"
                class="mr-2"
              >
                monorepo
              </v-chip>
              <div
                class="browse-icon d-flex align-center"
                title="Browse inside"
                @click.stop="navigateTo(dir.path)"
              >
                <v-icon icon="mdi-chevron-right" size="20" />
              </div>
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
          v-if="!multiSelect"
          variant="flat"
          color="primary"
          size="small"
          @click="selectSingleAndClose(currentPath)"
        >
          Select This Folder
        </v-btn>
        <v-btn
          v-else
          variant="flat"
          color="primary"
          size="small"
          :disabled="selectedPaths.size === 0"
          @click="confirmMultiSelect"
        >
          Add {{ selectedPaths.size }} Repo{{ selectedPaths.size !== 1 ? 's' : '' }}
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
  has_sub_repos: boolean
}

const emit = defineEmits<{
  select: [path: string]
  'select-multiple': [paths: string[]]
}>()

const props = withDefaults(defineProps<{
  initialPath?: string
  multiSelect?: boolean
}>(), {
  multiSelect: false,
})

const dialogOpen = ref(false)
const loading = ref(false)
const error = ref('')
const currentPath = ref('')
const parentPath = ref<string | null>(null)
const directories = ref<DirectoryEntry[]>([])
const selectedPaths = ref<Set<string>>(new Set())
// Reactive trigger for Set mutations
const reactivityKey = ref(0)

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
    selectedPaths.value = new Set()
    navigateTo(props.initialPath || '')
  }
})

function triggerReactivity(): void {
  reactivityKey.value++
}

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

function toggleRepo(path: string): void {
  if (selectedPaths.value.has(path)) {
    selectedPaths.value.delete(path)
  } else {
    selectedPaths.value.add(path)
  }
  triggerReactivity()
}

function selectSingleAndClose(path: string): void {
  emit('select', path)
  dialogOpen.value = false
}

function confirmMultiSelect(): void {
  const paths = [...selectedPaths.value]
  if (paths.length === 1) {
    emit('select', paths[0])
  } else {
    emit('select-multiple', paths)
  }
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

.invisible {
  visibility: hidden;
  width: 0;
  margin: 0;
}

.browse-icon {
  cursor: pointer;
  opacity: 0.5;
  transition: opacity 0.15s;
  padding: 4px;
  border-radius: 4px;
}

.browse-icon:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.1);
}
</style>
