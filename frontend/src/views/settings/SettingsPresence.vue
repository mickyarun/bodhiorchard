<template>
  <div class="settings-page">
    <!-- Header -->
    <div class="settings-header pa-6 pb-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h5 font-weight-bold">Presence & Auto Mode</div>
          <div class="text-body-2 text-medium-emphasis">
            Configure working days, hours, and timezone for automatic presence inference
          </div>
        </div>
        <div class="d-flex ga-2">
          <v-btn variant="text" prepend-icon="mdi-arrow-left" :to="{ name: 'settings' }">
            Back to Settings
          </v-btn>
          <v-btn
            color="primary"
            prepend-icon="mdi-content-save-outline"
            :loading="settingsStore.saving"
            :disabled="!isValid"
            @click="save"
          >
            Save Changes
          </v-btn>
        </div>
      </div>

      <v-alert v-if="settingsStore.error" type="error" variant="tonal" class="mt-4" closable>
        {{ settingsStore.error }}
      </v-alert>
      <v-alert
        v-if="settingsStore.saveSuccess"
        type="success"
        variant="tonal"
        class="mt-4"
        closable
        @click:close="settingsStore.saveSuccess = false"
      >
        Settings saved successfully.
      </v-alert>
    </div>

    <!-- Content -->
    <div class="px-6 pb-6">
      <div v-if="settingsStore.loading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <template v-else>
        <!-- ─── TIMEZONE-NOT-SET WARNING ─────────────────────── -->
        <v-alert
          v-if="presence.timezone === null"
          type="warning"
          variant="tonal"
          class="mb-6"
          icon="mdi-earth-off"
        >
          <div class="text-body-2 font-weight-medium">No timezone configured</div>
          <div class="text-caption">
            The simulator currently uses the server's local time. Set a primary
            office timezone below so Saturday-office or non-9-to-5 schedules
            work correctly for every team member.
          </div>
        </v-alert>

        <!-- ─── AUTO MODE CARD ────────────────────────────── -->
        <v-card class="pa-6 mb-6" variant="outlined">
          <div class="d-flex align-center ga-3 mb-4">
            <v-avatar size="36" color="surface-variant" rounded="lg">
              <v-icon icon="mdi-robot-outline" size="22" />
            </v-avatar>
            <div>
              <div class="text-body-1 font-weight-medium">Auto Mode</div>
              <div class="text-caption text-medium-emphasis">
                Automatically infer team presence from working hours and dev activity
              </div>
            </div>
          </div>
          <v-switch
            v-model="presence.autoModeEnabled"
            label="Enable automatic presence inference"
            color="primary"
            hide-details
            density="compact"
            class="mb-2"
          />
          <div class="text-caption text-medium-emphasis">
            When off, members stay wherever takeover or manual placement put them.
            Dev activity is still tracked so turning auto mode back on is seamless.
          </div>
        </v-card>

        <!-- ─── WORKING DAYS CARD ─────────────────────────── -->
        <v-card class="pa-6 mb-6" variant="outlined" :disabled="!presence.autoModeEnabled">
          <div class="d-flex align-center ga-3 mb-4">
            <v-avatar size="36" color="surface-variant" rounded="lg">
              <v-icon icon="mdi-calendar-week" size="22" />
            </v-avatar>
            <div>
              <div class="text-body-1 font-weight-medium">Working Days</div>
              <div class="text-caption text-medium-emphasis">
                Days when team members are expected to be at their desks
              </div>
            </div>
          </div>

          <div class="d-flex flex-wrap ga-2 mb-3">
            <v-chip
              v-for="day in WEEKDAY_ORDER"
              :key="day.key"
              :color="isDaySelected(day.key) ? 'primary' : undefined"
              :variant="isDaySelected(day.key) ? 'flat' : 'outlined'"
              filter
              :disabled="!presence.autoModeEnabled"
              @click="toggleDay(day.key)"
            >
              {{ day.label }}
            </v-chip>
          </div>

          <div class="d-flex ga-2 flex-wrap">
            <v-btn
              size="small"
              variant="text"
              :disabled="!presence.autoModeEnabled"
              @click="setDaysPreset('weekdays')"
            >
              Mon–Fri
            </v-btn>
            <v-btn
              size="small"
              variant="text"
              :disabled="!presence.autoModeEnabled"
              @click="setDaysPreset('weekdays-plus-sat')"
            >
              Mon–Sat
            </v-btn>
            <v-btn
              size="small"
              variant="text"
              :disabled="!presence.autoModeEnabled"
              @click="setDaysPreset('all-seven')"
            >
              All 7 days
            </v-btn>
          </div>

          <div v-if="presence.workingDays.length === 0" class="text-caption text-error mt-2">
            Select at least one working day.
          </div>
        </v-card>

        <!-- ─── WORKING HOURS CARD ────────────────────────── -->
        <v-card class="pa-6 mb-6" variant="outlined" :disabled="!presence.autoModeEnabled">
          <div class="d-flex align-center ga-3 mb-4">
            <v-avatar size="36" color="surface-variant" rounded="lg">
              <v-icon icon="mdi-clock-time-eight-outline" size="22" />
            </v-avatar>
            <div>
              <div class="text-body-1 font-weight-medium">Working Hours</div>
              <div class="text-caption text-medium-emphasis">
                Standard shift window. Minutes are accepted but the simulator
                currently rounds to the whole hour.
              </div>
            </div>
          </div>

          <v-row class="ga-0" no-gutters>
            <v-col cols="12" sm="6" class="pr-sm-2">
              <v-text-field
                v-model="presence.workingHoursStart"
                type="time"
                label="Start time"
                variant="outlined"
                density="compact"
                :disabled="!presence.autoModeEnabled"
                :error="!hoursAreOrdered"
                hide-details="auto"
              />
            </v-col>
            <v-col cols="12" sm="6" class="pl-sm-2">
              <v-text-field
                v-model="presence.workingHoursEnd"
                type="time"
                label="End time"
                variant="outlined"
                density="compact"
                :disabled="!presence.autoModeEnabled"
                :error="!hoursAreOrdered"
                hide-details="auto"
              />
            </v-col>
          </v-row>

          <div v-if="!hoursAreOrdered" class="text-caption text-error mt-2">
            Start time must be before end time.
          </div>
        </v-card>

        <!-- ─── TIMEZONE CARD ─────────────────────────────── -->
        <v-card class="pa-6 mb-6" variant="outlined" :disabled="!presence.autoModeEnabled">
          <div class="d-flex align-center ga-3 mb-4">
            <v-avatar size="36" color="surface-variant" rounded="lg">
              <v-icon icon="mdi-earth" size="22" />
            </v-avatar>
            <div>
              <div class="text-body-1 font-weight-medium">Timezone</div>
              <div class="text-caption text-medium-emphasis">
                The IANA zone used to interpret working hours and days.
              </div>
            </div>
          </div>

          <v-autocomplete
            v-model="timezoneSelection"
            :items="timezoneList"
            label="Timezone"
            variant="outlined"
            density="compact"
            :disabled="!presence.autoModeEnabled"
            clearable
            placeholder="Use server time"
            hide-details
            class="mb-3"
            style="max-width: 360px"
          />

          <div class="d-flex ga-2 flex-wrap">
            <v-btn
              size="small"
              variant="text"
              prepend-icon="mdi-crosshairs-gps"
              :disabled="!presence.autoModeEnabled"
              @click="detectBrowserTimezone"
            >
              Detect browser timezone
            </v-btn>
            <v-btn
              size="small"
              variant="text"
              prepend-icon="mdi-restart"
              :disabled="!presence.autoModeEnabled"
              @click="presence.timezone = null"
            >
              Use server time
            </v-btn>
          </div>
        </v-card>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'

