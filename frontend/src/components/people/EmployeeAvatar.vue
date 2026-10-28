<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->

<!-- An employee's profile photo, with upload and remove when editable.
     The picture itself is AppMonogram, which falls back to initials when
     there is no photo or it fails to load (a Slack link can rot after
     someone leaves the workspace). -->
<template>
  <div class="employee-avatar">
    <AppMonogram :name="name" :src="current" :size="size" />

    <template v-if="editable">
      <input ref="fileInput" type="file" :accept="AVATAR_ACCEPT" class="d-none" @change="onPick" />

      <!-- With a photo, the camera button opens a Replace / Remove menu and
           does nothing else; without one, it goes straight to the picker.
           Binding the menu to the button (not the wrapper) is what stops a
           single click from opening the file dialog and the menu at once. -->
      <v-menu v-if="current" location="bottom end">
        <template #activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            size="x-small"
            icon="mdi-camera-outline"
            variant="flat"
            color="surface-variant"
            class="employee-avatar__edit"
            :loading="busy"
            aria-label="Change profile photo"
          />
        </template>
        <v-list density="compact">
          <v-list-item
            prepend-icon="mdi-upload-outline"
            title="Replace photo"
            @click="fileInput?.click()"
          />
          <v-list-item
            prepend-icon="mdi-delete-outline"
            title="Remove photo"
            base-color="error"
            @click="remove"
          />
        </v-list>
      </v-menu>
      <v-btn
        v-else
        size="x-small"
        icon="mdi-camera-outline"
        variant="flat"
        color="surface-variant"
        class="employee-avatar__edit"
        :loading="busy"
        aria-label="Add profile photo"
        @click="fileInput?.click()"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import AppMonogram from '@/components/common/AppMonogram.vue'
import { AVATAR_ACCEPT, useAvatarEditor } from '@/composables/useAvatarEditor'

const props = withDefaults(
  defineProps<{
    userId: string
    name: string
    avatarUrl: string | null
    /** Show the camera button and the replace/remove menu. */
    editable?: boolean
    size?: number
  }>(),
  { editable: false, size: 64 },
)

const emit = defineEmits<{
  /** The new URL, or null after a removal. */
  updated: [avatarUrl: string | null]
  error: [message: string]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
// ``undefined`` = no local change yet; ``null`` = removed locally.
const localUrl = ref<string | null | undefined>(undefined)

/** The stored URL on show: a local upload or removal wins over the prop. */
const current = computed(() => (localUrl.value !== undefined ? localUrl.value : props.avatarUrl))

const { busy, onPick, remove } = useAvatarEditor(() => props.userId, {
  updated(avatarUrl) {
    localUrl.value = avatarUrl
    emit('updated', avatarUrl)
  },
  error: message => emit('error', message),
})
</script>

<style scoped>
.employee-avatar {
  position: relative;
  display: inline-flex;
}
.employee-avatar__edit {
  position: absolute;
  right: -4px;
  bottom: -4px;
}
</style>
