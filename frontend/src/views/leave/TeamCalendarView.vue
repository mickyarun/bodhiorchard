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

<!-- Team calendar: who's on leave or working from home this month.
     A month grid on wide screens, an agenda list under 720px. -->
<template>
  <div class="pa-6 team-calendar">
    <div class="d-flex align-start justify-space-between flex-wrap ga-3 mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold bo-display">Team calendar</h1>
        <p class="text-body-2 text-medium-emphasis">Who's on leave or working from home.</p>
      </div>
      <div class="d-flex align-center ga-1">
        <v-btn icon="mdi-chevron-left" variant="text" size="small" aria-label="Previous month" @click="calendar.step(-1)" />
        <span class="text-subtitle-1 font-weight-bold month-title">{{ monthTitle(calendar.month.value) }}</span>
        <v-btn icon="mdi-chevron-right" variant="text" size="small" aria-label="Next month" @click="calendar.step(1)" />
        <v-btn variant="tonal" size="small" class="ml-2" @click="calendar.today()">Today</v-btn>
      </div>
    </div>

    <AppCallout v-if="calendar.error.value" variant="error" class="mb-4">{{ calendar.error.value }}</AppCallout>

    <v-card color="surface" rounded="lg">
      <v-progress-linear v-if="calendar.loading.value" indeterminate color="primary" />
      <CalendarAgenda
        v-if="narrow"
        :month="calendar.month.value"
        :entries="calendar.data.value.entries"
        :context="calendar.context.value"
        :today="today"
        @select="selected = $event"
      />
      <CalendarMonthGrid
        v-else
        :weeks="calendar.weeks.value"
        :entries="calendar.data.value.entries"
        :context="calendar.context.value"
        :today="today"
        @select="selected = $event"
      />
    </v-card>

    <div class="d-flex flex-wrap ga-4 mt-3 text-caption text-medium-emphasis">
      <span>Dashed outline: work from home</span>
      <span>◐ Half day</span>
      <span>Faded: waiting for approval</span>
    </div>

    <CalendarDayDrawer
      :day="selected"
      :entries="calendar.data.value.entries"
      :context="calendar.context.value"
      @close="selected = null"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import CalendarAgenda from '@/components/leave/calendar/CalendarAgenda.vue'
import CalendarDayDrawer from '@/components/leave/calendar/CalendarDayDrawer.vue'
import CalendarMonthGrid from '@/components/leave/calendar/CalendarMonthGrid.vue'
import { useTeamCalendar } from '@/composables/useTeamCalendar'
import { monthTitle, toIsoDate } from '@/utils/leaveDates'

const NARROW_BELOW_PX = 720

const calendar = useTeamCalendar()
const { width } = useDisplay()
const narrow = computed(() => width.value < NARROW_BELOW_PX)
const today = toIsoDate(new Date())
const selected = ref<string | null>(null)
</script>

<style scoped>
.team-calendar {
  max-width: 1120px;
}
.month-title {
  min-width: 140px;
  text-align: center;
}
</style>
