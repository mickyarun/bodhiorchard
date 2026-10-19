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

<!-- Rules → Work week: the days leave is counted on. -->
<template>
  <LeaveSectionCard
    icon="mdi-calendar-week"
    title="Work week"
    caption="Leave only counts on working days. Weekends and holidays are skipped."
  >
    <WorkingDayChips v-model="days" hide-label />
    <div class="d-flex flex-wrap ga-2 mt-2">
      <v-btn
        v-for="preset in WORK_WEEK_PRESETS"
        :key="preset.label"
        size="small"
        variant="text"
        :aria-label="`Set working days to ${preset.label}`"
        @click="days = [...preset.days]"
      >
        {{ preset.label }}
      </v-btn>
    </div>
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import WorkingDayChips from '@/components/leave/settings/WorkingDayChips.vue'
import { WORK_WEEK_PRESETS } from '@/utils/leavePolicyDisplay'

const days = defineModel<number[]>({ required: true })
</script>
