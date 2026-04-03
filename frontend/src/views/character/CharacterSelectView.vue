<template>
  <div class="setup-gradient d-flex flex-column" style="min-height: 100vh;">
    <v-container class="flex-grow-1 py-6" fluid>
      <div class="text-h4 font-weight-bold text-center mb-2">
        Choose Your Character
      </div>
      <div class="text-body-2 text-medium-emphasis text-center mb-6">
        Pick your avatar for the Bodhigrove garden
      </div>

      <!-- XP Progress Card -->
      <v-card
        v-if="xpStore.profile"
        color="surface"
        class="xp-card pa-4 mb-5 mx-auto"
        :class="{ 'xp-card--near-levelup': nearLevelUp }"
        max-width="650"
      >
        <div class="d-flex align-center ga-3 mb-3">
          <!-- Level badge with icon -->
          <div class="xp-card__level">
            <span class="xp-card__level-icon">{{ levelIcon }}</span>
            <span class="text-body-2 font-weight-bold">
              Lv.{{ xpStore.profile.level }}
            </span>
            <span class="text-caption text-medium-emphasis text-capitalize">
              {{ xpStore.profile.level_name.replace('_', ' ') }}
            </span>
          </div>

          <v-spacer />

          <!-- XP total -->
          <span class="text-h6 font-weight-bold" style="color: rgb(var(--v-theme-secondary));">
            {{ xpStore.profile.total_xp.toLocaleString() }}
            <span class="text-caption font-weight-medium text-medium-emphasis">XP</span>
          </span>

          <!-- Streak flame -->
          <v-chip
            v-if="xpStore.profile.streak_count > 0"
            :color="xpStore.profile.streak_count >= 7 ? 'error' : 'warning'"
            variant="flat"
            size="small"
            :class="{ 'streak-pulse': xpStore.profile.streak_count >= 7 }"
          >
            <v-icon start :icon="xpStore.profile.streak_count >= 7 ? 'mdi-fire-alert' : 'mdi-fire'" />
            {{ xpStore.profile.streak_count }}d
            <span v-if="xpStore.profile.streak_count >= 7" class="ml-1 text-caption">
              {{ streakMultiplier }}x
            </span>
          </v-chip>
        </div>

        <!-- Animated gradient progress bar -->
        <div class="xp-card__bar-container">
          <div
            class="xp-card__bar-fill"
            :style="{ width: xpProgress + '%' }"
          />
        </div>

        <!-- Next level hint -->
        <div
          v-if="xpStore.profile.next_level_threshold > 0"
          class="text-caption text-medium-emphasis mt-2"
        >
          {{ xpStore.profile.xp_to_next_level.toLocaleString() }} XP to
          <span class="text-capitalize font-weight-medium" style="color: rgb(var(--v-theme-secondary));">
            {{ nextLevelName }}
          </span>
        </div>
        <div v-else class="text-caption mt-2" style="color: rgb(var(--v-theme-secondary));">
          Max level reached!
        </div>
      </v-card>

      <v-row>
        <!-- 3D Preview — shown first on mobile (order-1), right on desktop (order-md-2) -->
        <v-col cols="12" md="7" order="1" order-md="2">
          <v-card
            color="surface"
            class="character-select__preview-card mb-4"
          >
            <CharacterPreview
              :config="previewConfig"
              class="character-select__preview"
            />
          </v-card>
        </v-col>

        <!-- Controls — shown second on mobile (order-2), left on desktop (order-md-1) -->
        <v-col cols="12" md="5" order="2" order-md="1">
          <v-card color="surface" class="pa-5 mb-4">
            <CharacterGrid
              :selected-id="config.characterId"
              @select="onCharacterSelect"
            />
          </v-card>

          <v-card color="surface" class="pa-5 mb-4">
            <ColorCustomizer
              :shirt-color="config.shirtColor"
              :pants-color="config.pantsColor"
              :skin-color="config.skinColor"
              @update="onColorUpdate"
            />
          </v-card>

          <v-card color="surface" class="pa-5">
            <AccessoryPicker
              :right-hand="config.rightHand"
              :left-hand="config.leftHand"
              @update="onAccessoryUpdate"
            />
          </v-card>
        </v-col>
      </v-row>

      <!-- Save button -->
      <div class="d-flex justify-center mt-6">
        <v-btn
          color="primary"
          size="large"
          :loading="saving"
          :disabled="!config.characterId"
          @click="handleSave"
        >
          <v-icon start icon="mdi-check" />
          Save & Continue
        </v-btn>
      </div>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import CharacterGrid from '@/components/character/CharacterGrid.vue'
import CharacterPreview from '@/components/character/CharacterPreview.vue'
import ColorCustomizer from '@/components/character/ColorCustomizer.vue'
import AccessoryPicker from '@/components/character/AccessoryPicker.vue'
import {
  type CharacterConfig,
  parseCharacterModel,
  serializeCharacterConfig,
  DEFAULT_SHIRT_COLOR,
  DEFAULT_PANTS_COLOR,
  DEFAULT_SKIN_COLOR,
} from '@/engine/characters/CharacterConfig'
import { useMembersStore } from '@/stores/members'
import { useAuthStore } from '@/stores/auth'
import { useXPStore } from '@/stores/xp'
import { onMounted } from 'vue'

