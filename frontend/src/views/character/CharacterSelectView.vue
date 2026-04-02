<template>
  <div class="setup-gradient d-flex flex-column" style="min-height: 100vh;">
    <v-container class="flex-grow-1 py-6" fluid>
      <div class="text-h4 font-weight-bold text-center mb-2">
        Choose Your Character
      </div>
      <div class="text-body-2 text-medium-emphasis text-center mb-6">
        Pick your avatar for the Bodhigrove garden
      </div>

      <v-row>
        <!-- Left: Character grid + color customizer -->
        <v-col cols="12" md="5">
          <v-card color="surface" class="pa-5 mb-4">
            <CharacterGrid
              :selected-id="config.characterId"
              @select="onCharacterSelect"
            />
          </v-card>

          <!-- Color customizer disabled for V1 — KayKit uses pre-colored textures.
               Will be re-enabled in V2 with canvas-based texture manipulation. -->
          <!--
          <v-card color="surface" class="pa-5">
            <ColorCustomizer
              :shirt-color="config.shirtColor"
              :pants-color="config.pantsColor"
              :skin-color="config.skinColor"
              @update="onColorUpdate"
            />
          </v-card>
          -->
        </v-col>

        <!-- Right: 3D preview -->
        <v-col cols="12" md="7">
          <v-card
            color="surface"
            class="character-select__preview-card"
          >
            <CharacterPreview
              :config="previewConfig"
              class="character-select__preview"
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
import {
  type CharacterConfig,
  serializeCharacterConfig,
  DEFAULT_SHIRT_COLOR,
  DEFAULT_PANTS_COLOR,
  DEFAULT_SKIN_COLOR,
} from '@/engine/characters/CharacterConfig'
import { useMembersStore } from '@/stores/members'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const membersStore = useMembersStore()
const authStore = useAuthStore()
const saving = ref(false)

// Reactive config — drives both the grid selection and the 3D preview
const config = reactive<CharacterConfig>({
  pack: 'kaykit',
  characterId: 'barbarian',
  shirtColor: DEFAULT_SHIRT_COLOR,
  pantsColor: DEFAULT_PANTS_COLOR,
  skinColor: DEFAULT_SKIN_COLOR,
})

// Computed shallow copy for the preview (triggers reactivity on any change)
const previewConfig = computed<CharacterConfig>(() => ({
  pack: config.pack,
  characterId: config.characterId,
  shirtColor: config.shirtColor,
  pantsColor: config.pantsColor,
  skinColor: config.skinColor,
}))

function onCharacterSelect(id: string): void {
  config.characterId = id
}

function onColorUpdate(key: 'shirtColor' | 'pantsColor' | 'skinColor', value: string): void {
  config[key] = value
}

async function handleSave(): Promise<void> {
  // Ensure user is loaded (may not be if navigated directly after password change)
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
    // Refresh user so character_model is up to date for downstream checks
    await authStore.fetchUser()
    router.push({ name: 'methodology' })
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

.character-select__preview {
  height: 100%;
}
</style>
