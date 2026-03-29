<template>
  <div id="taskflow">
    <header>
      <nav>
        <router-link to="/tasks">Tasks</router-link>
        <router-link to="/billing">Billing</router-link>
        <NotificationBell />
      </nav>
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import NotificationBell from './components/notifications/NotificationBell.vue'
</script>

<style>
body { margin: 0; font-family: system-ui, sans-serif; }
header { background: #1a1a2e; padding: 12px 24px; }
nav { display: flex; gap: 16px; align-items: center; }
nav a { color: #e0e0e0; text-decoration: none; }
nav a.router-link-active { color: #fff; font-weight: 600; }
main { padding: 24px; max-width: 1200px; margin: 0 auto; }
</style>
