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

<!-- Fold duplicate accounts into the one to keep. The duplicates' skill
     profiles and emails move across, then they are deactivated. -->
<template>
  <v-dialog v-model="open" max-width="520" persistent>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span>Merge duplicates</span>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="open = false" />
      </v-card-title>
      <v-card-text>
        <AppCallout variant="info" class="mb-4">
          Pick the member to keep, then the duplicates to merge into them. Their skill profiles and
          emails move across, then the duplicates are deactivated.
        </AppCallout>
        <v-autocomplete
          v-model="targetId"
          :items="memberPickerItems(store.members)"
          label="Keep this member"
          variant="outlined"
          density="compact"
          auto-select-first
          class="mb-3"
        />
        <v-autocomplete
          v-model="sourceIds"
          :items="memberPickerItems(store.members, targetId)"
          label="Merge these duplicates"
          variant="outlined"
          density="compact"
          multiple
          chips
          closable-chips
          :disabled="!targetId"
        />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="merging" :disabled="!targetId || sourceIds.length === 0" @click="submit">
          Merge {{ plural(sourceIds.length, 'member') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useMembersStore } from '@/stores/members'
import { plural } from '@/utils/format'
import { memberPickerItems } from '@/utils/members'

const props = defineProps<{ initialTargetId?: string }>()
const open = defineModel<boolean>({ required: true })
const store = useMembersStore()

const targetId = ref('')
const sourceIds = ref<string[]>([])
const merging = ref(false)

watch(open, isOpen => {
  if (!isOpen) return
  targetId.value = props.initialTargetId ?? ''
  sourceIds.value = []
})

async function submit(): Promise<void> {
  merging.value = true
  let allOk = true
  for (const sourceId of sourceIds.value) {
    if (!(await store.mergeMember(targetId.value, sourceId))) allOk = false
  }
  merging.value = false
  if (allOk) open.value = false
}
</script>
