<template>
  <div>
    <div class="d-flex align-center mb-4">
      <v-icon size="20" class="mr-2" color="secondary">mdi-horse-variant-fast</v-icon>
      <span class="text-subtitle-2 font-weight-bold text-uppercase" style="letter-spacing: 0.05em;">
        Vehicles
      </span>
      <v-spacer />
      <v-chip size="x-small" variant="tonal" color="secondary">
        <v-icon start size="12">mdi-star-four-points</v-icon>
        {{ skillPoints }} SP
      </v-chip>
    </div>

    <div
      v-for="vehicle in vehicles"
      :key="vehicle.id"
      class="vehicle-row d-flex align-center pa-3 rounded-lg mb-2"
      :class="{ 'vehicle-row--unlocked': isUnlocked(vehicle.id) }"
    >
      <div
        class="vehicle-icon d-flex align-center justify-center rounded-lg mr-3"
        :class="isUnlocked(vehicle.id) ? 'bg-success' : 'bg-surface-variant'"
        style="width: 40px; height: 40px;"
      >
        <v-icon
          :color="isUnlocked(vehicle.id) ? 'white' : 'medium-emphasis'"
          size="22"
        >
          mdi-horse-variant
        </v-icon>
      </div>

      <div class="flex-grow-1">
        <div class="text-body-2 font-weight-medium">{{ vehicle.name }}</div>
        <div class="text-caption text-medium-emphasis">
          {{ isUnlocked(vehicle.id) ? 'Press V in garden to ride' : `${vehicle.unlockCost} skill points` }}
        </div>
      </div>

      <v-btn
        v-if="!isUnlocked(vehicle.id)"
        size="small"
        variant="flat"
        color="primary"
        :loading="unlocking === vehicle.id"
        :disabled="skillPoints < vehicle.unlockCost"
        @click="unlock(vehicle.id)"
      >
        <v-icon start size="16">mdi-lock-open-variant</v-icon>
        Unlock
      </v-btn>
      <v-icon v-else color="success" size="20">mdi-check-circle</v-icon>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import api from '@/services/api'
import { useXPStore } from '@/stores/xp'

const xpStore = useXPStore()
const unlocking = ref<string | null>(null)

const vehicles = [
  { id: 'horse', name: 'Horse', unlockCost: 50 },
]

const skillPoints = computed(() => xpStore.profile?.skill_points ?? 0)

function isUnlocked(vehicleId: string): boolean {
  return xpStore.profile?.vehicle_unlocks?.includes(vehicleId) ?? false
}

async function unlock(vehicleId: string): Promise<void> {
  unlocking.value = vehicleId
  try {
    await api.post('/v1/xp/unlock-vehicle', { vehicle_id: vehicleId })
    await xpStore.fetchProfile()
  } catch (err) {
    console.error('[VehicleUnlockPanel] unlock failed:', err)
  } finally {
    unlocking.value = null
  }
}
</script>

<style scoped>
.vehicle-row {
  border: 1px solid rgba(var(--v-border-color), 0.08);
  transition: border-color 0.2s;
}
.vehicle-row:hover {
  border-color: rgba(var(--v-theme-primary), 0.3);
}
.vehicle-row--unlocked {
  border-color: rgba(var(--v-theme-success), 0.2);
  background: rgba(var(--v-theme-success), 0.04);
}
</style>
