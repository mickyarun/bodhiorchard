<template>
  <div class="setup-gradient d-flex flex-column" style="min-height: 100vh;">
    <v-container class="flex-grow-1 py-6" fluid>
      <v-btn
        variant="text"
        size="small"
        class="mb-2"
        @click="router.back()"
      >
        <v-icon start>mdi-arrow-left</v-icon>
        Back
      </v-btn>

      <div class="text-h4 font-weight-bold text-center mb-2">
        Choose Your Character
      </div>
      <div class="text-body-2 text-medium-emphasis text-center mb-6">
        Pick your avatar for the Bodhiorchard garden
      </div>

      <!-- XP Progress — reusable component -->
      <XPProfileCard
        v-if="xpStore.profile"
        :total-xp="xpStore.profile.total_xp"
        :level="xpStore.profile.level"
        :level-name="xpStore.profile.level_name"
        :xp-to-next-level="xpStore.profile.xp_to_next_level"
        :next-level-threshold="xpStore.profile.next_level_threshold"
        :streak-count="xpStore.profile.streak_count"
        :skill-points="xpStore.profile.skill_points"
        class="mb-5 mx-auto"
        style="max-width: 650px;"
      />

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

          <v-card color="surface" class="pa-5 mb-4">
            <AccessoryPicker
              :right-hand="config.rightHand"
              :left-hand="config.leftHand"
              @update="onAccessoryUpdate"
            />
          </v-card>

          <v-card color="surface" class="pa-5">
            <UpgradeShopPanel />
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
import XPProfileCard from '@/components/xp/XPProfileCard.vue'
import CharacterGrid from '@/components/character/CharacterGrid.vue'
import CharacterPreview from '@/components/character/CharacterPreview.vue'
import ColorCustomizer from '@/components/character/ColorCustomizer.vue'
import AccessoryPicker from '@/components/character/AccessoryPicker.vue'
import UpgradeShopPanel from '@/components/xp/UpgradeShopPanel.vue'
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

// Load current selection from user profile, fallback to defaults
const existing = parseCharacterModel(authStore.user?.character_model ?? null)
const config = reactive<CharacterConfig>({
  characterId: existing.characterId,
  shirtColor: existing.shirtColor || DEFAULT_SHIRT_COLOR,
  pantsColor: existing.pantsColor || DEFAULT_PANTS_COLOR,
  skinColor: existing.skinColor || DEFAULT_SKIN_COLOR,
  rightHand: existing.rightHand || '',
  leftHand: existing.leftHand || '',
})

// Computed shallow copy for the preview (triggers reactivity on any change)
const previewConfig = computed<CharacterConfig>(() => ({
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

/* XP card styles moved to reusable XPProfileCard.vue */
</style>
