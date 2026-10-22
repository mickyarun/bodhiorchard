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

<!-- A policy's library type: its rules come from the library, so here HR
     only picks the yearly quota and whether it's on. "Stop following" keeps
     it (with its requests and balances) as the policy's own type. -->
<template>
  <v-dialog :model-value="modelValue" max-width="560" :fullscreen="xs" scrollable @update:model-value="emit('update:modelValue', $event)">
    <v-card v-if="type" color="surface" rounded="lg">
      <div class="d-flex align-start ga-2 pa-6 pb-2">
        <div class="flex-grow-1">
          <h2 class="text-h6 font-weight-bold">{{ type.name }} on {{ policyName }}</h2>
          <p class="text-body-2 text-medium-emphasis">From the leave type library. Its rules are set there, for every policy that uses it.</p>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-card-text class="px-6">
        <div class="rules mb-5">
          <v-chip size="small" variant="tonal" label>{{ type.is_paid ? 'Paid' : 'Unpaid' }}</v-chip>
          <v-chip v-for="tag in typeRuleTags(type)" :key="tag" size="small" variant="outlined" label>{{ tag }}</v-chip>
          <v-btn variant="text" size="small" append-icon="mdi-arrow-right" @click="openLibrary">Edit in library</v-btn>
        </div>
        <div class="text-overline text-medium-emphasis mb-2">Yearly quota on this policy</div>
        <LinkedQuotaField v-model:choice="choice" v-model:days="days" :library-quota="libraryQuota" :auto-approve="type.auto_approve" />
        <LeaveSwitchRow v-model="active" class="mt-3" label="Available to request" description="Switch off to retire it on this policy only. Past requests and balances are kept." />
        <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
      </v-card-text>
      <v-divider />
      <div class="d-flex flex-wrap align-center ga-2 pa-4">
        <v-btn variant="text" color="error" :disabled="saving" @click="confirmUnlink = true">Stop following the library</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!validLinkQuota(choice, days)" @click="save">Save changes</v-btn>
      </div>
    </v-card>
    <ConfirmDialog
      v-model="confirmUnlink"
      title="Stop following the library?"
      :message="`${type?.name ?? ''} stays on ${policyName} with its current rules, requests and balances, but library changes won't reach it any more.`"
      confirm-label="Stop following"
      icon="mdi-link-variant-off"
      @confirm="stopFollowing"
    />
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveSwitchRow from '@/components/leave/settings/LeaveSwitchRow.vue'
import LinkedQuotaField from '@/components/leave/settings/LinkedQuotaField.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { useLeaveLibraryStore } from '@/stores/leaveLibrary'
import type { LeaveTypeRead } from '@/types/leavePolicy'
import { toNumberOrNull } from '@/utils/leave'
import { type QuotaChoice, linkBody, quotaChoice, validLinkQuota } from '@/utils/leaveLibrary'
import { typeRuleTags } from '@/utils/leavePolicyDisplay'

const props = defineProps<{ modelValue: boolean; policyName: string; type: LeaveTypeRead | null }>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const library = useLeaveLibraryStore()
const router = useRouter()
const { xs } = useDisplay()
const choice = ref<QuotaChoice>('library')
const days = ref<number | null>(null)
const active = ref(true)
const saving = ref(false)
const confirmUnlink = ref(false)
const error = ref('')

const libraryQuota = computed(() => {
  const entry = library.entries.find(e => e.id === props.type?.template_id)
  // Until the library loads, a type that follows it holds the same quota.
  return entry ? entry.annual_quota_days : (props.type?.annual_quota_days ?? null)
})

watch(
  () => props.modelValue,
  open => {
    if (!open || !props.type) return
    choice.value = quotaChoice(props.type)
    days.value = toNumberOrNull(props.type.annual_quota_days)
    active.value = props.type.is_active
    error.value = ''
    if (!library.entries.length) void library.fetchEntries()
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function save(): Promise<void> {
  if (!props.type) return
  saving.value = true
  error.value = (await library.updateLink(props.type, linkBody(choice.value, days.value, active.value))) ?? ''
  saving.value = false
  if (!error.value) close()
}

async function stopFollowing(): Promise<void> {
  if (!props.type) return
  saving.value = true
  error.value = (await library.unlink(props.type)) ?? ''
  saving.value = false
  if (!error.value) close()
}

function openLibrary(): void {
  close()
  void router.replace({ query: { view: 'types', entry: props.type?.template_id ?? undefined } })
}
</script>

<style scoped>
.rules {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
</style>
