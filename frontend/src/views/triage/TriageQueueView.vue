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

<!-- Triage: requests from Slack that the Triage agent has scoped. Waiting
     ones can become a BUD or be rejected; History shows the rest with
     their outcome. -->
<template>
  <AppPage title="Triage" subtitle="Requests from Slack, scoped by the Triage agent. Create a BUD from the ones worth building.">
    <template #actions>
      <AppPillToggle v-model="tab" :options="tabOptions" aria-label="Show" />
    </template>

    <AppCallout v-if="triageStore.error" variant="error">
      {{ triageStore.error }}
      <template #actions><v-btn variant="outlined" size="small" @click="load">Retry</v-btn></template>
    </AppCallout>

    <div v-if="triageStore.loading && !triageStore.sessions.length" class="triage-page__loading">
      <v-progress-circular indeterminate color="primary" aria-label="Loading requests" />
    </div>

    <div v-else-if="!shown.length" class="triage-page__empty">
      <h2>{{ tab === 'waiting' ? 'Nothing waiting' : 'No decided requests yet' }}</h2>
      <p>
        Feature requests raised in Slack show up here once the Triage agent has scoped them.
      </p>
    </div>

    <TriageRequestCard
      v-for="session in shown"
      :key="session.id"
      :session="session"
      :now="now"
      :busy="pending?.session.id === session.id && working ? pending.action : null"
      @decide="pending = { session, action: $event }"
    />

    <TriageDecisionDialog
      :session="pending?.session ?? null"
      :action="pending?.action ?? 'approve'"
      :busy="working"
      @cancel="pending = null"
      @confirm="decide"
    />
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import TriageDecisionDialog from '@/components/triage/TriageDecisionDialog.vue'
import TriageRequestCard from '@/components/triage/TriageRequestCard.vue'
import { useNow } from '@/composables/useNow'
import { useTriageStore, type TriageSession } from '@/stores/triage'
import { partitionSessions } from '@/utils/triage'

const triageStore = useTriageStore()
const now = useNow()

const tab = ref<'waiting' | 'history'>('waiting')
const groups = computed(() => partitionSessions(triageStore.sessions))
const shown = computed(() => groups.value[tab.value])
const tabOptions = computed(() => [
  { label: `Waiting · ${groups.value.waiting.length}`, value: 'waiting' as const },
  { label: 'History', value: 'history' as const },
])

const pending = ref<{ session: TriageSession; action: 'approve' | 'reject' } | null>(null)
const working = ref(false)

async function decide(notes: string | undefined): Promise<void> {
  if (!pending.value) return
  const { session, action } = pending.value
  working.value = true
  const ok = action === 'approve'
    ? await triageStore.approveSession(session.id, notes)
    : await triageStore.rejectSession(session.id, notes)
  working.value = false
  if (ok) pending.value = null
}

function load(): void {
  void triageStore.fetchSessions()
}

onMounted(load)
</script>

<style scoped>
.triage-page__loading {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}
.triage-page__empty {
  padding: 48px 24px;
  text-align: center;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
.triage-page__empty h2 {
  margin: 0 0 6px;
  font-size: var(--text-base);
  font-weight: 600;
}
.triage-page__empty p {
  margin: 0 auto;
  max-width: 460px;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
