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

<!-- Celebrations card: whether the birthday and work anniversary are
     announced. Each switch saves straight away. -->
<template>
  <AppPanel title="Celebrations">
    <p class="celebrations__note">Announcements show the day and month only, never the year.</p>
    <v-switch
      v-for="pref in CELEBRATION_PREFS"
      :key="pref.key"
      :model-value="personal[pref.key]"
      :label="isSelf ? pref.selfLabel : pref.otherLabel"
      :disabled="!canChange(personal[pref.key]) || saving !== null"
      :loading="saving === pref.key"
      :hint="lockedHint(personal[pref.key])"
      :persistent-hint="!!lockedHint(personal[pref.key])"
      color="primary"
      density="compact"
      inset
      @update:model-value="value => setPref(pref.key, !!value)"
    />
    <AppCallout v-if="error" variant="error" class="mt-2">{{ error }}</AppCallout>
  </AppPanel>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPanel from '@/components/common/AppPanel.vue'
import { useEmployeesStore } from '@/stores/employees'
import type { EmployeePersonalRead } from '@/types/employee'

const props = defineProps<{
  employeeId: string
  personal: EmployeePersonalRead
  mode: 'hr' | 'self' | 'view'
  /** The viewer is looking at their own record (HR included). */
  isSelf: boolean
}>()

type PrefKey = 'celebrate_birthday' | 'celebrate_anniversary'
const CELEBRATION_PREFS: { key: PrefKey; selfLabel: string; otherLabel: string }[] = [
  { key: 'celebrate_birthday', selfLabel: 'Announce my birthday', otherLabel: 'Announce birthday' },
  {
    key: 'celebrate_anniversary',
    selfLabel: 'Announce my work anniversary',
    otherLabel: 'Announce work anniversary',
  },
]

const store = useEmployeesStore()
const saving = ref<PrefKey | null>(null)
const error = ref('')

/**
 * The opt-out is the employee's: they may switch it either way. HR may
 * mute on someone's behalf but never unmute — the API enforces the same.
 */
function canChange(current: boolean): boolean {
  if (props.isSelf) return true
  return props.mode === 'hr' && current
}

function lockedHint(current: boolean): string {
  if (props.isSelf || props.mode !== 'hr' || current) return ''
  return 'Muted by them or on their behalf. Only they can turn it back on.'
}

async function setPref(key: PrefKey, value: boolean): Promise<void> {
  saving.value = key
  error.value = (await store.updateCelebrationPrefs(props.employeeId, { [key]: value })) ?? ''
  saving.value = null
}
</script>

<style scoped>
.celebrations__note {
  margin: -4px 0 4px;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