type WeekdayKey = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun'

interface WeekdayOption {
  key: WeekdayKey
  label: string
}

// Order matches ISO week (Mon first). Stored order in `workingDays` is free;
// we always normalise to this canonical order on save so the backend sees
// a stable list regardless of click sequence.
const WEEKDAY_ORDER: readonly WeekdayOption[] = [
  { key: 'mon', label: 'Mon' },
  { key: 'tue', label: 'Tue' },
  { key: 'wed', label: 'Wed' },
  { key: 'thu', label: 'Thu' },
  { key: 'fri', label: 'Fri' },
  { key: 'sat', label: 'Sat' },
  { key: 'sun', label: 'Sun' },
] as const

const DAYS_PRESETS = {
  'weekdays':          ['mon', 'tue', 'wed', 'thu', 'fri'],
  'weekdays-plus-sat': ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
  'all-seven':         ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'],
} as const satisfies Record<string, WeekdayKey[]>

type DaysPresetId = keyof typeof DAYS_PRESETS

const settingsStore = useSettingsStore()
const presence = computed(() => settingsStore.connections.presence)

// ─── Working days ──────────────────────────────────────────────────────

function isDaySelected(day: WeekdayKey): boolean {
  return presence.value.workingDays.includes(day)
}

function toggleDay(day: WeekdayKey): void {
  const current = new Set(presence.value.workingDays)
  if (current.has(day)) current.delete(day)
  else current.add(day)
  presence.value.workingDays = normaliseDayOrder([...current])
}

