<template>
  <v-card class="standup-panel" elevation="8" rounded="lg">
    <!-- Header -->
    <div class="d-flex align-center px-4 pt-3 pb-1">
      <v-icon icon="mdi-calendar-clock-outline" size="24" class="mr-2" color="warning" />
      <div class="flex-grow-1">
        <div class="text-subtitle-1 font-weight-bold">Daily Standup</div>
        <div class="text-caption text-medium-emphasis">
          {{ formattedDate }}
        </div>
      </div>
      <v-btn
        icon="mdi-chevron-left"
        size="x-small"
        variant="text"
        :disabled="loading"
        @click="navigateDay(-1)"
      />
      <v-btn
        icon="mdi-chevron-right"
        size="x-small"
        variant="text"
        :disabled="loading || isToday"
        @click="navigateDay(1)"
      />
      <v-btn
        icon="mdi-close"
        size="x-small"
        variant="text"
        @click="emit('close')"
      />
    </div>

    <!-- Since indicator -->
    <div v-if="report?.since_timestamp" class="px-4 pb-2">
      <v-chip size="x-small" variant="tonal" color="grey" prepend-icon="mdi-clock-outline">
        Since {{ formattedSince }}
      </v-chip>
    </div>

    <v-divider />

    <!-- Loading -->
    <div v-if="loading" class="d-flex justify-center align-center pa-8">
      <v-progress-circular indeterminate color="warning" size="32" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="pa-4 text-center">
      <v-icon icon="mdi-alert-circle-outline" color="grey" size="40" class="mb-2" />
      <div class="text-body-2 text-medium-emphasis">{{ error }}</div>
    </div>

    <!-- Content -->
    <div v-else-if="report" class="standup-panel__content">
      <!-- Global flags -->
      <div v-if="globalFlags.length > 0" class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">Risk Flags</div>
        <div class="d-flex flex-column ga-1">
          <v-alert
            v-for="(flag, i) in globalFlags"
            :key="i"
            :type="alertType(flag.severity)"
            density="compact"
            variant="tonal"
            class="text-body-2"
          >
            {{ flag.description }}
          </v-alert>
        </div>
      </div>

      <v-divider v-if="globalFlags.length > 0" />

      <!-- Members -->
      <div class="pa-3">
        <div class="text-overline text-medium-emphasis mb-2">
          Team Activity ({{ report.members.length }})
        </div>
        <div class="d-flex flex-column ga-2">
          <v-card
            v-for="member in sortedMembers"
            :key="member.user_id"
            variant="outlined"
            density="compact"
            rounded="lg"
            class="pa-2"
          >
            <!-- Member header -->
            <div class="d-flex align-center mb-1">
              <v-avatar size="24" class="mr-2">
                <v-img v-if="member.avatar_url" :src="member.avatar_url" />
                <v-icon v-else icon="mdi-account" size="16" />
              </v-avatar>
              <div class="text-body-2 font-weight-medium text-truncate flex-grow-1">
                {{ member.name }}
              </div>
              <v-chip
                size="x-small"
                variant="tonal"
                :color="levelColor(member.level)"
              >
                Lv{{ member.level }}
              </v-chip>
            </div>

            <!-- Activity stats -->
            <div class="d-flex flex-wrap ga-1 mb-1">
              <v-chip
                v-if="member.commits_count > 0"
                size="x-small" variant="tonal" color="success"
                prepend-icon="mdi-source-commit"
              >
                {{ member.commits_count }}
              </v-chip>
              <v-chip
                v-if="member.prs_merged > 0"
                size="x-small" variant="tonal" color="purple"
                prepend-icon="mdi-source-merge"
              >
                {{ member.prs_merged }} merged
              </v-chip>
              <v-chip
                v-if="member.prs_opened > 0"
                size="x-small" variant="tonal" color="blue"
                prepend-icon="mdi-source-pull"
              >
                {{ member.prs_opened }} opened
              </v-chip>
              <v-chip
                v-if="member.bugs_resolved > 0"
                size="x-small" variant="tonal" color="error"
                prepend-icon="mdi-bug-check-outline"
              >
                {{ member.bugs_resolved }} fixed
              </v-chip>
              <v-chip
                v-if="member.xp_earned > 0"
                size="x-small" variant="tonal" color="amber"
                prepend-icon="mdi-star-outline"
              >
                +{{ member.xp_earned }} XP
              </v-chip>
            </div>

            <!-- BUD transitions -->
            <div v-if="member.buds_transitioned.length > 0" class="mb-1">
              <div
                v-for="(t, ti) in member.buds_transitioned"
                :key="ti"
                class="text-caption text-medium-emphasis"
              >
                BUD-{{ t.bud_number }}: {{ t.from_stage }} → {{ t.to_stage }}
              </div>
            </div>

            <!-- Member-level flags -->
            <div v-if="member.flags.length > 0">
              <v-chip
                v-for="(flag, fi) in member.flags"
                :key="fi"
                size="x-small"
                variant="tonal"
                :color="flagColor(flag.severity)"
                :prepend-icon="flagIcon(flag.type)"
                class="mr-1"
              >
                {{ flagLabel(flag.type) }}
              </v-chip>
            </div>

            <!-- No activity indicator -->
            <div
              v-if="memberTotal(member) === 0 && member.flags.length === 0"
              class="text-caption text-disabled"
            >
              No recorded activity
            </div>
          </v-card>
        </div>
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { MemberStandupItem } from '@/types/standup'
import { useStandupStore } from '@/stores/standup'
import { storeToRefs } from 'pinia'

