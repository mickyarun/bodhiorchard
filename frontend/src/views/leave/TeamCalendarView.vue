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
  <AppPage title="Team calendar" :subtitle="subtitle">
    <template #actions>
      <div class="month-nav">
        <v-btn icon="mdi-chevron-left" variant="outlined" size="small" aria-label="Previous month" @click="calendar.step(-1)" />
        <span class="month-nav__title" aria-live="polite">{{ monthTitle(calendar.month.value) }}</span>
        <v-btn icon="mdi-chevron-right" variant="outlined" size="small" aria-label="Next month" @click="calendar.step(1)" />
      </div>
      <v-btn variant="outlined" @click="calendar.today()">Today</v-btn>
    </template>

    <CalendarLegend />
    <AppCallout v-if="calendar.error.value" variant="error">{{ calendar.error.value }}</AppCallout>

    <section class="calendar" :aria-label="monthTitle(calendar.month.value)">
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
    </section>

    <CalendarDayDrawer
      :day="selected"
      :entries="calendar.data.value.entries"
      :context="calendar.context.value"
      @close="selected = null"
    />
  </AppPage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import CalendarAgenda from '@/components/leave/calendar/CalendarAgenda.vue'
import CalendarDayDrawer from '@/components/leave/calendar/CalendarDayDrawer.vue'
import CalendarLegend from '@/components/leave/calendar/CalendarLegend.vue'
import CalendarMonthGrid from '@/components/leave/calendar/CalendarMonthGrid.vue'
import { useTeamCalendar } from '@/composables/useTeamCalendar'
import { monthSummary } from '@/utils/leaveCalendar'
import { monthTitle, toIsoDate } from '@/utils/leaveDates'

const NARROW_BELOW_PX = 720

const calendar = useTeamCalendar()
const { width } = useDisplay()
const narrow = computed(() => width.value < NARROW_BELOW_PX)
const today = toIsoDate(new Date())
const selected = ref<string | null>(null)
const subtitle = computed(() => {
  if (calendar.loading.value || calendar.error.value) return ''
  return (
    monthSummary(calendar.data.value.entries, calendar.month.value) ||
    'Nobody else is on leave or working from home this month.'
  )
})
</script>

<style scoped>
.month-nav {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.month-nav__title {
  min-width: 132px;
  text-align: center;
  font-size: 15px;
  font-weight: 600;
}
.calendar {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  overflow: hidden;
  min-width: 0;
}
</style>
