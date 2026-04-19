// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import type { SkillProfile } from '@/types'

export const useSkillsStore = defineStore('skills', () => {
  const profiles = ref<SkillProfile[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchProfiles(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/v1/skills/profiles')
      profiles.value = data
    } catch {
      error.value = 'Failed to load skill profiles.'
    } finally {
      loading.value = false
    }
  }

  return {
    profiles,
    loading,
    error,
    fetchProfiles,
  }
})
