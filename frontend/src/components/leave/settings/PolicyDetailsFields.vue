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

<!-- A policy's name and where it applies: country, region (for public
     holidays) and the timezone its days are counted in. Used when adding
     a policy and in "Edit details". -->
<template>
  <LeaveFormGrid>
    <v-text-field
      v-model="name"
      label="Name"
      placeholder="e.g. UK Office"
      maxlength="100"
      autofocus
      class="span-2"
      v-bind="FIELD_PROPS"
    />
    <RegionFields v-model:country="country" v-model:subdivision="subdivision" />
    <v-autocomplete
      v-model="timezone"
      :items="timezones"
      label="Timezone"
      hint="Days and request cut-offs are counted in this timezone."
      persistent-hint
      auto-select-first
      class="span-2"
      v-bind="FIELD_PROPS"
    />
  </LeaveFormGrid>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LeaveFormGrid from '@/components/leave/settings/LeaveFormGrid.vue'
import RegionFields from '@/components/leave/settings/RegionFields.vue'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'
import { timezoneOptions } from '@/utils/timezones'

const name = defineModel<string>('name', { required: true })
const country = defineModel<string | null>('country', { required: true })
const subdivision = defineModel<string | null>('subdivision', { required: true })
const timezone = defineModel<string>('timezone', { required: true })

const timezones = computed(() => timezoneOptions(timezone.value))
</script>
