<template>
  <div class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="text-h5 font-weight-bold">Skill Profiles</div>
        <div class="text-body-2 text-medium-emphasis">
          Developer expertise extracted from git history
        </div>
      </div>
      <div class="d-flex align-center ga-2">
        <v-chip variant="tonal" color="primary" size="small" prepend-icon="mdi-account-group-outline">
          {{ store.profiles.length }} developer{{ store.profiles.length !== 1 ? 's' : '' }}
        </v-chip>
        <v-chip variant="tonal" color="secondary" size="small" prepend-icon="mdi-cube-outline">
          {{ totalModules }} module{{ totalModules !== 1 ? 's' : '' }}
        </v-chip>
      </div>
    </div>

    <!-- Search + View toggle -->
    <div class="d-flex align-center ga-3 mb-5">
      <v-text-field
        v-model="search"
        placeholder="Filter by developer or module..."
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 360px;"
      />
      <v-spacer />
      <v-btn-toggle v-model="viewMode" density="compact" mandatory variant="outlined" divided>
        <v-btn value="developers" size="small">
          <v-icon icon="mdi-account-outline" size="16" class="mr-1" />
          By Developer
        </v-btn>
        <v-btn value="modules" size="small">
          <v-icon icon="mdi-cube-outline" size="16" class="mr-1" />
          By Module
        </v-btn>
      </v-btn-toggle>
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error -->
    <v-alert v-if="store.error" type="error" variant="tonal" class="mb-4" closable>
      {{ store.error }}
    </v-alert>

    <!-- Empty state -->
    <v-card
      v-if="!store.loading && store.profiles.length === 0"
      class="pa-12 text-center"
      color="surface"
    >
      <v-icon icon="mdi-account-cog-outline" size="64" class="text-medium-emphasis mb-4" />
      <div class="text-h6 mb-2">No skill profiles yet</div>
      <div class="text-body-2 text-medium-emphasis">
        Run a repository scan from Settings to extract developer skills from git history.
      </div>
    </v-card>

    <!-- Developer View -->
    <template v-if="!store.loading && viewMode === 'developers'">
      <div class="profiles-grid">
        <v-card
          v-for="profile in filteredProfiles"
          :key="profile.email"
          class="profile-card pa-5"
          color="surface"
        >
          <!-- Developer header -->
          <div class="d-flex align-center ga-3 mb-4">
            <v-avatar size="40" color="primary" variant="tonal">
              <span class="text-body-2 font-weight-bold">{{ initials(profile.userName) }}</span>
            </v-avatar>
            <div class="flex-grow-1 overflow-hidden">
              <div class="text-body-1 font-weight-medium text-truncate">{{ profile.userName }}</div>
              <div class="text-caption text-medium-emphasis text-truncate">{{ profile.email }}</div>
            </div>
            <v-chip size="x-small" variant="tonal" color="primary">
              {{ profile.modules.length }} module{{ profile.modules.length !== 1 ? 's' : '' }}
            </v-chip>
          </div>

          <!-- Module skills -->
          <div class="d-flex flex-column ga-2">
            <div
              v-for="mod in sortedModules(profile.modules)"
              :key="mod.name"
              class="module-row"
            >
              <div class="d-flex align-center justify-space-between mb-1">
                <div class="d-flex align-center ga-1">
                  <span class="text-body-2 font-weight-medium">{{ mod.name }}</span>
                  <v-chip
                    v-for="lang in mod.languages.slice(0, 3)"
                    :key="lang"
                    size="x-small"
                    variant="outlined"
                    class="ml-1"
                  >
                    {{ lang }}
                  </v-chip>
                </div>
                <span class="text-caption text-medium-emphasis">
                  {{ (mod.score * 100).toFixed(0) }}%
                </span>
              </div>
              <v-progress-linear
                :model-value="mod.score * 100"
                :color="scoreColor(mod.score)"
                height="6"
                rounded
                bg-color="surface-variant"
              />
              <div class="text-caption text-medium-emphasis mt-1">
                {{ mod.touchCount }} commit{{ mod.touchCount !== 1 ? 's' : '' }}
              </div>
            </div>
          </div>
        </v-card>
      </div>
    </template>

    <!-- Module View -->
    <template v-if="!store.loading && viewMode === 'modules'">
      <div class="profiles-grid">
        <v-card
          v-for="mod in filteredModules"
          :key="mod.name"
          class="profile-card pa-5"
          color="surface"
        >
          <!-- Module header -->
          <div class="d-flex align-start ga-3 mb-4">
            <v-avatar size="40" color="secondary" variant="tonal">
              <v-icon icon="mdi-cube-outline" size="20" />
            </v-avatar>
            <div class="flex-grow-1 overflow-hidden">
              <div class="text-body-1 font-weight-medium module-title">{{ mod.name }}</div>
              <div class="d-flex flex-wrap ga-1 mt-1">
                <v-chip
                  v-for="lang in mod.languages.slice(0, 4)"
                  :key="lang"
                  size="x-small"
                  variant="outlined"
                >
                  {{ lang }}
                </v-chip>
              </div>
            </div>
            <v-chip size="x-small" variant="tonal" color="secondary">
              {{ mod.developers.length }} dev{{ mod.developers.length !== 1 ? 's' : '' }}
            </v-chip>
          </div>

          <!-- Developers for this module -->
          <div class="d-flex flex-column ga-2">
            <div
              v-for="dev in mod.developers"
              :key="dev.email"
              class="module-row"
            >
              <div class="d-flex align-center justify-space-between mb-1">
                <span class="text-body-2 font-weight-medium">{{ dev.userName }}</span>
                <span class="text-caption text-medium-emphasis">
                  {{ (dev.score * 100).toFixed(0) }}%
                </span>
              </div>
              <v-progress-linear
                :model-value="dev.score * 100"
                :color="scoreColor(dev.score)"
                height="6"
                rounded
                bg-color="surface-variant"
              />
              <div class="text-caption text-medium-emphasis mt-1">
                {{ dev.touchCount }} commit{{ dev.touchCount !== 1 ? 's' : '' }}
              </div>
            </div>
          </div>

          <!-- Bus factor warning -->
          <v-alert
            v-if="mod.developers.length === 1"
            type="warning"
            variant="tonal"
            density="compact"
            class="mt-3"
            icon="mdi-alert-outline"
          >
            <span class="text-caption">Bus factor risk — only one contributor</span>
          </v-alert>
        </v-card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useSkillsStore } from '@/stores/skills'