function setDaysPreset(preset: DaysPresetId): void {
  presence.value.workingDays = [...DAYS_PRESETS[preset]]
}

/** Re-sort a day list so it always matches the canonical WEEKDAY_ORDER. */
function normaliseDayOrder(days: WeekdayKey[]): WeekdayKey[] {
  const set = new Set(days)
  return WEEKDAY_ORDER.map(d => d.key).filter(k => set.has(k))
}

// ─── Working hours validation ──────────────────────────────────────────

const hoursAreOrdered = computed(() => {
  const s = presence.value.workingHoursStart
  const e = presence.value.workingHoursEnd
  if (!s || !e) return false
  // Lexicographic HH:MM comparison works thanks to zero-padding.
  return s < e
})

// ─── Timezone dropdown ─────────────────────────────────────────────────

const timezoneList = computed<string[]>(() => {
  // `Intl.supportedValuesOf('timeZone')` is available in Chrome 99+, FF 93+,
  // Safari 15.4+. Fall back to a short curated list for older browsers.
  try {
    const supportedValuesOf = (Intl as unknown as {
      supportedValuesOf?: (key: string) => string[]
    }).supportedValuesOf
    if (typeof supportedValuesOf === 'function') {
      return supportedValuesOf('timeZone')
    }
  } catch (_err) {
    // fallthrough
  }
  return [...FALLBACK_TIMEZONES]
})

// Hand-picked short list for browsers without `Intl.supportedValuesOf`.
const FALLBACK_TIMEZONES: readonly string[] = [
  'UTC',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Madrid',
  'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Singapore', 'Asia/Kolkata', 'Asia/Dubai',
  'Australia/Sydney', 'Pacific/Auckland',
] as const

// v-autocomplete with `clearable` emits `null` on clear, which maps
// cleanly to the backend `timezone: null` sentinel. We just pass the
// value through instead of wrapping.
const timezoneSelection = computed<string | null>({
  get: () => presence.value.timezone,
  set: (value) => {
    presence.value.timezone = value ?? null
  },
})

function detectBrowserTimezone(): void {
  try {
    presence.value.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  } catch (_err) {
    // Should never happen in a modern browser; leave unchanged on failure.
  }
}

// ─── Save gate ─────────────────────────────────────────────────────────

const isValid = computed(() =>
  presence.value.workingDays.length > 0 && hoursAreOrdered.value,
)

async function save(): Promise<void> {
  if (!isValid.value) return
  await settingsStore.saveConnections()
}

onMounted(async () => {
  // Fetch if the store hasn't been primed yet. Mirrors SettingsQAAutomation.vue.
  if (!settingsStore.connections.presence.timezone && !settingsStore.saving) {
    await settingsStore.fetchConnections()
  }
})
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.settings-header {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
</style>
