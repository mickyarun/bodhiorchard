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

<!-- Confirms a triage decision with an optional note. Either way the
     backend replies in the request's Slack thread. A failure shows here,
     with the note kept, so it can be tried again. -->
<template>
  <AppConfirmDialog
    :model-value="!!session"
    :title="approve ? 'Create a BUD from this request?' : 'Reject this request?'"
    :action="approve ? 'Create BUD' : 'Reject request'"
    :busy="busy"
    @update:model-value="!$event && emit('cancel')"
    @confirm="emit('confirm', notes.trim() || undefined)"
  >
    <template #body>
      <strong>{{ session?.feature_name || 'Untitled request' }}</strong>.
      {{ approve ? 'This creates the BUD and replies in the Slack thread.' : 'This replies in the Slack thread that the request was declined.' }}
    </template>
    <v-textarea v-model="notes" label="Note (optional)" rows="3" variant="outlined" density="compact" hide-details />
    <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
  </AppConfirmDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppConfirmDialog from '@/components/common/AppConfirmDialog.vue'
import type { TriageSession } from '@/stores/triage'

const props = defineProps<{ session: TriageSession | null; action: 'approve' | 'reject'; busy: boolean; error: string }>()
const emit = defineEmits<{ confirm: [notes: string | undefined]; cancel: [] }>()

const approve = computed(() => props.action === 'approve')
const notes = ref('')

// A fresh note for every request.
watch(
  () => props.session?.id,
  () => (notes.value = ''),
)
</script>