const emit = defineEmits<{ (e: 'close'): void }>()

const store = useStandupStore()
const { report, loading, error } = storeToRefs(store)

const currentDate = ref(new Date().toISOString().slice(0, 10))

const isToday = computed(() => currentDate.value === new Date().toISOString().slice(0, 10))

const formattedDate = computed(() => {
  const d = new Date(currentDate.value + 'T00:00:00')
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
})

const formattedSince = computed(() => {
  if (!report.value?.since_timestamp) return ''
  const d = new Date(report.value.since_timestamp)
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
})

const globalFlags = computed(() =>
  (report.value?.flags ?? []).filter(f => !f.user_id),
)

const sortedMembers = computed(() => {
  if (!report.value?.members) return []
  return [...report.value.members].sort((a, b) => memberTotal(b) - memberTotal(a))
})

function memberTotal(m: MemberStandupItem): number {
  return m.commits_count + m.prs_opened + m.prs_merged + m.buds_transitioned.length + m.bugs_resolved
}

function navigateDay(offset: number): void {
  const d = new Date(currentDate.value + 'T00:00:00')
  d.setDate(d.getDate() + offset)
  const today = new Date().toISOString().slice(0, 10)
  const target = d.toISOString().slice(0, 10)
  if (target > today) return // don't navigate past today
  currentDate.value = target
  if (target === today) {
    store.fetchToday()
  } else {
    store.fetchByDate(currentDate.value)
  }
}

function alertType(severity: string): 'info' | 'warning' | 'error' {
  if (severity === 'critical') return 'error'
  if (severity === 'warning') return 'warning'
  return 'info'
}

function flagColor(severity: string): string {
  if (severity === 'critical') return 'error'
  if (severity === 'warning') return 'warning'
  return 'info'
}

function flagIcon(type: string): string {
  const map: Record<string, string> = {
    no_activity: 'mdi-sleep',
    bud_lagging: 'mdi-clock-alert-outline',
    critical_bugs: 'mdi-bug-outline',
    bus_factor: 'mdi-account-alert-outline',
  }
  return map[type] ?? 'mdi-alert-outline'
}

function flagLabel(type: string): string {
  const map: Record<string, string> = {
    no_activity: 'Inactive',
    bud_lagging: 'Lagging',
    critical_bugs: 'Critical Bug',
    bus_factor: 'Bus Factor',
  }
  return map[type] ?? type
}

function levelColor(level: number): string {
  if (level >= 5) return 'amber'
  if (level >= 3) return 'success'
  return 'grey'
}

onMounted(() => {
  store.fetchToday()
})
</script>

<style scoped>
.standup-panel {
  position: absolute;
  top: 8px;
  right: 8px;
  bottom: 8px;
  width: 360px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  background: rgba(var(--v-theme-surface), 0.95) !important;
  backdrop-filter: blur(8px);
}

.standup-panel__content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
