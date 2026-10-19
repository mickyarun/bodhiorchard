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

<!-- "Edit details": a policy's name, country, region and timezone. Saves
     only these fields, so unsaved rule edits on the page are kept. -->
<template>
  <v-dialog v-model="open" max-width="600" :fullscreen="xs">
    <v-card color="surface" rounded="lg">
      <div class="d-flex align-start ga-2 pa-6 pb-4">
        <div class="flex-grow-1">
          <h2 class="text-h6 font-weight-bold">Edit details</h2>
          <p class="text-body-2 text-medium-emphasis">
            Public holidays are imported for the country and region.
          </p>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="open = false" />
      </div>
      <v-form class="px-6 pb-2" @submit.prevent="submit">
        <PolicyDetailsFields
          v-model:name="draft.name"
          v-model:country="draft.country_code"
          v-model:subdivision="draft.subdivision_code"
          v-model:timezone="draft.timezone"
        />
        <AppCallout v-if="error" variant="error" class="mt-4">{{ error }}</AppCallout>
      </v-form>
      <v-divider class="mt-4" />
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!valid || !dirty" @click="submit">
          Save changes
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, toRef, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import PolicyDetailsFields from '@/components/leave/settings/PolicyDetailsFields.vue'
import { usePolicyDraft } from '@/composables/usePolicyDraft'
import type { PolicyRead } from '@/types/leavePolicy'
import { DETAIL_FIELDS } from '@/utils/leavePolicy'

const props = defineProps<{ policy: PolicyRead }>()
const emit = defineEmits<{ saved: [] }>()
const open = defineModel<boolean>({ required: true })

const { xs } = useDisplay()
const { draft, dirty, saving, error, save, discard } = usePolicyDraft(
  toRef(props, 'policy'),
  DETAIL_FIELDS,
)
const valid = computed(() => !!draft.value.name.trim() && !!draft.value.timezone)

watch(open, isOpen => {
  if (isOpen) discard()
})

async function submit(): Promise<void> {
  if (!valid.value || !dirty.value) return
  draft.value.name = draft.value.name.trim()
  if (!(await save())) return
  open.value = false
  emit('saved')
}
</script>
