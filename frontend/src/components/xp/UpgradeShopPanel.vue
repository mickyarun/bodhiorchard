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
  <div class="upgrade-shop">
    <!-- SP balance -->
    <div class="d-flex align-center mb-5">
      <span class="text-h6 font-weight-bold">Upgrades</span>
      <v-spacer />
      <v-chip variant="flat" color="secondary" size="small">
        <v-icon start size="14">mdi-star-four-points</v-icon>
        {{ formatSP(skillPoints) }} SP
      </v-chip>
    </div>

    <!-- ─── HOUSE SECTION ─── -->
    <div class="d-flex align-center mb-3">
      <v-icon size="18" class="mr-2" color="secondary">mdi-home-group</v-icon>
      <span class="text-subtitle-2 font-weight-bold text-uppercase" style="letter-spacing: 0.05em;">
        House
      </span>
      <v-spacer />
      <v-chip size="x-small" variant="tonal" color="secondary">
        Tier {{ currentTier }}
      </v-chip>
    </div>

    <div class="upgrade-shop__grid">
      <v-tooltip
        v-for="tier in houseTiers"
        :key="tier.tier"
        :text="tierTooltip(tier)"
        location="top"
      >
        <template #activator="{ props: tp }">
          <div
            v-bind="tp"
            class="upgrade-shop__card"
            :class="houseCardClass(tier)"
            @click="onHouseClick(tier)"
          >
            <img
              :src="'/' + tier.thumbnail"
              :alt="tier.name"
              class="upgrade-shop__img"
            >
            <div class="upgrade-shop__name">{{ tier.name }}</div>

            <!-- Current badge -->
            <div v-if="tier.tier === currentTier" class="upgrade-shop__badge">
              <v-icon icon="mdi-check-circle" color="success" size="20" />
            </div>

            <!-- Lock overlay for unaffordable future tiers -->
            <div
              v-else-if="tier.tier > currentTier && skillPoints < tier.unlockCost"
              class="upgrade-shop__lock-overlay"
            >
              <v-icon icon="mdi-lock" size="28" />
              <v-chip size="x-small" color="secondary" variant="flat" class="upgrade-shop__cost-badge">
                {{ tier.unlockCost }} SP
              </v-chip>
            </div>

            <!-- Affordable upgrade chip -->
            <div
              v-else-if="tier.tier > currentTier"
              class="upgrade-shop__upgrade-overlay"
            >
              <v-btn
                size="x-small"
                variant="flat"
                color="secondary"
                :loading="upgrading === tier.tier"
                @click.stop="upgradeTier(tier.tier)"
              >
                <v-icon start size="14">mdi-arrow-up-bold</v-icon>
                {{ tier.unlockCost }} SP
              </v-btn>
            </div>
          </div>
        </template>
      </v-tooltip>
    </div>

    <!-- ─── VEHICLES SECTION ─── -->
    <div class="d-flex align-center mb-3 mt-6">
      <v-icon size="18" class="mr-2" color="secondary">mdi-horse-variant-fast</v-icon>
      <span class="text-subtitle-2 font-weight-bold text-uppercase" style="letter-spacing: 0.05em;">
        Vehicles
      </span>
    </div>

    <div class="upgrade-shop__grid">
      <v-tooltip
        v-for="v in vehicles"
        :key="v.id"
        :text="vehicleTooltip(v)"
        location="top"
      >
        <template #activator="{ props: tp }">
          <div
            v-bind="tp"
            class="upgrade-shop__card"
            :class="vehicleCardClass(v)"
            @click="onVehicleClick(v)"
          >
            <img
              :src="'/' + v.thumbnail"
              :alt="v.name"
              class="upgrade-shop__img"
              @error="($event.target as HTMLImageElement).style.display = 'none'"
            >
            <!-- Fallback icon when no thumbnail -->
            <div class="upgrade-shop__icon-fallback">
              <v-icon size="48" color="secondary">mdi-horse-variant</v-icon>
            </div>

            <div class="upgrade-shop__name">{{ v.name }}</div>

            <!-- Owned badge -->
            <div v-if="isVehicleUnlocked(v.id)" class="upgrade-shop__badge">
              <v-icon icon="mdi-check-circle" color="success" size="20" />
            </div>

            <!-- Lock overlay -->
            <div
              v-else-if="skillPoints < v.unlockCost"
              class="upgrade-shop__lock-overlay"
            >
              <v-icon icon="mdi-lock" size="28" />
              <v-chip size="x-small" color="secondary" variant="flat" class="upgrade-shop__cost-badge">
                {{ v.unlockCost }} SP
              </v-chip>
            </div>

            <!-- Affordable unlock -->
            <div v-else class="upgrade-shop__upgrade-overlay">
              <v-btn
                size="x-small"
                variant="flat"
                color="secondary"
                :loading="unlockingVehicle === v.id"
                @click.stop="unlockVehicle(v.id)"
              >
                <v-icon start size="14">mdi-lock-open-variant</v-icon>
                {{ v.unlockCost }} SP
              </v-btn>
            </div>
          </div>
        </template>
      </v-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import api from '@/services/api'
