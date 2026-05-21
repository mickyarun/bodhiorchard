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

<template>
  <v-card variant="outlined" class="linked-features-panel">
    <div class="d-flex align-center px-4 py-2">
      <div class="d-flex align-center text-subtitle-2">
        <span>Linked features</span>
        <span class="text-medium-emphasis ml-1">({{ rows.length }})</span>
        <!-- Tooltip explains what the panel surfaces — the PM agent auto-links
             features from the requirement; humans can correct it here before
             downstream agents (Designer / TechPlan / Tester) inherit the list. -->
        <v-tooltip location="bottom" max-width="320">
          <template #activator="{ props: tooltipProps }">
            <v-icon
              v-bind="tooltipProps"
              icon="mdi-information-outline"
              size="14"
              class="ml-1 text-medium-emphasis"
              tabindex="0"
              aria-label="What are linked features?"
            />
          </template>
          <div class="text-caption">
            Existing features in your codebase that this BUD touches. The PM agent
            picks them automatically when you enrich the requirement; downstream
            stages (Design, Tech Plan, Code Review, Testing) ground in the linked
            features' code so changes stay scoped. Correct the list before moving
            on if the agent missed or over-picked.
          </div>
        </v-tooltip>
      </div>
      <v-spacer />
      <v-btn
        v-if="canEdit"
        size="small"
        variant="tonal"
        color="teal"
        prepend-icon="mdi-plus"
        :disabled="store.loading"
        @click="pickerOpen = true"
      >
        Add
      </v-btn>
    </div>

    <v-divider />

    <template v-if="store.loading && rows.length === 0">
      <v-skeleton-loader type="list-item-two-line" />
      <v-skeleton-loader type="list-item-two-line" />
    </template>

    <template v-else-if="rows.length === 0">
      <div class="px-4 py-3 text-body-2 text-medium-emphasis">
        No linked features yet — the PM agent populates these from the requirement,
        or click <strong>+ Add</strong> to pick manually.
      </div>
    </template>

    <v-list v-else density="compact" class="py-0">
      <v-list-item
        v-for="row in rows"
        :key="row.id"
        :to="{ name: 'features', query: { id: row.id } }"
        class="linked-feature-row"
      >
        <template #default>
          <div class="d-flex align-center flex-wrap ga-2">
            <span class="text-body-2 font-weight-medium">{{ row.title }}</span>
            <v-chip v-if="row.repoName" size="x-small" variant="tonal" color="grey">
              {{ row.repoName }}
            </v-chip>
            <v-chip
              v-if="row.source !== 'pm_agent'"
              size="x-small"
              variant="tonal"
              :color="row.source === 'manual' ? 'blue' : 'purple'"
            >
              {{ row.source === 'manual' ? 'manual' : 'tech-arch' }}
            </v-chip>
          </div>
        </template>
        <template #append>
          <v-btn
            v-if="canEdit"
            icon="mdi-close"
            size="x-small"
            variant="text"
            :disabled="unlinkingIds.has(row.id)"
            title="Unlink"
            @click.stop.prevent="askUnlink(row)"
          />
        </template>
      </v-list-item>
    </v-list>

    <AddLinkedFeatureDialog
      v-if="canEdit"
      v-model="pickerOpen"
      :bud-id="props.budId"
      :existing-ids="existingIds"
      @linked="onLinked"
    />

    <!-- Unlink confirmation — destructive enough to warrant a confirm step
         because downstream stages (Tech Plan, Code Review, Testing) depend
         on this list to stay scoped. An accidental unlink silently widens
         the agent's working set. -->
    <v-dialog v-model="confirmOpen" max-width="420">
      <v-card>
        <v-card-title class="text-subtitle-1">Unlink feature?</v-card-title>
        <v-card-text class="text-body-2">
          Remove the link to
          <strong>{{ pendingUnlink?.title ?? 'this feature' }}</strong
          >? Downstream stages will no longer use it as grounding context.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="!!pendingUnlink && unlinkingIds.has(pendingUnlink.id)" @click="confirmOpen = false">Cancel</v-btn>
          <v-btn
            color="error"
            variant="flat"
            :loading="!!pendingUnlink && unlinkingIds.has(pendingUnlink.id)"
            @click="confirmUnlink"
          >
            Unlink
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar" :timeout="3500" :color="snackbarColor">
      {{ snackbarText }}
    </v-snackbar>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { LinkedFeature } from '@/types'
import { useBudLinkedFeaturesStore } from '@/stores/budLinkedFeatures'
import { usePermissions } from '@/composables/usePermissions'
import AddLinkedFeatureDialog from './AddLinkedFeatureDialog.vue'

const props = defineProps<{ budId: string }>()
const emit = defineEmits<{
  // Fired after any successful link or unlink so the parent can refresh
  // adjacent surfaces (e.g. the BUD timeline, which now logs these as events).
  change: []
}>()

const store = useBudLinkedFeaturesStore()
const { hasPermission } = usePermissions()

const canEdit = computed(() => hasPermission('buds:edit'))
const rows = computed(() => store.byBudId[props.budId] ?? [])
const existingIds = computed(() => rows.value.map(r => r.id))

const pickerOpen = ref(false)
// Set, not single ref: users can click [×] on multiple rows in quick
// succession — tracking each in-flight id independently lets only the
// targeted row spinner-disable while peers stay clickable.
const unlinkingIds = ref<Set<string>>(new Set())
const confirmOpen = ref(false)
const pendingUnlink = ref<LinkedFeature | null>(null)
const snackbar = ref(false)
const snackbarText = ref('')
const snackbarColor = ref<'success' | 'error'>('success')

function flash(text: string, color: 'success' | 'error' = 'success') {
  snackbarText.value = text
  snackbarColor.value = color
  snackbar.value = true
}

function askUnlink(row: LinkedFeature) {
  pendingUnlink.value = row
  confirmOpen.value = true
}

async function confirmUnlink() {
  const target = pendingUnlink.value
  if (!target) return
  // Trigger reactivity by replacing the Set — Vue's ref doesn't track
  // Set.add() / Set.delete() mutations.
  unlinkingIds.value = new Set(unlinkingIds.value).add(target.id)
  const ok = await store.unlink(props.budId, target.id)
  const next = new Set(unlinkingIds.value)
  next.delete(target.id)
  unlinkingIds.value = next
  if (ok) {
    confirmOpen.value = false
    pendingUnlink.value = null
    emit('change')
    flash('Unlinked')
  } else {
    flash(store.error || 'Failed to unlink', 'error')
  }
}

function onLinked(insertedCount: number) {
  if (insertedCount > 0) emit('change')
  flash(
    insertedCount === 0
      ? 'No new links added (all selected were already linked)'
      : `Linked ${insertedCount} feature${insertedCount === 1 ? '' : 's'}`,
  )
}

onMounted(() => {
  if (!store.byBudId[props.budId]) {
    void store.fetch(props.budId)
  }
})

watch(
  () => props.budId,
  (id, prev) => {
    if (id && id !== prev) void store.fetch(id)
  },
)
</script>

<style scoped>
.linked-features-panel {
  background: rgb(var(--v-theme-surface));
}
.linked-feature-row :deep(.v-list-item__append) {
  align-self: center;
}
</style>
