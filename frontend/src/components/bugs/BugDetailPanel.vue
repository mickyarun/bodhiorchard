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

<!-- The open bug (``bugsStore.currentBug``), shown in the Bugs side sheet:
     severity and environment, the title and description (editable in place
     for editors), status / owner / feature, the facts, attachments and the
     comment thread. -->
<template>
  <div v-if="bug" class="bug-detail">
    <div class="bug-detail__tags">
      <AppTag :color="BUG_SEVERITY_COLORS[bug.severity]" sr-prefix="Severity:">{{ severityLabel(bug.severity) }}</AppTag>
      <AppTag>{{ bug.bugType === 'production' ? 'Production' : 'Testing' }}</AppTag>
    </div>

    <BugEditableText
      :value="bug.title"
      label="Title"
      :editable="canEditBugs"
      required
      class="bug-detail__title"
      @save="bugsStore.updateBug(bug.id, { title: $event })"
    />
    <BugEditableText
      :value="bug.description ?? ''"
      label="Description"
      :editable="canEditBugs"
      multiline
      :empty-text="canEditBugs ? 'Add a description' : 'No description'"
      @save="bugsStore.updateBug(bug.id, { description: $event })"
    />

    <BugDetailFields v-if="canEditBugs || canAssignBugs" :bug="bug" />

    <dl class="bug-detail__facts">
      <template v-for="fact in facts" :key="fact.label">
        <dt>{{ fact.label }}</dt>
        <dd>
          <router-link v-if="fact.to" :to="fact.to">{{ fact.value }}</router-link>
          <template v-else>{{ fact.value }}</template>
        </dd>
      </template>
    </dl>

    <BugAttachments :bug-id="bug.id" :readonly="!canAttachToBugs" />
    <BugComments :bug-id="bug.id" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppTag from '@/components/common/AppTag.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useBugsStore } from '@/stores/bugs'
import { BUG_SEVERITY_COLORS, budRef } from '@/types'
import { severityLabel } from '@/utils/bugList'
import { formatDateTime } from '@/utils/date'
import BugAttachments from './BugAttachments.vue'
import BugComments from './BugComments.vue'
import BugDetailFields from './BugDetailFields.vue'
import BugEditableText from './BugEditableText.vue'

const bugsStore = useBugsStore()
const { canEditBugs, canAssignBugs, canReportBugs } = usePermissions()
const bug = computed(() => bugsStore.currentBug)

// Reporters attach evidence too, not just editors; the backend gates the
// upload route the same way.
const canAttachToBugs = computed(() => canReportBugs.value || canEditBugs.value)

const facts = computed(() => {
  const b = bug.value
  if (!b) return []
  const out: Array<{ label: string; value: string; to?: string }> = []
  // Shown as fields above for people who can change them.
  if (!canAssignBugs.value) out.push({ label: 'Owner', value: b.assigneeName || 'Unassigned' })
  if (!canEditBugs.value) out.push({ label: 'Feature', value: b.featureTitle || 'Not linked' })
  if (b.budId && b.budNumber) {
    out.push({ label: 'BUD', value: [budRef(b.budNumber), b.budTitle].filter(Boolean).join(' · '), to: `/buds/${b.budId}` })
  }
  if (b.module) out.push({ label: 'Module', value: b.module })
  out.push({ label: 'Reporter', value: b.reporterName || 'Unknown' })
  out.push({ label: 'Reported', value: formatDateTime(b.createdAt) })
  if (b.resolvedAt) out.push({ label: 'Resolved', value: formatDateTime(b.resolvedAt) })
  return out
})
</script>

<style scoped>
.bug-detail {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.bug-detail__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.bug-detail__title :deep(.bug-text__value) {
  font-size: 18px;
  line-height: 24px;
  font-weight: 600;
}
.bug-detail__facts {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 6px 16px;
  margin: 0;
  font-size: 13px;
}
.bug-detail__facts dt {
  color: rgb(var(--v-theme-on-surface-variant));
}
.bug-detail__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.bug-detail__facts a {
  color: var(--color-accent-text);
  text-decoration: none;
}
</style>