import { useXPStore } from '@/stores/xp'
import { formatSP } from '@/utils/format'
import { HOUSE_TIERS, type HouseTierDef } from '@/engine/buildings/HouseTierConfig'
import { getAllVehicles, type VehicleDef } from '@/engine/vehicles/VehicleManifest'

const xpStore = useXPStore()
const upgrading = ref<number | null>(null)
const unlockingVehicle = ref<string | null>(null)

const houseTiers = HOUSE_TIERS
const vehicles = getAllVehicles()
const currentTier = computed(() => xpStore.profile?.house_level ?? 1)
const skillPoints = computed(() => xpStore.profile?.skill_points ?? 0)

function isVehicleUnlocked(id: string): boolean {
  return xpStore.profile?.vehicle_unlocks?.includes(id) ?? false
}

// ─── Card class helpers ─────────────────────────

function houseCardClass(tier: HouseTierDef): Record<string, boolean> {
  const isCurrent = tier.tier === currentTier.value
  const isPast = tier.tier < currentTier.value
  const canAfford = skillPoints.value >= tier.unlockCost
  return {
    'upgrade-shop__card--current': isCurrent,
    'upgrade-shop__card--owned': isPast,
    'upgrade-shop__card--available': !isCurrent && !isPast && canAfford,
    'upgrade-shop__card--locked': !isCurrent && !isPast && !canAfford,
  }
}

function vehicleCardClass(v: VehicleDef): Record<string, boolean> {
  const owned = isVehicleUnlocked(v.id)
  const canAfford = skillPoints.value >= v.unlockCost
  return {
    'upgrade-shop__card--current': owned,
    'upgrade-shop__card--available': !owned && canAfford,
    'upgrade-shop__card--locked': !owned && !canAfford,
  }
}

// ─── Tooltips ────────────────────────────────────

function tierTooltip(tier: HouseTierDef): string {
  if (tier.tier === currentTier.value) return `${tier.name} — your current home`
  if (tier.tier < currentTier.value) return `${tier.name} — already owned`
  if (skillPoints.value >= tier.unlockCost) return `Upgrade to ${tier.name} for ${tier.unlockCost} SP`
  return `${tier.name} — ${tier.unlockCost} SP required (you have ${skillPoints.value})`
}

function vehicleTooltip(v: VehicleDef): string {
  if (isVehicleUnlocked(v.id)) return `${v.name} — press V in garden to ride`
  if (skillPoints.value >= v.unlockCost) return `Unlock ${v.name} for ${v.unlockCost} SP`
  return `${v.name} — ${v.unlockCost} SP required`
}

// ─── Click handlers ──────────────────────────────