import type { ModuleSkill } from '@/types'

const store = useSkillsStore()

const search = ref('')
const viewMode = ref<'developers' | 'modules'>('developers')

const totalModules = computed(() => {
  const names = new Set<string>()
  for (const p of store.profiles) {
    for (const m of p.modules) names.add(m.name)
  }
  return names.size
})

const filteredProfiles = computed(() => {
  const q = search.value?.toLowerCase().trim()
  if (!q) return store.profiles
  return store.profiles.filter(
    (p) =>
      p.userName.toLowerCase().includes(q) ||
      p.email.toLowerCase().includes(q) ||
      p.modules.some((m) => m.name.toLowerCase().includes(q)),
  )
})

interface ModuleGroup {
  name: string
  languages: string[]
  developers: { userName: string; email: string; score: number; touchCount: number }[]
}

const moduleGroups = computed<ModuleGroup[]>(() => {
  const map = new Map<string, ModuleGroup>()
  for (const profile of store.profiles) {
    for (const mod of profile.modules) {
      let group = map.get(mod.name)
      if (!group) {
        group = { name: mod.name, languages: [], developers: [] }
        map.set(mod.name, group)
      }
      group.developers.push({
        userName: profile.userName,
        email: profile.email,
        score: mod.score,
        touchCount: mod.touchCount,
      })
      for (const lang of mod.languages) {
        if (!group.languages.includes(lang)) group.languages.push(lang)
      }
    }
  }
  // Sort developers within each module by score desc
  for (const group of map.values()) {
    group.developers.sort((a, b) => b.score - a.score)
  }
  // Sort modules by number of developers desc
  return Array.from(map.values()).sort((a, b) => b.developers.length - a.developers.length)
})

const filteredModules = computed(() => {
  const q = search.value?.toLowerCase().trim()
  if (!q) return moduleGroups.value
  return moduleGroups.value.filter(
    (m) =>
      m.name.toLowerCase().includes(q) ||
      m.developers.some((d) => d.userName.toLowerCase().includes(q)),
  )
})

function sortedModules(modules: ModuleSkill[]): ModuleSkill[] {
  return [...modules].sort((a, b) => b.score - a.score)
}

function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2) || '?'
}

function scoreColor(score: number): string {
  if (score >= 0.7) return 'success'
  if (score >= 0.4) return 'primary'
  if (score >= 0.2) return 'warning'
  return 'grey'
}

onMounted(() => {
  store.fetchProfiles()
})
</script>

<style scoped>
.profiles-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}

.profile-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.15s ease;
}

.profile-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.3);
}

.module-row {
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
}

.module-title {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  line-height: 1.3;
}
</style>
