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

<!-- One triage request: the Slack message on the left, the BUD the Triage
     agent proposes on the right. A waiting request has one filled action,
     Create BUD, and Reject beside it; a decided one shows its outcome. -->
<template>
  <article class="triage-card" :aria-labelledby="titleId">
    <div class="triage-card__source">
      <span class="triage-card__eyebrow">From Slack · {{ session.slack_channel }}</span>
      <div class="triage-card__message">
        <AppMonogram :name="requester" square />
        <div class="triage-card__message-body">
          <span class="triage-card__who">
            <strong>{{ requester }}</strong>
            <span :title="formatDateTime(session.created_at)">{{ relativeTime(session.created_at, now) }}</span>
          </span>
          <p>{{ session.original_text || 'No message text' }}</p>
        </div>
      </div>
    </div>

    <div class="triage-card__proposal">
      <div class="triage-card__heading">
        <span class="triage-card__eyebrow">Proposed BUD</span>
        <BudPriorityChip :priority="triagePriority(session.priority)" />
        <AppTag v-if="compliance" color="warning">Compliance</AppTag>
        <AppTag v-if="!waiting" :color="status.color" sr-prefix="Status:" class="triage-card__status">{{ status.label }}</AppTag>
      </div>
      <h2 :id="titleId" class="triage-card__title">{{ session.feature_name || 'Untitled request' }}</h2>

      <dl v-if="facts.length" class="triage-card__facts">
        <div v-for="fact in facts" :key="fact.label">
          <dt>{{ fact.label }}</dt>
          <dd>{{ fact.value }}</dd>
        </div>
      </dl>
      <p v-else class="triage-card__none">The Triage agent hasn't added any context yet.</p>

      <div class="triage-card__actions">
        <template v-if="waiting">
          <v-btn color="primary" variant="flat" :loading="busy === 'approve'" @click="emit('decide', 'approve')">
            Create BUD
          </v-btn>
          <v-btn variant="text" :loading="busy === 'reject'" @click="emit('decide', 'reject')">Reject</v-btn>
        </template>
        <router-link v-else-if="session.bud_id" :to="`/buds/${session.bud_id}`" class="triage-card__link">Open the BUD</router-link>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'
import AppMonogram from '@/components/common/AppMonogram.vue'
import AppTag from '@/components/common/AppTag.vue'
import BudPriorityChip from '@/components/buds/BudPriorityChip.vue'
import type { TriageSession } from '@/stores/triage'
import { formatDateTime, relativeTime } from '@/utils/date'
import {
  contextFacts,
  isCompliance,
  requesterName,
  triagePriority,
  triageStatus,
  WAITING_STATUS,
} from '@/utils/triage'

const props = defineProps<{ session: TriageSession; now: Date; busy: 'approve' | 'reject' | null }>()
const emit = defineEmits<{ decide: [action: 'approve' | 'reject'] }>()

const titleId = useId()
const requester = computed(() => requesterName(props.session))
const waiting = computed(() => props.session.status === WAITING_STATUS)
const status = computed(() => triageStatus(props.session.status))
const facts = computed(() => contextFacts(props.session.triage_context))
const compliance = computed(() => isCompliance(props.session.triage_context))
</script>

<style scoped>
.triage-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  overflow: hidden;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
.triage-card__source,
.triage-card__proposal {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 20px 22px;
}
.triage-card__source {
  background: rgb(var(--v-theme-background));
  border-right: 1px solid rgb(var(--v-theme-rule));
}
.triage-card__eyebrow {
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface-variant));
  overflow-wrap: anywhere;
}
.triage-card__message {
  display: flex;
  gap: 10px;
}
.triage-card__message-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.triage-card__who {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 8px;
  font-size: 14px;
}
.triage-card__who strong {
  font-weight: 600;
}
.triage-card__who span {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.triage-card__message-body p {
  margin: 0;
  font-size: 14px;
  line-height: 21px;
  color: rgb(var(--v-theme-ink-2));
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.triage-card__heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.triage-card__status {
  margin-left: auto;
}
.triage-card__title {
  margin: 0;
  font-size: 18px;
  line-height: 24px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.triage-card__facts {
  display: grid;
  gap: 10px;
  margin: 0;
}
.triage-card__facts dt {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.triage-card__facts dd,
.triage-card__none {
  margin: 0;
  font-size: 14px;
  line-height: 21px;
  color: rgb(var(--v-theme-ink-2));
}
.triage-card__none {
  color: rgb(var(--v-theme-on-surface-variant));
}
.triage-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: auto;
  padding-top: 6px;
}
.triage-card__actions:empty {
  display: none;
}
.triage-card__link {
  font-size: 14px;
  color: var(--color-accent-text);
  text-decoration: none;
}
.triage-card__link:hover {
  text-decoration: underline;
}
@media (max-width: 860px) {
  .triage-card {
    grid-template-columns: minmax(0, 1fr);
  }
  .triage-card__source {
    border-right: 0;
    border-bottom: 1px solid rgb(var(--v-theme-rule));
  }
}
@media (max-width: 600px) {
  .triage-card__source,
  .triage-card__proposal {
    padding: 16px;
  }
}
</style>
