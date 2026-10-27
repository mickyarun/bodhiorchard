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
     backend replies in the request's Slack thread. -->
<template>
  <v-dialog :model-value="!!session" max-width="460" @update:model-value="!$event && emit('cancel')">
    <v-card v-if="session" color="surface" class="triage-decision">
      <h2 class="triage-decision__title">{{ approve ? 'Create a BUD from this request?' : 'Reject this request?' }}</h2>
      <p class="triage-decision__body">
        <strong>{{ session.feature_name || 'Untitled request' }}</strong>.
        {{ approve
          ? 'This creates the BUD and replies in the Slack thread.'
          : 'This replies in the Slack thread that the request was declined.' }}
      </p>
      <v-textarea v-model="notes" label="Note (optional)" rows="3" variant="outlined" density="compact" hide-details />
      <div class="triage-decision__actions">
        <v-btn variant="text" @click="emit('cancel')">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="emit('confirm', notes.trim() || undefined)">
          {{ approve ? 'Create BUD' : 'Reject request' }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TriageSession } from '@/stores/triage'

const props = defineProps<{ session: TriageSession | null; action: 'approve' | 'reject'; busy: boolean }>()
const emit = defineEmits<{ confirm: [notes: string | undefined]; cancel: [] }>()

const approve = computed(() => props.action === 'approve')
const notes = ref('')

// A fresh note for every decision.
watch(
  () => props.session?.id,
  () => (notes.value = ''),
)
</script>

<style scoped>
.triage-decision {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 24px;
}
.triage-decision__title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}
.triage-decision__body {
  margin: 0;
  font-size: 14px;
  line-height: 21px;
  color: rgb(var(--v-theme-ink-2));
}
.triage-decision__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