const router = useRouter()
const membersStore = useMembersStore()
const authStore = useAuthStore()
const xpStore = useXPStore()
const saving = ref(false)

// Fetch XP profile on mount (needed for unlock data + progress bar)
onMounted(() => { xpStore.fetchProfile() })

const LEVEL_ICONS: Record<string, string> = {
  seedling: '🌱', sprout: '🌿', sapling: '🌲', tree: '🌳', ancient_oak: '🏔️',
}
const LEVEL_NAMES = ['seedling', 'sprout', 'sapling', 'tree', 'ancient_oak']

const xpProgress = computed(() => {
  const p = xpStore.profile
  if (!p || p.next_level_threshold === 0) return 100
  const xpIntoLevel = p.next_level_threshold - p.xp_to_next_level
  return Math.min(100, (xpIntoLevel / p.next_level_threshold) * 100)
})

const levelIcon = computed(() => {
  return LEVEL_ICONS[xpStore.profile?.level_name || 'seedling'] || '⭐'
})

const nearLevelUp = computed(() => {
  const p = xpStore.profile
  if (!p || p.next_level_threshold === 0) return false
  return (p.xp_to_next_level / p.next_level_threshold) < 0.2
})

const nextLevelName = computed(() => {
  const p = xpStore.profile
  if (!p) return ''
  const idx = LEVEL_NAMES.indexOf(p.level_name)
  return idx >= 0 && idx < LEVEL_NAMES.length - 1
    ? LEVEL_NAMES[idx + 1].replace('_', ' ')
    : ''
})

const streakMultiplier = computed(() => {
  const s = xpStore.profile?.streak_count || 0
  if (s >= 30) return '2.5'
  if (s >= 14) return '2.0'
  if (s >= 7) return '1.5'
  return '1.0'
})

// Load current selection from user profile, fallback to defaults
const existing = parseCharacterModel(authStore.user?.character_model ?? null)
const config = reactive<CharacterConfig>({
  pack: 'kaykit',
  characterId: existing.pack === 'kaykit' ? existing.characterId : 'barbarian',
  shirtColor: existing.shirtColor || DEFAULT_SHIRT_COLOR,
  pantsColor: existing.pantsColor || DEFAULT_PANTS_COLOR,
  skinColor: existing.skinColor || DEFAULT_SKIN_COLOR,
  rightHand: existing.rightHand || '',
  leftHand: existing.leftHand || '',
})

// Computed shallow copy for the preview (triggers reactivity on any change)
const previewConfig = computed<CharacterConfig>(() => ({
  pack: config.pack,
  characterId: config.characterId,
  shirtColor: config.shirtColor,
  pantsColor: config.pantsColor,
  skinColor: config.skinColor,
  rightHand: config.rightHand,
  leftHand: config.leftHand,
}))

function onCharacterSelect(id: string): void {
  config.characterId = id
}

function onColorUpdate(key: 'shirtColor' | 'pantsColor' | 'skinColor', value: string): void {
  config[key] = value
}

function onAccessoryUpdate(key: 'rightHand' | 'leftHand', value: string): void {
  config[key] = value
}

async function handleSave(): Promise<void> {
  if (!authStore.user) {
    await authStore.fetchUser()
  }
  const userId = authStore.user?.id
  if (!userId) {
    console.error('[CharacterSelect] No authenticated user — cannot save character')
    return
  }

  saving.value = true
  try {
    const serialized = serializeCharacterConfig(config)
    await membersStore.updateCharacter(userId, serialized)
    await authStore.fetchUser()
    router.push({ name: 'dashboard' })
  } catch (err) {
    console.error('[CharacterSelect] Failed to save:', err)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.character-select__preview-card {
  height: 500px;
  overflow: hidden;
}

@media (max-width: 960px) {
  .character-select__preview-card {
    height: 320px;
  }
}

.character-select__preview {
  height: 100%;
}

/* ─── XP Card ─────────────────────────────── */

.xp-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.3s, box-shadow 0.3s;
}

.xp-card--near-levelup {
  border-color: rgba(var(--v-theme-secondary), 0.4);
  box-shadow: 0 0 16px rgba(var(--v-theme-secondary), 0.15);
}

.xp-card__level {
  display: flex;
  align-items: center;
  gap: 6px;
}

.xp-card__level-icon {
  font-size: 24px;
  line-height: 1;
}

/* Animated gradient progress bar */
.xp-card__bar-container {
  height: 10px;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.xp-card__bar-fill {
  height: 100%;
  border-radius: 5px;
  background: linear-gradient(90deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-secondary)));
  transition: width 0.6s ease;
}

/* Streak pulse animation */
.streak-pulse {
  animation: pulse-flame 1.5s ease-in-out infinite;
}

@keyframes pulse-flame {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}
</style>