function onHouseClick(tier: HouseTierDef): void {
  if (tier.tier > currentTier.value && skillPoints.value >= tier.unlockCost) {
    upgradeTier(tier.tier)
  }
}

function onVehicleClick(v: VehicleDef): void {
  if (!isVehicleUnlocked(v.id) && skillPoints.value >= v.unlockCost) {
    unlockVehicle(v.id)
  }
}

// ─── API calls ───────────────────────────────────

async function upgradeTier(tier: number): Promise<void> {
  upgrading.value = tier
  try {
    await api.post('/v1/xp/upgrade-house', { target_tier: tier })
    await xpStore.fetchProfile()
  } catch (err) {
    console.error('[UpgradeShopPanel] upgrade failed:', err)
  } finally {
    upgrading.value = null
  }
}

async function unlockVehicle(vehicleId: string): Promise<void> {
  unlockingVehicle.value = vehicleId
  try {
    await api.post('/v1/xp/unlock-vehicle', { vehicle_id: vehicleId })
    await xpStore.fetchProfile()
  } catch (err) {
    console.error('[UpgradeShopPanel] unlock failed:', err)
  } finally {
    unlockingVehicle.value = null
  }
}
</script>

<style scoped>
.upgrade-shop__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.upgrade-shop__card {
  position: relative;
  border: 2px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: rgba(255, 255, 255, 0.03);
  text-align: center;
  overflow: hidden;
}

/* ─── Current / Owned ─── */
.upgrade-shop__card--current,
.upgrade-shop__card--owned {
  border-color: rgba(var(--v-theme-success), 0.4);
  background: rgba(var(--v-theme-success), 0.06);
}

/* ─── Available (can afford) — gold shimmer ─── */
.upgrade-shop__card--available {
  border-color: rgba(var(--v-theme-secondary), 0.5);
  background: rgba(var(--v-theme-secondary), 0.06);
  animation: shimmer 2.5s ease-in-out infinite;
}
.upgrade-shop__card--available:hover {
  transform: translateY(-4px);
  box-shadow: 0 6px 20px rgba(212, 168, 67, 0.25);
  border-color: rgba(var(--v-theme-secondary), 0.8);
}

/* ─── Locked (can't afford) ─── */
.upgrade-shop__card--locked {
  cursor: not-allowed;
}
.upgrade-shop__card--locked .upgrade-shop__img {
  filter: grayscale(0.6) brightness(0.6);
}
.upgrade-shop__card--locked .upgrade-shop__name {
  opacity: 0.5;
}

/* ─── Image ─── */
.upgrade-shop__img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 8px;
  transition: filter 0.2s ease;
}

/* ─── Fallback icon (shown when img errors) ─── */
.upgrade-shop__icon-fallback {
  display: none;
  width: 100%;
  aspect-ratio: 1;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
}
.upgrade-shop__img[style*="display: none"] + .upgrade-shop__icon-fallback {
  display: flex;
}

.upgrade-shop__name {
  font-size: 13px;
  font-weight: 600;
  margin-top: 6px;
  transition: opacity 0.2s;
}

/* ─── Badge (checkmark for current/owned) ─── */
.upgrade-shop__badge {
  position: absolute;
  top: 6px;
  right: 6px;
}

/* ─── Lock overlay ─── */
.upgrade-shop__lock-overlay {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: rgba(255, 255, 255, 0.7);
  border-radius: 10px;
}

/* ─── Upgrade overlay (affordable) ─── */
.upgrade-shop__upgrade-overlay {
  position: absolute;
  bottom: 32px; left: 0; right: 0;
  display: flex;
  justify-content: center;
}

.upgrade-shop__cost-badge {
  font-size: 10px !important;
  font-weight: 700;
}

/* ─── Shimmer animation ─── */
@keyframes shimmer {
  0%, 100% { border-color: rgba(var(--v-theme-secondary), 0.3); }
  50% { border-color: rgba(var(--v-theme-secondary), 0.7); }
}
</style>
