<template>
  <div class="plans-page">
    <h1>Plans & Billing</h1>

    <div v-if="currentPlan" class="current-plan">
      <h2>Current Plan: {{ currentPlan.plan }}</h2>
      <p>{{ currentPlan.tier }} — ${{ currentPlan.price }}/mo</p>
    </div>

    <div class="usage">
      <h2>Usage</h2>
      <div v-if="usage">
        <p>Tasks: {{ usage.tasks_used }} / {{ usage.tasks_limit }}</p>
        <div class="progress-bar">
          <div :style="{ width: usagePercent + '%' }" class="fill" />
        </div>
      </div>
    </div>

    <div class="invoices">
      <h2>Invoices</h2>
      <table>
        <tr v-for="inv in invoices" :key="inv.id">
          <td>#{{ inv.id }}</td>
          <td>${{ inv.amount }}</td>
          <td>{{ inv.status }}</td>
        </tr>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '@/services/api'

const currentPlan = ref<{ plan: string; tier: string; price: number } | null>(null)
const usage = ref<{ tasks_used: number; tasks_limit: number } | null>(null)
const invoices = ref<Array<{ id: number; amount: number; status: string }>>([])

const usagePercent = computed(() => {
  if (!usage.value) return 0
  return Math.min(100, (usage.value.tasks_used / usage.value.tasks_limit) * 100)
})

onMounted(async () => {
  const [planRes, usageRes, invRes] = await Promise.all([
    api.get('/billing/plan'),
    api.get('/billing/usage'),
    api.get('/billing/invoices'),
  ])
  currentPlan.value = planRes.data
  usage.value = usageRes.data
  invoices.value = invRes.data
})
</script>
